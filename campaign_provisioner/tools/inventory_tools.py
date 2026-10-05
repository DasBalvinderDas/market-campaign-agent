"""Tools for the Inventory Agent (data from the repository / BigQuery)."""
from ..repositories import get_repo
from .audit import audit


def find_sku(description: str) -> dict:
    """Map a free-text item description to catalog SKUs. Call this BEFORE check_inventory
    whenever the user did not give an exact SKU. Never invent a SKU.

    Args:
        description: What the user asked for, e.g. "hoodies" or "LED video wall".
    """
    matches = get_repo().find_items(description)
    if matches:
        return {"status": "ok", "matches": [{"sku": m["sku"], "name": m["name"]} for m in matches]}
    return {"status": "no_match",
            "catalog": [{"sku": c["sku"], "name": c["name"]} for c in get_repo().list_catalog()],
            "message": "No match. Show the catalog to the user and ask which item they mean."}


def _unknown_sku(sku: str) -> dict:
    found = find_sku(sku)
    return {"status": "error",
            "message": f"'{sku}' is not a catalog SKU. Do NOT treat it as out of stock. "
                       "Retry with one of the SKUs in 'valid_skus', or ask the user.",
            "valid_skus": found.get("matches") or found.get("catalog")}


def check_inventory(sku: str, quantity_needed: int) -> dict:
    """Check free stock for a SKU against a requested quantity.

    Args:
        sku: Catalog SKU, e.g. "HOODIE-NEXT".
        quantity_needed: Units the campaign needs.
    """
    item = get_repo().get_availability(sku)
    if not item:
        return _unknown_sku(sku)
    free = int(item["free"])
    shortfall = max(0, quantity_needed - free)
    return {"status": "ok", "sku": sku, "name": item["name"], "free_stock": free,
            "requested": quantity_needed, "shortfall": shortfall, "fully_covered": shortfall == 0}


def reserve_inventory(request_id: str, sku: str, quantity: int) -> dict:
    """Reserve in-stock units for a request (reserves at most what is free).

    Args:
        request_id: Campaign request id returned by register_campaign_request.
        sku: Catalog SKU.
        quantity: Units wanted.
    """
    item = get_repo().get_availability(sku)
    if not item:
        return _unknown_sku(sku)
    reserved = max(0, min(int(item["free"]), quantity))
    if reserved:
        get_repo().reserve(request_id, sku, reserved)
    get_repo().record_line(request_id, sku, quantity, reserved)
    audit(request_id, "inventory_agent", "stock_reserved", sku=sku, reserved=reserved, requested=quantity)
    return {"status": "ok", "request_id": request_id, "sku": sku, "reserved": reserved,
            "shortfall_to_procure": quantity - reserved}


def release_inventory(request_id: str) -> dict:
    """Release all stock reserved for a request (use when its budget was declined or rejected).

    Args:
        request_id: Campaign request id.
    """
    released = get_repo().release_reservations(request_id)
    audit(request_id, "inventory_agent", "stock_released", units=released)
    return {"status": "ok", "request_id": request_id, "units_released": released}
