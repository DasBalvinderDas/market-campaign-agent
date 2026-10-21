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

    The catalog is never listed as text: it is a PDF that is attached when the campaign is created.

    Args:
        mode: "campaign" for a whole campaign, "items" if they only want some items. Leave empty if not clear yet.
        campaign: The campaign name the user gave (not needed for items).
        people: How many people come (campaigns). Optional: leave 0 if the user did not say.
        date: The date everything must be in hand, exactly as the user said it ("31st Oct", "October 24"). Never add a year
            the user did not say: you do not know today's date, the tool uses the current year.
        venue: Where the campaign is, city and country as the user said them ("New York, USA"). We serve USA, Canada, London
            and Singapore.
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
    v = _find_venue(repo.list_venues(), venue) if venue else None
    unknown = venue if (venue and not v) else ""
    iso = d.isoformat() if d else ""
    region = v["region"] if v else ""
    places = [x["venue_name"] for x in repo.list_venues()]
    names = (presentation.name_suggestions(people, d, v["venue_name"] if v else "")
             if (d and v and not campaign and (mode or "").lower().startswith("camp")) else [])
    md = presentation.intake_checklist(mode, campaign, people, iso, v["venue_name"] if v else "", picks, "", "",
                                       unknown, note, names, places)
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


_ALIASES = {"us": "usa", "u.s.": "usa", "united states": "usa", "america": "usa", "uk": "london", "united kingdom": "london",
            "england": "london", "britain": "london"}


def _find_venue(venues: list[dict], text: str):
    """The place we serve that the text names: "USA", "New York, USA", "London, UK", "Toronto, Canada"."""
    t = text.strip().lower()
    words = [w.strip() for w in t.replace("/", ",").split(",") if w.strip()] + [t]
    for part in reversed(words):                   # the country is usually said last
        part = _ALIASES.get(part, part)
        for x in venues:
            if part in (x["venue_name"].lower(), x["country"].lower(), x["venue_id"].lower()):
                return x
    for x in venues:
        names = (x["venue_name"].lower(), x["country"].lower())
        if any(n in t for n in names) or any(a in t.split() or a in t for a in [k for k, val in _ALIASES.items()
                                                                              if val == x["venue_name"].lower() and len(k) > 2]):
            return x
    return None


async def get_catalog(deadline_date: str = "", place: str = "", tool_context=None) -> dict:
    """Attach the catalog PDF to the chat (what we can offer, our stock, prices and ready-by dates). Call it only when the
    user asks for the catalog again. Never list the catalog as text.

    Args:
        deadline_date: Optional date as YYYY-MM-DD, for date-specific prices.
        place: Optional place, for the heading.
    """
    from datetime import date as _d

    from .brief_tools import _attach_catalog
    try:
        d = _d.fromisoformat(deadline_date) if deadline_date else None
    except ValueError:
        d = None
    ok = await _attach_catalog(get_repo(), tool_context, d, place)
    return {"status": "ok" if ok else "error",
            "display_markdown": "📎 Our catalog is attached as a PDF." if ok else "The catalog PDF could not be made just now."}
