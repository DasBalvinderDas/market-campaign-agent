"""Human approval by email link: request it, and carry on when the approver clicks.

request_human_approval(): builds the purchase plan from BigQuery, stores a PENDING approval and emails each approver
    an Approve and a Reject link (through the Application Integration email workflow).
finalize(): runs when an approver clicks (called by the approval-link service): Approve commits the budget and
    creates the purchase orders through the workflow; Reject releases the reserved stock.
The model never supplies the amount or the recipients: both come from BigQuery.
"""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from . import config
from .approval_links import make_token
from .repositories.base import new_id


def _audit(repo, request_id, actor, action, **details):
    repo.log_audit(request_id, actor, action, details)


def build_plan(repo, request_id: str) -> dict:
    """What has to be bought: every line's shortfall from the cheapest active vendor."""
    lines, unfulfillable = [], []
    for ln in repo.get_lines(request_id):
        short = int(ln["shortfall"])
        if short <= 0:
            continue
        quotes = repo.get_quotes(ln["sku"])
        if not quotes:
            unfulfillable.append(ln["sku"])
            continue
        q = quotes[0]
        lines.append({"sku": ln["sku"], "quantity": short, "vendor_id": q["vendor_id"], "vendor": q["vendor"],
                      "unit_price": float(q["unit_price"]), "lead_time_days": q["lead_time_days"],
                      "total": round(float(q["unit_price"]) * short, 2)})
    return {"lines": lines, "unfulfillable": unfulfillable, "total": round(sum(x["total"] for x in lines), 2)}


def email_text(approval: dict, plan: dict, approve_url: str, reject_url: str) -> tuple[str, str]:
    subject = f"Approval needed: {approval['request_id']} - {approval['campaign_id']} (USD {approval['amount']:,.2f})"
    items = "\n".join(f"  - {ln['quantity']} x {ln['sku']} from {ln['vendor']}: USD {ln['total']:,.2f} "
                      f"({ln['lead_time_days']} days)" for ln in plan["lines"])
    expires = approval["expires_at"].strftime("%Y-%m-%d %H:%M UTC")
    body = (f"{approval.get('justification') or 'A campaign purchase needs your approval.'}\n\n"
            f"Request {approval['request_id']} for {approval['campaign_id']}\nItems to buy:\n{items}\n"
            f"Total: USD {approval['amount']:,.2f}   (you are asked as: {approval['approver_role']})\n\n"
            f"APPROVE: {approve_url}\n\nREJECT:  {reject_url}\n\n"
            f"The links work without signing in to anything. They can be used once and expire on {expires}.")
    return subject, body


def request_human_approval(repo, executor, request_id: str, campaign_id: str, justification: str, policy: dict,
                           now: datetime | None = None) -> dict:
    if not config.APPROVAL_LINK_SECRET or not config.APPROVAL_BASE_URL:
        return {"status": "error", "message": "Email approval is not configured (APPROVAL_BASE_URL / "
                                              "APPROVAL_LINK_SECRET). Run scripts/deploy_approval_service.py."}
    plan = build_plan(repo, request_id)
    if not plan["lines"]:
        return {"status": "error", "message": "No purchase plan exists for this request: either everything is covered by stock, or the stock step did "
                                              "not record it. Have inventory_agent call reserve_inventory for every item (even when 0 units "
                                              "are free), then call approve_budget again."}
    role = policy["approver_role"]
    emails = repo.get_approver_emails(role)
    if not emails:
        _audit(repo, request_id, "orchestrator", "approval_not_requested_no_approvers", approver_role=role)
        return {"status": "NO_APPROVERS", "message": f"No approver email is configured for '{role}'. Set one with "
                                                     "scripts/setup_bigquery.py --approver-email."}
    now = now or datetime.now(timezone.utc)
    expires = now + timedelta(hours=config.APPROVAL_LINK_TTL_HOURS)
    approval = {"approval_id": new_id("APR"), "request_id": request_id, "campaign_id": campaign_id,
                "tier": policy["tier"], "approver_role": role, "approver_emails": ",".join(emails),
                "amount": plan["total"], "plan": json.dumps(plan), "justification": justification,
                "expires_at": expires}
    repo.create_approval(approval)
    sent, failed = [], []
    for email in emails:
        urls = {a: f"{config.APPROVAL_BASE_URL}/decide?t=" + quote(
            make_token(config.APPROVAL_LINK_SECRET, approval["approval_id"], email, a, expires.timestamp()))
            for a in ("approve", "reject")}
        subject, body = email_text(approval, plan, urls["approve"], urls["reject"])
        try:
            executor.execute(config.NOTIFY_TRIGGER, {
                "request_id": request_id, "campaign_id": campaign_id, "approver_role": role, "approver_email": email,
                "email_subject": subject, "email_body": body, "summary": justification or "",
                "amount": float(plan["total"])})
            sent.append(email)
        except Exception as exc:  # noqa: BLE001 - one bad address must not stop the others
            failed.append({"email": email, "error": str(exc)[:200]})
    _audit(repo, request_id, "orchestrator", "approval_requested", approval_id=approval["approval_id"],
           approver_role=role, amount=plan["total"], sent_to=sent, failed=failed)
    if not sent:
        repo.set_approval_note(approval["approval_id"], "FAILED", "approval email could not be sent")
        return {"status": "error", "message": "The approval email could not be sent: "
                + (failed[0]["error"] if failed else "no recipient")}
    return {"status": "pending_approval", "approval_id": approval["approval_id"], "amount": plan["total"],
            "approver_role": role, "emailed": sent, "email_failed": failed,
            "expires_at": expires.isoformat(timespec="minutes"),
            "next_step": "The approval request was emailed. Do NOT create purchase orders. Tell the user who was emailed "
                         "and that the purchase orders are created automatically when the approver clicks Approve "
                         "(or the stock is released if they click Reject). The user can ask for the status later."}


def finalize(repo, executor, approval: dict, decision: str, decided_by: str) -> dict:
    """Carry out the decision. ``decision`` is "approve" or "reject". The approval row is already marked."""
    request_id, campaign_id = approval["request_id"], approval["campaign_id"]
    who = f"human:{approval['approver_role']} ({decided_by})"
    if decision == "reject":
        released = repo.release_reservations(request_id)
        _audit(repo, request_id, who, "budget_rejected_by_approver", approval_id=approval["approval_id"],
               stock_units_released=released)
        return {"status": "rejected", "released": released}

    amount = float(approval["amount"])
    budget = repo.get_budget(campaign_id)
    if not budget or float(budget["remaining"]) < amount:
        repo.set_approval_note(approval["approval_id"], "FAILED", "the budget no longer covers this amount")
        _audit(repo, request_id, who, "approval_failed_insufficient_budget", amount=amount,
               remaining=float(budget["remaining"]) if budget else None)
        return {"status": "failed", "message": "The budget no longer covers this amount, so nothing was committed."}
    repo.commit_budget(campaign_id, request_id, amount, who)
    _audit(repo, request_id, who, "budget_approved", approval_id=approval["approval_id"], amount=amount,
           approved_by=who, tier=approval["tier"])
    plan = json.loads(approval.get("plan") or "{}")
    pos, failed = [], []
    for line in plan.get("lines", []):
        price = repo.get_vendor_price(line["vendor_id"], line["sku"])
        total = round(float(price["unit_price"]) * int(line["quantity"]), 2) if price else None
        head = repo.get_headroom(request_id)
        if total is None or head["approved"] - head["ordered"] + 1e-6 < total:
            failed.append({"sku": line["sku"], "error": "not covered by the approved budget"})
            _audit(repo, request_id, "approval_service", "po_blocked", sku=line["sku"], total=total)
            continue
        try:
            out = executor.execute(config.PO_TRIGGER, {
                "request_id": request_id, "campaign_id": campaign_id, "sku": line["sku"],
                "quantity": int(line["quantity"]), "vendor_id": line["vendor_id"], "total_amount": total})
            po_number = out.get("po_number")
            if not po_number:
                raise RuntimeError("the workflow returned no po_number")
            repo.record_po({"po_number": str(po_number), "request_id": request_id, "campaign_id": campaign_id,
                            "vendor_id": line["vendor_id"], "sku": line["sku"], "quantity": int(line["quantity"]),
                            "total_amount": total, "status": "CREATED",
                            "integration_execution_id": out.get("execution_id")})
            _audit(repo, request_id, "approval_service", "po_created", po_number=str(po_number), sku=line["sku"],
                   total=total, vendor_id=line["vendor_id"])
            pos.append({"po_number": str(po_number), "sku": line["sku"], "total": total})
        except Exception as exc:  # noqa: BLE001
            failed.append({"sku": line["sku"], "error": str(exc)[:200]})
            _audit(repo, request_id, "approval_service", "po_failed", sku=line["sku"], error=str(exc)[:300])
    return {"status": "approved", "pos": pos, "failed": failed, "amount": amount}


# ---------------------------------------------------------------- native Application Integration approval
_EXEC_PREFIX = "execution:"


def _param(params, name):
    """A parameter from an execution's response, whether it is plain or a typed {"stringValue": ...} value."""
    if isinstance(params, list):  # [{"key": ..., "value": ...}]
        params = {p.get("key"): p.get("value") for p in params if isinstance(p, dict)}
    v = (params or {}).get(name)
    if isinstance(v, dict):
        v = v.get("stringValue", next(iter(v.values()), None))
    return v


def _find_decision(obj):
    """Look for a decision value anywhere in an execution record (the field's location varies by API version)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "decision":
                found = v.get("stringValue") if isinstance(v, dict) else v
                if str(found).upper() in ("APPROVED", "REJECTED"):
                    return str(found).upper()
            hit = _find_decision(v)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find_decision(v)
            if hit:
                return hit
    return ""


def _suspension_decision(executor, execution_id):
    """Fallback: the approval record itself. REJECTED = rejected; LIFTED = approved; PENDING = still waiting."""
    try:
        states = {str(s.get("state", "")).upper() for s in executor.list_suspensions(execution_id)}
    except Exception:  # noqa: BLE001 - optional fallback
        return ""
    if "REJECTED" in states:
        return "REJECTED"
    if states == {"LIFTED"}:
        return "APPROVED"
    return ""


def request_integration_approval(repo, executor, request_id: str, campaign_id: str, justification: str,
                                 policy: dict, now: datetime | None = None) -> dict:
    """Start the Application Integration approval workflow. It emails the approver(s) an Approve / Reject request and
    waits. The decision is picked up by approval_status() and then carried out by finalize()."""
    plan = build_plan(repo, request_id)
    if not plan["lines"]:
        return {"status": "error", "message": "No purchase plan exists for this request: either everything is covered by stock, or the stock step did "
                                              "not record it. Have inventory_agent call reserve_inventory for every item (even when 0 units "
                                              "are free), then call approve_budget again."}
    role = policy["approver_role"]
    emails = repo.get_approver_emails(role)
    now = now or datetime.now(timezone.utc)
    approval = {"approval_id": new_id("APR"), "request_id": request_id, "campaign_id": campaign_id,
                "tier": policy["tier"], "approver_role": role, "approver_emails": ",".join(emails) or "(integration)",
                "amount": plan["total"], "plan": json.dumps(plan), "justification": justification,
                "expires_at": now + timedelta(hours=config.APPROVAL_LINK_TTL_HOURS)}
    items = "; ".join(f"{ln['quantity']} x {ln['sku']} from {ln['vendor']} (USD {ln['total']:,.2f})"
                      for ln in plan["lines"])
    message = (f"{justification or 'A campaign purchase needs your approval.'} Request {request_id} for {campaign_id}: "
               f"{items}. Total USD {plan['total']:,.2f} (approver role: {role}). Approve to create the purchase "
               f"orders, Reject to release the reserved stock.")
    repo.create_approval(approval)
    try:
        body = executor.start(config.APPROVAL_TRIGGER, {
            "request_id": request_id, "campaign_id": campaign_id, "approver_role": role,
            "amount": float(plan["total"]), "approval_message": message})
        execution_id = body.get("executionId")
        if not execution_id:
            raise RuntimeError("the workflow returned no executionId")
    except Exception as exc:  # noqa: BLE001
        repo.set_approval_note(approval["approval_id"], "FAILED", f"approval workflow did not start: {str(exc)[:200]}")
        _audit(repo, request_id, "orchestrator", "approval_workflow_failed", error=str(exc)[:300])
        return {"status": "error", "message": f"The approval workflow could not be started: {str(exc)[:300]}"}
    repo.set_approval_note(approval["approval_id"], "PENDING", _EXEC_PREFIX + str(execution_id))
    _audit(repo, request_id, "orchestrator", "approval_requested", approval_id=approval["approval_id"],
           approver_role=role, amount=plan["total"], channel="application_integration", execution_id=execution_id)
    return {"status": "pending_approval", "approval_id": approval["approval_id"], "amount": plan["total"],
            "approver_role": role, "approver_emails": emails, "channel": "application_integration",
            "announce": (f"HUMAN APPROVAL REQUIRED: an approval email with Approve / Reject buttons has been sent to "
                         f"{', '.join(emails) or 'the ' + role} ({role}) for USD {plan['total']:,.2f}. Procurement "
                         f"(purchase orders) will be done ONLY once it is approved."),
            "next_step": "Start your reply with the text in `announce`, in bold, exactly. Do NOT create purchase "
                         "orders. Tell the user that after the approver clicks Approve they should ask for the "
                         "approval status (get_approval_status): the purchase orders are then created, or the stock "
                         "is released if it was rejected."}


def sync_integration_decision(repo, executor, approval: dict) -> dict:
    """If the approver has decided in Application Integration, record it and carry it out. Returns the new row."""
    note = approval.get("decision_note") or ""
    if approval["status"] != "PENDING" or not note.startswith(_EXEC_PREFIX):
        return approval
    try:
        ex = executor.get_execution(note[len(_EXEC_PREFIX):])
    except Exception as exc:  # noqa: BLE001 - keep PENDING; the next status check retries
        approval["decision_note"] = f"could not read the approval workflow yet: {str(exc)[:150]}"
        return approval
    state = str((ex.get("executionDetails") or {}).get("state") or ex.get("state") or "").upper()
    exec_id = note[len(_EXEC_PREFIX):]
    decision = (str(_param(ex.get("responseParameters") or ex.get("responseParams"), "decision") or "").upper()
                or _find_decision(ex) or _suspension_decision(executor, exec_id))
    if state in ("FAILED", "CANCELLED", "CANCELED"):
        repo.set_approval_note(approval["approval_id"], "FAILED", f"approval workflow {state.lower()}")
        _audit(repo, approval["request_id"], "orchestrator", "approval_workflow_failed", state=state)
    elif decision in ("APPROVED", "REJECTED"):
        by = "Application Integration approval"
        if repo.decide_approval(approval["approval_id"], decision, by, "decided in Application Integration"):
            finalize(repo, executor, approval, "approve" if decision == "APPROVED" else "reject", by)
    return repo.get_approval(approval["approval_id"]) or approval


def approval_status(repo, request_id: str, executor=None) -> dict:
    a = repo.get_approval_for_request(request_id)
    if not a:
        return {"status": "none", "message": "No human approval was requested for this request."}
    if config.APPROVAL_CHANNEL == "integration" and a["status"] == "PENDING":
        a = sync_integration_decision(repo, executor or _default_executor(), a)
    out = {"status": a["status"], "approver_role": a["approver_role"], "amount": float(a["amount"]),
           "decided_by": a.get("decided_by"),
           "note": None if str(a.get("decision_note") or "").startswith(_EXEC_PREFIX) else a.get("decision_note"),
           "purchase_orders": repo.list_purchase_orders(request_id)}
    if a["status"] == "PENDING" and a["expires_at"] <= datetime.now(timezone.utc):
        out["status"] = "EXPIRED"
    return out


def _default_executor():
    from .workflow.integration_client import IntegrationExecutor
    return IntegrationExecutor()
