"""Regression tests for PDF ingest and citation verification on demo PDFs."""

from functools import cache
from pathlib import Path

from backend.clients.pdf_reader import read_pdf_pages
from backend.shared.citations import verify_citation
from backend.shared.messages import Citation, PageText

FAME_D_PDF_PATH = Path("data/protocols/demo/NCT04828785_protocol.pdf")
CANAGLIFLOZIN_PDF_PATH = Path("data/protocols/demo/NCT03170518_protocol.pdf")

FAME_D_EXPECTED_PAGES = 98
CANAGLIFLOZIN_EXPECTED_PAGES = 129

COVER_PAGE = 1
WRONG_PAGE = 3
FOLLOW_UP_PAGE = 8
SPACED_WORD_PAGE = 14
THRESHOLD_PAGE = 15


@cache
def _load_pages(pdf_path: Path) -> list[PageText]:
    return read_pdf_pages(pdf_path)


def test_demo_protocols_read_with_expected_page_counts() -> None:
    fame_d_pages = _load_pages(FAME_D_PDF_PATH)
    canagliflozin_pages = _load_pages(CANAGLIFLOZIN_PDF_PATH)

    assert len(fame_d_pages) == FAME_D_EXPECTED_PAGES
    assert len(canagliflozin_pages) == CANAGLIFLOZIN_EXPECTED_PAGES

    for page in [*fame_d_pages, *canagliflozin_pages]:
        assert "\uf0b3" not in page.text
        assert "\uf0a3" not in page.text


def test_canagliflozin_threshold_quote_verifies() -> None:
    pages = _load_pages(CANAGLIFLOZIN_PDF_PATH)
    quote = "HbA1c of ≥6.5% to ≤11.0%"

    right_page_citation = Citation(page_number=THRESHOLD_PAGE, quote=quote)
    wrong_page_citation = Citation(page_number=WRONG_PAGE, quote=quote)

    assert verify_citation(right_page_citation, pages).is_verified is True
    assert verify_citation(wrong_page_citation, pages).is_verified is False


def test_canagliflozin_spaced_word_quote_verifies() -> None:
    pages = _load_pages(CANAGLIFLOZIN_PDF_PATH)
    citation = Citation(
        page_number=SPACED_WORD_PAGE,
        quote="In children and adolescents (≥10 to <18 years)",
    )

    assert verify_citation(citation, pages).is_verified is True


def test_canagliflozin_line_broken_follow_up_verifies() -> None:
    pages = _load_pages(CANAGLIFLOZIN_PDF_PATH)
    citation = Citation(
        page_number=FOLLOW_UP_PAGE,
        quote="Lost to follow-up Clarified that a subject's contact info",
    )

    assert verify_citation(citation, pages).is_verified is True


def test_fame_d_cover_title_verifies() -> None:
    pages = _load_pages(FAME_D_PDF_PATH)
    citation = Citation(
        page_number=COVER_PAGE,
        quote="Food As MedicinE for Diabetes Study Protocol",
    )

    assert verify_citation(citation, pages).is_verified is True
