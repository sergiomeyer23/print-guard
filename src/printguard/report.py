from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from printguard.fsutil import private_mkdir

HEADER = ["ID", "SKU", "Description", "Qty", "Location", "Due"]
MIN_PDF_BYTES = 200
EOF_SCAN_BYTES = 1024


def render_pdf(rows: list[tuple], path: Path, queried_at: datetime) -> Path:
    private_mkdir(path.parent)
    tmp = path.with_suffix(".pdf.part")
    doc = SimpleDocTemplate(
        str(tmp), pagesize=A4, topMargin=28 * mm, bottomMargin=15 * mm, title="Pending shipments"
    )
    stamp = queried_at.strftime("%Y-%m-%d %H:%M:%S")
    story = [_summary(len(rows)), Spacer(1, 6 * mm), _table(rows)]
    doc.build(story, onFirstPage=_header(stamp), onLaterPages=_header(stamp))
    os.replace(tmp, path)
    return path


def pdf_problem(path: Path) -> str | None:
    if not path.exists():
        return "file does not exist"
    data = path.read_bytes()
    if len(data) < MIN_PDF_BYTES:
        return f"file is only {len(data)} bytes"
    if not data.startswith(b"%PDF-"):
        return "missing PDF header"
    if b"%%EOF" not in data[-EOF_SCAN_BYTES:]:
        return "missing end-of-file marker, the file looks truncated"
    return None


def _summary(count: int) -> Paragraph:
    text = f"{count} pending shipment(s) due today or earlier."
    return Paragraph(text, getSampleStyleSheet()["Normal"])


def _table(rows: list[tuple]) -> Table:
    data = [HEADER, *[[str(cell) for cell in row] for row in rows]] if rows else [HEADER]
    table = Table(
        data, repeatRows=1, colWidths=[14 * mm, 22 * mm, 62 * mm, 14 * mm, 28 * mm, 26 * mm]
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ALIGN", (3, 0), (3, -1), "RIGHT"),
            ]
        )
    )
    return table


def _header(stamp: str):
    def draw(canvas, doc):
        width, height = A4
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(20 * mm, height - 18 * mm, "Pending shipments")
        canvas.setFont("Helvetica", 9)
        canvas.drawRightString(width - 20 * mm, height - 18 * mm, f"Queried at {stamp}")
        canvas.drawRightString(width - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw
