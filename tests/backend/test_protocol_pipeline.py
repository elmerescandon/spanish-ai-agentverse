"""Tests for the shared /demo pipeline: run-once checks and failures."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.agents.completeness.rules import load_rule_catalogue
from backend.api import protocol_pipeline
from backend.api.protocol_pipeline import (
    AnalysisFailedError,
    ProtocolPipeline,
    code_fingerprint,
    get_protocol_pipeline,
    set_protocol_pipeline,
)
from backend.clients.gemini import LlmCallFailedError
from backend.shared.messages import PageText, ProtocolDocument
from tests.backend.agents.parser.scripted_responses import (
    demo_pdf,
    scripted_facet_responses,
)
from tests.conftest import (
    EmptyAnswersLlm,
    FakeJsonGenerator,
    UnavailableLlm,
    make_pdf,
)

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
    llm = EmptyAnswersLlm()
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


async def test_incomplete_check_reruns_on_the_next_request() -> None:
    llm = UnavailableLlm()
    pipeline = ProtocolPipeline(llm=llm)

    first = await pipeline.check(_document("proto-a", "Upload"))
    calls_after_first = llm.call_count
    await pipeline.check(_document("proto-a", "Upload"))

    assert first.failed_llm_calls == calls_after_first > 0
    assert llm.call_count == 2 * calls_after_first


async def test_parse_with_a_failed_facet_reruns_on_the_next_request(
    tmp_path: Path,
) -> None:
    pdf_path = demo_pdf(tmp_path)
    first_responses = scripted_facet_responses()
    first_responses[0] = LlmCallFailedError("down")
    llm = FakeJsonGenerator(first_responses + scripted_facet_responses())
    pipeline = ProtocolPipeline(llm=llm)

    first = await pipeline.parse(pdf_path)
    second = await pipeline.parse(pdf_path)

    assert first.extraction_warnings
    assert not second.extraction_warnings
    assert len(llm.prompts) == 2 * len(first_responses)


async def test_check_joins_the_run_started_after_upload() -> None:
    single_check_llm = UnavailableLlm()
    await ProtocolPipeline(llm=single_check_llm).check(
        _document("proto-ref", "Reference")
    )
    llm = UnavailableLlm()
    pipeline = ProtocolPipeline(llm=llm)

    pipeline.start_check(_document("proto-a", "Upload"))
    run = await pipeline.check(_document("proto-a", "Upload"))

    assert llm.call_count == single_check_llm.call_count > 0
    assert run.report.protocol_id == "proto-a"


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


async def test_check_duration_survives_the_wall_clock_going_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readings = iter(
        [
            datetime(2026, 11, 8, 7, 0, tzinfo=UTC),
            datetime(2026, 11, 8, 6, 5, tzinfo=UTC),
        ]
    )

    class _JumpingClock:
        @staticmethod
        def now(_tz: object) -> datetime:
            return next(readings)

    monkeypatch.setattr(protocol_pipeline, "datetime", _JumpingClock)

    run = await ProtocolPipeline(llm=UnavailableLlm()).check(
        _document("proto-a", "Trial")
    )

    assert run.duration_seconds >= 0
    assert run.completed_at >= run.started_at


async def test_results_survive_a_new_pipeline_on_the_same_directory(
    tmp_path: Path,
) -> None:
    pdf_path = demo_pdf(tmp_path)
    cache_dir = tmp_path / "cache"
    pipeline_a = ProtocolPipeline(
        llm=FakeJsonGenerator(scripted_facet_responses()),
        store_directory=cache_dir,
    )
    pipeline_a2 = ProtocolPipeline(
        llm=EmptyAnswersLlm(),
        store_directory=cache_dir,
    )

    parsed_a = await pipeline_a.parse(pdf_path)
    checked_a = await pipeline_a2.check(parsed_a)

    unavailable = UnavailableLlm()
    pipeline_b = ProtocolPipeline(
        llm=unavailable,
        store_directory=cache_dir,
    )
    parsed_b = await pipeline_b.parse(pdf_path)
    checked_b = await pipeline_b.check(parsed_b)

    assert parsed_b == parsed_a
    assert checked_b.report == checked_a.report
    assert checked_b.started_at == checked_a.started_at
    assert unavailable.call_count == 0


async def test_check_with_a_failed_gemini_call_is_not_saved(
    tmp_path: Path,
) -> None:
    pipeline = ProtocolPipeline(
        llm=UnavailableLlm(),
        store_directory=tmp_path,
    )

    run = await pipeline.check(_document("proto-a", "Trial"))

    assert len(run.report.findings) == len(load_rule_catalogue().rules)
    assert list((tmp_path / "check").glob("*.json")) == []


async def test_parse_with_a_failed_facet_is_not_saved(
    tmp_path: Path,
) -> None:
    pdf_path = demo_pdf(tmp_path)
    responses = scripted_facet_responses()
    responses[0] = LlmCallFailedError("down")
    pipeline = ProtocolPipeline(
        llm=FakeJsonGenerator(responses),
        store_directory=tmp_path,
    )

    document = await pipeline.parse(pdf_path)

    assert document.design is not None
    assert list((tmp_path / "parse").glob("*.json")) == []


def test_fingerprint_changes_when_a_package_file_changes(
    tmp_path: Path,
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    py_file = pkg / "a.py"
    toml_file = pkg / "rules.toml"
    py_file.write_bytes(b"x = 1\n")
    toml_file.write_bytes(b"[[rule]]\nid = 'R-01'\n")

    initial = code_fingerprint(pkg, ProtocolDocument, "gemini-4-argon")
    py_file.write_bytes(b"x = 2\n")
    after_edit = code_fingerprint(pkg, ProtocolDocument, "gemini-4-argon")

    pycache = pkg / "__pycache__"
    pycache.mkdir()
    (pycache / "x.pyc").write_bytes(b"\x00\x01\x02")
    after_pycache = code_fingerprint(pkg, ProtocolDocument, "gemini-4-argon")

    assert initial != after_edit
    assert after_pycache == after_edit


async def test_cached_check_is_relabelled_for_each_upload(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    pipeline_a = ProtocolPipeline(
        llm=EmptyAnswersLlm(),
        store_directory=cache_dir,
    )
    first = await pipeline_a.check(_document("proto-a", "First upload"))

    unavailable = UnavailableLlm()
    pipeline_b = ProtocolPipeline(
        llm=unavailable,
        store_directory=cache_dir,
    )
    second = await pipeline_b.check(_document("proto-b", "Second upload"))

    assert unavailable.call_count == 0
    assert second.report.protocol_id == "proto-b"
    assert second.report.protocol_title == "Second upload"
    assert second.started_at == first.started_at


async def test_app_pipeline_uses_the_configured_cache_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeSettings:
        gemini_model = "gemini-4-argon"
        result_cache_dir = tmp_path

        def require_gemini_api_key(self) -> str:
            return "unused"

    monkeypatch.setattr(protocol_pipeline, "load_settings", _FakeSettings)
    monkeypatch.setattr(
        protocol_pipeline,
        "_create_gemini_client",
        lambda: FakeJsonGenerator(scripted_facet_responses()),
    )
    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    set_protocol_pipeline(None)

    await get_protocol_pipeline().parse(demo_pdf(pdf_dir))

    assert len(list((tmp_path / "parse").glob("*.json"))) == 1
