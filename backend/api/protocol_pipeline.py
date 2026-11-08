"""One Gemini pipeline per process for the /demo endpoints.

Parsing a PDF and checking a protocol each take minutes, so both are done
once per distinct input and shared: a retried request, a parallel request
or a re-upload of the same PDF gets the stored result. State lives in
memory, and finished complete results also persist on disk when
store_directory is set.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict

import backend.agents.completeness
import backend.agents.parser
from backend.agents.completeness.agent import check_protocol
from backend.agents.parser.agent import (
    AllFacetsFailedError,
    CachedProtocolParser,
    has_failed_facets,
    hash_file_contents,
)
from backend.clients.gemini import (
    GeminiClient,
    JsonGenerator,
    LlmCallFailedError,
    ThinkingLevel,
)
from backend.shared.config import DEFAULT_GEMINI_MODEL, load_settings
from backend.shared.messages import ComplianceReport, ProtocolDocument
from backend.shared.result_store import ResultStore
from backend.shared.task_cache import JobFactory, SharedTaskCache

logger = logging.getLogger(__name__)

# Bump for result-changing edits outside the agent packages (e.g. shared/).
CACHE_FORMAT_VERSION = 1
PARSER_PACKAGE_DIRECTORY = Path(backend.agents.parser.__file__).parent
COMPLETENESS_PACKAGE_DIRECTORY = Path(
    backend.agents.completeness.__file__
).parent
FINGERPRINT_GLOBS: tuple[str, ...] = ("*.py", "*.toml")
EXCLUDED_DIRECTORY_PART = "__pycache__"
LOG_KEY_PREFIX_LENGTH = 12


class AnalysisFailedError(RuntimeError):
    """Raised when Gemini is not configured or no parser facet succeeded."""


class CheckRun(BaseModel):
    """A completeness report and when the check that produced it ran."""

    model_config = ConfigDict(frozen=True)

    report: ComplianceReport
    started_at: datetime
    # Monotonic, so a wall-clock adjustment mid-run cannot make it negative.
    duration_seconds: float
    # Gemini calls that failed; such a run is shown but never reused.
    failed_llm_calls: int = 0

    @property
    def is_complete(self) -> bool:
        """True when no Gemini call failed, so the run can be reused."""
        return self.failed_llm_calls == 0

    @property
    def completed_at(self) -> datetime:
        """Start time plus the measured duration."""
        return self.started_at + timedelta(seconds=self.duration_seconds)


def code_fingerprint(
    package_directory: Path,
    output_model: type[BaseModel],
    model_name: str,
) -> str:
    """Return a SHA-256 hex digest of schema, model name and package files."""
    digest = hashlib.sha256()
    digest.update(str(CACHE_FORMAT_VERSION).encode())
    digest.update(model_name.encode())
    schema_json = json.dumps(output_model.model_json_schema(), sort_keys=True)
    digest.update(schema_json.encode())
    files = sorted(
        (
            path
            for pattern in FINGERPRINT_GLOBS
            for path in package_directory.rglob(pattern)
            if EXCLUDED_DIRECTORY_PART not in path.parts and path.is_file()
        ),
        key=lambda path: path.relative_to(package_directory).as_posix(),
    )
    for path in files:
        relative = path.relative_to(package_directory).as_posix()
        digest.update(relative.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class _FailureCountingLlm:
    """JsonGenerator wrapper that counts LlmCallFailedError occurrences."""

    def __init__(self, inner: JsonGenerator) -> None:
        self._inner = inner
        self.failure_count: int = 0

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM,
    ) -> ModelT:
        """Delegate to the inner generator, counting failed calls."""
        try:
            return await self._inner.generate_json(
                prompt, response_model, thinking_level
            )
        except LlmCallFailedError:
            self.failure_count += 1
            raise


async def _load_or_run[ModelT: BaseModel](
    store: ResultStore[ModelT] | None,
    key: str,
    run: Callable[[], Awaitable[tuple[ModelT, bool]]],
) -> ModelT:
    """Load from store if present; otherwise run and save if complete."""
    if store is None:
        value, _ = await run()
        return value
    cached = await asyncio.to_thread(store.load, key)
    if cached is not None:
        logger.info(
            "result store hit: model=%s key=%s",
            type(cached).__name__,
            key[:LOG_KEY_PREFIX_LENGTH],
        )
        return cached
    value, is_complete = await run()
    if is_complete:
        await asyncio.to_thread(store.save, key, value)
    return value


async def _run_check(
    document: ProtocolDocument, llm: JsonGenerator
) -> tuple[CheckRun, bool]:
    wrapper = _FailureCountingLlm(llm)
    started_at = datetime.now(UTC)
    start = time.monotonic()
    report = await check_protocol(document, wrapper)
    run = CheckRun(
        report=report,
        started_at=started_at,
        duration_seconds=time.monotonic() - start,
        failed_llm_calls=wrapper.failure_count,
    )
    return run, run.is_complete


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


def _store_key(content_key: str, fingerprint: str) -> str:
    """Combine a content hash and a code fingerprint into a store key."""
    return hashlib.sha256(f"{content_key}:{fingerprint}".encode()).hexdigest()


class ProtocolPipeline:
    """Parses uploads and runs the completeness check, once per input.

    The Gemini client is created on first use, so the server starts
    without an API key and the first request reports the missing key.
    """

    def __init__(
        self,
        llm: JsonGenerator | None = None,
        store_directory: Path | None = None,
        model_name: str = DEFAULT_GEMINI_MODEL,
    ) -> None:
        self._llm = llm
        self._parser: CachedProtocolParser | None = None
        self._checks = SharedTaskCache[CheckRun](
            "completeness", is_reusable=lambda run: run.is_complete
        )
        if store_directory is not None:
            self._parse_store: ResultStore[ProtocolDocument] | None = (
                ResultStore(store_directory / "parse", ProtocolDocument)
            )
            self._check_store: ResultStore[CheckRun] | None = ResultStore(
                store_directory / "check", CheckRun
            )
            self._parse_fingerprint = code_fingerprint(
                PARSER_PACKAGE_DIRECTORY, ProtocolDocument, model_name
            )
            self._check_fingerprint = code_fingerprint(
                COMPLETENESS_PACKAGE_DIRECTORY, CheckRun, model_name
            )
        else:
            self._parse_store = None
            self._check_store = None
            self._parse_fingerprint = ""
            self._check_fingerprint = ""

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
        parser = self._parser
        key = ""
        if self._parse_store is not None:
            content_key = await asyncio.to_thread(hash_file_contents, pdf_path)
            key = _store_key(content_key, self._parse_fingerprint)

        async def run_parse() -> tuple[ProtocolDocument, bool]:
            document = await parser.parse(pdf_path)
            return document, not has_failed_facets(document)

        try:
            return await _load_or_run(self._parse_store, key, run_parse)
        except AllFacetsFailedError as error:
            raise AnalysisFailedError(str(error)) from error

    def start_check(self, document: ProtocolDocument) -> None:
        """Start checking a parsed protocol in the background.

        The upload calls this so the check runs while the user reads the
        INGEST step; check() on the same content then joins this run.

        Raises:
            AnalysisFailedError: Gemini is not configured.
        """
        self._checks.run_in_background(*self._check_job(document))

    async def check(self, document: ProtocolDocument) -> CheckRun:
        """Check a parsed protocol against every completeness rule.

        The same parsed content is checked once; later calls get the same
        report and timings, relabelled with this document's ID and title.

        Raises:
            AnalysisFailedError: Gemini is not configured.
            ValueError: the rule catalogue is invalid.
        """
        run = await self._checks.get_or_run(*self._check_job(document))
        report = run.report.model_copy(
            update={
                "protocol_id": document.protocol_id,
                "protocol_title": document.title,
            }
        )
        return run.model_copy(update={"report": report})

    def _check_job(
        self, document: ProtocolDocument
    ) -> tuple[str, JobFactory[CheckRun]]:
        """The cache key and job that check one document's content."""
        llm = self._client()
        content_key = _document_content_key(document)
        key = _store_key(content_key, self._check_fingerprint)
        return (
            key,
            lambda: _load_or_run(
                self._check_store, key, lambda: _run_check(document, llm)
            ),
        )


_pipeline: ProtocolPipeline | None = None


def get_protocol_pipeline() -> ProtocolPipeline:
    """Return the app pipeline, storing results in the configured cache dir."""
    global _pipeline
    if _pipeline is None:
        settings = load_settings()
        _pipeline = ProtocolPipeline(
            store_directory=settings.result_cache_dir,
            model_name=settings.gemini_model,
        )
    return _pipeline


def set_protocol_pipeline(pipeline: ProtocolPipeline | None) -> None:
    """Replace the process-wide pipeline (tests); None resets it."""
    global _pipeline
    _pipeline = pipeline
