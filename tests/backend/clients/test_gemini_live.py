"""Live integration test for GeminiClient against the demo protocol PDF."""

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader

from backend.clients.gemini import GeminiClient, ThinkingLevel
from backend.shared.config import load_settings

DEMO_PROTOCOL_PDF_PATH = Path("data/protocols/demo/NCT04828785_protocol.pdf")
EXPECTED_NCT_ID = "NCT04828785"
EXPECTED_TITLE_SUBSTRING = "FAME-D"


class ProtocolIdentity(BaseModel):
    """Test-local schema for identifying a protocol from its cover page."""

    nct_id: str
    brief_title: str


@pytest.mark.live
async def test_argon_identifies_demo_protocol_from_first_page() -> None:
    try:
        settings = load_settings()
    except ValidationError:
        pytest.skip("GEMINI_API_KEY or settings not configured in .env")

    api_key = settings.gemini_api_key.get_secret_value().strip()
    if not api_key:
        pytest.skip("GEMINI_API_KEY is empty in .env")

    reader = PdfReader(str(DEMO_PROTOCOL_PDF_PATH))
    first_page_text = reader.pages[0].extract_text() or ""

    client = GeminiClient(
        api_key=api_key,
        model=settings.gemini_model,
    )
    prompt = (
        f"=== PAGE 1 ===\n{first_page_text}\n---\n"
        "Extract the ClinicalTrials.gov NCT identifier and the brief study "
        "title (including the study acronym) from this protocol cover page."
    )

    result = await client.generate_json(
        prompt=prompt,
        response_model=ProtocolIdentity,
        thinking_level=ThinkingLevel.LOW,
    )

    assert result.nct_id.replace(" ", "") == EXPECTED_NCT_ID
    assert EXPECTED_TITLE_SUBSTRING in result.brief_title
