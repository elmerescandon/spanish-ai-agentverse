"""PDF text extractor with symbol-font cleanup and scanned-PDF checks."""

import logging
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from backend.shared.citations import replace_symbol_font_characters
from backend.shared.messages import PageText

logger = logging.getLogger(__name__)

MIN_CHARACTERS_PER_PAGE = 100  # below this average, treat the PDF as scanned
MAX_PROTOCOL_PAGES = 400
PRIVATE_USE_START_CODEPOINT = 0xE000
PRIVATE_USE_END_CODEPOINT = 0xF8FF


class UnreadablePdfError(RuntimeError):
    """Raised when a PDF has too little extractable text (e.g. scanned)."""


def _count_private_use_characters(text: str) -> int:
    """Count Unicode Basic Multilingual Plane private-use characters."""
    return sum(
        1
        for char in text
        if PRIVATE_USE_START_CODEPOINT
        <= ord(char)
        <= PRIVATE_USE_END_CODEPOINT
    )


def _extract_raw_page_texts(pdf_path: Path) -> list[str]:
    """Return each page's raw text, in order.

    Raises UnreadablePdfError when pypdf cannot parse the file (not a PDF,
    truncated, encrypted), so callers only handle one error type.
    """
    try:
        reader = PdfReader(str(pdf_path))
        return [page.extract_text() or "" for page in reader.pages]
    except PyPdfError as error:
        raise UnreadablePdfError(
            f"expected a readable PDF at {pdf_path}, "
            f"got pypdf error: {type(error).__name__}: {error}"
        ) from error


def read_pdf_pages(pdf_path: Path) -> list[PageText]:
    """Extract 1-based PageText items from pdf_path and check readability."""
    raw_page_texts = _extract_raw_page_texts(pdf_path)
    page_count = len(raw_page_texts)

    if page_count > MAX_PROTOCOL_PAGES:
        raise ValueError(
            f"protocol PDF page count must be <= {MAX_PROTOCOL_PAGES}, "
            f"got {page_count} for {pdf_path}"
        )

    if page_count == 0:
        raise UnreadablePdfError(
            f"protocol PDF must contain at least 1 page with >= "
            f"{MIN_CHARACTERS_PER_PAGE} characters per page on average, "
            f"got 0 pages for {pdf_path}"
        )

    pages: list[PageText] = []
    total_characters = 0

    for index, extracted in enumerate(raw_page_texts, start=1):
        cleaned = replace_symbol_font_characters(extracted)
        unmapped_count = _count_private_use_characters(cleaned)
        if unmapped_count > 0:
            logger.warning(
                "unmapped private-use characters in pdf page: "
                "pdf_path=%s page_number=%d count=%d",
                pdf_path,
                index,
                unmapped_count,
            )
        pages.append(PageText(page_number=index, text=cleaned))
        total_characters += len(cleaned)

    average_characters = total_characters / page_count
    if average_characters < MIN_CHARACTERS_PER_PAGE:
        raise UnreadablePdfError(
            "protocol PDF appears scanned or unreadable: expected average "
            f">= {MIN_CHARACTERS_PER_PAGE} characters per page, "
            f"got {average_characters:.1f} across {page_count} pages"
        )

    return pages
