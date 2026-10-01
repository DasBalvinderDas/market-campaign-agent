"""Tools for the Procurement Agent."""
from google.adk.tools import ToolContext

from ..data import VENDORS
from .audit import audit


def get_vendor_quotes(sku: str, quantity: int) -> dict:
    """Get vendor quotes for a SKU, cheapest first.

    Args:
        sku: Inventory SKU.
        quantity: Units to buy.
    """
    quotes = [{"vendor_id": vid, "vendor": v["name"], "unit_price": v["prices"][sku],
               "total": round(v["prices"][sku] * quantity, 2),
               "lead_time_days": v["lead_time_days"]}
              for vid, v in VENDORS.items() if sku in v["prices"]]
    if not quotes:
        return {"status": "error", "message": f"No vendor supplies '{sku}'."}
    return {"status": "ok", "sku": sku, "quantity": quantity,
            "quotes": sorted(quotes, key=lambda q: q["total"])}


def place_purchase_order(request_id: str, sku: str, quantity: int,
                         vendor_id: str, tool_context: ToolContext) -> dict:
    """Place a purchase order. Hard-blocked unless budget approval covers it.

    Args:
        request_id: Campaign request id (must already have an approved budget).
        sku: Inventory SKU.
        quantity: Units to buy.
        vendor_id: Vendor chosen from the quotes.
    """
    vendor = VENDORS.get(vendor_id)
    if not vendor or sku not in vendor["prices"]:
        return {"status": "error", "message": "Vendor does not supply this SKU."}
    total = round(vendor["prices"][sku] * quantity, 2)
    approvals = tool_context.state.get("approvals", {})
    approval = approvals.get(request_id)
    spent = tool_context.state.get("po_spend", {}).get(request_id, 0.0)
    if not approval or spent + total > approval["approved_amount"] + 1e-9:
        audit(tool_context.state, "procurement_agent", "po_blocked_no_approval",
              request_id=request_id, total=total)
        return {"status": "blocked",
                "reason": "No sufficient budget approval for this request. Route to budget_agent first."}
    po_spend = dict(tool_context.state.get("po_spend", {}))
    po_spend[request_id] = spent + total
    tool_context.state["po_spend"] = po_spend
    po_id = f"PO-{request_id}-{sku}"
    audit(tool_context.state, "procurement_agent", "po_placed",
          request_id=request_id, po_id=po_id, total=total, vendor=vendor["name"])
    return {"status": "placed", "po_id": po_id, "vendor": vendor["name"], "sku": sku,
            "quantity": quantity, "total": total, "lead_time_days": vendor["lead_time_days"]}
