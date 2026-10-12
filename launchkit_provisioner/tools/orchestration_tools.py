"""Read-only tools of the root agent."""
from .. import presentation
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
                              for d in repo.list_depot_free() if int(d["free"]) > 0],
            "display_markdown": presentation.board_markdown(rows, repo.list_depot_free(), {a["sku"]: a for a in repo.list_assets()})}


def get_audit_trail(request_id: str = "") -> dict:
    """Return the audit trail from BigQuery (all events, or only one request).

    Args:
        request_id: Optional request id to filter on.
    """
    events = get_repo().list_audit(request_id or None)
    return {"status": "ok", "events": events, "display_markdown": presentation.audit_markdown(events)}


def show_capabilities() -> dict:
    """What this assistant can do and what it needs from the user. Call it when the user greets (hi, hello), asks what
    you can do, or sends a first message that is not a request to plan or buy."""
    return {"status": "ok", "display_markdown": presentation.capabilities_card()}


def get_approval_rules() -> dict:
    """Who has to approve an order of which size (the approval levels), read from the approval policy table. Call it
    when the user asks who approves what, about approval limits or about the approval levels."""
    return {"status": "ok", "display_markdown": presentation.approval_rules_markdown(get_repo().list_policies())}


def get_vendor_report(request_id: str) -> dict:
    """The vendor comparison for a request: every vendor checked per item with price and days to make, who was chosen,
    and the stock we already own. Call it when the user asks to compare vendors.

    Args:
        request_id: Request id, e.g. "REQ-1A2B3C4D".
    """
    repo = get_repo()
    if not repo.get_scenarios(request_id):
        return {"status": "error", "message": "No options exist for this request yet: plan it first."}
    return {"status": "ok", "display_markdown": presentation.stock_report(repo, request_id) + "\n\n"
            + presentation.vendor_report(repo, request_id)}


def show_checklist(mode: str = "", campaign: str = "", date: str = "", needs: str = "") -> dict:
    """Show the four things to close on (what the user wants to do, the campaign name, the date, what they pick) with what
    we know so far and the ONE next question. When it is time to pick, it also shows what we can offer: ready-made packs and
    single items with our stock, best vendor prices and ready-by dates. Call it on every question turn, passing what the
    user has told you so far (leave the rest empty).

    Args:
        mode: "campaign" if they want to plan a whole campaign, "items" if they want to buy selected items.
        campaign: The campaign name the user chose. "Quick purchase" if the items are not for a campaign.
        date: The date everything must be in hand as YYYY-MM-DD (for a campaign on file, the date on file if the user said to use it).
        needs: A short summary of what they picked and how many.
    """
    from datetime import date as _date

    repo = get_repo()
    on_file = None
    if campaign and not date:
        known = next((x for x in repo.list_launches() if campaign.strip().lower() in
                      (x["launch_id"].lower(), x["launch_name"].lower())), None)
        on_file = known["in_hand_by"] if known else None
    deadline = None
    if date:
        try:
            deadline = _date.fromisoformat(date)
        except ValueError:
            deadline = None
    catalog = presentation.catalog_markdown(repo, deadline, "items" if "item" in (mode or "").lower() else "campaign") \
        if (mode and campaign and date and not needs) else ""
    out = {"status": "ok", "display_markdown": presentation.intake_checklist(mode, campaign, date, needs, catalog, on_file)}
    if on_file:
        out["date_on_file"] = str(on_file)
    return out
