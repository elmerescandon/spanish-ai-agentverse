"""Runs the parser and completeness checker in the background per protocol.

A full analysis takes minutes (one Gemini call per parser facet), longer
than an HTTP request should wait, so routes start it and the UI polls.
State lives in memory: one long-running server process, not serverless.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from backend.agents.completeness.agent import check_protocol
from backend.agents.parser.agent import (
    AllFacetsFailedError,
    CachedProtocolParser,
)
from backend.api.schemas import AnalysisState
from backend.clients.gemini import GeminiClient, LlmCallFailedError
from backend.clients.pdf_reader import UnreadablePdfError
from backend.shared.config import load_settings
from backend.shared.messages import ComplianceReport

logger = logging.getLogger(__name__)

DEFAULT_UPLOAD_DIRECTORY = Path("data/uploads")  # gitignored
EXPECTED_ANALYSIS_ERRORS = (
    UnreadablePdfError,
    OSError,
    ValueError,
    AllFacetsFailedError,
    LlmCallFailedError,
)

type AnalyseFunction = Callable[[Path], Awaitable[ComplianceReport]]
type ReportListener = Callable[[str, ComplianceReport], None]
type FailureListener = Callable[[str, str], None]


class AnalysisInProgressError(RuntimeError):
    """Raised when a PDF is replaced while its analysis is still running."""


@dataclass
class AnalysisJob:
    """One protocol's analysis: its state, result or error, and its task."""

    state: AnalysisState
    report: ComplianceReport | None = None
    error: str | None = None
    task: asyncio.Task[None] | None = None


class GeminiPipeline:
    """Parse a PDF and check it, with one shared Gemini client and cache.

    The client is created on the first analysis, so the server starts
    without an API key; a missing key fails that analysis with a clear
    message instead.
    """

    def __init__(self) -> None:
        self._llm: GeminiClient | None = None
        self._parser: CachedProtocolParser | None = None

    async def __call__(self, pdf_path: Path) -> ComplianceReport:
        if self._llm is None or self._parser is None:
            settings = load_settings()
            self._llm = GeminiClient(
                api_key=settings.require_gemini_api_key(),
                model=settings.gemini_model,
            )
            self._parser = CachedProtocolParser(self._llm)
        document = await self._parser.parse(pdf_path)
        return await check_protocol(document, self._llm)


class ComplianceService:
    """Stores uploaded protocol PDFs and runs one analysis per protocol."""

    def __init__(
        self,
        analyse: AnalyseFunction,
        upload_directory: Path = DEFAULT_UPLOAD_DIRECTORY,
        on_report: ReportListener | None = None,
        on_failure: FailureListener | None = None,
    ) -> None:
        self._analyse = analyse
        self._upload_directory = upload_directory
        self._on_report = on_report
        self._on_failure = on_failure
        self._pdf_paths: dict[str, Path] = {}
        self._jobs: dict[str, AnalysisJob] = {}

    def store_pdf(self, protocol_id: str, content: bytes) -> Path:
        """Save a protocol's PDF; a new PDF discards its previous result.

        Raises:
            AnalysisInProgressError: the protocol is being analysed.
        """
        job = self._jobs.get(protocol_id)
        if job is not None and job.state == AnalysisState.RUNNING:
            raise AnalysisInProgressError(
                f"protocol '{protocol_id}' is being analysed; wait for it "
                "to finish before uploading a new PDF"
            )
        self._upload_directory.mkdir(parents=True, exist_ok=True)
        pdf_path = self._upload_directory / f"{protocol_id}.pdf"
        pdf_path.write_bytes(content)
        self._pdf_paths[protocol_id] = pdf_path
        self._jobs.pop(protocol_id, None)
        return pdf_path

    def has_pdf(self, protocol_id: str) -> bool:
        """Return True if a PDF was uploaded for the protocol."""
        return protocol_id in self._pdf_paths

    def get(self, protocol_id: str) -> AnalysisJob | None:
        """Return the protocol's analysis, or None if never started."""
        return self._jobs.get(protocol_id)

    def start(self, protocol_id: str) -> AnalysisJob:
        """Start the analysis unless it is running or already done.

        Safe to call twice: a running or finished analysis is returned as
        is; a failed one is retried.

        Raises:
            KeyError: no PDF was uploaded for the protocol.
        """
        pdf_path = self._pdf_paths.get(protocol_id)
        if pdf_path is None:
            raise KeyError(f"no PDF uploaded for protocol '{protocol_id}'")
        job = self._jobs.get(protocol_id)
        if job is not None and job.state != AnalysisState.FAILED:
            return job
        job = AnalysisJob(state=AnalysisState.RUNNING)
        self._jobs[protocol_id] = job
        job.task = asyncio.create_task(self._run(protocol_id, pdf_path, job))
        job.task.add_done_callback(
            lambda task: self._surface_unexpected_failure(
                protocol_id, job, task
            )
        )
        logger.info("compliance analysis started: protocol_id=%s", protocol_id)
        return job

    async def _run(
        self, protocol_id: str, pdf_path: Path, job: AnalysisJob
    ) -> None:
        try:
            report = await self._analyse(pdf_path)
        except EXPECTED_ANALYSIS_ERRORS as error:
            self._fail(protocol_id, job, str(error), error)
            return
        job.report = report
        job.state = AnalysisState.DONE
        logger.info(
            "compliance analysis done: protocol_id=%s score=%.1f",
            protocol_id,
            report.before.score,
        )
        if self._on_report is not None:
            self._on_report(protocol_id, report)

    def _surface_unexpected_failure(
        self, protocol_id: str, job: AnalysisJob, task: asyncio.Task[None]
    ) -> None:
        """Mark the job failed if its task died of an unexpected error.

        Without this, a bug would leave the job "running" forever and the
        UI would poll endlessly.
        """
        if job.state != AnalysisState.RUNNING:
            return
        error = (
            asyncio.CancelledError("analysis was cancelled")
            if task.cancelled()
            else task.exception()
        )
        if error is not None:
            self._fail(
                protocol_id,
                job,
                f"internal error: {type(error).__name__}: {error}",
                error,
            )

    def _fail(
        self,
        protocol_id: str,
        job: AnalysisJob,
        message: str,
        error: BaseException,
    ) -> None:
        logger.error(
            "compliance analysis failed: protocol_id=%s error=%s",
            protocol_id,
            message,
            exc_info=error,
        )
        job.state = AnalysisState.FAILED
        job.error = message
        if self._on_failure is not None:
            self._on_failure(protocol_id, message)
