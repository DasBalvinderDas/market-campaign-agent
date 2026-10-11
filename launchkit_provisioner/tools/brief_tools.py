"""Tools of the brief analyst agent (and the intake tool of the root agent)."""
from pydantic import BaseModel

from .. import planner
from ..repositories import get_repo
from .audit import audit


def register_launch_request(launch_id: str, summary: str) -> dict:
    """Register a new launch collateral request and get its request id.

    Args:
        launch_id: The launch, e.g. "LAUNCH-AURORA".
        summary: One line describing the brief.
    """
    repo = get_repo()
    launch = repo.get_launch(launch_id)
    if not launch:
        known = [x["launch_id"] for x in repo.list_launches()]
        return {"status": "error", "message": f"Unknown launch '{launch_id}'. Known launches: {known}"}
    request_id = repo.create_request(launch_id, summary)
    audit(request_id, "orchestrator", "request_registered", launch_id=launch_id, summary=summary)
    return {"status": "ok", "request_id": request_id, "launch_name": launch["launch_name"],
            "in_hand_by": str(launch["in_hand_by"]), "embargo_date": str(launch["embargo_date"])}


class BundleRequest(BaseModel):
    bundle_type: str  # CREATOR_KIT, SHOWROOM_DISPLAY or SALES_FOLIO
    quantity: int
    region: str = ""  # only when the brief limits this bundle to one region: US, EMEA or APAC


def build_requirements(request_id: str, bundles: list[BundleRequest]) -> dict:
    """Break the brief into requirement lines in one call: what is needed, per SKU and destination region. Creator kits
    are personalised from the creator list (hoodie size, power plug, engraving); showroom displays and sales folios
    follow the regional split. Call it ONCE with every bundle of the brief.

    Args:
        request_id: Request id returned by register_launch_request.
        bundles: Every bundle in the brief: bundle_type (CREATOR_KIT, SHOWROOM_DISPLAY, SALES_FOLIO), quantity and an
            optional region (US, EMEA, APAC).
    """
    repo = get_repo()
    req = repo.get_request(request_id)
    if not req:
        return {"status": "error", "message": f"Unknown request '{request_id}'."}
    try:
        lines = planner.expand_bundles(repo, req["launch_id"], [b.model_dump() for b in bundles])
    except planner.PlanError as exc:
        return {"status": "error", "message": str(exc)}
    repo.replace_requirement_lines(request_id, lines)
    audit(request_id, "brief_analyst_agent", "requirements_built", lines=len(lines),
          bundles=[b.model_dump() for b in bundles])
    by_channel: dict = {}
    for ln in lines:
        ch = by_channel.setdefault(ln["channel"], {"units": 0, "regions": {}})
        ch["units"] += ln["quantity"]
        ch["regions"][ln["region"]] = ch["regions"].get(ln["region"], 0) + ln["quantity"]
    out = {"status": "ok", "request_id": request_id, "requirement_lines": len(lines), "channels": by_channel,
           "total_units": sum(ln["quantity"] for ln in lines)}
    sizes, plugs = {}, {}
    for ln in lines:
        if ln["sku"].startswith("HOODIE-AURORA-"):
            size = ln["sku"].rsplit("-", 1)[1]
            sizes[size] = sizes.get(size, 0) + ln["quantity"]
        if ln["sku"].startswith("PWR-"):
            plug = ln["sku"][4:]
            plugs[plug] = plugs.get(plug, 0) + ln["quantity"]
    if sizes:
        out["creator_hoodie_sizes"] = sizes
        out["creator_power_plugs"] = plugs
    return out
