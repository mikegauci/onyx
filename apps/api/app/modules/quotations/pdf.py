"""PDF preview of one quote version, rendered only from stored snapshots and computed totals.

Nothing here calculates money: every figure comes from ``QuoteDetail`` (computed by
``pricing.py``). All text from the tenant's data is escaped before it reaches ReportLab's
paragraph markup. A version that is not approved carries a "DRAFT - not a valid offer"
watermark on every page.
"""

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.modules.quotations.models import VersionStatus
from app.modules.quotations.schemas import QuoteDetail

WATERMARK = "DRAFT - not a valid offer"


def _euro(amount: str) -> str:
    return f"€{amount}"


def _p(value: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(value).replace("\n", "<br/>"), style)


def render_quote_pdf(detail: QuoteDetail, *, organization: str, timezone: str) -> bytes:
    draft = detail.version_status is not VersionStatus.APPROVED and detail.approved_at is None
    styles = getSampleStyleSheet()
    body, small = styles["BodyText"], ParagraphStyle("small", parent=styles["BodyText"], fontSize=8)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{detail.number} v{detail.version}",
        author=organization,
        invariant=1,  # reproducible output (no random ids or creation time)
    )
    try:
        zone = ZoneInfo(timezone)
    except (KeyError, ValueError):
        zone = ZoneInfo("UTC")

    def when(value: datetime | None) -> str:
        return value.astimezone(zone).strftime("%d %b %Y") if value else "—"

    story: list[object] = [
        _p(organization, styles["Title"]),
        _p(f"Quotation {detail.number} · version {detail.version}", styles["Heading2"]),
        _p(detail.title, body),
        Spacer(1, 4 * mm),
        _p(f"For: {detail.contact.label}", body),
    ]
    if detail.customer:
        story.append(_p(detail.customer.label, body))
    story += [
        _p(
            f"Approved: {when(detail.approved_at)}"
            + (f" · Valid until: {detail.valid_until:%d %b %Y}" if detail.valid_until else ""),
            body,
        ),
        _p(
            f"Prices {'include' if detail.prices_include_vat else 'exclude'} VAT · EUR",
            small,
        ),
        Spacer(1, 6 * mm),
    ]

    rows: list[list[object]] = [["SKU", "Description", "Qty", "Unit", "Disc.", "VAT", "Total"]]
    for line in detail.lines:
        rows.append(
            [
                _p(line.sku or "—", small),
                _p(line.description, small),
                str(line.quantity),
                _euro(line.unit_price.amount),
                f"{line.discount_percent}%" if line.discount_percent else "",
                f"{line.vat_code} {line.vat_percent}%",
                _euro(line.gross.amount if detail.prices_include_vat else line.net.amount),
            ]
        )
    table = Table(rows, colWidths=[24 * mm, 60 * mm, 12 * mm, 20 * mm, 14 * mm, 22 * mm, 22 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story += [table, Spacer(1, 6 * mm)]

    t = detail.totals
    summary: list[list[str]] = [["List total", _euro(t.list_total.amount)]]
    if t.discount.minor:
        summary.append(["Discount", f"-{_euro(t.discount.amount)}"])
    summary.append(["Net", _euro(t.net.amount)])
    for group in t.vat_breakdown:
        summary.append([f"VAT {group.code} {group.rate_percent}%", _euro(group.vat.amount)])
    summary.append(["Total (EUR)", _euro(t.gross.amount)])
    totals = Table(summary, colWidths=[40 * mm, 30 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(totals)
    if detail.notes:
        story += [Spacer(1, 6 * mm), _p(detail.notes, body)]

    def decorate(canvas: Canvas, _doc: object) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 10 * mm, f"{detail.number} v{detail.version}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        if draft:
            canvas.setFont("Helvetica-Bold", 36)
            canvas.setFillColor(colors.Color(0.85, 0.2, 0.2, alpha=0.25))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, WATERMARK)
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buffer.getvalue()
