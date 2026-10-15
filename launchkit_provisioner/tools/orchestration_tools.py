"""Read-only tools of the root agent."""
from .. import presentation
from ..dates import parse_date
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
    return {"status": "ok", "display_markdown": presentation.capabilities_card(get_repo().list_launches())}


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


def show_checklist(mode: str = "", campaign: str = "", people: int = 0, date: str = "", venue: str = "",
                   picks: str = "") -> dict:
    """The interviewer. Shows what we know so far (✅/⬜) and the ONE next question. When the date is known it also shows
    where we can deliver (vendors and warehouses), and when the place is known it shows our offer with a suggested plan
    for the headcount. Call it on EVERY question turn with everything the user has said so far (leave the rest empty).
    Users talk naturally ("a campaign for 300 people on 31st Oct"): pass what you can read from their words.

    Args:
        mode: "campaign" for a whole campaign, "items" if they only want some items. Leave empty if not clear yet.
        campaign: The campaign name the user gave (not needed for items).
        people: How many people come (campaigns).
        date: The date everything must be in hand, exactly as the user said it ("31st Oct", "October 24"). Never add a year
            the user did not say: you do not know today's date, the tool uses the current year.
        venue: Where the campaign is: USA, Canada, London or Singapore (or a city in one of them).
        picks: A short summary of what they picked, once they pick.
    Returns date_iso, region and venue_name when known, `name_suggestions` (when it asks for a name: the user may say a
    number to pick one, use the matching name), and `suggested` (bundles and items for the headcount) for
    "use the suggested plan". Use date_iso as deadline_date and region for every pick.
    """
    from datetime import date as _date

    repo = get_repo()
    d = parse_date(date) if date else None
    note = ""
    if date and not d:
        note = f"I could not read the date '{date}'."
    elif d and d <= _date.today():
        note, d = f"{d} has already passed. Ask for a later date (or the year, if they mean next year).", None
    v = None
    unknown = ""
    if venue:
        t = venue.strip().lower()
        v = next((x for x in repo.list_venues() if t in (x["venue_name"].lower(), x["country"].lower(), x["venue_id"].lower())
                  or x["venue_name"].lower() in t or t in x["country"].lower()), None)
        unknown = "" if v else venue
    iso = d.isoformat() if d else ""
    region = v["region"] if v else ""
    venues_md = presentation.venues_markdown(repo, people, presentation.day(d) if d else "") if (d and not v) else ""
    catalog = (presentation.catalog_markdown(repo, d, "items" if (mode or "").lower().startswith("item") else "campaign",
                                              people=people, region=region)
               if (d and v and not picks and (campaign or (mode or "").lower().startswith("item"))) else "")
    names = (presentation.name_suggestions(people, d, v["venue_name"] if v else "")
             if (d and v and not campaign and (mode or "").lower().startswith("camp")) else [])
    md = presentation.intake_checklist(mode, campaign, people, iso, v["venue_name"] if v else "", picks, venues_md, catalog,
                                       unknown, note, names)
    out = {"status": "ok", "display_markdown": md}
    if names:
        out["name_suggestions"] = names
    if iso:
        out["date_iso"] = iso
    if v:
        out.update(region=region, venue_name=v["venue_name"])
        if people and (mode or "").lower().startswith("camp"):
            out["suggested"] = presentation.suggested_plan(repo, people, region)
    return out
