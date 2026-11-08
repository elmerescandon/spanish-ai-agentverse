"""Shared pytest fixtures and test doubles for the protocol parser suite."""

from collections.abc import Sequence
from pathlib import Path

import pytest
from fpdf import FPDF
from pydantic import BaseModel

from backend.clients.gemini import GeminiClient, ThinkingLevel
from backend.shared.config import load_settings

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
