"""The sign-off on a chosen scenario: autopilot below the limit, a human decision through Application Integration above it.

authorize(): validates the chosen scenario, holds the surplus depot stock it needs, and either approves it by policy
    (autopilot) or starts the Application Integration `request_approval` workflow, which emails the approver(s) an
    Approve / Reject request and waits.
status(): reads the workflow's result when the user asks. Approved: the decision is recorded (first one wins) and the
    fulfilment agent places the orders. Rejected: the held depot stock is released.
The amount, the options and the recipients all come from BigQuery; the model only names the option.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import config, emails, presentation
from .repositories.base import new_id

_EXEC_PREFIX = "execution:"
_FINAL_OK = ("PENDING", "APPROVED")
_SYNONYMS = {"FULL_NEW": ("FULL", "BRAND", "NEW"), "REBALANCE": ("REBAL", "SMART", "DEPOT", "SURPLUS", "REUSE"),
             "ECO": ("ECO", "SUSTAIN", "GREEN", "CARBON", "RECYCL")}


def _audit(repo, request_id, actor, action, **details):
    repo.log_audit(request_id, actor, action, details)


def resolve_option(scenarios: list[dict], text: str) -> dict | None:
    """The scenario a user means: 'option 2', '2', 'rebalance', 'eco', 'recommended', or the exact option code."""
    t = (text or "").strip().upper().replace("OPTION", "").replace("_", " ").replace("-", " ").strip()
    if t in ("RECOMMENDED", "RECOMMENDATION", "DEFAULT", ""):
        return next((s for s in scenarios if s["recommended"]), None)
    if t.isdigit() and 1 <= int(t) <= len(scenarios):
        return scenarios[int(t) - 1]
    for s in scenarios:
        words = {s["option_code"].replace("_", " "), s["option_name"].upper()}
        if t in words or any(t and (t in w or w in t) for w in words):
            return s
    for code, words in _SYNONYMS.items():  # "full", "smart", "sustainable", "green", ...
        if any(w in t for w in words):
            return next((s for s in scenarios if s["option_code"] == code), None)
    return None


def _check_stock(repo, lines) -> str | None:
    """Surplus stock must still be there (another request may have taken it since the plan was made)."""
    need: dict = {}
    for ln in lines:
        if ln["source_type"] == "DEPOT":
            need[(ln["source_id"], ln["sku"])] = need.get((ln["source_id"], ln["sku"]), 0) + ln["quantity"]
    if not need:
        return None
    stock = {(d["depot_id"], d["sku"]): int(d["free"]) for d in repo.list_depot_free()}
    for (depot, sku), qty in need.items():
        free = stock.get((depot, sku), 0)
        if free < qty:
            return f"depot {depot} now has only {free} of {sku} free (the plan needs {qty})"
    return None


def _approval_message(launch, scenario, lines, request_id, justification, min_buffer) -> str:
    depot_units = sum(x["quantity"] for x in lines if x["source_type"] == "DEPOT")
    vendor_units = sum(x["quantity"] for x in lines if x["source_type"] == "VENDOR")
    p = presentation
    return (f"Please approve or reject this order for the {launch['launch_name']} (request {request_id}).\n"
            f"Choice: {scenario['option_name']}\n"
            f"Total price: {p.money(scenario['total_cost'])} ({p.money(abs(scenario['savings_usd']))} "
            f"{'saved' if scenario['savings_usd'] >= 0 else 'extra'} compared with buying everything new)\n"
            f"Everything arrives: {p.day(scenario['delivery_date'])}, deadline {p.day(launch['in_hand_by'])} "
            f"({scenario['buffer_hours'] // 24} days to spare)\n"
            f"How: {depot_units:,} items from our own warehouses, {vendor_units:,} items ordered from vendors\n"
            f"Cost center: {launch.get('cost_center') or 'n/a'}\n"
            f"Why this choice: {justification or 'best balance of price and delivery time'}\n"
            f"If you approve we place the orders. If you reject nothing is bought and the held stock is released.")


def authorize(repo, executor, request_id: str, option: str, justification: str = "", now: datetime | None = None) -> dict:
    req = repo.get_request(request_id)
    if not req:
        return {"status": "error", "message": f"Unknown request '{request_id}'."}
    scenarios = repo.get_scenarios(request_id)
    if not scenarios:
        return {"status": "error", "message": "No sourcing options exist for this request yet: run the sourcing planner first."}
    scenario = resolve_option(scenarios, option)
    if not scenario:
        return {"status": "error", "message": f"'{option}' is not one of the options. Valid: "
                + ", ".join(f"Option {i} ({s['option_name']})" for i, s in enumerate(scenarios, start=1))}
    existing = repo.get_decision_for_request(request_id)
    if existing and existing["status"] in _FINAL_OK:
        same = existing["scenario_id"] == scenario["scenario_id"]
        return {"status": "pending_approval" if existing["status"] == "PENDING" else "approved", "already": True,
                "message": ("A sign-off already exists for this option." if same else
                            f"A sign-off already exists for another option ({existing['option_code']}); it cannot be changed."),
                "decision_id": existing["decision_id"], "option": existing["option_code"]}
    if not scenario["feasible"]:
        return {"status": "error", "message": f"{scenario['option_name']} cannot be authorised: {scenario['risk']}. "
                                             "Choose another option or re-plan."}
    lines = repo.get_scenario_lines(scenario["scenario_id"])
    problem = _check_stock(repo, lines)
    if problem:
        return {"status": "error", "message": f"The surplus stock changed: {problem}. Re-run the sourcing planner."}
    launch = repo.get_launch(req["launch_id"])
    total = float(scenario["total_cost"])
    policy = repo.get_policy(total)
    now = now or datetime.now(timezone.utc)
    holds = [{"request_id": request_id, "scenario_id": scenario["scenario_id"], "line_id": ln["line_id"],
              "depot_id": ln["source_id"], "sku": ln["sku"], "quantity": ln["quantity"]}
             for ln in lines if ln["source_type"] == "DEPOT"]
    decision = {"decision_id": new_id("DEC"), "request_id": request_id, "scenario_id": scenario["scenario_id"],
                "option_code": scenario["option_code"], "tier": policy["tier"], "approver_role": policy["approver_role"],
                "amount": total, "justification": justification,
                "expires_at": now + timedelta(hours=config.APPROVAL_TTL_HOURS)}
    if not policy["requires_human"]:
        repo.create_decision({**decision, "status": "APPROVED", "approver_emails": "", "decided_by": "autopilot",
                              "decided_at": now, "decision_note": "within the autopilot limit"})
        repo.create_holds(holds)
        _audit(repo, request_id, "orchestrator", "decision_autopilot", option=scenario["option_code"], amount=total,
               tier=policy["tier"])
        return {"status": "approved", "tier": policy["tier"], "option": scenario["option_name"], "amount": total,
                "approved_by": "autopilot",
                "display_markdown": presentation.sign_off_markdown(scenario, repo.list_policies(), policy, "", False, request_id),
                "next_step": "Approved by policy (autopilot). Now call the fulfilment_agent tool with the request_id to "
                             "place the orders."}
    emails_to = repo.get_approver_emails(policy["approver_role"])
    repo.create_decision({**decision, "status": "PENDING", "approver_emails": ",".join(emails_to)})
    repo.create_holds(holds)
    min_buffer = repo.get_planning_rules().get("MIN_BUFFER_HOURS", 24)
    message = _approval_message(launch, scenario, lines, request_id, justification, min_buffer)
    try:
        body = executor.start(config.APPROVAL_TRIGGER, {
            "request_id": request_id, "launch_id": req["launch_id"], "approver_role": policy["approver_role"],
            "amount": total, "approval_message": message})
        execution_id = body.get("executionId")
        if not execution_id:
            raise RuntimeError("the workflow returned no executionId")
    except Exception as exc:  # noqa: BLE001
        repo.set_decision_note(decision["decision_id"], "FAILED", f"approval request not sent: {str(exc)[:200]}")
        repo.release_holds(request_id)
        _audit(repo, request_id, "orchestrator", "approval_workflow_failed", error=str(exc)[:300])
        return {"status": "error", "message": "The approval request could not be sent. Nothing was ordered and the held stock is released. "
                                              f"Please try again. ({str(exc)[:200]})"}
    repo.set_decision_note(decision["decision_id"], "PENDING", _EXEC_PREFIX + str(execution_id))
    # Our own approval email (HTML, with Approve and Reject buttons, the shopping list and the vendors). The Application
    # Integration approval task does not send its own email, so this is the one the approver gets.
    rng = presentation._band(repo.list_policies(), total)[0]
    subject, html = emails.approval_email(repo, launch, scenario, lines, request_id, justification, policy["approver_role"],
                                          emails.approval_url(execution_id), rng)
    sent, failed_to = [], []

    def _send(address):
        executor.execute(config.UPDATE_TRIGGER, {"request_id": request_id, "launch_id": req["launch_id"],
                                                 "recipient_email": address, "email_subject": subject, "email_body": html})

    # The approvers' emails go out at the same time, so the chat answers sooner.
    with ThreadPoolExecutor(max_workers=max(1, min(len(emails_to), 5))) as pool:
        futures = [(a, pool.submit(_send, a)) for a in emails_to]
    for address, fut in futures:
        try:
            fut.result()
            sent.append(address)
        except Exception as exc:  # noqa: BLE001
            failed_to.append({"email": address, "error": str(exc)[:200]})
    if not sent:
        repo.set_decision_note(decision["decision_id"], "FAILED", "the approval email could not be sent")
        repo.release_holds(request_id)
        _audit(repo, request_id, "orchestrator", "approval_email_failed", failed=failed_to or "no approver address on file")
        return {"status": "error", "message": "The approval email could not be sent (" + (
            failed_to[0]["error"] if failed_to else f"no email address is set for {policy['approver_role']}; run "
            "setup_bigquery.py --approver-email") + "). Nothing was ordered and the stock is released."}
    _audit(repo, request_id, "orchestrator", "approval_requested", decision_id=decision["decision_id"],
           option=scenario["option_code"], approver_role=policy["approver_role"], amount=total, tier=policy["tier"],
           execution_id=execution_id)
    who = f"the {policy['approver_role']}"          # the role, never a name or an address
    return {"status": "pending_approval", "decision_id": decision["decision_id"], "tier": policy["tier"],
            "option": scenario["option_name"], "amount": total, "approver_role": policy["approver_role"],
            "approvers_notified": len(sent),
            "announce": (f"HUMAN APPROVAL REQUIRED: an approval email with Approve / Reject buttons has been sent to "
                         f"{who} for {scenario['option_name']}, USD {total:,.2f}. "
                         f"No orders are placed until it is approved."),
            "display_markdown": presentation.sign_off_markdown(scenario, repo.list_policies(), policy, who, True, request_id),
            "next_step": "Start your reply with the text in `announce`, in bold, exactly, then show `display_markdown` exactly. "
                         "Never write an email address or a person's name. Do NOT call the fulfilment_agent tool."}


# ---------------------------------------------------------------------------- reading the workflow's answer
def _param(params, name):
    if isinstance(params, list):
        params = {p.get("key"): p.get("value") for p in params if isinstance(p, dict)}
    v = (params or {}).get(name)
    if isinstance(v, dict):
        v = v.get("stringValue", next(iter(v.values()), None))
    return v


def _find_decision(obj):
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
    """The approval record itself: REJECTED = rejected, LIFTED = approved, PENDING = still waiting."""
    try:
        states = {str(s.get("state", "")).upper() for s in executor.list_suspensions(execution_id)}
    except Exception:  # noqa: BLE001 - optional fallback
        return ""
    if "REJECTED" in states:
        return "REJECTED"
    if states == {"LIFTED"}:
        return "APPROVED"
    return ""


def sync(repo, executor, decision: dict) -> dict:
    """If the approver has decided in Application Integration, record it. Returns the current decision row."""
    note = decision.get("decision_note") or ""
    if decision["status"] != "PENDING" or not note.startswith(_EXEC_PREFIX):
        return decision
    exec_id = note[len(_EXEC_PREFIX):]
    try:
        ex = executor.get_execution(exec_id)
    except Exception as exc:  # noqa: BLE001 - stays PENDING; the next status check retries
        decision["decision_note"] = f"could not read the approval yet: {str(exc)[:150]}"
        return decision
    state = str((ex.get("executionDetails") or {}).get("state")
                or (ex.get("eventExecutionDetails") or {}).get("eventExecutionState") or ex.get("state") or "").upper()
    answer = (str(_param(ex.get("responseParameters") or ex.get("responseParams"), "decision") or "").upper()
              or _find_decision(ex) or _suspension_decision(executor, exec_id))
    request_id = decision["request_id"]
    if state in ("FAILED", "CANCELLED", "CANCELED"):
        repo.set_decision_note(decision["decision_id"], "FAILED", f"approval {state.lower()}")
        repo.release_holds(request_id)
        _audit(repo, request_id, "orchestrator", "approval_workflow_failed", state=state)
    elif answer in ("APPROVED", "REJECTED"):
        by = "Approver"
        if repo.decide(decision["decision_id"], answer, by, "decided by the approver"):
            if answer == "REJECTED":
                released = repo.release_holds(request_id)
                _audit(repo, request_id, f"human:{decision['approver_role']}", "launch_rejected",
                       decision_id=decision["decision_id"], depot_units_released=released)
            else:
                _audit(repo, request_id, f"human:{decision['approver_role']}", "launch_approved",
                       decision_id=decision["decision_id"], amount=float(decision["amount"]),
                       option=decision["option_code"], tier=decision["tier"])
    return repo.get_decision(decision["decision_id"]) or decision


def status(repo, request_id: str, executor=None) -> dict:
    d = repo.get_decision_for_request(request_id)
    if not d:
        return {"status": "none", "message": "No sign-off was requested for this request yet."}
    if d["status"] == "PENDING":
        d = sync(repo, executor or _default_executor(), d)
        if d["status"] == "PENDING" and d["expires_at"] <= datetime.now(timezone.utc):
            repo.set_decision_note(d["decision_id"], "FAILED", "the sign-off expired")
            repo.release_holds(request_id)
            d = repo.get_decision(d["decision_id"]) or d
    lines = repo.get_scenario_lines(d["scenario_id"])
    done = sum(1 for x in lines if x["execution_status"] == "EXECUTED")
    note = None if str(d.get("decision_note") or "").startswith(_EXEC_PREFIX) else d.get("decision_note")
    out = {"status": d["status"], "option": d["option_code"], "approver_role": d["approver_role"],
           "amount": float(d["amount"]), "decided_by": d.get("decided_by"), "note": note,
           "lines_executed": done, "lines_total": len(lines),
           "purchase_orders": [p["po_number"] for p in repo.list_pos(request_id)],
           "depot_transfers": [t["transfer_number"] for t in repo.list_transfers(request_id)]}
    scenario = repo.get_scenario(d["scenario_id"]) or {}
    placed = bool(lines) and done == len(lines)
    shown_note = None if note in (None, "", "decided by the approver", "within the autopilot limit") else note
    out["display_markdown"] = presentation.status_markdown(
        request_id, d, scenario.get("option_name", ""), len(repo.list_pos(request_id)), len(repo.list_transfers(request_id)),
        placed, shown_note)
    if d["status"] == "APPROVED" and done < len(lines):
        out["next_step"] = "Approved. Now call the fulfilment_agent tool with the request_id to place the orders."
    elif d["status"] == "REJECTED":
        out["next_step"] = ("The approver rejected it. The held depot stock was released and nothing was ordered. "
                            "Offer to re-plan (another option, or after a change).")
    return out


def _default_executor():
    from .workflow.integration_client import IntegrationExecutor
    return IntegrationExecutor()
