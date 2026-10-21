"""The catalog as a PDF: where we deliver, the ready-made packs and the single items, with our stock, prices and ready-by dates.

The chat never shows the catalog as text (it is too long for Gemini Enterprise); this file is attached to the chat instead.
Pure Python (reportlab). Built from the stored data, so it always matches what the planner uses.
"""
import io
from datetime import date
from xml.sax.saxutils import escape

from . import presentation


def build_pdf(repo, deadline: date | None = None, place: str = "", today: date | None = None) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    p = presentation
    data = p.catalog_data(repo, deadline, today)
    base = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=base["BodyText"], fontSize=9, leading=12)
    cell = ParagraphStyle("c", parent=body, fontSize=8, leading=10)
    head = ParagraphStyle("h", parent=base["Heading2"], textColor=colors.HexColor("#111827"), spaceBefore=12, spaceAfter=4)
    title = ParagraphStyle("t", parent=base["Title"], alignment=0, fontSize=20, textColor=colors.HexColor("#4338ca"))

    def table(headers, rows, widths):
        rows_ = [[Paragraph(f"<b>{escape(h)}</b>", cell) for h in headers]] + [[Paragraph(escape(str(c)), cell) for c in r] for r in rows]
        t = Table(rows_, colWidths=[w * mm for w in widths], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    when = (f" Prices are per unit for your date, {p.day(deadline)}" + (f" ({data['band'].lower()})" if data["band"] else "") + "."
            if deadline else " Prices are per unit.")
    story = [Paragraph("Catalog: what we can offer", title),
             Paragraph(f"Today is {p.day(data['today'])}." + (f" Delivery to {escape(place)}." if place else "") + when
                       + " Ready by is when the vendor finishes; shipping time comes on top.", body)]
    story.append(Paragraph("Where we deliver", head))
    story.append(table(["Place", "Vendors based there", "Our warehouse and stock", "How it is served"], p.venue_rows(repo), [28, 75, 60, 84]))
    story.append(Paragraph("Ready-made packs", head))
    story.append(table(["Pack", "What is inside", "Part of it in our stock", "From (per pack)", "Ready by"],
                       [[x["name"], x["inside"], x["stock"] or "-", p.money(x["price"]), p.day(x["ready_by"]) if x["ready_by"] else "-"]
                        for x in data["packs"]], [45, 85, 55, 30, 32]))
    story.append(Paragraph("Single items", head))
    story.append(table(["Item", "In our stock", "Best price", "Vendor", "Ready by", "Faster option", "Eco price"],
                       [[x["name"], x["stock"] or "-", p.money(x["price"]) if x["price"] is not None else "-", x["vendor"] or "-",
                         p.day(x["ready_by"]) if x["ready_by"] else "-", x["faster"] or "-",
                         p.money(x["eco"]) if x["eco"] is not None else "-"] for x in data["items"]],
                       [48, 36, 22, 38, 24, 60, 22]))
    story += [Spacer(1, 8), Paragraph("How CO₂ is estimated", head), Paragraph(escape(p.CARBON_NOTE), body)]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                      title="Catalog").build(story)
    return buf.getvalue()
