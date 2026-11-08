"""Tests for rendering the final review to PDF."""

import io
from datetime import UTC, datetime

from pypdf import PdfReader

from backend.api.report_pdf import render_review_pdf
from backend.clients.protocol_db import (
    ProtocolRecord,
    ProtocolReview,
    StoredField,
)

GENERATED_AT = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def _review(fields: list[StoredField]) -> ProtocolReview:
    return ProtocolReview(
        protocol=ProtocolRecord(
            protocol_id="proto-test",
            title="T2D trial — draft",
            page_count=3,
            uploaded_at=GENERATED_AT,
        ),
        fields=fields,
        changes=[],
    )


def _text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_report_spells_out_clinical_symbols_beyond_latin1() -> None:
    field = StoredField("eligibility.egfr_min", "≥45", "mL/min", 31)

    text = _text(render_review_pdf(_review([field]), GENERATED_AT))

    assert ">=45 mL/min" in text
    assert "T2D trial - draft" in text


def test_report_renders_a_protocol_with_no_fields_or_changes() -> None:
    text = _text(render_review_pdf(_review([]), GENERATED_AT))

    assert "No changes accepted yet." in text
    assert "No fields stored." in text
