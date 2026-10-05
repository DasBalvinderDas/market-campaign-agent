"""Code-level guardrails around the Application Integration tools.

before_tool: a purchase order is blocked unless the request has an approved budget (a COMMIT in
             the BigQuery budget ledger) that still covers it. The amount is recomputed from the
             vendor price list - the model's value is ignored.
before_tool also fills the email recipient, subject and body for notify_approver (recipients from the BigQuery
`approvers` table; one call per address).
after_tool:  records the PO and the notification in BigQuery and the audit log.
"""
from ..repositories import get_repo
from ..tools.audit import audit


def _is_po(tool) -> bool:
    return "purchase_order" in tool.name


def _is_notify(tool) -> bool:
    return "notify" in tool.name


def _find(obj, keys):
    """Find the first value for any of ``keys`` in a nested response."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and v not in (None, ""):
                return v
        for v in obj.values():
            found = _find(v, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, keys)
            if found is not None:
                return found
    return None


def _blocked(request_id, reason, **details):
    audit(request_id, "procurement_agent", "po_blocked", reason=reason, **details)
    return {"status": "BLOCKED", "reason": reason,
            "next_step": "Route to budget_agent for approval first. Do not retry or work around."}


def _email_text(args):
    role = args.get("approver_role", "")
    subject = f"Approval needed: {args.get('request_id', '')} - {args.get('campaign_id', '')} ({role})"
    body = (f"{args.get('summary', '')}\n\nRequest {args.get('request_id', '')} needs approval from {role}. "
            "Open the Campaign Provisioner chat and choose Confirm or Reject.")
    return subject, body


async def _before_notify(tool, args, tool_context):
    """Recipients, subject and body are set here from BigQuery and the request, never by the model.
    The workflow emails one address per call, so every extra recipient gets its own call."""
    role = args.get("approver_role", "")
    emails = get_repo().get_approver_emails(role)
    if not emails:
        audit(args.get("request_id"), "budget_agent", "approver_email_skipped_no_recipients", approver_role=role)
        return {"status": "NO_APPROVERS",
                "reason": f"No approver email is configured for '{role}', so no email was sent.",
                "next_step": "Continue to approve_budget (the approver can still confirm in the chat) and tell "
                             "the user that no email was sent. Setup: scripts/setup_bigquery.py --approver-email"}
    args["email_subject"], args["email_body"] = _email_text(args)
    args.pop("approver_emails", None)
    for extra in emails[1:]:
        try:
            await tool.run_async(args={**args, "approver_email": extra}, tool_context=tool_context)
            audit(args.get("request_id"), "budget_agent", "approver_notified", approver_role=role,
                  recipients=extra, amount=args.get("amount"))
        except Exception as exc:  # noqa: BLE001 - one bad address must not stop the approval flow
            audit(args.get("request_id"), "budget_agent", "approver_notification_failed", approver_role=role,
                  recipients=extra, error=str(exc)[:300])
    args["approver_email"] = emails[0]
    return None


async def before_tool(tool, args, tool_context):
    if _is_notify(tool):
        return await _before_notify(tool, args, tool_context)
    if not _is_po(tool):
        return None
    repo = get_repo()
    request_id, sku = args.get("request_id", ""), args.get("sku", "")
    quantity = int(args.get("quantity") or 0)
    request = repo.get_request(request_id)
    if not request:
        return _blocked(request_id, "Unknown request id")
    price = repo.get_vendor_price(args.get("vendor_id", ""), sku)
    if not price or quantity <= 0:
        return _blocked(request_id, "Vendor does not supply this SKU or quantity is invalid")
    total = round(float(price["unit_price"]) * quantity, 2)
    head = repo.get_headroom(request_id)
    if head["approved"] - head["ordered"] + 1e-6 < total:
        return _blocked(request_id, "No approved budget covers this purchase order",
                        total=total, approved=head["approved"], already_ordered=head["ordered"])
    args["campaign_id"] = request["campaign_id"]
    args["total_amount"] = total
    return None


def after_tool(tool, args, tool_context, tool_response):
    if _is_po(tool):
        if not isinstance(tool_response, dict) or tool_response.get("status") == "BLOCKED":
            return None
        po_number = _find(tool_response, ("po_number", "poNumber", "PoNumber"))
        if not po_number or _find(tool_response, ("error", "errorMessage")):
            audit(args.get("request_id"), "procurement_agent", "po_failed", response=str(tool_response)[:500])
            return None
        get_repo().record_po({
            "po_number": str(po_number), "request_id": args["request_id"], "campaign_id": args["campaign_id"],
            "vendor_id": args["vendor_id"], "sku": args["sku"], "quantity": int(args["quantity"]),
            "total_amount": float(args["total_amount"]), "status": "CREATED",
            "integration_execution_id": _find(tool_response, ("execution_id", "executionId"))})
        audit(args["request_id"], "procurement_agent", "po_created", po_number=str(po_number),
              total=args["total_amount"], vendor_id=args["vendor_id"], sku=args["sku"])
        return {**tool_response, "po_number": str(po_number), "total_amount": args["total_amount"],
                "recorded": True}
    if _is_notify(tool):
        resp = tool_response if isinstance(tool_response, dict) else {}
        if resp.get("status") == "NO_APPROVERS":
            return None
        failed = bool(resp.get("executionFailed") or _find(resp, ("error", "errorMessage")))
        audit(args.get("request_id"), "budget_agent", "approver_notification_failed" if failed else "approver_notified",
              approver_role=args.get("approver_role"), recipients=args.get("approver_email"),
              amount=args.get("amount"), response=str(resp)[:400] if failed else None)
    return None


def on_tool_error(tool, args, tool_context, error):
    """A tool that raises (BigQuery table missing, permission denied, ...) must not end the run silently: hand the
    error text to the model so it tells the user what to fix."""
    import logging
    logging.getLogger(__name__).exception("tool %s failed", getattr(tool, "name", tool))
    return {"status": "error", "tool": getattr(tool, "name", str(tool)),
            "message": f"{type(error).__name__}: {str(error)[:500]}",
            "next_step": "Tell the user this tool failed, quote the message, and stop. Do not retry or invent data."}
