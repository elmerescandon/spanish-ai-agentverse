"""Shared pytest fixtures and test doubles."""

import asyncio
from collections.abc import Generator, Sequence
from pathlib import Path

import pytest
from fpdf import FPDF
from pydantic import BaseModel
from vercel import blob

from backend.agents.protocol_comparison.agent import compare_registry_draft
from backend.agents.protocol_comparison.comparison import (
    Category,
    FlagRule,
)
from backend.agents.protocol_comparison.demo import (
    DEMO_DRAFT_NCT_ID,
    DEMO_PEER_QUERY,
    DEMO_PROTOCOL_DATE,
    DemoComparison,
    compare_demo_draft,
)
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.agents.protocol_comparison.peer_store import PeerStore
from backend.agents.protocol_comparison.review import (
    ReasoningStatus,
    SuggestionCard,
)
from backend.agents.protocol_comparison.suggestions import Suggestion
from backend.api.protocol_pipeline import (
    ProtocolPipeline,
    set_protocol_pipeline,
)
from backend.clients import document_store
from backend.clients.document_store import (
    MemoryDocumentStore,
    set_document_store,
)
from backend.clients.gemini import (
    GeminiClient,
    JsonGenerator,
    LlmCallFailedError,
    ThinkingLevel,
)
from backend.clients.pdf_reader import read_pdf_pages
from backend.clients.protocol_db import ProtocolDb, set_protocol_db
from backend.shared.config import load_settings
from backend.shared.messages import ProtocolDocument
from tests.fake_blob import FakeBlobBackend

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


# Values a test card offers for the HbA1c upper bound, one per peer group.
OFFERED_HBA1C_VALUES = {Category.ALL: 10.5, Category.RECENT: 10.0}


async def flagged_demo_comparison() -> DemoComparison:
    """Theo's real demo comparison plus one card for the HbA1c upper bound.

    The committed peer snapshot flags nothing for the demo draft, so this
    adds the card a flag would produce, letting tests accept a value.
    """
    comparison = await compare_demo_draft()
    result = next(
        r
        for r in comparison.results
        if r.dimension.dimension_id == DimensionId.HBA1C_UPPER_BOUND
    )
    card = SuggestionCard(
        comparison=result,
        suggestions=tuple(
            Suggestion(
                category=category,
                rule=FlagRule.PERCENTILE_RANGE,
                suggested_value=value,
                peer_ids=("NCT00000001", "NCT00000002"),
            )
            for category, value in OFFERED_HBA1C_VALUES.items()
        ),
        reasoning=None,
        reasoning_status=ReasoningStatus.SKIPPED,
    )
    return DemoComparison(
        draft_trial_id=comparison.draft_trial_id,
        protocol_date=comparison.protocol_date,
        results=comparison.results,
        cards=(card,),
    )


# Registry values far outside the demo peers, so Theo's own rules flag them.
OUT_OF_LINE_MINIMUM_AGE = "60 Years"
OUT_OF_LINE_MAXIMUM_AGE = "99 Years"
OUT_OF_LINE_ENROLLMENT = 5000


async def out_of_line_demo_comparison() -> DemoComparison:
    """Theo's real comparison of a demo draft with three values out of line.

    The draft's minimum age, maximum age and enrollment are pushed far
    from its peers, so his rules flag all three and suggest peer values;
    nothing about the flags or the suggestions is made up by the test.
    """
    store = PeerStore()
    peers = store.load_studies(DEMO_PEER_QUERY)
    assert peers is not None, "expected the committed demo peers"
    draft = store.load_study(DEMO_DRAFT_NCT_ID)
    section = draft.protocol_section
    assert section.eligibility_module is not None
    assert section.design_module is not None
    assert section.design_module.enrollment_info is not None
    eligibility = section.eligibility_module.model_copy(
        update={
            "minimum_age": OUT_OF_LINE_MINIMUM_AGE,
            "maximum_age": OUT_OF_LINE_MAXIMUM_AGE,
        }
    )
    enrollment = section.design_module.enrollment_info.model_copy(
        update={"count": OUT_OF_LINE_ENROLLMENT}
    )
    design = section.design_module.model_copy(
        update={"enrollment_info": enrollment}
    )
    draft = draft.model_copy(
        update={
            "protocol_section": section.model_copy(
                update={
                    "eligibility_module": eligibility,
                    "design_module": design,
                }
            )
        }
    )
    results, cards = await compare_registry_draft(
        draft, DEMO_PROTOCOL_DATE, peers, store
    )
    return DemoComparison(
        draft_trial_id=DEMO_DRAFT_NCT_ID,
        protocol_date=DEMO_PROTOCOL_DATE,
        results=results,
        cards=cards,
    )


@pytest.fixture
def fake_blob(monkeypatch: pytest.MonkeyPatch) -> FakeBlobBackend:
    """Replace vercel.blob with shared in-memory storage, no retry waits."""
    fake = FakeBlobBackend()
    monkeypatch.setattr(blob, "put_blob", fake.put_blob)
    monkeypatch.setattr(blob, "get_blob", fake.get_blob)
    monkeypatch.setattr(blob, "delete_blob", fake.delete_blob)
    monkeypatch.setattr(blob, "query_blobs", fake.query_blobs)
    monkeypatch.setattr(document_store, "RETRY_BACKOFF_SECONDS", 0.0)
    return fake


@pytest.fixture(autouse=True)
def _memory_document_store() -> Generator[None]:
    """Every test starts with an empty in-memory document store, never Blob."""
    set_document_store(MemoryDocumentStore())
    yield
    set_document_store(None)


@pytest.fixture(autouse=True)
def _temporary_protocol_db(tmp_path: Path) -> Generator[None]:
    """Every test gets its own empty database, never data/protocols.db."""
    set_protocol_db(ProtocolDb(tmp_path / "protocols.db"))
    yield
    set_protocol_db(None)
