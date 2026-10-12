"""Everything the user reads: simple words, tables and icons, built from stored data (never typed in by the model).

Each function returns Markdown. The agents show it exactly as returned, so the numbers on screen are the numbers in
BigQuery, and the wording is the same every time.
"""
import re
from datetime import date, timedelta

from .planner import price_factor

ICON = {"FULL_NEW": "🛒", "REBALANCE": "♻️", "ECO": "🌱"}
_UNITS = {"GUEST_KIT": "kits", "VENUE_DISPLAY": "stands", "SALES_PACK": "folders"}


def money(x) -> str:
    return f"${float(x):,.2f}"


def day(d) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day} {d:%b %Y}"


def spare(hours, min_buffer=24) -> str:
    """Spare time before the deadline in plain words, with a traffic light."""
    days = int(hours) // 24
    if hours < 0:
        return f"🔴 {-days} day LATE" if days == -1 else f"🔴 {-days} days LATE"
    if hours < min_buffer:
        return "🟡 none (tight!)"
    return f"🟢 {days} day to spare" if days == 1 else f"🟢 {days} days to spare"


# ---------------------------------------------------------------------------- the first hello
def capabilities_card() -> str:
    return """## 👋 Hi! I am your Campaign Procurement Assistant
> Tell me about your campaign. I show you what we have, compare vendors, find the best date, and place the orders once the right person says OK.

| | I can | In simple words |
|---|---|---|
| 📍 | Show **where we can deliver** | Vendors and warehouses in the USA, Canada, London and Singapore |
| 🛍️ | Show **what we offer** | Our stock, best prices, ready-by dates, a plan for your headcount |
| 🧾 | Make your **shopping list** | Exact items, amounts and places |
| 💡 | Spot **what you may be missing** | Spares, extra items, dates that are too tight |
| 🏭 | Compare **vendors** | Prices, ready-by dates, late vendors |
| 📅 | Find the **best date** | Vendors charge less when you order early, more for a rush |
| ✍️ | Get the **right OK** | Small = automatic · bigger = manager · biggest = CMO |
| 📦 | **Place all the orders** | At once, with a clear summary |

**Just talk to me.** For example: *"Hi, I am looking for a campaign for 300 people on 31st Oct."* Only need a few items? Tell me which. I will ask for anything that is missing.

**💡 Planning the whole campaign is best:** more stock to reuse, more vendors to compare, a stronger case for better rates.

### 👉 First question
**Tell me about your campaign:** how many people, and on which date?
"""


def _fits(ready: date, deadline: date | None) -> str:
    if deadline is None:
        return ""
    gap = (deadline - ready).days
    return "🔴 too late" if gap < 0 else ("🟡 tight" if gap < 3 else "🟢 fits")


def _ceil(x: float) -> int:
    return int(-(-x // 1)) if x > 0 else 0


def suggested_plan(repo, people: int, region: str = "") -> dict:
    """A starter plan for this many guests from the suggested_per_person columns: {bundles: [...], items: [...]}."""
    if not people:
        return {"bundles": [], "items": []}
    assets = {a["sku"]: a for a in repo.list_assets()}
    bundles, items = [], []
    for btype in repo.list_bundle_types():
        ratios = [t.get("suggested_per_person") for t in repo.get_bundle_templates(btype) if t.get("suggested_per_person")]
        if ratios:
            bundles.append({"bundle_type": btype, "quantity": max(1, _ceil(people * float(ratios[0]))), "region": region})
    for sku, a in assets.items():
        if a.get("suggested_per_person"):
            items.append({"item": a["name"], "quantity": max(1, _ceil(people * float(a["suggested_per_person"]))), "region": region})
    return {"bundles": bundles, "items": items}


def venues_markdown(repo, people: int = 0, date_text: str = "") -> str:
    """Where a campaign can be held, the vendors that serve each place and what we have in the warehouse there."""
    assets = {a["sku"]: a for a in repo.list_assets()}
    vendors = repo.list_vendors()
    depots = {}
    for d in repo.list_depot_free():
        if int(d["free"]) > 0:
            e = depots.setdefault(d["region"], {"name": d["depot_name"], "skus": set()})
            e["skus"].add(_item_label(assets, d["sku"]))
    names = sorted({_item_label(assets, k) for k in assets})
    head = (f"For **{people} people**" if people else "For your campaign") + (f" on **{date_text}**" if date_text else "")
    out = [f"### 📍 {head}: where can we deliver?", "",
           f"🧩 **What we have in place:** {', '.join(names)}.", "",
           "| 📍 Where | 🏭 Vendors based there | 🏢 Our warehouse and stock | 🚚 How it is served |", "|---|---|---|---|"]
    for v in repo.list_venues():
        local = ", ".join(x["vendor_name"] for x in vendors if x["home_region"] == v["region"]) or "-"
        dep = depots.get(v["region"])
        stock = f"{dep['name']}: {len(dep['skus'])} kinds of items" if dep else "none"
        out.append(f"| **{v['venue_name']}** | {local} | {stock} | {v.get('served_from') or ''} |")
    out += ["", "Vendors from other regions can ship in too. I compare them all for you."]
    return "\n".join(out)


def catalog_markdown(repo, deadline: date | None = None, focus: str = "campaign", today: date | None = None,
                     people: int = 0, region: str = "") -> str:
    """What we can offer: ready-made packs and single items, with our stock, the best vendor price for the date and
    ready-by dates, and (for a headcount) what we suggest."""
    today = today or date.today()
    window = (deadline - today).days if deadline else None
    rules = repo.list_date_pricing()
    assets = {a["sku"]: a for a in repo.list_assets()}
    offers = repo.list_vendor_offers_all()
    stock: dict = {}
    for d in repo.list_depot_free():
        if int(d["free"]) > 0:      # every warehouse: stock from another region can be moved in
            stock.setdefault(d["sku"], []).append((d["depot_name"].split(" ")[0], int(d["free"])))
    groups: dict = {}
    for sku in assets:
        groups.setdefault(_item_label(assets, sku), []).append(sku)

    def ready(o):
        return today + timedelta(days=int(o["lead_days"]) + int(o["delay_days"]))

    def price(o):
        f = price_factor(rules, o["vendor_id"], window)[0] if window is not None else 1.0
        return float(o["unit_price"]) * f

    sug = suggested_plan(repo, people, region)
    sug_item = {i["item"]: i["quantity"] for i in sug["items"]}
    info = {}
    for label, skus in groups.items():
        mine = [o for o in offers if o["sku"] == skus[0]]
        std = [o for o in mine if o["variant"] == "STANDARD"]
        eco = [o for o in mine if o["variant"] == "ECO"]
        best = min(std, key=lambda o: (price(o), int(o["lead_days"]))) if std else None
        fast = min(mine, key=lambda o: (int(o["lead_days"]) + int(o["delay_days"]), price(o))) if mine else None
        free = {}
        for k in skus:
            for place, n in stock.get(k, []):
                free[place] = free.get(place, 0) + n
        info[label] = {"skus": skus, "best": best, "fast": fast, "eco": min(eco, key=price) if eco else None,
                       "free": free, "free_total": sum(free.values())}

    packs = []
    for btype in repo.list_bundle_types():
        templates = repo.get_bundle_templates(btype)
        parts = []
        for t in templates:
            sku = next((k for k in assets if _pattern(t["sku_pattern"]).match(k)), None)
            if sku:
                parts.append((_item_label(assets, sku), int(t["qty_per_bundle"])))
        if not parts:
            continue
        cost = sum(q * price(info[l]["best"]) for l, q in parts if info[l]["best"])
        ready_by = max((ready(info[l]["best"]) for l, _ in parts if info[l]["best"]), default=None)
        in_stock = ", ".join(f"{l} {info[l]['free_total']}" for l, _ in parts if info[l]["free_total"])
        qty = next((b["quantity"] for b in sug["bundles"] if b["bundle_type"] == btype), 0)
        packs.append((templates[0]["description"], ", ".join(l for l, _ in parts), in_stock, cost, ready_by, qty))
    band = price_factor(rules, "*", window)[1] if window is not None else ""
    out = ["### 🛍️ What we can offer you",
           f"Prices are per unit" + (f" **for your date** ({band.lower()})" if band else "") + ". *Ready by* is when the vendor finishes; "
           f"shipping time comes on top. Today is **{day(today)}**" + (f" and your date is **{day(deadline)}**." if deadline else ".")
           + (f" 💡 *For {people} people* shows what we suggest." if people else ""), ""]
    sug_col = f" | 💡 For {people} people" if people else ""
    sug_sep = "|---" if people else ""
    pack_md = ["**🎁 Ready-made packs** (the easy way)", "",
               "| 🎁 Pack | 🧩 What is inside | ♻️ Part of it in our stock | 💰 From (per pack) | 📅 Ready by | 🚦" + sug_col + " |",
               "|---|---|---|---|---|---" + sug_sep + "|"]
    for n, inside, ins, pr, rb, qty in packs:
        pack_md.append(f"| **{n}** | {inside} | {ins or '-'} | {money(pr)} | {day(rb) if rb else '-'} | {_fits(rb, deadline) if rb else ''}"
                       + (f" | {qty or '-'}" if people else "") + " |")
    item_md = ["**🧩 Single items** (pick only what you need)", "",
               "| 🧩 Item | ♻️ In our stock | 💰 Best price | 🏭 Vendor | 📅 Ready by | 🚦 | ⚡ Faster option | 🌱 Eco" + sug_col + " |",
               "|---|---|---|---|---|---|---|---" + sug_sep + "|"]
    for label, v in info.items():
        b, f, e = v["best"], v["fast"], v["eco"]
        stock_txt = ", ".join(f"{n} {p}" for p, n in v["free"].items()) or "-"
        if b:
            rb = ready(b)
            faster = (f"{f['vendor_name']} {money(price(f))}, {day(ready(f))}" if f["vendor_id"] != b["vendor_id"]
                      and ready(f) < rb else "-")
            row = (money(price(b)), b["vendor_name"], day(rb), _fits(rb, deadline), faster, money(price(e)) if e else "-")
        else:
            row = ("-", "-", "-", "", "-", "-")
        item_md.append(f"| {label} | {stock_txt} | " + " | ".join(row) + (f" | {sug_item.get(label, '-')}" if people else "") + " |")
    first, second = (pack_md, item_md) if focus != "items" else (item_md, pack_md)
    out += first + [""] + second
    out += ["", "👉 **Pick what you want.** " + ("Say **use the suggested plan**, or " if people else "") +
            "say how many, for example *150 VIP guest welcome kits* or *5 venue display stands*. You can mix packs and items. "
            "I will show your shopping list and tell you what you may be missing."]
    return "\n".join(out)


def date_options_markdown(rows: list[dict], policies: list[dict]) -> str:
    """Could another date save money? One row per date: the best total, the difference and the spare time."""
    if len(rows) < 2:
        return ""
    base = next((r for r in rows if r["offset"] == 0), rows[0])["best"]["total_cost"]
    cheapest = min(rows, key=lambda r: r["best"]["total_cost"])
    out = ["### 📅 Could another date save you money?",
           "Vendors charge less when you order well ahead, and more for a rush. Same list, different date:", "",
           "| 📅 In hand by | 🏷️ Price band | 💰 Best total | 💸 Compared with your date | ⏳ Spare time | ✍️ OK from |", "|---|---|---|---|---|---|"]
    for r in rows:
        b = r["best"]
        diff = float(b["total_cost"]) - float(base)
        cmp_txt = "👈 **your date**" if r["offset"] == 0 else (f"**Save {money(-diff)}**" if diff < -0.005 else (f"Pay {money(diff)} more" if diff > 0.005 else "Same"))
        who = _band(policies, float(b["total_cost"]))[1] or "nobody ✅"
        spare_txt = spare(b["buffer_hours"]) if b["feasible"] else "🔴 too late for some items"
        out.append(f"| **{day(r['deadline'])}** | {r['band'] or '-'} | {money(b['total_cost'])} | {cmp_txt} | {spare_txt} | {who} |")
    if cheapest["offset"] != 0 and float(base) - float(cheapest["best"]["total_cost"]) > 0.005:
        out += ["", f"💡 The cheapest is **{day(cheapest['deadline'])}**: you would save **{money(float(base) - float(cheapest['best']['total_cost']))}**. "
                    f"Want that? Say *move it to {day(cheapest['deadline'])}*."]
    else:
        out += ["", "💡 Your date is a good one. Want to try another? Say *move it to* and a date."]
    return "\n".join(out)


_STEPS = {"mode": "🧭", "campaign": "🎪", "people": "👥", "date": "📅", "venue": "📍", "picks": "🛒"}


def intake_checklist(mode: str = "", campaign: str = "", people: int = 0, date_text: str = "", venue: str = "",
                     picks: str = "", venues_md: str = "", catalog_md: str = "", venue_unknown: str = "",
                     date_note: str = "", suggested: dict | None = None) -> str:
    """What we have so far (✅/⬜) and the ONE next question. Shows where we deliver once the date is known, and our
    offer once the place is known."""
    quick = (campaign or "").strip().lower() in ("quick purchase", "no campaign", "none")
    items_mode = (mode or "").lower().startswith("item")
    camp_mode = (mode or "").lower().startswith("camp")
    try:
        shown_date = day(date.fromisoformat(date_text)) if date_text else ""
    except ValueError:
        shown_date = date_text
    rows = []
    if camp_mode or not items_mode:
        rows.append(("🎪 Campaign name", campaign))
        rows.append(("👥 How many people", f"{people}" if people else ""))
    elif campaign and not quick:
        rows.append(("🎪 Campaign name", campaign))
    rows += [("📅 Date it must be in hand", shown_date), ("📍 Where", venue), ("🛒 What you pick", picks)]
    out = ["### 📝 Where we are", "", "| | What | Your answer |", "|---|---|---|"]
    out += [f"| {'✅' if v else '⬜'} | {k} | {v or ''} |" for k, v in rows]
    after, ask = "", ""
    if not (camp_mode or items_mode):
        ask = ("**Tell me about your campaign:** how many people, and on which date?\n\n"
               "Or tell me the items you need. Just talk to me, I will ask for anything that is missing.")
    elif camp_mode and not people:
        ask = "**How many people will come to your campaign?**"
    elif not date_text:
        ask = "**On which date must everything be in hand?** *(Please give day and month, and the year if it is not this year.)*"
        if date_note:
            ask = f"{date_note}\n\n" + ask
    elif not venue:
        ask = ("**Where is your campaign?** " + (f"*(I do not serve '{venue_unknown}' yet.)* " if venue_unknown else "")
               + "Pick a place from the table: " + ", ".join(f"**{n}**" for n in _venue_names(venues_md)) + ".")
        after = venues_md
    elif camp_mode and not campaign:
        ask = "**What would you like to call your campaign?**"
    elif not picks:
        ask = "**What would you like from our offer?**"
        after = catalog_md
    out += ["", "### 👉 Next question" if ask else "### ✅ All closed. Let me look at your list.", ask]
    if after:
        out += ["", after]
    return "\n".join(out).rstrip()


def _venue_names(venues_md: str) -> list[str]:
    import re
    return re.findall(r"^\| \*\*([^*|]+)\*\* \|", venues_md or "", flags=re.M)


def advice_markdown(items: list[dict]) -> str:
    if not items:
        return ""
    out = ["### 💡 Step 1b: Anything you may be missing?", "",
           "| | What | Why it matters | To add it, say |", "|---|---|---|---|"]
    out += [f"| {i['icon']} | **{i['what']}** | {i['why']} | *{i['say']}* |" for i in items]
    out += ["", "👉 Want any of these? **Tell me.** Happy as it is? Say **Looks good** and I will check our stock and the vendors."]
    return "\n".join(out)


# ---------------------------------------------------------------------------- the shopping list (BOM)
def _group_label(template: dict, asset: dict) -> str:
    name = asset["name"]
    if template["split_by"] == "SIZE":
        return name.rsplit(" ", 1)[0]
    if template["split_by"] == "PLUG":
        return name.split(",")[0]
    return name


def _pattern(sku_pattern: str):
    return re.compile("^" + re.escape(sku_pattern).replace(r"\{size\}", ".+").replace(r"\{plug\}", ".+") + "$")


def bom_markdown(repo, request_id: str) -> str:
    """The Bill of Materials: what goes into each bundle, how many in total, and where it goes."""
    lines = repo.get_requirement_lines(request_id)
    assets = {a["sku"]: a for a in repo.list_assets()}
    rows, total_items = [], 0
    for btype in dict.fromkeys(ln["bundle_type"] for ln in lines):
        blines = [ln for ln in lines if ln["bundle_type"] == btype]
        if btype == "SINGLE_ITEM":
            for sku in dict.fromkeys(ln["sku"] for ln in blines):
                hit = [ln for ln in blines if ln["sku"] == sku]
                qty = sum(ln["quantity"] for ln in hit)
                rows.append(("**Single items**" if not any(r[0] for r in rows if r[0].startswith("**Single")) else "",
                             assets[sku]["name"], "-", qty,
                             " · ".join(f"{k} {v}" for k, v in _sum_by(hit, lambda ln: ln["region"]))))
                total_items += qty
            continue
        templates = repo.get_bundle_templates(btype)
        first = True
        count = None
        for t in templates:
            rx = _pattern(t["sku_pattern"])
            hit = [ln for ln in blines if rx.match(ln["sku"])]
            if not hit:
                continue
            qty = sum(ln["quantity"] for ln in hit)
            if count is None:
                count = qty // max(int(t["qty_per_bundle"]), 1)
            if t["split_by"] == "SIZE":
                split = " · ".join(f"{k} {v}" for k, v in _sum_by(hit, lambda ln: ln["sku"].rsplit("-", 1)[1]))
            elif t["split_by"] == "PLUG":
                split = " · ".join(f"{k} {v}" for k, v in _sum_by(hit, lambda ln: ln["sku"][4:]))
            else:
                split = " · ".join(f"{k} {v}" for k, v in _sum_by(hit, lambda ln: ln["region"]))
            asset = assets[hit[0]["sku"]]
            rows.append((t["description"] if first else "", _group_label(t, asset), int(t["qty_per_bundle"]), qty, split))
            total_items += qty
            first = False
        if rows and count is not None:
            idx = next(i for i in range(len(rows) - 1, -1, -1) if rows[i][0])
            rows[idx] = (f"**{rows[idx][0]}** ({count} {_UNITS.get(btype, 'bundles')})",) + rows[idx][1:]
    out = ["### 🧾 Step 1: Your shopping list (Bill of Materials)",
           "Everything you need, worked out from what you told me.", "",
           "| 🎁 Bundle | 🧩 Item | Per bundle | Total needed | 🌍 Where it goes |", "|---|---|---|---|---|"]
    out += [f"| {b} | {i} | {p} | **{q:,}** | {s} |" for b, i, p, q, s in rows]
    out += ["", f"📦 **{total_items:,} items in total**, in {len(lines)} separate order lines (one per item and region)."]
    return "\n".join(out)


def _sum_by(lines, key):
    acc: dict = {}
    for ln in lines:
        acc[key(ln)] = acc.get(key(ln), 0) + ln["quantity"]
    return sorted(acc.items())


# ---------------------------------------------------------------------------- the three choices
def _how(s: dict) -> str:
    return s["summary"]


def decision_card(request_id: str, launch: dict, scenarios: list[dict], policies: list[dict], min_buffer=24,
                  single_item: bool = False) -> str:
    def who(total):
        p = next((p for p in policies if p["min_amount"] < total <= p["max_amount"]), None)
        if p is None and policies:
            p = policies[0]
        return "Nobody: automatic ✅" if p and not p["requires_human"] else (p["approver_role"] if p else "-")

    head = ["Everything we compare"] + [f"{ICON.get(s['option_code'], '')} **Option {i}: {s['option_name']}**"
                                       + (" ⭐ **Best choice**" if s["recommended"] else "")
                                       for i, s in enumerate(scenarios, start=1)]
    rows = [
        ("💰 Total price", [money(s["total_cost"]) for s in scenarios]),
        ("💸 Compared with Option 1", ["-" if i == 0 else (f"**Save {money(s['savings_usd'])}**" if s["savings_usd"] > 0
                                       else (f"Pay {money(-s['savings_usd'])} more" if s["savings_usd"] < 0 else "Same"))
                                       for i, s in enumerate(scenarios)]),
        ("📅 Everything arrives", [day(s["delivery_date"]) for s in scenarios]),
        ("⏳ Spare time before the deadline", [spare(s["buffer_hours"], min_buffer) for s in scenarios]),
        ("🌍 Pollution (CO₂)", [f"{s['carbon_kg']:,.0f} kg" for s in scenarios]),
        ("🛠️ How we get it", [_how(s) for s in scenarios]),
        ("✍️ Who has to say OK", [who(float(s["total_cost"])) for s in scenarios]),
    ]
    out = [f"### 🎯 Step 4: Your 3 choices for the {launch['launch_name']}",
           f"📅 Deadline (in our hands): **{day(launch['in_hand_by'])}**",
           f"🧾 Request number: `{request_id}`", "",
           "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join([label] + vals) + " |" for label, vals in rows]
    out += ["", "🚦 🟢 plenty of spare time · 🟡 tight · 🔴 too late", "",
            "👉 **Does this plan feel good?** Say **Choose option 2** (or 1, or 3). Want something different? Tell me what to change, "
            "for example *make it 200 kits*, *add 50 brochures* or *we need it a week earlier*."]
    if single_item:
        out += ["", "💡 **Tip:** buying selected items works fine. But if you plan the **whole campaign** with me, "
                "I can reuse more of our own stock, compare more vendors, and we have a stronger case for better rates."]
    return "\n".join(out)


# ---------------------------------------------------------------------------- stock and vendors
def _item_label(assets: dict, sku: str) -> str:
    a = assets[sku]
    if sku.startswith("HOODIE-"):
        return a["name"].rsplit(" ", 1)[0]
    if sku.startswith("PWR-"):
        return a["name"].split(",")[0]
    return a["name"]


def _best_plan(repo, request_id):
    scenarios = repo.get_scenarios(request_id)
    best = next((s for s in scenarios if s["recommended"]), scenarios[0] if scenarios else None)
    return best, (repo.get_scenario_lines(best["scenario_id"]) if best else [])


def stock_report(repo, request_id: str) -> str:
    """What we already own for the items on the list, and how much of it the best plan uses."""
    lines = repo.get_requirement_lines(request_id)
    needed = {ln["sku"] for ln in lines}
    assets = {a["sku"]: a for a in repo.list_assets()}
    best, plan = _best_plan(repo, request_id)
    depot = [d for d in repo.list_depot_free() if d["sku"] in needed and int(d["free"]) > 0]
    out = ["### ♻️ Step 2: What we already have in stock",
           "We always look in our own warehouses first, so we do not buy things twice.", ""]
    if not depot:
        return "\n".join(out + ["📭 We have **none of these items** in our warehouses, so everything will be ordered from vendors."])
    used_units: dict = {}
    for ln in plan:
        if ln["source_type"] == "DEPOT":
            k = (ln["source_id"], ln["sku"])
            used_units[k] = used_units.get(k, 0) + ln["quantity"]
    agg: dict = {}
    for d in depot:
        a = agg.setdefault((_item_label(assets, d["sku"]), d["depot_name"]), [0, 0])
        a[0] += int(d["free"])
        a[1] += used_units.get((d["depot_id"], d["sku"]), 0)
    out += ["| 🧩 Item | 🏢 Warehouse | Free units | Used in the best choice |", "|---|---|---|---|"]
    out += [f"| {item} | {wh} | {free} | {used} |" for (item, wh), (free, used) in agg.items()]
    return "\n".join(out)


def vendor_report(repo, request_id: str, today: date | None = None) -> str:
    """Which vendors were compared for each item, what we saw, when each can be ready, and who was picked."""
    today = today or date.today()
    req = repo.get_request(request_id)
    deadline = repo.get_launch(req["launch_id"])["in_hand_by"]
    lines = repo.get_requirement_lines(request_id)
    needed = {ln["sku"] for ln in lines}
    assets = {a["sku"]: a for a in repo.list_assets()}
    offers = [o for o in repo.list_vendor_offers_all() if o["sku"] in needed]
    _best, plan = _best_plan(repo, request_id)
    picked_vendor = {(ln["sku"], ln["source_id"]) for ln in plan if ln["source_type"] == "VENDOR"}
    groups: dict = {}
    for o in offers:
        groups.setdefault(_item_label(assets, o["sku"]), {}).setdefault(o["vendor_id"], []).append(o)

    def ready(o):
        d = today + timedelta(days=int(o["lead_days"]) + int(o["delay_days"]))
        return f"{day(d)}{' 🔴' if d > deadline else ''}"

    out = ["### 🏭 Step 3: What vendors can do, and by when",
           f"We looked at **{len({o['vendor_id'] for o in offers})} vendors** and **{len(offers)} price offers** "
           f"for the {len(groups)} different items. Shipping time to each region comes on top of *ready by*. "
           f"Deadline: **{day(deadline)}**.", "",
           "| 🧩 Item | 🏭 Vendor | 💰 Price each (normal / eco) | 📅 Ready by (normal / eco) | Result |",
           "|---|---|---|---|---|"]
    notes = []
    for item, vendors in groups.items():
        std_price = lambda v: min((float(x["unit_price"]) for x in vendors[v] if x["variant"] == "STANDARD"), default=1e9)
        cheapest = min(vendors, key=std_price)
        for vid, offs in vendors.items():
            std = next((x for x in offs if x["variant"] == "STANDARD"), None)
            eco = next((x for x in offs if x["variant"] == "ECO"), None)
            name = offs[0]["vendor_name"]
            delay = max(int(x["delay_days"]) for x in offs)
            price = " / ".join([money(std["unit_price"]) if std else "-", money(eco["unit_price"]) if eco else "-"])
            when = " / ".join([ready(std) if std else "-", ready(eco) if eco else "-"])
            used = any((o["sku"], vid) in picked_vendor for o in offs)
            result = ("✅ Chosen" if used else "➖ Not needed") + (f" · ⚠️ running {delay} days late" if delay else "")
            out.append(f"| {item} | {name} | {price} | {when} | {result} |")
            if used and vid != cheapest and len(vendors) > 1:
                notes.append(f"🧠 **{item}**: we used {name} for some orders even though {vendors[cheapest][0]['vendor_name']} is "
                             f"cheaper, because {name} is ready sooner and the cheaper one would not arrive in time.")
    return "\n".join(out + ([""] + notes if notes else []))


# ---------------------------------------------------------------------------- approval
def approval_ladder(policies: list[dict], amount=None) -> str:
    out = ["| 💵 Order value | ✍️ Who has to say OK | 👈 |", "|---|---|---|"]
    for p in policies:
        top = "no limit" if p["max_amount"] >= 1e9 else money(p["max_amount"])
        if p["min_amount"] <= 0:
            band = f"Up to {top}"
        elif p["max_amount"] >= 1e9:
            band = f"Over {money(p['min_amount'])}"
        else:
            band = f"{money(p['min_amount'])} to {top}"
        who = "Nobody, it is automatic ✅" if not p["requires_human"] else f"**{p['approver_role']}**"
        here = ""
        if amount is not None and p["min_amount"] < amount <= p["max_amount"] or (amount is not None and amount == 0 and p["min_amount"] <= 0):
            here = "👈 **this order**"
        out.append(f"| {band} | {who} | {here} |")
    return "\n".join(out)


def approval_rules_markdown(policies: list[dict]) -> str:
    return ("### ✍️ Who has to say OK?\nThe bigger the order, the more senior the person who must approve it.\n\n"
            + approval_ladder(policies)
            + "\n\n📧 The approver gets an email with **Approve** and **Reject**. Nothing is bought until they approve.")


def sign_off_markdown(scenario: dict, policies: list[dict], policy: dict, who: str, human: bool, request_id: str) -> str:
    total = float(scenario["total_cost"])
    out = [f"### ✍️ Step 5: Getting the OK",
           f"You chose **{scenario['option_name']}** for **{money(total)}**.", "",
           approval_ladder(policies, total), ""]
    if human:
        out += [f"📧 **An email with Approve and Reject buttons is on its way to {who}.**", "",
                "| Step | What happens | Status |", "|---|---|---|",
                "| 1 | Email sent to the approver | ✅ Done |",
                "| 2 | Approver clicks **Approve** or **Reject** | ⏳ Waiting |",
                "| 3 | You ask: *What is the status of " + request_id + "?* | ⏳ After step 2 |",
                "| 4 | We place all the orders | ⏳ After approval |", "",
                "🔒 The stock we planned to use is **held for you** while you wait. Nothing has been bought yet."]
    else:
        out += ["✅ This is within the automatic limit, so **no approval is needed**. I am placing the orders now."]
    return "\n".join(out)


# ---------------------------------------------------------------------------- after the orders
def _why(ln: dict, offers: list[dict], eco_plan: bool) -> str:
    alts = [o for o in offers if o["sku"] == ln["sku"] and o["vendor_id"] != ln["source_id"]
            and o["variant"] == ln.get("variant")]
    if eco_plan and ln.get("variant") == "ECO":
        return "🌱 eco-friendly option"
    cheaper_slow = [o for o in alts if float(o["unit_price"]) < float(ln["unit_price"])]
    if cheaper_slow:
        return "⚡ fastest way to make the date (a cheaper vendor was too slow)"
    return "💰 lowest price that arrives on time"


def bar(pct: float, width: int = 10) -> str:
    """A tiny picture of a percentage: 🟩🟩🟩⬜⬜..."""
    filled = max(0, min(width, round(width * pct / 100)))
    return "🟩" * filled + "⬜" * (width - filled)


def _band(policies: list[dict], amount: float) -> str:
    p = next((p for p in policies if p["min_amount"] < amount <= p["max_amount"]), policies[0])
    top = "no limit" if p["max_amount"] >= 1e9 else money(p["max_amount"])
    rng = f"up to {top}" if p["min_amount"] <= 0 else (f"over {money(p['min_amount'])}" if p["max_amount"] >= 1e9
                                                          else f"{money(p['min_amount'])} to {top}")
    return rng, (None if not p["requires_human"] else p["approver_role"])


def tldr(repo, request_id: str, scenarios: list[dict], policies: list[dict]) -> str:
    """One box at the top of the plan: the best choice in a few words."""
    best = next((s for s in scenarios if s["recommended"]), scenarios[0])
    idx = scenarios.index(best) + 1
    lines = repo.get_scenario_lines(best["scenario_id"])
    items = sum(ln["quantity"] for ln in lines)
    own = sum(ln["quantity"] for ln in lines if ln["source_type"] == "DEPOT")
    _rng, who = _band(policies, float(best["total_cost"]))
    save = (f" (save **{money(best['savings_usd'])}**)" if best["savings_usd"] > 0 else "")
    out = ["### 📌 In short",
           f"> 🎯 **Best choice: Option {idx}, {best['option_name']}**  ",
           f"> 💰 **{money(best['total_cost'])}**{save}  ",
           f"> 📅 Arrives **{day(best['delivery_date'])}**, {spare(best['buffer_hours'])[2:]}  ",
           f"> ✍️ OK from: **{who or 'nobody, it is automatic ✅'}**"]
    if own:
        out.append(f"\n♻️ Our own stock covers **{own:,} of {items:,} items** ({round(100 * own / items)}%) {bar(100 * own / items)}")
    return "\n".join(out)


def order_summary(repo, request_id: str, scenario: dict, decision: dict, update_sent_to: list, failed: list) -> str:
    lines = repo.get_scenario_lines(scenario["scenario_id"])
    offers = repo.list_vendor_offers_all()
    assets = {a["sku"]: a for a in repo.list_assets()}
    vendors = {v["vendor_id"]: v["vendor_name"] for v in repo.list_vendors()}
    depots = {d["depot_id"]: d["depot_name"] for d in repo.list_depot_free()}
    launch = repo.get_launch(repo.get_request(request_id)["launch_id"])
    policies = repo.list_policies()
    vlines = [ln for ln in lines if ln["source_type"] == "VENDOR"]
    dlines = [ln for ln in lines if ln["source_type"] == "DEPOT"]
    items = sum(ln["quantity"] for ln in lines)
    own = sum(ln["quantity"] for ln in dlines)
    eco_plan = scenario["option_code"] == "ECO"

    by_vendor: dict = {}
    for ln in vlines:
        v = by_vendor.setdefault(ln["source_id"], {"orders": 0, "units": 0, "amount": 0.0, "skus": set(), "why": set()})
        v["orders"] += 1
        v["units"] += ln["quantity"]
        v["amount"] += float(ln["line_total"])
        v["skus"].add(ln["sku"])
        v["why"].add(_why(ln, offers, eco_plan))

    def item_names(skus):
        names = []
        for sku in sorted(skus):
            n = _item_label(assets, sku)
            if n not in names:
                names.append(n)
        return ", ".join(names)

    total = float(scenario["total_cost"])
    rng, who = _band(policies, total)
    approval = (f"{money(total)} is {rng}, so **{decision['approver_role']}** approved it ✅"
                if who and decision.get("decided_by") != "autopilot" else f"{money(total)} is {rng}, so **no approval was needed** ✅")
    saved = (f"**{money(scenario['savings_usd'])}** saved" if scenario["savings_usd"] > 0
             else f"{money(-scenario['savings_usd'])} more" if scenario["savings_usd"] < 0 else "same")
    out = [f"## ✅ Done! All your orders are placed",
           f"> 🎪 **{launch['launch_name']}** · {scenario['option_name']} · `{request_id}`", "",
           "| 💵 Total | 💸 Compared with buying new | 📅 Arrives | 🧾 Orders | 🌍 Pollution |", "|---|---|---|---|---|",
           f"| **{money(total)}** | {saved} | **{day(scenario['delivery_date'])}** ({spare(scenario['buffer_hours'])[2:]}) | "
           f"{len(vlines)} purchase orders + {len(dlines)} warehouse moves | {scenario['carbon_kg']:,.0f} kg |",
           "", "### 📖 What we did, in 4 lines",
           f"1. 🎪 We planned **one whole campaign**: **{items:,} items**, {len(item_names({ln['sku'] for ln in lines}).split(', '))} different products, {len({ln['region'] for ln in lines})} {'region' if len({ln['region'] for ln in lines}) == 1 else 'regions'}.",
           f"2. 🏭 We compared vendors and bought from **{len(by_vendor)}** of them.",
           f"3. ♻️ We took **{own:,} items from our own stock** {bar(100 * own / items) if items else ''}, so we did not buy them twice.",
           f"4. ✍️ {approval}", "", "### 🏭 Who we bought from, and why", "",
           "| 🏭 Vendor | 🧩 What | 🧾 Orders | 📦 Items | 💵 Amount | 🧠 Why |", "|---|---|---|---|---|---|"]
    for vid, v in sorted(by_vendor.items(), key=lambda kv: -kv[1]["amount"]):
        out.append(f"| {vendors.get(vid, vid)} | {item_names(v['skus'])} | {v['orders']} | {v['units']:,} | "
                   f"{money(v['amount'])} | {' · '.join(sorted(v['why']))} |")
    if dlines:
        agg: dict = {}
        for ln in dlines:
            k = (depots.get(ln["source_id"], ln["source_id"]), _item_label(assets, ln["sku"]), ln["region"])
            agg[k] = agg.get(k, 0) + ln["quantity"]
        out += ["", "### ♻️ From our own warehouses", "", "| 🏢 From | 🧩 What | 📦 Items | 🌍 To |", "|---|---|---|---|"]
        out += [f"| {w} | {i} | {q} | {r} |" for (w, i, r), q in agg.items()]
    out += ["", f"❓ **Why so many orders?** One order per item per region: **{len(vlines)} + {len(dlines)}**, all placed together."]
    if update_sent_to:
        out += ["", f"📧 The launch team got an email: {', '.join(update_sent_to)}."]
    if failed:
        out += ["", f"⚠️ **{len(failed)} order lines failed** and were not retried. Ask me for the status."]
    return "\n".join(out)


def status_markdown(request_id: str, d: dict, done: int, total: int, note=None) -> str:
    icon = {"PENDING": "⏳", "APPROVED": "✅", "REJECTED": "❌", "FAILED": "⚠️"}.get(d["status"], "ℹ️")
    words = {"PENDING": f"Waiting for **{d['approver_role']}** to click Approve or Reject",
             "APPROVED": "Approved" if done < total else "Approved and all orders placed",
             "REJECTED": "Rejected. Nothing was bought and the held stock is free again",
             "FAILED": "The approval did not finish"}.get(d["status"], d["status"])
    out = [f"### {icon} Status of `{request_id}`", "", "| | |", "|---|---|",
           f"| Choice | {d['option_code']} |", f"| Order value | {money(d['amount'])} |",
           f"| Who decides | {d['approver_role']} |", f"| Status | {icon} {words} |",
           f"| Orders placed | {done} of {total} lines |"]
    if note:
        out.append(f"| Note | {note} |")
    return "\n".join(out)


# ---------------------------------------------------------------------------- boards
def board_markdown(requests: list[dict], depot: list[dict], assets: dict) -> str:
    light = {"GREEN": "🟢 Green", "AMBER": "🟡 Amber", "RED": "🔴 Red", "NO_DECISION": "⚪ Waiting for a choice",
             "PENDING": "⏳ Waiting for approval", "REJECTED": "❌ Rejected", "FAILED": "⚠️ Failed"}
    out = ["### 📊 Event status board", ""]
    if requests:
        out += ["| 🧾 Request | 🎪 Event | Choice | ✍️ Status | 📅 Arrives | 🚦 Readiness | 📦 Orders |", "|---|---|---|---|---|---|---|"]
        for r in requests:
            out.append(f"| `{r['request_id']}` | {r['launch_name']} | {r.get('chosen_option') or '-'} | "
                       f"{r.get('decision_status') or '-'} | {day(r['delivery_date']) if r.get('delivery_date') else '-'} | "
                       f"{light.get(r['readiness'], r['readiness'])} | {r['lines_executed']} of {r['lines_total']} |")
    else:
        out.append("No requests yet. Tell me about your campaign to start.")
    out += ["", "### ♻️ Stock we already own", "", "| 🏢 Warehouse | 🌍 Region | 🧩 Item | Free units |", "|---|---|---|---|"]
    out += [f"| {d['depot_name']} | {d['region']} | {assets.get(d['sku'], {}).get('name', d['sku'])} | {int(d['free'])} |"
            for d in depot if int(d["free"]) > 0]
    return "\n".join(out)


_ACTIONS = {"request_registered": "📝 Request created", "requirements_built": "🧾 Shopping list made",
            "scenarios_built": "🎯 3 choices worked out", "approval_requested": "📧 Approval email sent",
            "decision_autopilot": "✅ Approved automatically", "launch_approved": "✅ Approved by a person",
            "launch_rejected": "❌ Rejected by a person", "po_created": "🧾 Purchase order placed",
            "transfer_created": "♻️ Warehouse move placed", "launch_update_sent": "📧 Team told by email",
            "vendor_delay_reported": "⚠️ Vendor delay noted", "execution_blocked": "🛑 Blocked: no approval",
            "order_failed": "⚠️ An order failed", "approval_workflow_failed": "⚠️ Approval email failed"}


def audit_markdown(events: list[dict], limit: int = 40) -> str:
    counted: dict = {}
    order = []
    for e in events:
        key = (e["actor"], e["action"])
        if key not in counted:
            order.append(key)
        counted[key] = counted.get(key, 0) + 1
    out = ["### 🕵️ What happened, step by step", "", "| Who | What | How many times |", "|---|---|---|"]
    out += [f"| {a} | {_ACTIONS.get(act, act)} | {counted[(a, act)]} |" for a, act in order[:limit]]
    return "\n".join(out)
