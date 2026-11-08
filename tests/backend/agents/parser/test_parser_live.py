"""Live parser checks on both demo protocols, parsed once per test session.

Each PDF goes through the real parse_protocol (all facets, real Gemini)
exactly once; every test below asserts on that shared result, so the live
suite costs one parse per PDF instead of one per test.
"""

import asyncio
import logging
from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.agents.parser.agent import parse_protocol
from backend.agents.parser.logic import citation_stats
from backend.shared.messages import (
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    EndpointKind,
    M11Heading,
    ProtocolDocument,
    ProtocolSection,
    TrialDesignFacts,
)
from tests.conftest import make_live_gemini_client

logger = logging.getLogger(__name__)

FAME_D_PDF_PATH = Path("data/protocols/demo/NCT04828785_protocol.pdf")
CANAGLIFLOZIN_PDF_PATH = Path("data/protocols/demo/NCT03170518_protocol.pdf")
DEMO_PDF_PATHS = (FAME_D_PDF_PATH, CANAGLIFLOZIN_PDF_PATH)
GOLDEN_PATH = Path("tests/fixtures/golden/NCT04828785_expected.json")

GOLDEN_MIN_ACCURACY = 0.8
MIN_VERIFIED_SHARE = 0.9
FAME_D_NCT_ID = "NCT04828785"
# FAME-D prints two titles: the trial title ("Food As MedicinE for
# Diabetes") and the grant/scientific title ("Food is Medicine: A
# Randomized Clinical Trial ... Type 2 Diabetes"). Either is correct.
FAME_D_TITLE_WORDS = ("medicine", "diabetes")
FAME_D_CRITERIA_PAGE = 22
CANAGLIFLOZIN_CRITERIA_PAGE = 47
FAME_D_PRIMARY_ENDPOINT_SUBSTRING = "a1c"
FAME_D_SAMPLE_SIZE = 200  # PDF page 52
FAME_D_DROPOUT_RATE = 0.10  # PDF page 52, "drop-out rate < 10%"
CANAGLIFLOZIN_ALPHA = 0.05  # PDF page 82
MIN_EXPECTED_VISITS = 2


class ExpectedCriterion(BaseModel):
    """Expected eligibility criterion entry in a golden fixture file."""

    kind: CriterionKind
    text_contains: str
    page_number: int


class GoldenExpectations(BaseModel):
    """Hand-checked expected design and eligibility facts for a protocol."""

    pdf_path: str
    design: dict[str, str | int | float | bool]
    criteria: list[ExpectedCriterion]


async def _parse_demo_protocols() -> dict[Path, ProtocolDocument]:
    llm = make_live_gemini_client()
    documents = await asyncio.gather(
        *(parse_protocol(pdf_path, llm) for pdf_path in DEMO_PDF_PATHS)
    )
    return dict(zip(DEMO_PDF_PATHS, documents, strict=True))


@pytest.fixture(scope="session")
def parsed_protocols() -> dict[Path, ProtocolDocument]:
    """Parse every demo PDF once per session (skips without key or PDFs)."""
    for pdf_path in DEMO_PDF_PATHS:
        if not pdf_path.exists():
            pytest.skip(f"Demo protocol PDF not found at {pdf_path}")
    documents = asyncio.run(_parse_demo_protocols())
    for document in documents.values():
        stats = citation_stats(document)
        logger.info(
            "live parse: protocol_id=%s criteria=%d sections=%d "
            "endpoints=%d visits=%d verified=%d/%d (%.1f%%) warnings=%s",
            document.protocol_id,
            len(document.eligibility_criteria or []),
            len(document.sections or []),
            len(document.endpoints or []),
            len(document.schedule or []),
            stats.verified,
            stats.total,
            stats.verified_share * 100.0,
            document.extraction_warnings,
        )
    return documents


def _design_fact_matches(
    facts: TrialDesignFacts,
    field_name: str,
    expected_value: str | float | bool,
) -> bool:
    cited: CitedValue[object] | None = getattr(facts, field_name, None)
    return cited is not None and cited.value == expected_value


def _criterion_matches(
    criteria: list[EligibilityCriterion], expected: ExpectedCriterion
) -> bool:
    needle = expected.text_contains.lower()
    return any(
        criterion.kind == expected.kind
        and needle in criterion.text.lower()
        and criterion.citation is not None
        and criterion.citation.page_number == expected.page_number
        for criterion in criteria
    )


def _has_trial_population_covering_page(
    sections: list[ProtocolSection], page_number: int
) -> bool:
    return any(
        section.heading == M11Heading.TRIAL_POPULATION
        and section.start_page <= page_number <= section.end_page
        for section in sections
    )


@pytest.mark.live
def test_every_facet_present_and_citations_verified(
    parsed_protocols: dict[Path, ProtocolDocument],
) -> None:
    for pdf_path, document in parsed_protocols.items():
        facet_fields = {
            "design": document.design,
            "eligibility_criteria": document.eligibility_criteria,
            "sections": document.sections,
            "endpoints": document.endpoints,
            "schedule": document.schedule,
            "statistics": document.statistics,
        }
        missing = [name for name, value in facet_fields.items() if not value]
        assert missing == [], f"{pdf_path.name}: facets missing: {missing}"
        share = citation_stats(document).verified_share
        assert share >= MIN_VERIFIED_SHARE, (
            f"{pdf_path.name}: verified share {share:.2%} < "
            f"{MIN_VERIFIED_SHARE:.0%}"
        )


@pytest.mark.live
def test_fame_d_golden_facts(
    parsed_protocols: dict[Path, ProtocolDocument],
) -> None:
    if not GOLDEN_PATH.exists():
        pytest.skip(f"Golden expectations file not found at {GOLDEN_PATH}")
    golden = GoldenExpectations.model_validate_json(
        GOLDEN_PATH.read_text(encoding="utf-8")
    )
    document = parsed_protocols[Path(golden.pdf_path)]
    assert document.design is not None
    criteria = document.eligibility_criteria or []

    matched_design = sum(
        1
        for field_name, expected in golden.design.items()
        if _design_fact_matches(document.design, field_name, expected)
    )
    matched_criteria = sum(
        1
        for expected in golden.criteria
        if _criterion_matches(criteria, expected)
    )
    total_facts = len(golden.design) + len(golden.criteria)
    accuracy = (matched_design + matched_criteria) / total_facts
    summary = (
        f"accuracy={accuracy:.2%} "
        f"({matched_design + matched_criteria}/{total_facts}: "
        f"design={matched_design}/{len(golden.design)}, "
        f"criteria={matched_criteria}/{len(golden.criteria)})"
    )
    logger.info("golden parser accuracy: %s", summary)
    assert accuracy >= GOLDEN_MIN_ACCURACY, summary


@pytest.mark.live
def test_fame_d_identity_and_verified_title(
    parsed_protocols: dict[Path, ProtocolDocument],
) -> None:
    document = parsed_protocols[FAME_D_PDF_PATH]

    assert document.protocol_id == FAME_D_NCT_ID
    assert all(
        word in document.title.lower() for word in FAME_D_TITLE_WORDS
    ), document.title
    assert document.design is not None
    assert document.design.official_title is not None
    assert document.design.official_title.citation.is_verified


@pytest.mark.live
def test_population_section_covers_eligibility_pages(
    parsed_protocols: dict[Path, ProtocolDocument],
) -> None:
    for pdf_path, criteria_page in (
        (FAME_D_PDF_PATH, FAME_D_CRITERIA_PAGE),
        (CANAGLIFLOZIN_PDF_PATH, CANAGLIFLOZIN_CRITERIA_PAGE),
    ):
        sections = parsed_protocols[pdf_path].sections or []
        assert _has_trial_population_covering_page(sections, criteria_page), (
            f"{pdf_path.name}: no TRIAL_POPULATION section covering page "
            f"{criteria_page}: {sections}"
        )


@pytest.mark.live
def test_fame_d_primary_endpoint_is_hba1c(
    parsed_protocols: dict[Path, ProtocolDocument],
) -> None:
    endpoints = parsed_protocols[FAME_D_PDF_PATH].endpoints or []

    assert any(
        endpoint.kind == EndpointKind.PRIMARY
        and FAME_D_PRIMARY_ENDPOINT_SUBSTRING in endpoint.description.lower()
        for endpoint in endpoints
    ), f"FAME-D primary endpoints did not mention A1c: {endpoints}"


@pytest.mark.live
def test_statistics_match_values_stated_in_pdfs(
    parsed_protocols: dict[Path, ProtocolDocument],
) -> None:
    fame = parsed_protocols[FAME_D_PDF_PATH].statistics
    cana = parsed_protocols[CANAGLIFLOZIN_PDF_PATH].statistics

    assert fame is not None and fame.sample_size is not None
    assert fame.sample_size.value == FAME_D_SAMPLE_SIZE, fame
    assert fame.dropout_rate is not None
    assert fame.dropout_rate.value == pytest.approx(FAME_D_DROPOUT_RATE), fame
    assert cana is not None and cana.alpha is not None
    assert cana.alpha.value == pytest.approx(CANAGLIFLOZIN_ALPHA), cana


@pytest.mark.live
def test_schedules_have_visits(
    parsed_protocols: dict[Path, ProtocolDocument],
) -> None:
    for pdf_path, document in parsed_protocols.items():
        visits = document.schedule or []
        assert len(visits) >= MIN_EXPECTED_VISITS, (
            f"{pdf_path.name}: fewer than {MIN_EXPECTED_VISITS} visits: "
            f"{visits}"
        )
