"""Unit tests for PDF page extraction and scanned-document validation."""

import logging
from pathlib import Path

import pytest

from backend.clients import pdf_reader
from backend.clients.pdf_reader import (
    MIN_CHARACTERS_PER_PAGE,
    UnreadablePdfError,
    read_pdf_pages,
)
from tests.conftest import make_pdf

READABLE_PADDING = (
    "This clinical trial protocol evaluates glycemic control in adults "
    "with type 2 diabetes mellitus across multiple investigative sites."
)
EXACT_THRESHOLD_LINE_A_LEN = 49
EXACT_THRESHOLD_LINE_B_LEN = 50
LOW_MAX_PAGES_LIMIT = 2


class _FakePdfPage:
    """Stand-in for a pypdf PageObject returning scripted text."""

    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakePdfReader:
    """Stand-in for pypdf.PdfReader with scripted pages."""

    def __init__(self, page_texts: list[str]) -> None:
        self.pages = [_FakePdfPage(text) for text in page_texts]


def test_reads_pages_in_order_one_based(tmp_path: Path) -> None:
    first_text = f"Page one protocol overview. {READABLE_PADDING}"
    second_text = f"Page two study objectives. {READABLE_PADDING}"
    pdf_path = make_pdf(tmp_path, [first_text, second_text])

    pages = read_pdf_pages(pdf_path)

    assert [page.page_number for page in pages] == [1, 2]
    assert "Page one protocol overview." in pages[0].text
    assert "Page two study objectives." in pages[1].text


def test_blank_pdf_raises_unreadable_error(tmp_path: Path) -> None:
    pdf_path = make_pdf(tmp_path, ["", "too short"])

    with pytest.raises(UnreadablePdfError, match=str(MIN_CHARACTERS_PER_PAGE)):
        read_pdf_pages(pdf_path)


def test_average_exactly_at_threshold_is_readable(tmp_path: Path) -> None:
    exact_100_chars = (
        ("A" * EXACT_THRESHOLD_LINE_A_LEN)
        + "\n"
        + ("B" * EXACT_THRESHOLD_LINE_B_LEN)
    )
    assert len(exact_100_chars) == MIN_CHARACTERS_PER_PAGE
    pdf_path = make_pdf(tmp_path, [exact_100_chars])

    pages = read_pdf_pages(pdf_path)

    assert len(pages) == 1
    assert len(pages[0].text) == MIN_CHARACTERS_PER_PAGE


def test_more_than_max_pages_raises_value_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_reader, "MAX_PROTOCOL_PAGES", LOW_MAX_PAGES_LIMIT)
    pdf_path = make_pdf(
        tmp_path,
        [READABLE_PADDING, READABLE_PADDING, READABLE_PADDING],
    )

    with pytest.raises(ValueError, match=str(LOW_MAX_PAGES_LIMIT)):
        read_pdf_pages(pdf_path)


def test_symbol_font_characters_replaced_in_page_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_page = (
        f"Inclusion: HbA1c of \uf0b36.5% to \uf0a311.0% \uf02d item \uf0b7 "
        f"{READABLE_PADDING}"
    )
    monkeypatch.setattr(
        pdf_reader,
        "PdfReader",
        lambda _path: _FakePdfReader([raw_page]),
    )

    pages = read_pdf_pages(tmp_path / "dummy.pdf")

    assert "HbA1c of ≥6.5% to ≤11.0% - item •" in pages[0].text
    assert "\uf0b3" not in pages[0].text
    assert "\uf0a3" not in pages[0].text


def test_unmapped_private_use_character_is_kept_and_logged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    raw_page = f"Unmapped glyph \ue001 and \ue002 in {READABLE_PADDING}"
    monkeypatch.setattr(
        pdf_reader,
        "PdfReader",
        lambda _path: _FakePdfReader([raw_page]),
    )

    with caplog.at_level(logging.WARNING):
        pages = read_pdf_pages(tmp_path / "dummy.pdf")

    assert "\ue001" in pages[0].text
    assert "\ue002" in pages[0].text
    assert "page_number=1" in caplog.text
    assert "count=2" in caplog.text


def test_file_that_is_not_a_pdf_raises_unreadable_error(
    tmp_path: Path,
) -> None:
    not_a_pdf = tmp_path / "upload.pdf"
    not_a_pdf.write_text("this is a word document, not a pdf")

    with pytest.raises(UnreadablePdfError, match="upload.pdf"):
        read_pdf_pages(not_a_pdf)


def test_truncated_pdf_raises_unreadable_error(tmp_path: Path) -> None:
    complete_pdf = make_pdf(tmp_path, [READABLE_PADDING, READABLE_PADDING])
    truncated_pdf = tmp_path / "truncated.pdf"
    complete_bytes = complete_pdf.read_bytes()
    truncated_pdf.write_bytes(complete_bytes[: len(complete_bytes) // 3])

    with pytest.raises(UnreadablePdfError, match="truncated.pdf"):
        read_pdf_pages(truncated_pdf)
