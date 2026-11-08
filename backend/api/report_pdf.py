"""Render a protocol's final review (fields and accepted changes) to PDF.

Pure: takes the review loaded from the database and returns PDF bytes.
"""

from datetime import datetime

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from backend.clients.protocol_db import (
    FieldChangeRecord,
    ProtocolReview,
    StoredField,
)

FONT_FAMILY = "Helvetica"
TITLE_FONT_SIZE_PT = 16
HEADING_FONT_SIZE_PT = 12
BODY_FONT_SIZE_PT = 9
LINE_HEIGHT_MM = 5
SECTION_GAP_MM = 4
# Field name, value and page, as fractions of the table width.
FIELD_COLUMN_WIDTHS = (45, 45, 10)
# Built-in PDF fonts only cover Latin-1; other characters print as "?".
PDF_TEXT_ENCODING = "latin-1"
# Common clinical symbols outside Latin-1, spelled out instead of "?".
ASCII_SUBSTITUTES = str.maketrans(
    {
        "\u2265": ">=",
        "\u2264": "<=",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "-",
    }
)


def _pdf_text(text: str) -> str:
    """Text the built-in fonts can draw, so rendering never fails."""
    readable = text.translate(ASCII_SUBSTITUTES)
    return readable.encode(PDF_TEXT_ENCODING, "replace").decode(
        PDF_TEXT_ENCODING
    )


def _timestamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M UTC")


def _value_with_unit(field: StoredField) -> str:
    return field.value if field.unit is None else f"{field.value} {field.unit}"


def _line(pdf: FPDF, text: str) -> None:
    pdf.multi_cell(
        0,
        LINE_HEIGHT_MM,
        _pdf_text(text),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )


def _heading(pdf: FPDF, text: str) -> None:
    pdf.ln(SECTION_GAP_MM)
    pdf.set_font(FONT_FAMILY, "B", HEADING_FONT_SIZE_PT)
    _line(pdf, text)
    pdf.set_font(FONT_FAMILY, size=BODY_FONT_SIZE_PT)


def _change_lines(change: FieldChangeRecord) -> list[str]:
    old_value = "(not set)" if change.old_value is None else change.old_value
    source = f"decision {change.decision_id}, option {change.option_id}"
    return [
        f"{change.field}: {old_value} -> {change.new_value}",
        f"    Why: {change.rationale}",
        f"    Accepted {_timestamp(change.changed_at)} ({source})",
    ]


def render_review_pdf(review: ProtocolReview, generated_at: datetime) -> bytes:
    """The final protocol review as a PDF document."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font(FONT_FAMILY, "B", TITLE_FONT_SIZE_PT)
    _line(pdf, review.protocol.title)
    pdf.set_font(FONT_FAMILY, size=BODY_FONT_SIZE_PT)
    _line(pdf, f"Protocol ID: {review.protocol.protocol_id}")
    _line(pdf, f"Pages: {review.protocol.page_count}")
    _line(pdf, f"Uploaded: {_timestamp(review.protocol.uploaded_at)}")
    _line(pdf, f"Report generated: {_timestamp(generated_at)}")

    _heading(pdf, f"Accepted changes ({len(review.changes)})")
    if not review.changes:
        _line(pdf, "No changes accepted yet.")
    for change in review.changes:
        for text in _change_lines(change):
            _line(pdf, text)

    _heading(pdf, f"Current protocol fields ({len(review.fields)})")
    if not review.fields:
        _line(pdf, "No fields stored.")
        return bytes(pdf.output())
    with pdf.table(
        col_widths=FIELD_COLUMN_WIDTHS, line_height=LINE_HEIGHT_MM
    ) as table:
        table.row(["Field", "Value", "Page"])
        for field in review.fields:
            page = "" if field.page is None else str(field.page)
            table.row(
                [
                    _pdf_text(field.field),
                    _pdf_text(_value_with_unit(field)),
                    page,
                ]
            )
    return bytes(pdf.output())
