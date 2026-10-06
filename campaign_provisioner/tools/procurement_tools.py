"""Read-only procurement tool. Purchase orders are created through Application Integration
(see workflow/) and are guarded by workflow/guard.py."""
from ..repositories import get_repo


def get_vendor_quotes(sku: str, quantity: int) -> dict:
    """Get vendor quotes for a SKU, cheapest first.

    Args:
        sku: Catalog SKU.
        quantity: Units to buy.
    """
    repo = get_repo()
    quotes = repo.get_quotes(sku)
    if not quotes:
        # A description such as "hoodies" instead of the SKU: resolve it through the catalog.
        matches = repo.find_items(sku)
        if len(matches) == 1:
            sku = matches[0]["sku"]
            quotes = repo.get_quotes(sku)
        elif matches:
            return {"status": "error", "message": f"'{sku}' matches several catalog items. Call again with one SKU.",
                    "valid_skus": [{"sku": m["sku"], "name": m["name"]} for m in matches]}
    if not quotes:
        return {"status": "error", "message": f"No active vendor supplies '{sku}'. Use the catalog SKU (for example "
                                              "HOODIE-NEXT), not a description."}
    out = [{**q, "total": round(float(q["unit_price"]) * quantity, 2)} for q in quotes]
    return {"status": "ok", "sku": sku, "quantity": quantity, "quotes": out}
