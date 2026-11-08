"""Unit tests for the parser's pure facet logic."""

from pydantic import BaseModel

from backend.agents.parser.logic import (
    DESIGN_FACET,
    ELIGIBILITY_FACET,
    FACETS,
    Facet,
    FacetOutcome,
    assemble_document,
    assign_criterion_ids,
    build_repair_prompt,
    collect_citations,
    count_verified,
    format_pages_for_prompt,
    normalize_design_facts,
    verify_result,
)
from backend.shared.messages import (
    Citation,
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    EligibilityExtraction,
    FacetName,
    PageText,
    TrialDesignFacts,
)

PAGES = [
    PageText(
        page_number=1,
        text="Food As Medicine for Diabetes study protocol, version 1.",
    ),
    PageText(
        page_number=2,
        text="Participants must have HbA1c ≥ 8.0% at the screening visit.",
    ),
]
VERIFIABLE_QUOTE = "HbA1c ≥ 8.0% at the screening visit"
INVENTED_QUOTE = "HbA1c above 9.5% for six months"
PROTOCOL_ID = "NCT00000000"
PROTOCOL_TITLE = "Example protocol"
TARGET_ENROLLMENT = 200


class _Note(BaseModel):
    text: str
    citation: Citation


class _NestedResult(BaseModel):
    headline: CitedValue[str] | None
    notes: list[_Note]


def _citation(quote: str, page_number: int = 2) -> Citation:
    return Citation(page_number=page_number, quote=quote)


def _nested_result(headline_quote: str | None) -> _NestedResult:
    headline = (
        CitedValue[str](value="HbA1c", citation=_citation(headline_quote))
        if headline_quote is not None
        else None
    )
    return _NestedResult(
        headline=headline,
        notes=[
            _Note(text="first", citation=_citation(VERIFIABLE_QUOTE)),
            _Note(text="second", citation=_citation(INVENTED_QUOTE)),
        ],
    )


def test_collect_citations_finds_nested_and_cited_values() -> None:
    citations = collect_citations(_nested_result(VERIFIABLE_QUOTE))

    assert [citation.quote for citation in citations] == [
        VERIFIABLE_QUOTE,
        VERIFIABLE_QUOTE,
        INVENTED_QUOTE,
    ]


def test_collect_citations_skips_missing_values() -> None:
    citations = collect_citations(_nested_result(None))

    assert len(citations) == 2


def test_verify_result_sets_flags_without_mutating_input() -> None:
    original = _nested_result(VERIFIABLE_QUOTE)

    verified = verify_result(original, PAGES)

    assert [c.is_verified for c in collect_citations(verified)] == [
        True,
        True,
        False,
    ]
    assert not any(c.is_verified for c in collect_citations(original))
    assert isinstance(verified, _NestedResult)


def test_count_verified_counts_only_verified_citations() -> None:
    verified = verify_result(_nested_result(VERIFIABLE_QUOTE), PAGES)

    assert count_verified(verified) == 2


def test_page_markers_are_one_based_and_ordered() -> None:
    prompt_pages = format_pages_for_prompt(PAGES)

    first_marker = prompt_pages.index("=== PAGE 1 ===")
    second_marker = prompt_pages.index("=== PAGE 2 ===")
    assert first_marker < second_marker
    assert prompt_pages.index(PAGES[1].text) > second_marker


def test_repair_prompt_lists_each_failed_quote_with_its_page() -> None:
    base_prompt = "=== PAGE 1 ===\ntext\n---\nInstructions."

    repair_prompt = build_repair_prompt(
        base_prompt, [_citation(INVENTED_QUOTE, page_number=2)]
    )

    assert repair_prompt.startswith(base_prompt)
    assert INVENTED_QUOTE in repair_prompt
    assert "page 2" in repair_prompt


def test_assemble_document_maps_facet_results_to_fields() -> None:
    criterion = EligibilityCriterion(
        criterion_id="IN-01",
        kind=CriterionKind.INCLUSION,
        text="HbA1c at least 8.0%",
        citation=_citation(VERIFIABLE_QUOTE),
    )
    design = TrialDesignFacts(
        target_enrollment=CitedValue[int](
            value=TARGET_ENROLLMENT, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    outcomes = {
        FacetName.ELIGIBILITY: FacetOutcome(
            facet=FacetName.ELIGIBILITY,
            result=EligibilityExtraction(criteria=[criterion]),
            warnings=[],
        ),
        FacetName.DESIGN: FacetOutcome(
            facet=FacetName.DESIGN, result=design, warnings=[]
        ),
    }

    document = assemble_document(PROTOCOL_ID, PROTOCOL_TITLE, PAGES, outcomes)

    assert document.eligibility_criteria == [criterion]
    assert document.design == design
    assert document.sections is None
    assert document.page_count == len(PAGES)
    assert document.extraction_warnings == []


def test_assemble_document_failed_facet_is_none_with_warning() -> None:
    outcomes = {
        FacetName.ELIGIBILITY: FacetOutcome(
            facet=FacetName.ELIGIBILITY,
            result=None,
            warnings=["facet failed after retries"],
        )
    }

    document = assemble_document(PROTOCOL_ID, PROTOCOL_TITLE, PAGES, outcomes)

    assert document.eligibility_criteria is None
    assert [
        (warning.facet, warning.message)
        for warning in document.extraction_warnings
    ] == [(FacetName.ELIGIBILITY, "facet failed after retries")]


def test_assemble_document_empty_facet_is_empty_list_with_warning() -> None:
    outcomes = {
        FacetName.ELIGIBILITY: FacetOutcome(
            facet=FacetName.ELIGIBILITY,
            result=EligibilityExtraction(criteria=[]),
            warnings=[],
        )
    }

    document = assemble_document(PROTOCOL_ID, PROTOCOL_TITLE, PAGES, outcomes)

    assert document.eligibility_criteria == []
    assert len(document.extraction_warnings) == 1
    assert "no items" in document.extraction_warnings[0].message


def _run_sanity_rules[ResultT: BaseModel](
    facet: Facet[ResultT], result: ResultT
) -> list[str]:
    return [
        warning
        for rule in facet.sanity_rules
        for warning in rule(result, len(PAGES))
    ]


def test_criterion_ids_follow_kind_and_document_order() -> None:
    raw = EligibilityExtraction(
        criteria=[
            EligibilityCriterion(
                criterion_id="x",
                kind=CriterionKind.INCLUSION,
                text="Aged 18 years or older",
                citation=_citation(VERIFIABLE_QUOTE),
            ),
            EligibilityCriterion(
                criterion_id="y",
                kind=CriterionKind.EXCLUSION,
                text="Prior bariatric surgery",
                citation=_citation(VERIFIABLE_QUOTE),
            ),
            EligibilityCriterion(
                criterion_id="z",
                kind=CriterionKind.INCLUSION,
                text="HbA1c at least 8.0%",
                citation=_citation(VERIFIABLE_QUOTE),
            ),
            EligibilityCriterion(
                criterion_id="w",
                kind=CriterionKind.EXCLUSION,
                text="Active malignancy",
                citation=_citation(VERIFIABLE_QUOTE),
            ),
        ]
    )

    normalized = assign_criterion_ids(raw)

    assert [c.criterion_id for c in normalized.criteria] == [
        "IN-01",
        "EX-01",
        "IN-02",
        "EX-02",
    ]
    assert [c.criterion_id for c in raw.criteria] == ["x", "y", "z", "w"]


def test_missing_inclusion_criteria_produces_warning() -> None:
    only_exclusion = EligibilityExtraction(
        criteria=[
            EligibilityCriterion(
                criterion_id="EX-01",
                kind=CriterionKind.EXCLUSION,
                text="Prior bariatric surgery",
                citation=_citation(VERIFIABLE_QUOTE),
            )
        ]
    )

    warnings = _run_sanity_rules(ELIGIBILITY_FACET, only_exclusion)

    assert len(warnings) == 1
    assert "inclusion" in warnings[0].lower()


def test_min_age_above_max_age_produces_warning() -> None:
    inverted_ages = TrialDesignFacts(
        min_age_years=CitedValue[float](
            value=65.0, citation=_citation(VERIFIABLE_QUOTE)
        ),
        max_age_years=CitedValue[float](
            value=18.0, citation=_citation(VERIFIABLE_QUOTE)
        ),
    )
    equal_ages = TrialDesignFacts(
        min_age_years=CitedValue[float](
            value=18.0, citation=_citation(VERIFIABLE_QUOTE)
        ),
        max_age_years=CitedValue[float](
            value=18.0, citation=_citation(VERIFIABLE_QUOTE)
        ),
    )

    assert len(_run_sanity_rules(DESIGN_FACET, inverted_ages)) == 1
    assert len(_run_sanity_rules(DESIGN_FACET, equal_ages)) == 1


def test_non_positive_target_enrollment_produces_warning() -> None:
    zero_enrollment = TrialDesignFacts(
        target_enrollment=CitedValue[int](
            value=0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    negative_enrollment = TrialDesignFacts(
        target_enrollment=CitedValue[int](
            value=-10, citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    assert len(_run_sanity_rules(DESIGN_FACET, zero_enrollment)) == 1
    assert len(_run_sanity_rules(DESIGN_FACET, negative_enrollment)) == 1


def test_zero_arm_count_produces_warning() -> None:
    zero_arms = TrialDesignFacts(
        arm_count=CitedValue[int](
            value=0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    warnings = _run_sanity_rules(DESIGN_FACET, zero_arms)

    assert len(warnings) == 1
    assert "arm" in warnings[0].lower()


def test_design_facet_tolerates_all_fields_null() -> None:
    empty_facts = TrialDesignFacts()

    assert len(DESIGN_FACET.sanity_rules) == 3
    assert normalize_design_facts(empty_facts) == empty_facts
    assert _run_sanity_rules(DESIGN_FACET, empty_facts) == []


def test_nct_id_normalized_without_spaces() -> None:
    raw = TrialDesignFacts(
        nct_id=CitedValue[str](
            value="nct 04828785 ", citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    normalized = normalize_design_facts(raw)

    assert normalized.nct_id is not None
    assert normalized.nct_id.value == "NCT04828785"
    assert raw.nct_id is not None
    assert raw.nct_id.value == "nct 04828785 "


def test_age_inclusivity_kept_when_its_age_is_present() -> None:
    raw = TrialDesignFacts(
        max_age_years=CitedValue[float](
            value=18.0, citation=_citation(VERIFIABLE_QUOTE)
        ),
        is_max_age_inclusive=False,
    )

    assert normalize_design_facts(raw).is_max_age_inclusive is False


def test_age_inclusivity_cleared_when_its_age_is_missing() -> None:
    raw = TrialDesignFacts(
        min_age_years=CitedValue[float](
            value=18.0, citation=_citation(VERIFIABLE_QUOTE)
        ),
        is_min_age_inclusive=True,
        is_max_age_inclusive=False,
    )

    normalized = normalize_design_facts(raw)

    assert normalized.is_min_age_inclusive is True
    assert normalized.is_max_age_inclusive is None


def test_design_instructions_explain_age_inclusivity() -> None:
    for field_name in ("is_min_age_inclusive", "is_max_age_inclusive"):
        assert field_name in DESIGN_FACET.instructions


def test_registry_contains_eligibility_and_design() -> None:
    assert FACETS == (ELIGIBILITY_FACET, DESIGN_FACET)
    assert [facet.name for facet in FACETS] == [
        FacetName.ELIGIBILITY,
        FacetName.DESIGN,
    ]
