"""The two HTML emails: the approval request (with Approve and Reject buttons) and the orders-placed update.

Plain inline-styled HTML so it looks the same in Outlook, Gmail and Teams. All numbers come from the stored plan; the
approval link goes to the Application Integration approval page, where the approver confirms with one click.
"""
from datetime import timedelta
from html import escape
from urllib.parse import quote

from . import config, presentation

_FONT = "font-family:Arial,Helvetica,sans-serif"
_GRID = "padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top"


def approval_url(execution_id: str, task_number: int = 10) -> str:
    """The page where the approver chooses Approve or Reject for this run (the Approval task is task 10)."""
    return (f"https://console.cloud.google.com/integrations/integration/{quote(config.APP_INTEGRATION_NAME)}/locations/"
            f"{quote(config.APP_INTEGRATION_LOCATION)}/approval?project={quote(config.PROJECT)}"
            f"&execution_id={quote(str(execution_id))}&task_number={task_number}")


def _kv(rows) -> str:
    return ('<table style="width:100%;border-collapse:collapse;font-size:14px">' + "".join(
        f'<tr><td style="{_GRID};color:#6b7280;width:42%">{escape(k)}</td>'
        f'<td style="{_GRID};font-weight:600;color:#111827">{v}</td></tr>' for k, v in rows) + "</table>")


def _table(headers, rows, right=(), nowrap=()) -> str:
    head = "".join(f'<th style="{_GRID};background:#f3f4f6;color:#374151;font-size:12px;text-transform:uppercase;'
                   f'letter-spacing:.3px{";text-align:right" if i in right else ""}">{escape(h)}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td style="{_GRID};font-size:13px;color:#111827'
                                    f'{";text-align:right;white-space:nowrap" if i in right else (";white-space:nowrap" if i in nowrap else "")}">{c}</td>'
                                    for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<table style="width:100%;border-collapse:collapse;margin:6px 0 4px">{"<tr>" + head + "</tr>"}{body}</table>'


def _h(text) -> str:
    return f'<h3 style="margin:22px 0 6px;font-size:15px;color:#111827">{escape(text)}</h3>'


def _page(color, kicker, title, inner) -> str:
    return (f'<div style="{_FONT};max-width:640px;margin:0 auto;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden">'
            f'<div style="background:{color};color:#ffffff;padding:20px 24px"><div style="font-size:13px;opacity:.85">{escape(kicker)}</div>'
            f'<div style="font-size:22px;font-weight:700">{escape(title)}</div></div>'
            f'<div style="padding:20px 24px;color:#111827;font-size:15px;line-height:1.5">{inner}</div></div>')


def _button(href, label, bg) -> str:
    return (f'<a href="{escape(href, quote=True)}" style="display:inline-block;background:{bg};color:#ffffff;text-decoration:none;'
            f'font-weight:700;font-size:15px;padding:13px 30px;border-radius:8px;margin:4px 8px 4px 0">{label}</a>')


# ---------------------------------------------------------------------------- what is in the plan
def _bom_html(repo, request_id) -> str:
    rows, total, regions = presentation.bom_rows(repo, request_id)
    where = len(regions) > 1
    head = ["What", "How many", "What is inside"] + (["Where"] if where else [])
    data = [[f"<b>{escape(n)}</b>" if inside else escape(n), f"<b>{escape(q)}</b>", escape(inside or "-")]
            + ([escape(" · ".join(f"{k} {v}" for k, v in split))] if where else []) for n, q, inside, split in rows]
    return _h("Shopping list (Bill of Materials)") + _table(head, data) + f'<div style="font-size:13px;color:#6b7280">{total:,} items in total</div>'


def vendor_data(repo, scenario, lines):
    """(vendor rows [name, what, arrives, amount], warehouse rows [name, what]) as plain text, for the emails and the PDF."""
    assets = {a["sku"]: a for a in repo.list_assets()}
    vendors = {v["vendor_id"]: v["vendor_name"] for v in repo.list_vendors()}
    depots = {d["depot_id"]: d["depot_name"] for d in repo.list_depot_free()}
    longest = max((ln["days_to_deliver"] for ln in lines), default=0)
    by_v: dict = {}
    for ln in (x for x in lines if x["source_type"] == "VENDOR"):
        v = by_v.setdefault(ln["source_id"], {"items": {}, "amount": 0.0, "days": 0})
        label = presentation._item_label(assets, ln["sku"])
        v["items"][label] = v["items"].get(label, 0) + ln["quantity"]
        v["amount"] += float(ln["line_total"])
        v["days"] = max(v["days"], ln["days_to_deliver"])
    rows = []
    for vid, v in sorted(by_v.items(), key=lambda kv: -kv[1]["amount"]):
        arrives = scenario["delivery_date"] - timedelta(days=longest - v["days"])
        rows.append([vendors.get(vid, vid), ", ".join(f"{k} ({q:,})" for k, q in v["items"].items()),
                     presentation.day(arrives), presentation.money(v["amount"])])
    moves: dict = {}
    for ln in (x for x in lines if x["source_type"] == "DEPOT"):
        w = depots.get(ln["source_id"], ln["source_id"])
        label = presentation._item_label(assets, ln["sku"])
        moves.setdefault(w, {})[label] = moves.get(w, {}).get(label, 0) + ln["quantity"]
    return rows, [[w, ", ".join(f"{k} ({q:,})" for k, q in items.items())] for w, items in moves.items()]


def _vendors_html(repo, scenario, lines) -> str:
    rows, moves = vendor_data(repo, scenario, lines)
    out = _h("Vendors we are ordering from") + _table(["Vendor", "What", "Arrives", "Amount"],
                                                      [[f"<b>{escape(r[0])}</b>", escape(r[1]), r[2], r[3]] for r in rows],
                                                      right=(3,), nowrap=(2,))
    if moves:
        out += _h("Taken from our own warehouses") + _table(["Warehouse", "What"], [[f"<b>{escape(w)}</b>", escape(t)] for w, t in moves])
    return out


# ---------------------------------------------------------------------------- the approval request
def approval_waiting_email(repo, launch, scenario, request_id, approver_role) -> tuple[str, str]:
    """(subject, html): a plain notice, no buttons. The approval itself is done in the Gemini Enterprise app."""
    p = presentation
    subject = f"Approval waiting: {launch['launch_name']}"
    rows = [("Request", f"<b>{escape(request_id)}</b>"), ("Choice", escape(scenario["option_name"])),
            ("Total", p.money(scenario["total_cost"])), ("Everything arrives", p.day(scenario["delivery_date"])),
            ("Needs", escape(approver_role))]
    steps = ('<ol style="margin:12px 0 0 18px;padding:0"><li>Open <b>Gemini Enterprise</b> and choose <b>Workflow</b>.</li>'
             f'<li>Start <b>LaunchKit order approval</b> with the request number <b>{escape(request_id)}</b>.</li>'
             '<li>Open your <b>Inbox</b>, look under <b>Needs input</b>, and choose <b>Approve</b> or <b>Reject</b>.</li></ol>')
    inner = ('<p style="margin-top:0">An order is waiting for your approval. Nothing is bought until it is approved.</p>'
             + _kv(rows) + steps)
    return subject, _page("#4338ca", "APPROVAL WAITING", launch["launch_name"], inner)


def approval_email(repo, launch, scenario, lines, request_id, justification, approver_role, url, amount_rule) -> tuple[str, str]:
    """(subject, html). Two buttons, both open the approval page where the approver confirms with one click."""
    p = presentation
    saved = float(scenario["savings_usd"])
    saving = f"Saves {p.money(saved)} compared with buying everything new" if saved > 0 else (
        f"{p.money(-saved)} more than buying everything new" if saved < 0 else "Same as buying everything new")
    own = sum(x["quantity"] for x in lines if x["source_type"] == "DEPOT")
    bought = sum(x["quantity"] for x in lines if x["source_type"] == "VENDOR")
    subject = f"Approval needed: {launch['launch_name']}, {p.money(scenario['total_cost'])}"
    inner = (
        f'<p style="margin-top:0">Please approve or reject this order. <b>Nothing is bought until you approve.</b></p>'
        + _kv([("Campaign", escape(launch["launch_name"])), ("Choice", escape(scenario["option_name"])),
               ("Total", f"<span style='font-size:18px'>{p.money(scenario['total_cost'])}</span>"), ("Compared with buying new", escape(saving)),
               ("Everything arrives", f"{p.day(scenario['delivery_date'])} ({scenario['buffer_hours'] // 24} days before the "
                                      f"{p.day(launch['in_hand_by'])} deadline)"),
               ("How", f"{own:,} items from our own warehouses, {bought:,} items ordered from vendors"),
               ("Why this choice", escape(justification or "best balance of price and delivery time")),
               ("Who has to approve", f"{escape(approver_role)} ({escape(amount_rule)})"),
               ("Cost center", escape(str(launch.get("cost_center") or "n/a")))])
        + '<div style="margin:22px 0 6px">' + _button(url, "&#10003; Approve", "#16a34a") + _button(url, "&#10007; Reject", "#dc2626") + "</div>"
        + '<div style="font-size:12px;color:#6b7280">Both buttons open the approval page. Sign in with your Google account and choose '
          '<b>Approve</b> or <b>Reject</b> there. If you reject, nothing is bought and the held stock is released.</div>'
        + _bom_html(repo, request_id) + _vendors_html(repo, scenario, lines))
    return subject, _page("#4338ca", "APPROVAL NEEDED", launch["launch_name"], inner)


# ---------------------------------------------------------------------------- the orders-placed update
def orders_placed_email(repo, launch, scenario, pos, transfers, saved, request_id) -> tuple[str, str]:
    """(subject, html): the summary table, then the shopping list and the vendor details."""
    p = presentation
    subject = f"Orders placed for the {launch['launch_name']}"
    saving = (f"Saved {p.money(saved)} compared with buying everything new" if saved > 0
              else f"{p.money(-saved)} more than buying everything new" if saved < 0 else "Same as buying everything new")
    rows = [("Choice", escape(scenario["option_name"])), ("Purchase orders placed", str(len(pos))),
            ("Moves between our warehouses", str(len(transfers))), ("Total", p.money(scenario["total_cost"])),
            ("Price compared with buying new", escape(saving)),
            ("Everything arrives", f"{p.day(scenario['delivery_date'])} ({scenario['buffer_hours'] // 24} days before the "
                                   f"{p.day(launch['in_hand_by'])} deadline)"),
            ("CO2 (making + shipping)", f"{scenario['carbon_kg']:,.0f} kg")]
    lines = repo.get_scenario_lines(scenario["scenario_id"])
    names = {v["vendor_id"]: v["vendor_name"] for v in repo.list_vendors()}
    po_rows = [[f"<b>{escape(x['po_number'])}</b>", escape(names.get(x["vendor_id"], x["vendor_id"])), escape(x["sku"]),
                p.money(x["total_amount"])] for x in pos]
    inner = ('<p style="margin-top:0">Good news! All orders for this campaign have been placed. Here is the summary.</p>'
             + _kv(rows) + _bom_html(repo, request_id) + _vendors_html(repo, scenario, lines)
             + (_h("Purchase order numbers") + _table(["PO", "Vendor", "Items", "Amount"], po_rows, right=(3,)) if pos else ""))
    return subject, _page("#0f766e", "ORDERS PLACED", launch["launch_name"], inner)

