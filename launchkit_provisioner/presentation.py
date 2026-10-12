"""Everything the user reads: simple words, tables and icons, built from stored data (never typed in by the model).

Each function returns Markdown. The agents show it exactly as returned, so the numbers on screen are the numbers in
BigQuery, and the wording is the same every time.
"""
import re
from datetime import date, timedelta

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
        return f"🔴 {-days} days LATE"
    if hours < min_buffer:
        return "🟡 none (tight!)"
    return f"🟢 {days} days to spare"


# ---------------------------------------------------------------------------- the first hello
def capabilities_card() -> str:
    return """## 👋 Hi! I am your Event Procurement Assistant
> I plan and buy **everything for an event in one go**, and I only place orders when you are happy.

| | I can | In simple words |
|---|---|---|
| 🧾 | Make your **shopping list** | Exact items, amounts and places |
| 💡 | Spot **what you may be missing** | Spares, extra items, dates that are too tight |
| ♻️ | Check **our stock** | Use what we own before buying |
| 🏭 | Compare **vendors** | Prices, ready-by dates, late vendors |
| 🎯 | Give you **3 choices** | Price, arrival date, spare time |
| ✍️ | Get the **right OK** | Small = automatic · bigger = manager · biggest = CMO |
| 📦 | **Place all the orders** | At once, with a clear summary |
| 🛍️ | Buy **one single item** | A simple purchase order |

**💡 Best way to use me:** tell me the **whole event**. More in one plan means more stock to reuse, more vendors to compare, and a stronger case for better rates.

### 📝 Let's close on 3 things
| | What | Your answer |
|---|---|---|
| ⬜ | 🎪 The event | |
| ⬜ | 📅 The date it must be in hand | |
| ⬜ | 🎁 What you need and how many | |

### 👉 First question
**What is the event?** *(I know the Spring Product Launch Event, or tell me a new one.)*
"""


def intake_checklist(event: str = "", date_text: str = "", needs: str = "") -> str:
    """The three things to close on, with what we have so far and the one next question."""
    rows = [("🎪 The event", event), ("📅 The date it must be in hand", date_text), ("🎁 What you need and how many", needs)]
    out = ["### 📝 Let's close on 3 things", "", "| | What | Your answer |", "|---|---|---|"]
    out += [f"| {'✅' if v else '⬜'} | {k} | {v or ''} |" for k, v in rows]
    ask = ("**What is the event?** *(I know the Spring Product Launch Event, or tell me a new one.)*" if not event else
           "**By what date must everything be in hand?** *(Please give day, month and year.)*" if not date_text else
           "**What do you need, and how many?**\n\n💡 Tell me the **whole event**, for example *150 guest welcome kits, 10 venue display "
           "stands and 300 sales folders*. More in one plan means more stock to reuse, more vendors to compare and a stronger case "
           "for better rates. Just one thing? That works too: tell me the item, how many and the region (US, EMEA or APAC)."
           if not needs else "")
    out += ["", "### 👉 Next question" if ask else "### ✅ All 3 closed. Let me look at your list.", ask]
    return "\n".join(out).rstrip()


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
           f"📅 Deadline (in our hands): **{day(launch['in_hand_by'])}** · 📣 Press embargo: **{day(launch['embargo_date'])}**",
           f"🧾 Request number: `{request_id}`", "",
           "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join([label] + vals) + " |" for label, vals in rows]
    out += ["", "🚦 🟢 plenty of spare time · 🟡 tight · 🔴 too late", "",
            "👉 **Does this plan feel good?** Say **Choose option 2** (or 1, or 3). Want something different? Tell me what to change, "
            "for example *make it 200 kits*, *add 50 brochures* or *we need it a week earlier*."]
    if single_item:
        out += ["", "💡 **Tip:** this is a single-item purchase, and that works fine. But if you tell me your **whole event plan**, "
                "I can reuse more of our own stock, compare more vendors for you, and we have a stronger case for better rates."]
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
           f"1. 🎪 We planned **one whole event**: **{items:,} items**, {len(item_names({ln['sku'] for ln in lines}).split(', '))} different products, 3 regions.",
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
        out.append("No requests yet. Tell me about your event to start.")
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
