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
    is_fully_parsed,
    parse_protocol,
)
from backend.clients.gemini import (
    GeminiClient,
    JsonGenerator,
    LlmCallFailedError,
    ThinkingLevel,
)
from backend.shared.config import (
    DEFAULT_CHECK_MODEL,
    DEFAULT_GEMINI_MODEL,
    load_settings,
)
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
HASH_CHUNK_BYTES = 1024 * 1024  # stream large PDFs while hashing


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
    run: Callable[[], Awaitable[ModelT]],
    is_reusable: Callable[[ModelT], bool],
) -> ModelT:
    """Return the stored result for key, or run the job and store it.

    Only a reusable (complete) result is stored.
    """
    if store is not None:
        stored = await asyncio.to_thread(store.load, key)
        if stored is not None:
            return stored
    value = await run()
    if store is not None and is_reusable(value):
        await asyncio.to_thread(store.save, key, value)
    return value


def _is_complete_check(run: CheckRun) -> bool:
    return run.failed_llm_calls == 0


async def _run_check(
    document: ProtocolDocument, llm: JsonGenerator
) -> CheckRun:
    counting_llm = _FailureCountingLlm(llm)
    started_at = datetime.now(UTC)
    start = time.monotonic()
    report = await check_protocol(document, counting_llm)
    return CheckRun(
        report=report,
        started_at=started_at,
        duration_seconds=time.monotonic() - start,
        failed_llm_calls=counting_llm.failure_count,
    )


def _create_gemini_client(model: str | None = None) -> GeminiClient:
    """Build a Gemini client from settings, for model or the default one.

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
    return GeminiClient(api_key=api_key, model=model or settings.gemini_model)


def _document_content_key(document: ProtocolDocument) -> str:
    """Hash the parsed content, ignoring the per-upload ID and title."""
    content = document.model_copy(update={"protocol_id": "", "title": ""})
    return hashlib.sha256(content.model_dump_json().encode()).hexdigest()


def _hash_file_contents(pdf_path: Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    digest = hashlib.sha256()
    with pdf_path.open("rb") as pdf_file:
        while chunk := pdf_file.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _open_store[ModelT: BaseModel](
    store_directory: Path | None,
    name: str,
    model: type[ModelT],
    package_directory: Path,
    model_name: str,
) -> ResultStore[ModelT] | None:
    """A store versioned by the code that produces model, or None."""
    if store_directory is None:
        return None
    return ResultStore(
        store_directory / name,
        model,
        version=code_fingerprint(package_directory, model, model_name),
    )


class ProtocolPipeline:
    """Parses uploads and runs the completeness check, once per input.

    Each job runs once per content key and is shared by every request for
    it; a complete result is reused, and also kept on disk when
    store_directory is set. An incomplete one is returned but run again
    next time. The Gemini client is created when a job first needs it, so
    the server starts, and serves stored results, without an API key.
    """

    def __init__(
        self,
        llm: JsonGenerator | None = None,
        store_directory: Path | None = None,
        model_name: str = DEFAULT_GEMINI_MODEL,
        check_model_name: str = DEFAULT_CHECK_MODEL,
    ) -> None:
        # A given llm (tests) serves every job; otherwise the check gets
        # its own client on the faster check model.
        self._llm = llm
        self._check_llm = llm
        self._check_model_name = check_model_name
        self._parses = SharedTaskCache[ProtocolDocument](
            "parse", is_reusable=is_fully_parsed
        )
        self._checks = SharedTaskCache[CheckRun](
            "completeness", is_reusable=_is_complete_check
        )
        self._parse_store = _open_store(
            store_directory,
            "parse",
            ProtocolDocument,
            PARSER_PACKAGE_DIRECTORY,
            model_name,
        )
        self._check_store = _open_store(
            store_directory,
            "check",
            CheckRun,
            COMPLETENESS_PACKAGE_DIRECTORY,
            check_model_name,
        )

    def _client(self) -> JsonGenerator:
        if self._llm is None:
            self._llm = _create_gemini_client()
        return self._llm

    def _check_client(self) -> JsonGenerator:
        if self._check_llm is None:
            self._check_llm = _create_gemini_client(self._check_model_name)
        return self._check_llm

    def llm(self) -> JsonGenerator:
        """The Gemini client the pipeline's jobs share.

        Raises:
            AnalysisFailedError: Gemini is not configured.
        """
        return self._client()

    async def parse(self, pdf_path: Path) -> ProtocolDocument:
        """Parse a protocol PDF into a ProtocolDocument.

        PDFs are keyed by a hash of their bytes, so a renamed copy is
        still a hit (its ID and title come from the first parse). Each
        caller gets its own deep copy, so one review editing its document
        can't change another's.

        Raises:
            OSError: the file can't be read.
            UnreadablePdfError: the file is not a readable PDF.
            AnalysisFailedError: Gemini is not configured, or every parser
                facet failed.
        """
        key = await asyncio.to_thread(_hash_file_contents, pdf_path)
        try:
            document = await self._parses.get_or_run(
                key,
                lambda: _load_or_run(
                    self._parse_store,
                    key,
                    lambda: parse_protocol(pdf_path, self._client()),
                    is_fully_parsed,
                ),
            )
        except AllFacetsFailedError as error:
            raise AnalysisFailedError(str(error)) from error
        return document.model_copy(deep=True)

    def start_check(self, document: ProtocolDocument) -> None:
        """Start checking a parsed protocol in the background.

        The upload calls this so the check runs while the user reads the
        INGEST step; check() on the same content then joins this run.
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
        key = _document_content_key(document)
        return key, lambda: _load_or_run(
            self._check_store,
            key,
            lambda: _run_check(document, self._check_client()),
            _is_complete_check,
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
            check_model_name=settings.check_model,
        )
    return _pipeline


def set_protocol_pipeline(pipeline: ProtocolPipeline | None) -> None:
    """Replace the process-wide pipeline (tests); None resets it."""
    global _pipeline
    _pipeline = pipeline
