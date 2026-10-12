"""Tools of the brief analyst agent (and the intake tool of the root agent)."""
import re
from datetime import date, timedelta

from pydantic import BaseModel

from .. import advisor, planner, presentation
from ..repositories import get_repo
from .audit import audit


def _ensure_campaign(repo, campaign: str, deadline_date: str):
    """Find the campaign by id or name, or create it (a new name needs a date). Returns (launch, how, error)."""
    deadline = None
    if deadline_date:
        try:
            deadline = date.fromisoformat(deadline_date.strip())
        except ValueError:
            return None, "", f"'{deadline_date}' is not a date. Ask for the date as day, month and year."
        if deadline <= date.today():
            return None, "", f"{deadline} is not in the future. Ask for a later date."
    launch, how = _find_event(repo, campaign), "found"
    if launch and deadline and launch["in_hand_by"] != deadline:
        gap = (launch["embargo_date"] - launch["in_hand_by"]).days
        repo.update_launch_dates(launch["launch_id"], deadline, deadline + timedelta(days=gap))
        audit(None, "orchestrator", "event_date_updated", launch_id=launch["launch_id"], old=str(launch["in_hand_by"]),
              new=str(deadline))
        launch, how = repo.get_launch(launch["launch_id"]), "date_updated"
    if not launch:
        if not deadline:
            known = [x["launch_name"] for x in repo.list_launches()]
            return None, "", (f"I do not know a campaign called '{campaign}' (known: {known}). Ask the user for the date "
                              "everything must be in hand, then call this again.")
        launch_id = "EVT-" + re.sub(r"[^A-Z0-9]+", "-", campaign.upper()).strip("-")[:30]
        while repo.get_launch(launch_id):
            launch_id += "-2"
        launch = {"launch_id": launch_id, "launch_name": campaign.strip(), "product_name": campaign.strip(),
                  "cost_center": "CC-EVENTS-GENERAL", "owner": "Marketing", "in_hand_by": deadline,
                  "embargo_date": deadline + timedelta(days=7)}
        repo.create_launch(launch)
        how = "created"
    return launch, how, ""


def create_campaign(campaign: str, deadline_date: str, people: int = 0, venue: str = "") -> dict:
    """Create the campaign as soon as the user has given or picked its name. Shows a confirmation. Call it once the name
    is known (campaigns only), then carry on with show_checklist. If the campaign already exists it is found, not
    duplicated.

    Args:
        campaign: The campaign name the user gave or picked.
        deadline_date: The date everything must be in hand, as YYYY-MM-DD (date_iso from show_checklist).
        people: How many people come.
        venue: The place (venue_name from show_checklist).
    """
    repo = get_repo()
    launch, how, err = _ensure_campaign(repo, campaign, deadline_date)
    if err:
        return {"status": "error", "message": err}
    audit(None, "orchestrator", "campaign_created" if how == "created" else "campaign_found", launch_id=launch["launch_id"],
          name=launch["launch_name"], people=people, venue=venue, in_hand_by=str(launch["in_hand_by"]))
    return {"status": "ok", "campaign_status": how, "launch_id": launch["launch_id"], "launch_name": launch["launch_name"],
            "in_hand_by": str(launch["in_hand_by"]),
            "display_markdown": presentation.campaign_created_markdown(launch, how, people, venue)}


def register_launch_request(campaign: str, summary: str, deadline_date: str = "") -> dict:
    """Register a new request for a campaign (or a quick purchase) and get its request id. The campaign is found by id or
    name (for example "Spring Product Launch Event"). A new campaign name is created when a deadline_date is given. If
    the campaign exists and a different deadline_date is given, its date is updated.

    Args:
        campaign: The campaign name the user chose. For items that are not for a campaign use "Quick purchase".
        summary: One line describing what is needed.
        deadline_date: The date everything must be in hand, as YYYY-MM-DD. Leave empty to use the date on file.
    """
    repo = get_repo()
    launch, how, err = _ensure_campaign(repo, campaign, deadline_date)
    if err:
        return {"status": "error", "message": err}
    request_id = repo.create_request(launch["launch_id"], summary)
    audit(request_id, "orchestrator", "request_registered", launch_id=launch["launch_id"], summary=summary, campaign_status=how)
    return {"status": "ok", "request_id": request_id, "launch_name": launch["launch_name"], "campaign_status": how,
            "in_hand_by": str(launch["in_hand_by"]), "embargo_date": str(launch["embargo_date"])}


def _find_event(repo, text: str):
    t = (text or "").strip().lower()
    events = repo.list_launches()
    for x in events:
        if t in (x["launch_id"].lower(), x["launch_name"].lower()):
            return x
    hits = [x for x in events if t and (t in x["launch_name"].lower() or x["launch_name"].lower() in t)]
    return hits[0] if len(hits) == 1 else None


class BundleRequest(BaseModel):
    bundle_type: str  # GUEST_KIT, VENUE_DISPLAY or SALES_PACK
    quantity: int
    region: str = ""  # only when the brief limits this bundle to one region: US, EMEA or APAC


class ItemRequest(BaseModel):
    item: str  # what to buy, in the user's words, e.g. "venue display stand" or "hoodie size M"
    quantity: int
    region: str  # where it goes: US, EMEA or APAC


def build_requirements(request_id: str, bundles: list[BundleRequest] | None = None,
                       items: list[ItemRequest] | None = None) -> dict:
    """Break the brief into requirement lines in one call: what is needed, per SKU and destination region. Guest kits
    are personalised from the guest list (hoodie size, power plug, engraving); venue display stands and sales folders
    follow the regional split. Single items are taken as they are. Call it ONCE with the whole brief. Calling it
    again replaces the earlier list (use it when the user changes the plan).

    Args:
        request_id: Request id returned by register_launch_request.
        bundles: Event bundles: bundle_type (GUEST_KIT, VENUE_DISPLAY, SALES_PACK), quantity and an optional region
            (US, EMEA, APAC). Leave out when there are none.
        items: Single items to buy as they are: item (user's words), quantity and region (US, EMEA or APAC). Leave out when
            there are none.
    """
    repo = get_repo()
    bundles, items = bundles or [], items or []
    req = repo.get_request(request_id)
    if not req:
        return {"status": "error", "message": f"Unknown request '{request_id}'."}
    if not bundles and not items:
        return {"status": "error", "message": "Nothing to plan yet: ask the user what they need and how many."}
    try:
        lines = (planner.expand_bundles(repo, req["launch_id"], [b.model_dump() for b in bundles]) if bundles else [])
        lines += planner.expand_items(repo, [i.model_dump() for i in items]) if items else []
    except planner.PlanError as exc:
        return {"status": "error", "message": str(exc)}
    repo.replace_requirement_lines(request_id, lines)
    audit(request_id, "brief_analyst_agent", "requirements_built", lines=len(lines),
          bundles=[b.model_dump() for b in bundles], items=[i.model_dump() for i in items])
    by_channel: dict = {}
    for ln in lines:
        ch = by_channel.setdefault(ln["channel"], {"units": 0, "regions": {}})
        ch["units"] += ln["quantity"]
        ch["regions"][ln["region"]] = ch["regions"].get(ln["region"], 0) + ln["quantity"]
    out = {"status": "ok", "request_id": request_id, "requirement_lines": len(lines), "channels": by_channel,
           "total_units": sum(ln["quantity"] for ln in lines), "bom_markdown": presentation.bom_markdown(repo, request_id)}
    tips = advisor.suggestions(repo, request_id)
    out["advice_count"] = len(tips)
    out["advice_markdown"] = presentation.advice_markdown(tips)
    if tips:
        audit(request_id, "brief_analyst_agent", "advice_given", suggestions=[t["what"] for t in tips])
    sizes, plugs = {}, {}
    for ln in lines:
        if ln["sku"].startswith("HOODIE-EVENT-"):
            size = ln["sku"].rsplit("-", 1)[1]
            sizes[size] = sizes.get(size, 0) + ln["quantity"]
        if ln["sku"].startswith("PWR-"):
            plug = ln["sku"][4:]
            plugs[plug] = plugs.get(plug, 0) + ln["quantity"]
    if any(b.bundle_type.upper() == "GUEST_KIT" for b in bundles) and not repo.guest_mix(req["launch_id"]):
        out["note"] = ("This campaign has no guest list yet, so the standard guest mix (sizes, regions, plugs) was used. "
                       "Tell the user a real guest list can be added later.")
    if sizes:
        out["guest_hoodie_sizes"] = sizes
        out["guest_power_plugs"] = plugs
    return out
