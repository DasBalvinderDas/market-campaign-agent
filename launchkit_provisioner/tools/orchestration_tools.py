"""Read-only tools of the root agent."""
from ..repositories import get_repo


def get_launch_overview(launch_id: str = "") -> dict:
    """Launch readiness board and surplus depot stock: each request with its chosen option, sign-off status, delivery
    buffer and readiness (GREEN, AMBER, RED), plus the free surplus stock per depot.

    Args:
        launch_id: Optional launch id to filter on.
    """
    repo = get_repo()
    rows = repo.list_readiness(launch_id or None)
    return {"status": "ok",
            "launches": [{"launch_id": x["launch_id"], "launch_name": x["launch_name"], "in_hand_by": str(x["in_hand_by"]),
                          "embargo_date": str(x["embargo_date"])} for x in repo.list_launches()],
            "requests": [{**r, "in_hand_by": str(r["in_hand_by"]), "embargo_date": str(r["embargo_date"]),
                          "delivery_date": str(r["delivery_date"]) if r["delivery_date"] else None} for r in rows],
            "depot_surplus": [{"depot": d["depot_name"], "region": d["region"], "sku": d["sku"], "free": d["free"]}
                              for d in repo.list_depot_free() if int(d["free"]) > 0]}


def get_audit_trail(request_id: str = "") -> dict:
    """Return the audit trail from BigQuery (all events, or only one request).

    Args:
        request_id: Optional request id to filter on.
    """
    return {"status": "ok", "events": get_repo().list_audit(request_id or None)}
