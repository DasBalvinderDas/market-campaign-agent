"""The order pack: one formatted PDF with the shopping list (Bill of Materials), the vendors and the warehouse moves.

Pure Python (reportlab), no other service. Built from the stored plan, so it always matches the emails and the chat.
"""
import io
from xml.sax.saxutils import escape

from . import emails, presentation


def _plain(text) -> str:
    return escape(str(text))


def build_pdf(repo, request_id: str, decision: dict | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    decision = decision or repo.get_decision_for_request(request_id)
    if not decision:
        raise ValueError("no plan has been chosen for this request yet")
    scenario = repo.get_scenario(decision["scenario_id"])
    launch = repo.get_launch(repo.get_request(request_id)["launch_id"])
    lines = repo.get_scenario_lines(decision["scenario_id"])
    p = presentation
    base = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=base["BodyText"], fontSize=9, leading=12)
    cell = ParagraphStyle("c", parent=body, fontSize=8.5, leading=11)
    head = ParagraphStyle("h", parent=base["Heading2"], textColor=colors.HexColor("#111827"), spaceBefore=14, spaceAfter=4)
    title = ParagraphStyle("t", parent=base["Title"], alignment=0, fontSize=20, textColor=colors.HexColor("#4338ca"))

    def table(headers, rows, widths, right=()):
        data = [[Paragraph(f"<b>{_plain(h)}</b>", cell) for h in headers]] + [[Paragraph(_plain(c), cell) for c in r] for r in rows]
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        for i in right:
            style.append(("ALIGN", (i, 0), (i, -1), "RIGHT"))
        t.setStyle(TableStyle(style))
        return t

    saved = float(scenario["savings_usd"])
    saving = (f"Saves {p.money(saved)} compared with buying everything new" if saved > 0 else
              f"{p.money(-saved)} more than buying everything new" if saved < 0 else "Same as buying everything new")
    story = [Paragraph(f"Order pack: {_plain(launch['launch_name'])}", title),
             Paragraph(f"Request {_plain(request_id)} · {_plain(scenario['option_name'])}", body), Spacer(1, 6)]
    story.append(table(["", ""], [
        ["Total", p.money(scenario["total_cost"])], ["Compared with buying new", saving],
        ["Everything arrives", f"{p.day(scenario['delivery_date'])} ({scenario['buffer_hours'] // 24} days before the "
                               f"{p.day(launch['in_hand_by'])} deadline)"],
        ["Approval", f"{decision.get('approver_role') or '-'} · {decision.get('status', '')}"],
        ["Cost center", str(launch.get("cost_center") or "n/a")]], [55, 115]))
    rows, total, regions = p.bom_rows(repo, request_id)
    where = len(regions) > 1
    story.append(Paragraph("Shopping list (Bill of Materials)", head))
    story.append(table(["What", "How many", "What is inside"] + (["Where"] if where else []),
                       [[n, q, inside or "-"] + ([" · ".join(f"{k} {v}" for k, v in split)] if where else [])
                        for n, q, inside, split in rows],
                       [45, 22, 60, 43] if where else [55, 25, 90]))
    story.append(Paragraph(f"{total:,} items in total", body))
    vrows, moves = emails.vendor_data(repo, scenario, lines)
    story.append(Paragraph("Vendors we are ordering from", head))
    story.append(table(["Vendor", "What", "Arrives", "Amount"], vrows, [38, 80, 28, 24], right=(3,)))
    if moves:
        story.append(Paragraph("Taken from our own warehouses", head))
        story.append(table(["Warehouse", "What"], moves, [45, 125]))
    pos = repo.list_pos(request_id)
    if pos:
        names = {v["vendor_id"]: v["vendor_name"] for v in repo.list_vendors()}
        story.append(Paragraph("Purchase orders", head))
        story.append(table(["PO", "Vendor", "Amount"], [[x["po_number"], names.get(x["vendor_id"], x["vendor_id"]),
                                                          p.money(x["total_amount"])] for x in pos], [50, 80, 40], right=(2,)))
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                      title=f"Order pack {request_id}").build(story)
    return buf.getvalue()
