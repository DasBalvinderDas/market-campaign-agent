"""Read-only procurement tool. Purchase orders are created through Application Integration
(see workflow/) and are guarded by workflow/guard.py."""
from ..repositories import get_repo


def get_vendor_quotes(sku: str, quantity: int) -> dict:
    """Get vendor quotes for a SKU, cheapest first.

    Args:
        sku: Catalog SKU.
        quantity: Units to buy.
    """
    quotes = get_repo().get_quotes(sku)
    if not quotes:
        return {"status": "error", "message": f"No active vendor supplies '{sku}'."}
    out = [{**q, "total": round(float(q["unit_price"]) * quantity, 2)} for q in quotes]
    return {"status": "ok", "sku": sku, "quantity": quantity, "quotes": out}
