"""Code-level guardrails around the Application Integration tools.

before_tool: a purchase order is blocked unless the request has an approved budget (a COMMIT in
             the BigQuery budget ledger) that still covers it. The amount is recomputed from the
             vendor price list - the model's value is ignored.
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


def before_tool(tool, args, tool_context):
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
        audit(args.get("request_id"), "budget_agent", "approver_notified",
              approver_role=args.get("approver_role"), amount=args.get("amount"))
    return None
