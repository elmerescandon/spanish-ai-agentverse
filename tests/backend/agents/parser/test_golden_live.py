"""Live golden accuracy test for ELIGIBILITY and DESIGN facets."""

import asyncio
import logging
from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.agents.parser.agent import extract_facet
from backend.agents.parser.logic import (
    DESIGN_FACET,
    ELIGIBILITY_FACET,
    collect_citations,
    count_verified,
)
from backend.clients.pdf_reader import read_pdf_pages
from backend.shared.messages import (
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    EligibilityExtraction,
    TrialDesignFacts,
)
from tests.conftest import make_live_gemini_client

logger = logging.getLogger(__name__)

GOLDEN_PATH = Path("tests/fixtures/golden/NCT04828785_expected.json")
GOLDEN_MIN_ACCURACY = 0.8


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


def _design_fact_matches(
    facts: TrialDesignFacts,
    field_name: str,
    expected_value: str | float | bool,
) -> bool:
    cited: CitedValue[object] | None = getattr(facts, field_name, None)
    if cited is None:
        return False
    return cited.value == expected_value


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


@pytest.mark.live
async def test_fame_d_golden_eligibility_and_design() -> None:
    if not GOLDEN_PATH.exists():
        pytest.skip(f"Golden expectations file not found at {GOLDEN_PATH}")

    golden = GoldenExpectations.model_validate_json(
        GOLDEN_PATH.read_text(encoding="utf-8")
    )
    pdf_path = Path(golden.pdf_path)
    if not pdf_path.exists():
        pytest.skip(f"Demo protocol PDF not found at {pdf_path}")

    llm = make_live_gemini_client()
    pages = read_pdf_pages(pdf_path)

    design_outcome, eligibility_outcome = await asyncio.gather(
        extract_facet(DESIGN_FACET, pages, llm),
        extract_facet(ELIGIBILITY_FACET, pages, llm),
    )

    assert isinstance(design_outcome.result, TrialDesignFacts), (
        f"DESIGN facet failed: {design_outcome.warnings}"
    )
    assert isinstance(eligibility_outcome.result, EligibilityExtraction), (
        f"ELIGIBILITY facet failed: {eligibility_outcome.warnings}"
    )

    design_facts = design_outcome.result
    criteria = eligibility_outcome.result.criteria

    matched_design = sum(
        1
        for field_name, expected_val in golden.design.items()
        if _design_fact_matches(design_facts, field_name, expected_val)
    )
    matched_criteria = sum(
        1
        for expected_item in golden.criteria
        if _criterion_matches(criteria, expected_item)
    )

    total_facts = len(golden.design) + len(golden.criteria)
    matched_facts = matched_design + matched_criteria
    accuracy = matched_facts / total_facts if total_facts > 0 else 0.0

    all_citations = collect_citations(design_facts) + collect_citations(
        eligibility_outcome.result
    )
    verified_count = count_verified(design_facts) + count_verified(
        eligibility_outcome.result
    )
    verified_share = (
        verified_count / len(all_citations) if all_citations else 0.0
    )

    summary = (
        f"accuracy={accuracy:.2%} ({matched_facts}/{total_facts}: "
        f"design={matched_design}/{len(golden.design)}, "
        f"criteria={matched_criteria}/{len(golden.criteria)}), "
        f"verified_citations={verified_share:.2%} "
        f"({verified_count}/{len(all_citations)})"
    )
    logger.info("golden parser accuracy: %s", summary)
    assert accuracy >= GOLDEN_MIN_ACCURACY, summary
