"""One Gemini pipeline per process for the /demo endpoints.

Parsing a PDF and checking a protocol each take minutes, so both are done
once per distinct input and shared: a retried request, a parallel request
or a re-upload of the same PDF gets the stored result. State lives in
memory, so the API must run as one long-lived server process.
"""

import dataclasses
import hashlib
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from backend.agents.completeness.agent import check_protocol
from backend.agents.parser.agent import (
    AllFacetsFailedError,
    CachedProtocolParser,
)
from backend.clients.gemini import GeminiClient, JsonGenerator
from backend.shared.config import load_settings
from backend.shared.messages import ComplianceReport, ProtocolDocument
from backend.shared.task_cache import SharedTaskCache

logger = logging.getLogger(__name__)


class AnalysisFailedError(RuntimeError):
    """Raised when Gemini is not configured or no parser facet succeeded."""


@dataclass(frozen=True)
class CheckRun:
    """A completeness report and when the check that produced it ran."""

    report: ComplianceReport
    started_at: datetime
    # Monotonic, so a wall-clock adjustment mid-run cannot make it negative.
    duration_seconds: float

    @property
    def completed_at(self) -> datetime:
        """Start time plus the measured duration."""
        return self.started_at + timedelta(seconds=self.duration_seconds)


async def _run_check(
    document: ProtocolDocument, llm: JsonGenerator
) -> CheckRun:
    started_at = datetime.now(UTC)
    start = time.monotonic()
    report = await check_protocol(document, llm)
    return CheckRun(report, started_at, time.monotonic() - start)


def _create_gemini_client() -> GeminiClient:
    """Build the Gemini client from settings.

    Raises:
        AnalysisFailedError: GEMINI_API_KEY is not set.
    """
    settings = load_settings()
    try:
        api_key = settings.require_gemini_api_key()
    except ValueError as error:
        raise AnalysisFailedError(
            f"Gemini is not configured: {error}"
        ) from error
    return GeminiClient(api_key=api_key, model=settings.gemini_model)


def _document_content_key(document: ProtocolDocument) -> str:
    """Hash the parsed content, ignoring the per-upload ID and title."""
    content = document.model_copy(update={"protocol_id": "", "title": ""})
    return hashlib.sha256(content.model_dump_json().encode()).hexdigest()


class ProtocolPipeline:
    """Parses uploads and runs the completeness check, once per input.

    The Gemini client is created on first use, so the server starts
    without an API key and the first request reports the missing key.
    """

    def __init__(self, llm: JsonGenerator | None = None) -> None:
        self._llm = llm
        self._parser: CachedProtocolParser | None = None
        self._checks = SharedTaskCache[CheckRun]("completeness")

    def _client(self) -> JsonGenerator:
        if self._llm is None:
            self._llm = _create_gemini_client()
        return self._llm

    async def parse(self, pdf_path: Path) -> ProtocolDocument:
        """Parse a protocol PDF into a ProtocolDocument.

        Raises:
            UnreadablePdfError: the file is not a readable PDF.
            AnalysisFailedError: Gemini is not configured, or every parser
                facet failed.
        """
        if self._parser is None:
            self._parser = CachedProtocolParser(self._client())
        try:
            return await self._parser.parse(pdf_path)
        except AllFacetsFailedError as error:
            raise AnalysisFailedError(str(error)) from error

    async def check(self, document: ProtocolDocument) -> CheckRun:
        """Check a parsed protocol against every completeness rule.

        The same parsed content is checked once; later calls get the same
        report and timings, relabelled with this document's ID and title.

        Raises:
            AnalysisFailedError: Gemini is not configured.
            ValueError: the rule catalogue is invalid.
        """
        llm = self._client()
        run = await self._checks.get_or_run(
            _document_content_key(document),
            lambda: _run_check(document, llm),
        )
        report = run.report.model_copy(
            update={
                "protocol_id": document.protocol_id,
                "protocol_title": document.title,
            }
        )
        return dataclasses.replace(run, report=report)


_pipeline: ProtocolPipeline | None = None


def get_protocol_pipeline() -> ProtocolPipeline:
    """Return the process-wide pipeline, creating it on first use."""
    global _pipeline
    if _pipeline is None:
        _pipeline = ProtocolPipeline()
    return _pipeline


def set_protocol_pipeline(pipeline: ProtocolPipeline | None) -> None:
    """Replace the process-wide pipeline (tests); None resets it."""
    global _pipeline
    _pipeline = pipeline
