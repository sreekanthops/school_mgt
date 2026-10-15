"""CSV and PDF builders shared by the export, receipt and invoice endpoints. Pure functions: bytes in, bytes out."""
import csv
import io
import re
from datetime import date
from typing import Iterable, Sequence
from xml.sax.saxutils import escape

from fastapi import Response
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

PDF_MAX_ROWS = 3000
CSV_MAX_ROWS = 50000
_FORMULA = ("=", "+", "-", "@", "\t", "\r")
_INK, _MUTED, _LINE, _HEAD = colors.HexColor("#1f2937"), colors.HexColor("#6b7280"), colors.HexColor("#d1d5db"), colors.HexColor("#eef0fb")


def safe_cell(v):
    """Text that starts with = + - @ would run as a formula when the CSV is opened in a spreadsheet."""
    if isinstance(v, str) and v.startswith(_FORMULA):
        return "'" + v
    return "" if v is None else v


def csv_bytes(headers: Sequence[str], rows: Iterable[Sequence]) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(headers)
    for n, r in enumerate(rows):
        if n >= CSV_MAX_ROWS:
            break
        w.writerow([safe_cell(c) for c in r])
    return ("\ufeff" + out.getvalue()).encode("utf-8")  # BOM so Excel reads accents/Telugu correctly


def file_name(stem: str, ext: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("_")[:80] + "." + ext


def download(data: bytes, name: str, media: str) -> Response:
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def csv_response(headers, rows, stem: str) -> Response:
    return download(csv_bytes(headers, rows), file_name(f"{stem}-{date.today():%Y%m%d}", "csv"), "text/csv; charset=utf-8")


def pdf_response(data: bytes, stem: str) -> Response:
    return download(data, file_name(stem, "pdf"), "application/pdf")


def rs(n) -> str:
    """Rupees for PDFs. The built-in PDF fonts have no rupee sign, so 'Rs.' is used."""
    return "Rs. " + f"{round(float(n or 0)):,}"


_ss = getSampleStyleSheet()
H1 = ParagraphStyle("h1", parent=_ss["Heading1"], fontSize=16, textColor=_INK, spaceAfter=2)
SUB = ParagraphStyle("sub", parent=_ss["Normal"], fontSize=9, textColor=_MUTED, spaceAfter=8)
CELL = ParagraphStyle("cell", parent=_ss["Normal"], fontSize=8, leading=10, textColor=_INK)
HEADC = ParagraphStyle("headc", parent=CELL, fontName="Helvetica-Bold")
BODY = ParagraphStyle("body", parent=_ss["Normal"], fontSize=10, leading=14, textColor=_INK)
H2 = ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=11, textColor=_INK, spaceBefore=10, spaceAfter=4)


def P(text, style=CELL) -> Paragraph:
    return Paragraph(escape("" if text is None else str(text)), style)


def _footer(school: str):
    def draw(c, doc):
        c.saveState()
        c.setFont("Helvetica", 7.5)
        c.setFillColor(_MUTED)
        c.drawString(doc.leftMargin, 10 * mm, f"{school} - generated {date.today():%d %b %Y}")
        c.drawRightString(doc.pagesize[0] - doc.rightMargin, 10 * mm, f"Page {doc.page}")
        c.restoreState()
    return draw


def build(story: list, school: str, wide: bool = False) -> bytes:
    buf = io.BytesIO()
    size = landscape(A4) if wide else A4
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                            bottomMargin=18 * mm, title=school, author=school)
    f = _footer(school)
    doc.build(story, onFirstPage=f, onLaterPages=f)
    return buf.getvalue()


def grid(data: list[list], col_widths=None, header: bool = True, align_right: Sequence[int] = ()) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, _LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), _HEAD))
    for c in align_right:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def table_pdf(school: str, title: str, subtitle: str, headers: Sequence[str], rows: Sequence[Sequence],
              align_right: Sequence[int] = ()) -> bytes:
    rows = list(rows)[:PDF_MAX_ROWS]
    data = [[P(h, HEADC) for h in headers]] + [[P(c) for c in r] for r in rows]
    story = [Paragraph(escape(school), H1), Paragraph(escape(f"{title} - {subtitle}" if subtitle else title), SUB),
             grid(data, align_right=align_right) if rows else Paragraph("No records.", BODY)]
    return build(story, school, wide=len(headers) > 6)


def kv_table(pairs: Sequence[tuple[str, str]], widths=(45 * mm, 110 * mm)) -> Table:
    t = Table([[P(k, HEADC), P(v)] for k, v in pairs], colWidths=widths)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, _LINE), ("BACKGROUND", (0, 0), (0, -1), _HEAD),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


__all__ = ["HEADC", "csv_response", "pdf_response", "table_pdf", "build", "grid", "kv_table", "P", "rs", "H1", "H2", "SUB", "BODY",
           "Spacer", "Paragraph", "escape", "colors", "mm"]
