"""Tools for the Inventory Agent."""
from google.adk.tools import ToolContext

from ..data import INVENTORY
from .audit import audit


def check_inventory(sku: str, quantity_needed: int) -> dict:
    """Check stock for a SKU against a requested quantity.

    Args:
        sku: Inventory SKU, e.g. "TSHIRT-M".
        quantity_needed: Units the campaign needs.

    Returns:
        available units, shortfall (0 if fully covered) and a status.
    """
    item = INVENTORY.get(sku)
    if not item:
        return {"status": "error", "message": f"Unknown SKU '{sku}'. Known: {sorted(INVENTORY)}"}
    free = item["available"] - item["reserved"]
    shortfall = max(0, quantity_needed - free)
    return {"status": "ok", "sku": sku, "name": item["name"], "free_stock": free,
            "requested": quantity_needed, "shortfall": shortfall,
            "fully_covered": shortfall == 0}


def reserve_inventory(request_id: str, sku: str, quantity: int, tool_context: ToolContext) -> dict:
    """Reserve in-stock units for a campaign request (reserves at most what is free).

    Args:
        request_id: Campaign request id, e.g. "REQ-001".
        sku: Inventory SKU.
        quantity: Units wanted.

    Returns:
        units reserved and the remaining shortfall to procure.
    """
    item = INVENTORY.get(sku)
    if not item:
        return {"status": "error", "message": f"Unknown SKU '{sku}'."}
    free = item["available"] - item["reserved"]
    reserved = max(0, min(free, quantity))
    item["reserved"] += reserved
    audit(tool_context.state, "inventory_agent", "reserve_inventory",
          request_id=request_id, sku=sku, reserved=reserved)
    return {"status": "ok", "request_id": request_id, "sku": sku,
            "reserved": reserved, "shortfall_to_procure": quantity - reserved}
