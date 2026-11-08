"""Live check for SECTIONS and ENDPOINTS facets on both demo protocols."""

import asyncio
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.agents.parser.agent import extract_facet
from backend.agents.parser.logic import (
    ENDPOINTS_FACET,
    SECTIONS_FACET,
    collect_citations,
    count_verified,
)
from backend.clients.gemini import GeminiClient
from backend.clients.pdf_reader import read_pdf_pages
from backend.shared.config import load_settings
from backend.shared.messages import (
    EndpointKind,
    EndpointList,
    M11Heading,
    ProtocolSection,
    SectionMap,
)

logger = logging.getLogger(__name__)

FAME_D_PDF_PATH = Path("data/protocols/demo/NCT04828785_protocol.pdf")
CANAGLIFLOZIN_PDF_PATH = Path("data/protocols/demo/NCT03170518_protocol.pdf")
FAME_D_CRITERIA_PAGE = 22
CANAGLIFLOZIN_CRITERIA_PAGE = 47
FAME_D_PRIMARY_ENDPOINT_SUBSTRING = "a1c"
MIN_VERIFIED_SHARE = 0.9


async def _extract_sections_and_endpoints(
    pdf_path: Path, llm: GeminiClient
) -> tuple[SectionMap, EndpointList, float]:
    pages = read_pdf_pages(pdf_path)
    sections_outcome, endpoints_outcome = await asyncio.gather(
        extract_facet(SECTIONS_FACET, pages, llm),
        extract_facet(ENDPOINTS_FACET, pages, llm),
    )

    assert isinstance(sections_outcome.result, SectionMap), (
        f"SECTIONS facet failed on {pdf_path.name}: "
        f"{sections_outcome.warnings}"
    )
    assert isinstance(endpoints_outcome.result, EndpointList), (
        f"ENDPOINTS facet failed on {pdf_path.name}: "
        f"{endpoints_outcome.warnings}"
    )

    section_map = sections_outcome.result
    endpoint_list = endpoints_outcome.result
    all_citations = collect_citations(section_map) + collect_citations(
        endpoint_list
    )
    verified = count_verified(section_map) + count_verified(endpoint_list)
    verified_share = verified / len(all_citations) if all_citations else 0.0

    logger.info(
        "sections & endpoints extracted: pdf=%s sections=%d endpoints=%d "
        "verified=%d/%d (%.1f%%) warnings=%s",
        pdf_path.name,
        len(section_map.sections),
        len(endpoint_list.endpoints),
        verified,
        len(all_citations),
        verified_share * 100.0,
        sections_outcome.warnings + endpoints_outcome.warnings,
    )
    return section_map, endpoint_list, verified_share


def _has_trial_population_covering_page(
    sections: list[ProtocolSection], page_number: int
) -> bool:
    return any(
        section.heading == M11Heading.TRIAL_POPULATION
        and section.start_page <= page_number <= section.end_page
        for section in sections
    )


@pytest.mark.live
async def test_sections_and_endpoints_on_both_demo_protocols() -> None:
    for pdf_path in (FAME_D_PDF_PATH, CANAGLIFLOZIN_PDF_PATH):
        if not pdf_path.exists():
            pytest.skip(f"Demo protocol PDF not found at {pdf_path}")

    try:
        settings = load_settings()
    except ValidationError:
        pytest.skip("GEMINI_API_KEY or settings not configured in .env")

    api_key = settings.gemini_api_key.get_secret_value().strip()
    if not api_key:
        pytest.skip("GEMINI_API_KEY is empty in .env")

    llm = GeminiClient(api_key=api_key, model=settings.gemini_model)

    (
        fame_sections,
        fame_endpoints,
        fame_verified_share,
    ) = await _extract_sections_and_endpoints(FAME_D_PDF_PATH, llm)
    (
        cana_sections,
        _cana_endpoints,
        cana_verified_share,
    ) = await _extract_sections_and_endpoints(CANAGLIFLOZIN_PDF_PATH, llm)

    assert fame_verified_share >= MIN_VERIFIED_SHARE, (
        f"FAME-D verified share {fame_verified_share:.2%} < "
        f"{MIN_VERIFIED_SHARE:.0%}"
    )
    assert cana_verified_share >= MIN_VERIFIED_SHARE, (
        f"Canagliflozin verified share {cana_verified_share:.2%} < "
        f"{MIN_VERIFIED_SHARE:.0%}"
    )

    assert any(
        endpoint.kind == EndpointKind.PRIMARY
        and FAME_D_PRIMARY_ENDPOINT_SUBSTRING in endpoint.description.lower()
        for endpoint in fame_endpoints.endpoints
    ), f"FAME-D primary endpoints did not mention A1c: {fame_endpoints}"

    assert _has_trial_population_covering_page(
        fame_sections.sections, FAME_D_CRITERIA_PAGE
    ), (
        f"FAME-D had no TRIAL_POPULATION section covering page "
        f"{FAME_D_CRITERIA_PAGE}: {fame_sections.sections}"
    )

    assert _has_trial_population_covering_page(
        cana_sections.sections, CANAGLIFLOZIN_CRITERIA_PAGE
    ), (
        f"Canagliflozin had no TRIAL_POPULATION section covering page "
        f"{CANAGLIFLOZIN_CRITERIA_PAGE}: {cana_sections.sections}"
    )
