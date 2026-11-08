"""Live end-to-end test of the parse workflow on a real protocol."""

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.agents.parser.agent import parse_protocol
from backend.agents.parser.logic import collect_citations, count_verified
from backend.clients.gemini import GeminiClient
from backend.shared.config import load_settings

logger = logging.getLogger(__name__)

FAME_D_PDF_PATH = Path("data/protocols/demo/NCT04828785_protocol.pdf")
EXPECTED_NCT_ID = "NCT04828785"
# FAME-D prints two titles: the trial title ("Food As MedicinE for
# Diabetes") and the grant/scientific title ("Food is Medicine: A
# Randomized Clinical Trial ... Type 2 Diabetes"). Either is correct.
EXPECTED_TITLE_WORDS = ("medicine", "diabetes")


@pytest.mark.live
async def test_parse_protocol_end_to_end_on_fame_d() -> None:
    if not FAME_D_PDF_PATH.exists():
        pytest.skip(f"Demo protocol PDF not found at {FAME_D_PDF_PATH}")

    try:
        settings = load_settings()
    except ValidationError:
        pytest.skip("GEMINI_API_KEY or settings not configured in .env")

    api_key = settings.gemini_api_key.get_secret_value().strip()
    if not api_key:
        pytest.skip("GEMINI_API_KEY is empty in .env")

    llm = GeminiClient(api_key=api_key, model=settings.gemini_model)
    document = await parse_protocol(FAME_D_PDF_PATH, llm)

    assert document.design is not None
    assert document.eligibility_criteria is not None
    assert document.sections is not None
    assert document.endpoints is not None
    assert document.protocol_id == EXPECTED_NCT_ID
    assert all(
        word in document.title.lower() for word in EXPECTED_TITLE_WORDS
    ), document.title
    assert document.design.official_title is not None
    assert document.design.official_title.citation.is_verified

    citations = collect_citations(document)
    verified = count_verified(document)
    verified_share = verified / len(citations) if citations else 0.0
    logger.info(
        "fame-d end-to-end parse: protocol_id=%s title=%r "
        "facets=4/4 criteria=%d sections=%d endpoints=%d "
        "verified=%d/%d (%.1f%%) warnings=%s",
        document.protocol_id,
        document.title,
        len(document.eligibility_criteria),
        len(document.sections),
        len(document.endpoints),
        verified,
        len(citations),
        verified_share * 100.0,
        document.extraction_warnings,
    )
