"""The assistant's business advice on a shopping list: what the user may be missing, before anything is planned.

Plain rules over stored data (no model involved), so the advice is the same every time:
  SPARES      a few extra units for late additions, damage and loss (SPARE_PERCENT in planning_rules, default 5)
  MISSING     a whole kind of bundle the campaign plan does not have (guest kits, venue stands, sales folders)
  COMPANIONS  a single item that is normally part of a bundle: the rest of that bundle
  DEADLINE    an item no vendor can have ready in time (and no stock covers), or only just
"""
import math
import re
from datetime import date, timedelta

_WHY_MISSING = {
    "GUEST_KIT": ("🎁", "VIP guest welcome kits", "Welcome kits make guests feel special and help them share the news."),
    "VENUE_DISPLAY": ("🖼️", "Venue display stands", "Display stands show the product at the venue, where people can see it."),
    "SALES_PACK": ("📁", "Sales folders and brochures", "The sales team needs something to leave with customers."),
}
_UNIT = {"GUEST_KIT": ("kit", "kits"), "VENUE_DISPLAY": ("stand", "stands"), "SALES_PACK": ("folder", "folders")}


def _matches(pattern: str, sku: str) -> bool:
    return bool(re.match("^" + re.escape(pattern).replace(r"\{size\}", ".+").replace(r"\{plug\}", ".+") + "$", sku))


def _label(assets: dict, sku: str) -> str:
    name = assets[sku]["name"]
    if sku.startswith("HOODIE-"):
        return name.rsplit(" ", 1)[0]
    return name.split(",")[0] if sku.startswith("PWR-") else name


def _bundle_count(repo, btype, lines):
    t = repo.get_bundle_templates(btype)
    if not t:
        return 0
    rx = re.compile("^" + re.escape(t[0]["sku_pattern"]).replace(r"\{size\}", ".+").replace(r"\{plug\}", ".+") + "$")
    return sum(ln["quantity"] for ln in lines if ln["bundle_type"] == btype and rx.match(ln["sku"])) // max(int(t[0]["qty_per_bundle"]), 1)


def suggestions(repo, request_id: str, today: date | None = None) -> list[dict]:
    today = today or date.today()
    lines = repo.get_requirement_lines(request_id)
    if not lines:
        return []
    req = repo.get_request(request_id)
    deadline = repo.get_launch(req["launch_id"])["in_hand_by"]
    assets = {a["sku"]: a for a in repo.list_assets()}
    pct = repo.get_planning_rules().get("SPARE_PERCENT", 5.0)
    present = list(dict.fromkeys(ln["bundle_type"] for ln in lines if ln["bundle_type"] != "SINGLE_ITEM"))
    out = []

    spares = []
    for btype in present:
        n = _bundle_count(repo, btype, lines)
        if n:
            k = max(1, math.ceil(n * pct / 100))
            spares.append(f"{k} {_UNIT.get(btype, ('bundle', 'bundles'))[0 if k == 1 else 1]}")
    if spares:
        out.append({"icon": "🛟", "what": f"A few spares ({pct:g}% extra: {', '.join(spares)})",
                    "why": "People get added late, and things get damaged or lost.", "say": "Add the spares"})

    if present:
        for btype, (icon, name, why) in _WHY_MISSING.items():
            if btype not in present:
                out.append({"icon": icon, "what": name, "why": why, "say": f"Add {name.lower()} (tell me how many)"})

    seen = set()
    for ln in (x for x in lines if x["bundle_type"] == "SINGLE_ITEM"):
        for btype in _WHY_MISSING:
            templates = repo.get_bundle_templates(btype)
            if btype in seen or not any(_matches(t["sku_pattern"], ln["sku"]) for t in templates):
                continue
            seen.add(btype)
            others = []
            for t in templates:
                skus = [k for k in assets if _matches(t["sku_pattern"], k)]
                if skus and ln["sku"] not in skus:
                    others.append(_label(assets, skus[0]))
            if others:
                desc = templates[0]["description"]
                out.append({"icon": "🧩", "what": f"The rest of the {desc}",
                            "why": f"This item is normally part of it, with: {', '.join(others)}. A whole bundle means more stock "
                                   "to reuse and more vendors to compare.", "say": f"Plan the whole {desc}"})

    if lines and all(x["bundle_type"] == "SINGLE_ITEM" for x in lines):
        out.append({"icon": "📣", "what": "Plan the whole campaign",
                    "why": "With only selected items I cannot spot spares, missing items or date risks across your campaign.",
                    "say": "Plan the whole campaign (tell me what else it needs)"})

    window = (deadline - today).days
    free = {}
    for d in repo.list_depot_free():
        free[d["sku"]] = free.get(d["sku"], 0) + int(d["free"])
    need = {}
    for ln in lines:
        need[ln["sku"]] = need.get(ln["sku"], 0) + ln["quantity"]
    offers = repo.list_vendor_offers_all()
    worst: dict = {}
    for sku, qty in need.items():
        if free.get(sku, 0) >= qty:
            continue
        mine = [o for o in offers if o["sku"] == sku]
        if not mine:
            continue
        fastest = min(int(o["lead_days"]) + int(o["delay_days"]) for o in mine)
        label = _label(assets, sku)
        worst[label] = max(worst.get(label, 0), fastest)
    for label, fastest in worst.items():
        if fastest > window:
            out.append({"icon": "🔴", "what": f"{label}: the date is too close",
                        "why": f"The fastest vendor needs {fastest} days and you have {window}.", "say": "Move the date later"})
        elif window - fastest < 3:
            out.append({"icon": "🟡", "what": f"{label}: very tight",
                        "why": f"The fastest vendor needs {fastest} days and you have {window}. One late truck is a problem.",
                        "say": "Move the date a little later"})
    return out
