"""Tests for the shared /demo pipeline: run-once checks and failures."""

from pathlib import Path

import pytest

from backend.agents.completeness.rules import load_rule_catalogue
from backend.api import protocol_pipeline
from backend.api.protocol_pipeline import AnalysisFailedError, ProtocolPipeline
from backend.shared.messages import PageText, ProtocolDocument
from tests.conftest import UnavailableLlm, make_pdf

PAGE_TEXT = (
    "A randomised, double-blind trial of a new oral drug compared with "
    "placebo in adults with type 2 diabetes on stable metformin."
)


def _document(protocol_id: str, title: str) -> ProtocolDocument:
    return ProtocolDocument(
        protocol_id=protocol_id,
        title=title,
        page_count=1,
        pages=[PageText(page_number=1, text=PAGE_TEXT)],
    )


async def test_same_content_is_checked_once_and_relabelled() -> None:
    llm = UnavailableLlm()
    pipeline = ProtocolPipeline(llm=llm)

    first = await pipeline.check(_document("proto-a", "First upload"))
    calls_after_first = llm.call_count
    second = await pipeline.check(_document("proto-b", "Second upload"))

    assert calls_after_first > 0
    assert llm.call_count == calls_after_first
    assert second.report.protocol_id == "proto-b"
    assert second.report.protocol_title == "Second upload"
    assert second.started_at == first.started_at
    assert second.report.findings == first.report.findings
    assert len(first.report.findings) == len(load_rule_catalogue().rules)


async def test_missing_api_key_fails_with_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoKeySettings:
        gemini_model = "gemini-4-argon"

        def require_gemini_api_key(self) -> str:
            raise ValueError("GEMINI_API_KEY is not set")

    monkeypatch.setattr(protocol_pipeline, "load_settings", _NoKeySettings)

    with pytest.raises(AnalysisFailedError, match="GEMINI_API_KEY"):
        await ProtocolPipeline().check(_document("proto-a", "Trial"))


async def test_parse_with_every_facet_failing_raises_analysis_failed(
    tmp_path: Path,
) -> None:
    pdf_path = make_pdf(tmp_path, [PAGE_TEXT])

    with pytest.raises(AnalysisFailedError):
        await ProtocolPipeline(llm=UnavailableLlm()).parse(pdf_path)
