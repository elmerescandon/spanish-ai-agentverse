"""Tests for the background compliance analysis service."""

import asyncio
from pathlib import Path

import pytest

from backend.api.compliance_service import (
    AnalysisInProgressError,
    ComplianceService,
)
from backend.api.schemas import AnalysisState
from backend.clients.pdf_reader import UnreadablePdfError
from backend.shared.messages import ComplianceReport
from tests.backend.test_compliance import _build_illustrative_example_report

PROTOCOL_ID = "proto-test"
PDF_BYTES = b"%PDF-1.7 fake protocol bytes"


class _FakeAnalysis:
    """Analysis stand-in that counts runs and can fail or block."""

    def __init__(self, failure: BaseException | None = None) -> None:
        self.runs = 0
        self.failure = failure
        self.release = asyncio.Event()
        self.release.set()

    async def __call__(self, pdf_path: Path) -> ComplianceReport:
        self.runs += 1
        await self.release.wait()
        if self.failure is not None:
            raise self.failure
        return _build_illustrative_example_report()


def _service(
    tmp_path: Path, analysis: _FakeAnalysis
) -> tuple[ComplianceService, list[str]]:
    finished: list[str] = []
    service = ComplianceService(
        analyse=analysis,
        upload_directory=tmp_path,
        on_report=lambda protocol_id, report: finished.append(protocol_id),
    )
    service.store_pdf(PROTOCOL_ID, PDF_BYTES)
    return service, finished


async def _settle(service: ComplianceService) -> None:
    job = service.get(PROTOCOL_ID)
    assert job is not None and job.task is not None
    await asyncio.wait({job.task})


def test_stored_pdf_is_written_to_the_upload_directory(tmp_path: Path) -> None:
    service, _ = _service(tmp_path, _FakeAnalysis())

    assert (tmp_path / f"{PROTOCOL_ID}.pdf").read_bytes() == PDF_BYTES
    assert service.has_pdf(PROTOCOL_ID)


async def test_finished_analysis_stores_report_and_notifies(
    tmp_path: Path,
) -> None:
    service, finished = _service(tmp_path, _FakeAnalysis())

    service.start(PROTOCOL_ID)
    await _settle(service)

    job = service.get(PROTOCOL_ID)
    assert job is not None
    assert job.state == AnalysisState.DONE
    assert job.report is not None
    assert finished == [PROTOCOL_ID]


async def test_starting_twice_while_running_runs_once(tmp_path: Path) -> None:
    analysis = _FakeAnalysis()
    analysis.release.clear()
    service, _ = _service(tmp_path, analysis)

    first = service.start(PROTOCOL_ID)
    second = service.start(PROTOCOL_ID)
    analysis.release.set()
    await _settle(service)

    assert first is second
    assert analysis.runs == 1


async def test_starting_after_done_reuses_the_report(tmp_path: Path) -> None:
    analysis = _FakeAnalysis()
    service, _ = _service(tmp_path, analysis)
    service.start(PROTOCOL_ID)
    await _settle(service)

    job = service.start(PROTOCOL_ID)

    assert job.state == AnalysisState.DONE
    assert analysis.runs == 1


async def test_known_failure_is_reported_and_can_be_retried(
    tmp_path: Path,
) -> None:
    analysis = _FakeAnalysis(UnreadablePdfError("scanned PDF"))
    service, finished = _service(tmp_path, analysis)

    service.start(PROTOCOL_ID)
    await _settle(service)
    failed = service.get(PROTOCOL_ID)
    analysis.failure = None
    service.start(PROTOCOL_ID)
    await _settle(service)

    assert failed is not None
    assert failed.state == AnalysisState.FAILED
    assert failed.error is not None and "scanned PDF" in failed.error
    assert service.get(PROTOCOL_ID).state == AnalysisState.DONE  # type: ignore[union-attr]
    assert analysis.runs == 2
    assert finished == [PROTOCOL_ID]


async def test_unexpected_error_never_leaves_the_job_running(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path, _FakeAnalysis(RuntimeError("bug")))

    service.start(PROTOCOL_ID)
    await _settle(service)

    job = service.get(PROTOCOL_ID)
    assert job is not None
    assert job.state == AnalysisState.FAILED
    assert job.error is not None and "RuntimeError" in job.error


def test_starting_without_a_pdf_raises(tmp_path: Path) -> None:
    service = ComplianceService(
        analyse=_FakeAnalysis(), upload_directory=tmp_path
    )

    with pytest.raises(KeyError, match="no-pdf"):
        service.start("no-pdf")


async def test_new_pdf_is_refused_while_analysis_runs(tmp_path: Path) -> None:
    analysis = _FakeAnalysis()
    analysis.release.clear()
    service, _ = _service(tmp_path, analysis)
    service.start(PROTOCOL_ID)

    with pytest.raises(AnalysisInProgressError, match=PROTOCOL_ID):
        service.store_pdf(PROTOCOL_ID, PDF_BYTES)

    analysis.release.set()
    await _settle(service)
