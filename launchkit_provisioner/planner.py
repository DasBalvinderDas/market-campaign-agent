"""The planning engine: turns a brief into requirement lines and computes the sourcing scenarios.

Everything here is deterministic and works only from data in the repository (BigQuery in real use), so the numbers a
decision maker sees are computed, never typed in by the model.

Scenarios (option codes)
  FULL_NEW   everything bought new from the cheapest standard offer (ignores surplus stock and the deadline)
  REBALANCE  surplus depot stock first (nearest depot first), the rest from the cheapest standard offer that keeps the
             target safety buffer before the in-hand date (else the fastest offer)
  ECO        eco offers, with the same deadline-aware choice (falls back to a standard offer where no eco offer
             can make the date); no depot reuse
Every scenario reports cost, delivery date, safety buffer in hours, savings versus FULL_NEW, carbon and risk. The
recommendation is the cheapest scenario that keeps at least the minimum buffer.
"""
import math
import re
from datetime import date, timedelta

from .repositories.base import Repository

OPTIONS = [("FULL_NEW", "FN", "Buy everything new"),
           ("REBALANCE", "RB", "Use our stock first, buy the rest"),
           ("ECO", "EC", "Go green with eco-friendly materials")]
CHANNEL = {"GUEST_KIT": "GUESTS", "VENUE_DISPLAY": "VENUES", "SALES_PACK": "SALES", "SINGLE_ITEM": "ITEMS"}


def price_factor(rules: list[dict], vendor_id: str, days_ahead: int) -> tuple[float, str]:
    """The vendor's price factor for an order placed this many days before the in-hand date (early-bird or rush).
    A vendor with its own rows uses only those; every other vendor uses the '*' rows."""
    mine = [r for r in rules if r["vendor_id"] == vendor_id] or [r for r in rules if r["vendor_id"] == "*"]
    fits = [r for r in mine if int(r["min_days_ahead"]) <= days_ahead]
    if not fits:
        return 1.0, ""
    r = max(fits, key=lambda r: int(r["min_days_ahead"]))
    return float(r["price_factor"]), r.get("label") or ""


class PlanError(ValueError):
    """A problem the model should explain to the user (unknown bundle, missing launch, ...)."""


# ---------------------------------------------------------------------------- brief -> requirement lines
def _scale(counts: dict, total: int) -> dict:
    """Spread ``total`` over keys in proportion to ``counts`` (largest remainder, so the sum is exact)."""
    base = sum(counts.values())
    if base == 0:
        raise PlanError("There is no distribution data to split the quantity.")
    exact = {k: total * v / base for k, v in counts.items()}
    out = {k: int(math.floor(x)) for k, x in exact.items()}
    for k in sorted(exact, key=lambda k: (exact[k] - out[k], k), reverse=True)[: total - sum(out.values())]:
        out[k] += 1
    return {k: v for k, v in out.items() if v}


STANDARD_GUEST_LIST = "GUEST-MIX-TEMPLATE"      # a standing guest list (sizes, regions) that is not tied to any campaign


def _standard_guest_mix(repo: Repository) -> list[dict]:
    """A new campaign has no guest list yet: use the standing guest list if there is one, else the guest mix (sizes,
    regions, plugs) of the first event that has one."""
    mix = repo.guest_mix(STANDARD_GUEST_LIST)
    if mix:
        return mix
    for launch in repo.list_launches():
        mix = repo.guest_mix(launch["launch_id"])
        if mix:
            return mix
    return []


_STOP = {"a", "an", "the", "of", "for", "size", "type", "pcs", "units", "unit", "item", "items"}


def _tokens(text: str) -> set:
    out = set()
    for w in re.split(r"[^a-z0-9]+", (text or "").lower()):
        if w and w not in _STOP:
            out.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return out


def resolve_item(assets: list[dict], text: str) -> dict:
    """The asset a user means by 'display stand', 'hoodie size M', 'HOODIE-EVENT-M'. Raises PlanError with the choices
    when it is unclear."""
    t = (text or "").strip()
    for a in assets:
        if t.lower() in (a["sku"].lower(), a["name"].lower()):
            return a
    want = _tokens(t)
    hits = [a for a in assets if want and want <= _tokens(a["name"]) | _tokens(a["sku"])]
    if len(hits) == 1:
        return hits[0]
    if hits:
        raise PlanError(f"'{text}' could mean: " + "; ".join(a["name"] for a in hits) + ". Ask the user which one.")
    raise PlanError(f"No item called '{text}'. Items we can buy: " + "; ".join(sorted(a["name"] for a in assets)) + ".")


_REGION_WORDS = {"US": ("us", "usa", "united states", "america", "canada", "north america"),
                 "EMEA": ("emea", "uk", "united kingdom", "london", "england", "europe", "eu"),
                 "APAC": ("apac", "singapore", "asia", "asia pacific")}
_BUNDLE_WORDS = {"GUEST_KIT": ("guest", "welcome", "kit"), "VENUE_DISPLAY": ("display", "stand", "venue"),
                 "SALES_PACK": ("sales", "folder", "leave")}


def normalize_region(repo, text) -> str:
    """US, EMEA or APAC from what the assistant passed: the region itself, a place (Singapore, London, USA), a country or a
    venue id. Empty text stays empty; anything not understood is returned upper-cased (the caller reports it)."""
    t = (text or "").strip().lower()
    if not t:
        return ""
    if t.upper() in ("US", "EMEA", "APAC"):
        return t.upper()
    for v in repo.list_venues():
        if t in (v["venue_id"].lower(), v["venue_name"].lower(), v["country"].lower()):
            return v["region"]
    for region, words in _REGION_WORDS.items():
        if t in words:
            return region
    return t.upper()


def normalize_bundle(text, valid) -> str:
    """GUEST_KIT, VENUE_DISPLAY or SALES_PACK from the exact type or a name like "guest welcome kit" or "sales folders"."""
    t = (text or "").strip()
    if t.upper().replace(" ", "_") in valid:
        return t.upper().replace(" ", "_")
    low = t.lower()
    for btype, words in _BUNDLE_WORDS.items():
        if btype in valid and any(w in low for w in words):
            return btype
    return t.upper()


def expand_items(repo: Repository, items: list[dict]) -> list[dict]:
    """Single items as they are: [{item, quantity, region}] -> requirement lines (no bundle, no split)."""
    assets = repo.list_assets()
    merged: dict = {}
    for it in items:
        qty, region = int(it["quantity"]), normalize_region(repo, it.get("region"))
        if qty <= 0:
            raise PlanError(f"The quantity for '{it['item']}' must be positive.")
        if region not in ("US", "EMEA", "APAC"):
            raise PlanError(f"Which region should '{it['item']}' be delivered to (US, EMEA or APAC)? Ask the user.")
        a = resolve_item(assets, it["item"])
        key = ("SINGLE_ITEM", a["sku"], region)
        merged[key] = merged.get(key, 0) + qty
    return [{"bundle_type": k[0], "channel": CHANNEL["SINGLE_ITEM"], "sku": k[1], "region": k[2], "quantity": q}
            for k, q in sorted(merged.items())]


def expand_bundles(repo: Repository, launch_id: str, bundles: list[dict]) -> list[dict]:
    """bundles: [{bundle_type, quantity, region (optional)}] -> merged lines {bundle_type, channel, sku, region, quantity}."""
    merged: dict = {}
    valid = repo.list_bundle_types()
    for b in bundles:
        btype, qty = normalize_bundle(b["bundle_type"], valid), int(b["quantity"])
        only_region = normalize_region(repo, b.get("region"))
        if btype not in valid:
            raise PlanError(f"Unknown bundle type '{b['bundle_type']}'. Valid types: {valid}")
        if qty <= 0:
            raise PlanError(f"The quantity for {btype} must be positive.")
        templates = repo.get_bundle_templates(btype)
        if btype == "GUEST_KIT":
            mix = [m for m in (repo.guest_mix(launch_id) or _standard_guest_mix(repo)) if not only_region or m["region"] == only_region]
            if not mix:
                raise PlanError(f"No guests on the list for launch {launch_id}" + (f" in {only_region}." if only_region else "."))
            kits = _scale({(m["size"], m["region"], m["plug_type"]): m["n"] for m in mix}, qty)
            for (size, region, plug), n in kits.items():
                for t in templates:
                    key = (btype, t["sku_pattern"].format(size=size, plug=plug), region)
                    merged[key] = merged.get(key, 0) + n * int(t["qty_per_bundle"])
        else:
            if only_region:
                per_region = {only_region: qty}
            else:
                per_region = _scale({s["region"]: float(s["share_pct"]) for s in repo.get_regional_split(btype)}, qty)
            if not per_region:
                raise PlanError(f"No regional split is defined for {btype}; give a region.")
            for region, n in per_region.items():
                for t in templates:
                    key = (btype, t["sku_pattern"], region)
                    merged[key] = merged.get(key, 0) + n * int(t["qty_per_bundle"])
    lines = [{"bundle_type": k[0], "channel": CHANNEL.get(k[0], k[0]), "sku": k[1], "region": k[2], "quantity": q}
             for k, q in merged.items()]
    return sorted(lines, key=lambda x: (x["channel"], x["sku"], x["region"]))


# ---------------------------------------------------------------------------- scenarios
class _Ctx:
    def __init__(self, repo: Repository, request_id: str, today: date, deadline: date | None = None):
        req = repo.get_request(request_id)
        if not req:
            raise PlanError(f"Unknown request '{request_id}'.")
        self.launch = dict(repo.get_launch(req["launch_id"]))
        if deadline:
            self.launch["in_hand_by"] = deadline
        self.lines = repo.get_requirement_lines(request_id)
        if not self.lines:
            raise PlanError("This request has no requirement lines yet: run the brief analysis first.")
        self.rules = repo.get_planning_rules()
        self.lanes = repo.get_lanes()
        self.today = today
        self.repo = repo
        self.window_days = (self.launch["in_hand_by"] - today).days
        self._offers = self._assets = self._depots = self._pricing = None

    def set_deadline(self, deadline: date) -> None:
        self.launch["in_hand_by"] = deadline
        self.window_days = (deadline - self.today).days

    def factor(self, vendor_id: str) -> float:
        """Early-bird discount or rush charge for this vendor on this date."""
        if self._pricing is None:
            self._pricing = self.repo.list_date_pricing()
        return price_factor(self._pricing, vendor_id, self.window_days)[0]

    def lane(self, a, b):
        lane = self.lanes.get((a, b))
        if not lane:
            raise PlanError(f"No shipping lane from {a} to {b}.")
        return lane

    # One bulk read each (three queries in BigQuery), grouped here, instead of a query per SKU.
    def offers(self, sku):
        if self._offers is None:
            self._offers = {}
            for o in self.repo.list_vendor_offers_all():
                self._offers.setdefault(o["sku"], []).append(o)
        return self._offers.get(sku, [])

    def asset(self, sku):
        if self._assets is None:
            self._assets = {a["sku"]: a for a in self.repo.list_assets()}
        if sku not in self._assets:
            raise PlanError(f"'{sku}' is not in the asset catalog.")
        return self._assets[sku]

    def depots(self, sku):
        if self._depots is None:
            self._depots = {}
            for d in self.repo.list_depot_free():
                self._depots.setdefault(d["sku"], []).append(d)
        return self._depots.get(sku, [])


def _vendor_line(ctx: _Ctx, line: dict, offer: dict) -> dict:
    lane = ctx.lane(offer["home_region"], line["region"])
    factor = float(ctx.asset(line["sku"])["ship_factor"])
    qty = line["quantity"]
    shipping = round(qty * factor * lane["cost_per_unit"], 2)
    days = int(offer["lead_days"]) + int(offer["delay_days"]) + lane["days"]
    price = round(float(offer["unit_price"]) * ctx.factor(offer["vendor_id"]), 2)
    return {"source_type": "VENDOR", "source_id": offer["vendor_id"], "variant": offer["variant"],
            "unit_price": price, "shipping_cost": shipping,
            "line_total": round(qty * price + shipping, 2), "days_to_deliver": days,
            "carbon_kg": round(qty * float(offer["carbon_kg"]), 2)}


def _depot_line(ctx: _Ctx, line: dict, depot: dict, qty: int) -> dict:
    lane = ctx.lane(depot["region"], line["region"])
    factor = float(ctx.asset(line["sku"])["ship_factor"])
    shipping = round(qty * factor * lane["cost_per_unit"], 2)
    carbon = round(qty * factor * ctx.rules.get("TRANSFER_CARBON_KG_PER_FACTOR", 0.4), 2)
    return {"source_type": "DEPOT", "source_id": depot["depot_id"], "variant": None, "unit_price": 0.0,
            "shipping_cost": shipping, "line_total": shipping,
            "days_to_deliver": int(ctx.rules.get("DEPOT_HANDLING_DAYS", 1)) + lane["days"], "carbon_kg": carbon}


def _choose_offer(ctx: _Ctx, line: dict, variants: list[str], deadline_aware: bool):
    """Pick a vendor offer. Without deadline awareness: the cheapest. With it: the cheapest that keeps the target
    buffer (preferring the requested variants), else the fastest."""
    offers = [o for o in ctx.offers(line["sku"])]
    if not offers:
        return None
    built = [(o, _vendor_line(ctx, line, o)) for o in offers]
    if not deadline_aware:
        pool = [p for p in built if p[0]["variant"] in variants]
        return min(pool, key=lambda p: (p[1]["line_total"], p[1]["days_to_deliver"])) if pool else None
    target_days = ctx.window_days - math.ceil(ctx.rules.get("TARGET_BUFFER_HOURS", 48) / 24)
    for variant_group in (variants, ["STANDARD", "ECO"]):
        pool = [p for p in built if p[0]["variant"] in variant_group and p[1]["days_to_deliver"] <= target_days]
        if pool:
            return min(pool, key=lambda p: (p[1]["line_total"], p[1]["days_to_deliver"]))
    return min(built, key=lambda p: (p[1]["days_to_deliver"], p[1]["line_total"]))


def _allocate_depots(ctx: _Ctx) -> dict:
    """Greedy reuse of surplus stock: per SKU, nearest (fewest days) depot-to-destination pairs first.
    Returns {line_index: [(depot, qty), ...]}."""
    plan: dict = {}
    by_sku: dict = {}
    for i, ln in enumerate(ctx.lines):
        by_sku.setdefault(ln["sku"], []).append(i)
    for sku, idxs in by_sku.items():
        free = {d["depot_id"]: int(d["free"]) for d in ctx.depots(sku)}
        meta = {d["depot_id"]: d for d in ctx.depots(sku)}
        need = {i: ctx.lines[i]["quantity"] for i in idxs}
        pairs = sorted(((ctx.lane(meta[d]["region"], ctx.lines[i]["region"])["days"], d, i) for d in free for i in idxs))
        for _days, d, i in pairs:
            take = min(free[d], need[i])
            if take > 0:
                plan.setdefault(i, []).append((meta[d], take))
                free[d] -= take
                need[i] -= take
    return plan


def _build_lines(ctx: _Ctx, code: str) -> tuple[list[dict], list[str]]:
    out, unsourced = [], []
    depot_plan = _allocate_depots(ctx) if code == "REBALANCE" else {}
    for i, ln in enumerate(ctx.lines):
        remaining = ln["quantity"]
        base = {"channel": ln["channel"], "sku": ln["sku"], "region": ln["region"]}
        for depot, qty in depot_plan.get(i, []):
            out.append({**base, "quantity": qty, **_depot_line(ctx, {**ln, "quantity": qty}, depot, qty)})
            remaining -= qty
        if remaining > 0:
            part = {**ln, "quantity": remaining}
            if code == "FULL_NEW":
                pick = _choose_offer(ctx, part, ["STANDARD"], deadline_aware=False)
            elif code == "REBALANCE":
                pick = _choose_offer(ctx, part, ["STANDARD"], deadline_aware=True)
            else:
                pick = _choose_offer(ctx, part, ["ECO"], deadline_aware=True)
            if pick is None:
                unsourced.append(ln["sku"])
                continue
            out.append({**base, "quantity": remaining, **pick[1]})
    return out, unsourced


def _risk(buffer_hours: int, min_buffer: float, unsourced: list) -> str:
    if unsourced:
        return f"HIGH: no vendor can supply {', '.join(sorted(set(unsourced)))}"
    if buffer_hours < 0:
        return f"HIGH: misses the in-hand date by {-buffer_hours} hours"
    if buffer_hours < min_buffer:
        return f"MODERATE: only {buffer_hours} hours of safety buffer"
    return f"LOW: {buffer_hours} hours of safety buffer"


def plan_scenarios(repo: Repository, request_id: str, today: date | None = None,
                   deadline: date | None = None) -> tuple[list[dict], list[dict]]:
    """Compute the three scenarios for a request. Returns (scenarios, scenario_lines), ready to store.
    A deadline other than the one on file plans for that date instead (used to compare dates; nothing is stored)."""
    return _plan(_Ctx(repo, request_id, today or date.today(), deadline), request_id)


def plan_dates(repo: Repository, request_id: str, offsets: list[int], today: date | None = None) -> list[dict]:
    """The best option for the same list on other dates: [{offset, deadline, window, best, band}], one planning pass each.
    Dates that are not at least a day away are left out."""
    today = today or date.today()
    ctx = _Ctx(repo, request_id, today)
    base = ctx.launch["in_hand_by"]
    rules = repo.list_date_pricing()
    out = []
    for off in offsets:
        d = base + timedelta(days=off)
        if (d - today).days < 1:
            continue
        ctx.set_deadline(d)
        scenarios, _ = _plan(ctx, request_id)
        best = next(s for s in scenarios if s["recommended"])
        out.append({"offset": off, "deadline": d, "window": ctx.window_days, "best": best,
                    "band": price_factor(rules, "*", ctx.window_days)[1]})
    return out


def _plan(ctx: _Ctx, request_id: str) -> tuple[list[dict], list[dict]]:
    min_buffer = ctx.rules.get("MIN_BUFFER_HOURS", 24)
    scenarios, all_lines = [], []
    for code, short, name in OPTIONS:
        sid = f"{request_id}-{short}"
        lines, unsourced = _build_lines(ctx, code)
        for n, ln in enumerate(lines, start=1):
            ln.update(line_id=f"{sid}-L{n:02d}", scenario_id=sid, request_id=request_id, execution_status="PLANNED")
        longest = max((ln["days_to_deliver"] for ln in lines), default=0)
        delivery = ctx.today + timedelta(days=longest)
        buffer_hours = (ctx.launch["in_hand_by"] - delivery).days * 24
        total = round(sum(ln["line_total"] for ln in lines), 2)
        scenarios.append({
            "scenario_id": sid, "request_id": request_id, "option_code": code, "option_name": name,
            "total_cost": total, "shipping_cost": round(sum(ln["shipping_cost"] for ln in lines), 2),
            "savings_usd": 0.0, "delivery_date": delivery, "buffer_hours": int(buffer_hours),
            "carbon_kg": round(sum(ln["carbon_kg"] for ln in lines), 1),
            "risk": _risk(int(buffer_hours), min_buffer, unsourced),
            "feasible": buffer_hours >= 0 and not unsourced, "recommended": False,
            "summary": _summary(code, lines)})
        all_lines += lines
    base = next((s["total_cost"] for s in scenarios if s["option_code"] == "FULL_NEW"), 0.0)
    for s in scenarios:
        s["savings_usd"] = round(base - s["total_cost"], 2)
    ok = [s for s in scenarios if s["feasible"] and s["buffer_hours"] >= min_buffer]
    pool = ok or [s for s in scenarios if s["feasible"]] or scenarios
    best = min(pool, key=(lambda s: (s["total_cost"], -s["buffer_hours"])) if ok
               else (lambda s: (-s["buffer_hours"], s["total_cost"])))   # none has the minimum buffer: most buffer, then cheapest
    best["recommended"] = True
    return scenarios, all_lines


def _summary(code: str, lines: list[dict]) -> str:
    depot_units = sum(ln["quantity"] for ln in lines if ln["source_type"] == "DEPOT")
    vendor_units = sum(ln["quantity"] for ln in lines if ln["source_type"] == "VENDOR")
    eco_units = sum(ln["quantity"] for ln in lines if ln.get("variant") == "ECO")
    if code == "FULL_NEW":
        return f"Order all {vendor_units:,} items new from the cheapest vendors."
    if code == "REBALANCE":
        return f"Take {depot_units:,} items we already own from our warehouses and order the other {vendor_units:,}."
    return f"{eco_units:,} items made from eco-friendly materials, {vendor_units - eco_units:,} normal ones where eco is too slow."


# ---------------------------------------------------------------------------- presentation
def decision_card(request_id: str, launch: dict, scenarios: list[dict], policies: list[dict], min_buffer: float = 24,
                  single_item: bool = False) -> str:
    """The three choices as a table (see presentation.py), computed from the stored scenarios."""
    from . import presentation
    return presentation.decision_card(request_id, launch, scenarios, policies, min_buffer, single_item)


# ---------------------------------------------------------------------------- vendor delays
def resolve_vendor(repo: Repository, text: str) -> dict | None:
    """A vendor by id or by (part of) its name."""
    t = (text or "").strip().lower()
    vendors = repo.list_vendors()
    for v in vendors:
        if t in (v["vendor_id"].lower(), v["vendor_name"].lower()):
            return v
    hits = [v for v in vendors if t and (t in v["vendor_name"].lower() or t in v["vendor_id"].lower())]
    return hits[0] if len(hits) == 1 else None


def delay_impact(repo: Repository, scenario: dict, delay_days: int, vendor_id: str) -> dict:
    """What a vendor delay does to an already chosen scenario: the lines it touches and the new buffer."""
    lines = repo.get_scenario_lines(scenario["scenario_id"])
    longest = max((ln["days_to_deliver"] for ln in lines), default=0)
    start = scenario["delivery_date"] - timedelta(days=longest)
    affected = [ln for ln in lines if ln["source_type"] == "VENDOR" and ln["source_id"] == vendor_id]
    new_longest = max((ln["days_to_deliver"] + (delay_days if ln in affected else 0) for ln in lines), default=0)
    new_delivery = start + timedelta(days=new_longest)
    launch = repo.get_launch(repo.get_request(scenario["request_id"])["launch_id"])
    buffer_hours = (launch["in_hand_by"] - new_delivery).days * 24
    return {"affected_lines": len(affected), "new_delivery_date": new_delivery, "new_buffer_hours": int(buffer_hours),
            "still_on_time": buffer_hours >= 0}
