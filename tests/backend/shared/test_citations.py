"""Unit tests for deterministic citation normalization and verification."""

from backend.shared.citations import (
    replace_symbol_font_characters,
    verify_citation,
)
from backend.shared.messages import Citation, PageText

PAGE_ONE = 1
PAGE_TWO = 2
OUT_OF_RANGE_PAGE = 99


def test_quote_on_cited_page_is_verified() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text=(
                "Participants must provide written informed consent "
                "before any study-specific procedures."
            ),
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="provide written informed consent before any",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is True


def test_quote_on_wrong_page_is_not_verified() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text="Cover page with protocol synopsis and sponsor details.",
        ),
        PageText(
            page_number=PAGE_TWO,
            text="Randomized double-blind parallel-group clinical trial.",
        ),
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="Randomized double-blind parallel-group clinical trial.",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is False


def test_quote_spanning_page_break_is_verified() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text="Secondary endpoints include change from baseline in",
        ),
        PageText(
            page_number=PAGE_TWO,
            text="fasting plasma glucose at Week 26.",
        ),
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="change from baseline in fasting plasma glucose at Week 26",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is True


def test_quote_with_different_whitespace_and_dashes_is_verified() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text=(
                "Patients   aged 18\u201375\n"
                "years with   type\u20112 diabetes."
            ),
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="Patients aged 18-75 years with type-2 diabetes.",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is True


def test_quote_matches_page_with_space_inside_word() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text="In c hildren and adolescents with type 2 diabetes mellitus.",
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="In children and adolescents",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is True


def test_hyphenated_word_broken_across_lines_is_verified() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text=(
                "All randomized participants enter a 4-week "
                "follow-\nup period."
            ),
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="enter a 4-week follow-up period",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is True


def test_curly_and_straight_quotes_match() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text=(
                "The investigator’s assessment of "
                "“clinically significant” events."
            ),
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote='investigator\'s assessment of "clinically significant" events',
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is True


def test_greater_than_does_not_match_greater_or_equal() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text=(
                "Screening glycosylated hemoglobin HbA1c value "
                "of ≥7.5% at visit."
            ),
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="glycosylated hemoglobin HbA1c value of >7.5% at visit",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is False


def test_symbol_font_threshold_matches_real_symbol() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text=(
                "Participants must have screening HbA1c of "
                "\uf0b36.5% at entry."
            ),
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="Participants must have screening HbA1c of ≥6.5%",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is True


def test_short_quote_is_never_verified() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text="Short quote check in protocol text.",
        )
    ]
    citation = Citation(
        page_number=PAGE_ONE,
        quote="Short quote",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is False


def test_page_out_of_range_is_not_verified() -> None:
    pages = [
        PageText(
            page_number=PAGE_ONE,
            text=(
                "Participants must provide written informed consent "
                "before study."
            ),
        )
    ]
    citation = Citation(
        page_number=OUT_OF_RANGE_PAGE,
        quote="Participants must provide written informed consent",
    )

    verified = verify_citation(citation, pages)

    assert verified.is_verified is False


def test_symbol_font_greek_and_math_characters_are_replaced() -> None:
    extracted = "\uf061=0.05, \uf062-hCG, PPAR\uf067, 0-\uf0a5, \uf0b14 days"

    assert replace_symbol_font_characters(extracted) == (
        "α=0.05, β-hCG, PPARγ, 0-∞, ±4 days"
    )
