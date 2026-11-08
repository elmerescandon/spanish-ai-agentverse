"""Checks that the synthetic sample protocol stays usable on /demo.

The PDF is committed so anyone can upload it; these tests keep it in sync
with its generator and keep the planted issues (README answer key) on the
pages the key says.
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import reset_mock_state
from backend.clients.pdf_reader import read_pdf_pages
from backend.main import app
from scripts.make_sample_protocol import OUTPUT_PATH, build_protocol_pdf

EXPECTED_PAGE_COUNT = 15
# (verbatim quote, 1-based page) for each planted issue in the README.
PLANTED_ISSUE_QUOTES: list[tuple[str, int]] = [
    ("HbA1c (central lab) X X X X", 5),
    ("Change from baseline in HbA1c (%) Week 26", 7),
    ("The primary estimand compares the mean change in HbA1c", 7),
    ("eGFR) >= 60 mL/min/1.73m2", 9),
    ("HbA1c >= 7.5% and <= 9.5%", 9),
    ("aged 18 to 70 years inclusive", 9),
    ("Able to read and speak English", 9),
    ("any prior use of a GLP-1 receptor agonist or insulin", 9),
    ("0.3% in mean HbA1c change", 13),
    ("12 clinic visits", 14),
    ("Safety oversight will be performed by the sponsor's medical", 14),
]


@pytest.fixture(autouse=True)
def _reset_state() -> Generator[None]:
    reset_mock_state()
    yield
    reset_mock_state()


def test_committed_pdf_matches_generator_output() -> None:
    assert OUTPUT_PATH.read_bytes() == build_protocol_pdf(), (
        "sample protocol PDF is stale: run `make sample-protocol`"
    )


def test_sample_pdf_is_readable_with_expected_page_count() -> None:
    pages = read_pdf_pages(OUTPUT_PATH)
    assert len(pages) == EXPECTED_PAGE_COUNT


@pytest.mark.parametrize(("quote", "page_number"), PLANTED_ISSUE_QUOTES)
def test_planted_issue_quote_is_on_documented_page(
    quote: str, page_number: int
) -> None:
    pages = read_pdf_pages(OUTPUT_PATH)
    pages_with_quote = [
        page.page_number for page in pages if quote in page.text
    ]
    assert page_number in pages_with_quote, (
        f"expected {quote!r} on page {page_number}, "
        f"found on pages {pages_with_quote}"
    )


def test_sample_pdf_uploads_and_runs_all_demo_steps() -> None:
    client = TestClient(app)
    upload = client.post(
        "/api/upload-file",
        files={
            "file": (
                OUTPUT_PATH.name,
                OUTPUT_PATH.read_bytes(),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body["page_count"] == EXPECTED_PAGE_COUNT
    assert body["title"] == OUTPUT_PATH.stem
    for route in (
        "/api/checklist-recommendation",
        "/api/protocol-recommendation",
        "/api/cohort-recommendation",
    ):
        response = client.post(
            route, json={"protocol_id": body["protocol_id"]}
        )
        assert response.status_code == 200, f"{route}: {response.text}"
