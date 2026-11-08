"""Shared pytest fixtures and test doubles."""

import asyncio
from collections.abc import Generator, Sequence
from pathlib import Path

import pytest
from fpdf import FPDF
from pydantic import BaseModel

from backend.agents.protocol_comparison.demo import load_demo_peers
from backend.agents.protocol_comparison.peer_store import (
    PeerSource,
    PeerStore,
)
from backend.api import agent_runners
from backend.api.protocol_pipeline import (
    ProtocolPipeline,
    set_protocol_pipeline,
)
from backend.clients.clinicaltrials_gov import PeerSearchQuery, StudyRecord
from backend.clients.gemini import (
    GeminiClient,
    JsonGenerator,
    LlmCallFailedError,
    ThinkingLevel,
)
from backend.clients.pdf_reader import read_pdf_pages
from backend.shared.config import load_settings
from backend.shared.messages import ProtocolDocument

PDF_FONT_FAMILY = "Helvetica"
PDF_FONT_SIZE_PT = 10
PDF_LINE_HEIGHT_MM = 8
DEFAULT_PDF_FILENAME = "protocol_fixture.pdf"


def make_pdf(tmp_path: Path, pages: list[str]) -> Path:
    """Create a synthetic Latin-1 PDF in tmp_path with one entry per page."""
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    for page_text in pages:
        pdf.add_page()
        pdf.set_font(PDF_FONT_FAMILY, size=PDF_FONT_SIZE_PT)
        if page_text:
            pdf.multi_cell(w=0, h=PDF_LINE_HEIGHT_MM, text=page_text)
    output_path = tmp_path / DEFAULT_PDF_FILENAME
    pdf.output(str(output_path))
    return output_path


class FakeJsonGenerator:
    """In-memory JsonGenerator test double that replays scripted responses."""

    def __init__(self, responses: Sequence[BaseModel | Exception]) -> None:
        self._responses: list[BaseModel | Exception] = list(responses)
        self.prompts: list[str] = []
        self.thinking_levels: list[ThinkingLevel] = []

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM,
    ) -> ModelT:
        """Record the prompt and return or raise the next scripted item."""
        self.prompts.append(prompt)
        self.thinking_levels.append(thinking_level)
        if not self._responses:
            raise AssertionError(
                "FakeJsonGenerator ran out of scripted responses"
            )
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        assert isinstance(next_item, response_model)
        return next_item


def make_live_gemini_client() -> GeminiClient:
    """Return a real Gemini client from settings, or skip the live test."""
    settings = load_settings()
    try:
        api_key = settings.require_gemini_api_key()
    except ValueError:
        pytest.skip("GEMINI_API_KEY is not set in .env or the environment")
    return GeminiClient(api_key=api_key, model=settings.gemini_model)


class UnavailableLlm:
    """JsonGenerator that fails every call, as when Gemini is down."""

    def __init__(self) -> None:
        self.call_count = 0

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM,
    ) -> ModelT:
        """Count the call and fail it."""
        self.call_count += 1
        raise LlmCallFailedError("Gemini is unavailable in offline tests")


class EmptyAnswersLlm:
    """JsonGenerator that returns an empty default response_model()."""

    def __init__(self) -> None:
        self.call_count = 0

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM,
    ) -> ModelT:
        """Count the call and return response_model()."""
        self.call_count += 1
        return response_model()


class OfflineProtocolPipeline(ProtocolPipeline):
    """API-test pipeline: text-only parse, rule check without Gemini.

    By default every Gemini call fails, so the check keeps its flags at
    capped confidence and is rerun on each request; pass EmptyAnswersLlm
    for a complete check that repeat requests reuse.
    """

    def __init__(self, llm: JsonGenerator | None = None) -> None:
        super().__init__(llm=llm or UnavailableLlm())

    async def parse(self, pdf_path: Path) -> ProtocolDocument:
        """Read the PDF's text only (raises UnreadablePdfError like parse)."""
        pages = await asyncio.to_thread(read_pdf_pages, pdf_path)
        return ProtocolDocument(
            protocol_id="offline",
            title=pdf_path.stem,
            page_count=len(pages),
            pages=pages,
        )

    def start_check(self, document: ProtocolDocument) -> None:
        """Skip: TestClient runs each request on its own event loop, so a
        background check would be cancelled when the upload returns."""


@pytest.fixture(autouse=True)
def _offline_protocol_pipeline(
    request: pytest.FixtureRequest,
) -> Generator[None]:
    """Keep API tests off Gemini; live tests use the real pipeline."""
    if request.node.get_closest_marker("live") is None:
        set_protocol_pipeline(OfflineProtocolPipeline())
    yield
    set_protocol_pipeline(None)


async def search_committed_demo_peers(
    _query: PeerSearchQuery,
) -> list[StudyRecord]:
    """Offline stand-in for a registry search: the committed demo peers."""
    return load_demo_peers(PeerStore())


@pytest.fixture(autouse=True)
def _offline_peer_search(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep API tests off ClinicalTrials.gov; live tests search for real."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setattr(
            agent_runners,
            "_peer_source",
            PeerSource(PeerStore(), search=search_committed_demo_peers),
        )
