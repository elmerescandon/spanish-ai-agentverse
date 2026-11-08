"""Unit tests for shared completeness check helpers."""

import re

import pytest

from backend.agents.completeness.checks.common import (
    absence_fired_outcome,
    cap_citations,
    compare_category_sets,
    extract_all_timepoints_weeks,
    find_pattern_citation,
    format_offenders,
    parse_duration_to_weeks,
    weeks_match,
)
from backend.shared.messages import (
    M11Heading,
    PageText,
    RuleStatus,
    StratificationFactorType,
)
from tests.backend.agents.completeness.factories import (
    make_citation,
    make_document,
    make_section,
    make_strata,
)


@pytest.mark.parametrize(
    ("text", "expected_weeks"),
    [
        ("Week 26", 26.0),
        ("26 weeks", 26.0),
        ("6 months", 26.0),
        ("Month 6", 26.0),
        ("3 months", 13.0),
        ("12 months", 52.0),
        ("1 year", 52.0),
        ("Day 182", 26.0),
        ("during the study", None),
    ],
)
def test_parse_duration_to_weeks(
    text: str, expected_weeks: float | None
) -> None:
    parsed = parse_duration_to_weeks(text)
    if expected_weeks is None:
        assert parsed is None
    else:
        assert parsed == pytest.approx(expected_weeks)


def test_extract_all_timepoints_weeks_handles_lists_and_baseline() -> None:
    assert extract_all_timepoints_weeks("Baseline and Week 26") == [26.0]
    assert extract_all_timepoints_weeks("Week 12, Week 26, and Week 52") == [
        12.0,
        26.0,
        52.0,
    ]
    assert extract_all_timepoints_weeks("at 3, 6, and 12 months") == [
        13.0,
        26.0,
        52.0,
    ]


def test_weeks_match_accepts_study_day_rounding() -> None:
    assert weeks_match(26.0, 180.0 / 7.0) is True
    assert weeks_match(26.0, 12.0) is False


def test_compare_category_sets_handles_match_mismatch_and_other() -> None:
    left = make_strata(
        (StratificationFactorType.BASELINE_HBA1C, "HbA1c"),
        (StratificationFactorType.REGION, "Region"),
    )
    same = make_strata(
        (StratificationFactorType.REGION, "Geographic region"),
        (StratificationFactorType.BASELINE_HBA1C, "Baseline HbA1c"),
    )
    different = make_strata(
        (StratificationFactorType.BASELINE_HBA1C, "HbA1c"),
    )
    with_other = make_strata(
        (StratificationFactorType.OTHER, "eGFR stratum"),
    )

    passed = compare_category_sets("Synopsis", left, "Section 10", same)
    assert passed.status == RuleStatus.PASSED
    assert len(passed.evidence) >= 1

    fired = compare_category_sets("Synopsis", left, "Section 10", different)
    assert fired.status == RuleStatus.FIRED
    assert "Synopsis" in fired.finding
    assert "Section 10" in fired.finding
    assert len(fired.evidence) >= 2

    unassessed = compare_category_sets(
        "Synopsis", left, "Section 10", with_other
    )
    assert unassessed.status == RuleStatus.CANNOT_ASSESS
    assert unassessed.status_reason is not None
    assert "eGFR stratum" in unassessed.status_reason


def test_absence_fired_outcome_flags_second_opinion_with_no_evidence() -> None:
    outcome = absence_fired_outcome("Sample-size calculation is missing.")

    assert outcome.status == RuleStatus.FIRED
    assert outcome.evidence == ()
    assert outcome.needs_second_opinion is True


def test_find_pattern_citation_verifies_quote_against_section_pages() -> None:
    pages = [
        PageText(
            page_number=1,
            text="1 Protocol Summary: General overview of the study.",
        ),
        PageText(
            page_number=2,
            text=(
                "3 Objectives: Primary outcome is improvement in HbA1c at "
                "Week 26."
            ),
        ),
    ]
    sections = [
        make_section(M11Heading.PROTOCOL_SUMMARY, start_page=1, end_page=1),
        make_section(
            M11Heading.OBJECTIVES_AND_ESTIMANDS, start_page=2, end_page=2
        ),
    ]
    document = make_document(pages=pages, sections=sections)
    pattern = re.compile(r"\bimprovement\b", re.IGNORECASE)

    citation = find_pattern_citation(
        document, pattern, (M11Heading.OBJECTIVES_AND_ESTIMANDS,)
    )

    assert citation is not None
    assert citation.page_number == 2
    assert citation.is_verified is True
    assert "improvement" in citation.quote.lower()


def test_format_offenders_and_cap_citations_enforce_cap_of_five() -> None:
    """format_offenders and cap_citations cap at 5 and append 'and N more'."""
    items = [f"item-{idx}" for idx in range(1, 8)]
    formatted = format_offenders(items)
    assert formatted == "item-1; item-2; item-3; item-4; item-5; and 2 more"
    assert format_offenders(items[:3]) == "item-1; item-2; item-3"

    citations = [
        make_citation(quote=f"quote-{idx}", page_number=idx)
        for idx in range(1, 8)
    ]
    capped = cap_citations(citations)
    assert len(capped) == 5
    assert [c.page_number for c in capped] == [1, 2, 3, 4, 5]
