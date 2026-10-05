"""Tools owned by the root orchestrator."""
from ..repositories import get_repo
from .audit import audit


def register_campaign_request(campaign_id: str, summary: str) -> dict:
    """Register a new campaign logistics request and get its request id.

    Args:
        campaign_id: Campaign code, e.g. "NEXT27-MAIN".
        summary: One-line description of what is needed.
    """
    repo = get_repo()
    budget = repo.get_budget(campaign_id)
    if not budget:
        known = [{"campaign_id": b["campaign_id"], "name": b["campaign_name"]} for b in repo.list_budgets()]
        return {"status": "error", "message": f"Unknown campaign '{campaign_id}'.", "known_campaigns": known}
    request_id = repo.create_request(campaign_id, summary)
    audit(request_id, "orchestrator", "request_registered", campaign_id=campaign_id, summary=summary)
    return {"status": "ok", "request_id": request_id, "campaign_id": campaign_id,
            "campaign_name": budget["campaign_name"]}


def get_campaign_overview() -> dict:
    """Budget position of every Google Next 2027 campaign (total, spent, committed, remaining)."""
    return {"status": "ok", "campaigns": [
        {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in b.items()}
        for b in get_repo().list_budgets()]}


def get_approval_status(request_id: str) -> dict:
    """Status of the emailed human approval for a request (PENDING, APPROVED, REJECTED, FAILED or EXPIRED) and
    the purchase orders created after it.

    Args:
        request_id: Campaign request id.
    """
    from .. import approval_flow
    return {"request_id": request_id, **approval_flow.approval_status(get_repo(), request_id)}


def get_audit_trail(request_id: str = "") -> dict:
    """Return the audit trail from BigQuery (all events, or only one request).

    Args:
        request_id: Optional request id to filter on.
    """
    return {"status": "ok", "events": get_repo().list_audit(request_id or None)}
