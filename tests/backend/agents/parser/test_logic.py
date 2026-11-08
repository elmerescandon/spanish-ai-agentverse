"""Unit tests for the parser's pure facet logic."""

from pathlib import Path

from pydantic import BaseModel

from backend.agents.parser.facets import (
    DESIGN_FACET,
    ELIGIBILITY_FACET,
    ENDPOINTS_FACET,
    FACETS,
    SCHEDULE_FACET,
    SECTIONS_FACET,
    STATISTICS_FACET,
    assign_criterion_ids,
    normalize_design_facts,
    sort_sections,
    sort_visits,
)
from backend.agents.parser.logic import (
    Facet,
    FacetOutcome,
    assemble_document,
    build_repair_prompt,
    citation_stats,
    collect_citations,
    count_verified,
    derive_protocol_id,
    derive_title,
    format_pages_for_prompt,
    verify_result,
)
from backend.shared.messages import (
    Citation,
    CitedValue,
    CriterionKind,
    EligibilityCriterion,
    EligibilityExtraction,
    Endpoint,
    EndpointKind,
    EndpointList,
    FacetName,
    M11Heading,
    PageText,
    ProtocolSection,
    ScheduledVisit,
    ScheduleOfActivities,
    SectionMap,
    StatisticalAssumptions,
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


def _section(
    title: str,
    start_page: int,
    end_page: int,
    heading: M11Heading = M11Heading.INTRODUCTION,
) -> ProtocolSection:
    return ProtocolSection(
        heading=heading,
        title=title,
        start_page=start_page,
        end_page=end_page,
        summary="One-sentence summary of the section.",
        citation=_citation(VERIFIABLE_QUOTE),
    )


def test_section_page_range_outside_document_produces_warning() -> None:
    sections = SectionMap(
        sections=[
            _section("Zero Start Section", start_page=0, end_page=1),
            _section("Valid Section", start_page=1, end_page=len(PAGES)),
            _section(
                "Past End Section", start_page=2, end_page=len(PAGES) + 1
            ),
        ]
    )

    warnings = _run_sanity_rules(SECTIONS_FACET, sections)

    assert len(warnings) == 2
    assert "Zero Start Section" in warnings[0]
    assert "Past End Section" in warnings[1]


def test_section_start_after_end_produces_warning() -> None:
    sections = SectionMap(
        sections=[
            _section("Inverted Section", start_page=2, end_page=1),
        ]
    )

    warnings = _run_sanity_rules(SECTIONS_FACET, sections)

    assert len(warnings) == 1
    assert "Inverted Section" in warnings[0]


def test_no_sections_produces_warning() -> None:
    warnings = _run_sanity_rules(SECTIONS_FACET, SectionMap(sections=[]))

    assert len(warnings) == 1
    assert "section" in warnings[0].lower()


def test_sections_sorted_by_start_page() -> None:
    raw = SectionMap(
        sections=[
            _section("5 Study Population", start_page=2, end_page=2),
            _section("2 Introduction", start_page=1, end_page=2),
            _section("1 Protocol Summary", start_page=1, end_page=1),
        ]
    )

    sorted_map = sort_sections(raw)

    assert [s.title for s in sorted_map.sections] == [
        "1 Protocol Summary",
        "2 Introduction",
        "5 Study Population",
    ]
    assert [s.title for s in raw.sections] == [
        "5 Study Population",
        "2 Introduction",
        "1 Protocol Summary",
    ]


def test_endpoints_require_at_least_one_primary_or_warn() -> None:
    only_secondary = EndpointList(
        endpoints=[
            Endpoint(
                kind=EndpointKind.SECONDARY,
                description="Change in diabetes distress score",
                time_frame="6 months",
                citation=_citation(VERIFIABLE_QUOTE),
            )
        ]
    )
    with_primary = EndpointList(
        endpoints=[
            Endpoint(
                kind=EndpointKind.PRIMARY,
                description="Change in Hemoglobin A1c",
                time_frame="6 months",
                citation=_citation(VERIFIABLE_QUOTE),
            )
        ]
    )

    warnings = _run_sanity_rules(ENDPOINTS_FACET, only_secondary)

    assert len(warnings) == 1
    assert "primary" in warnings[0].lower()
    assert _run_sanity_rules(ENDPOINTS_FACET, with_primary) == []


def _visit(
    visit_name: str,
    study_day: int | None,
    procedures: list[str] | None = None,
) -> ScheduledVisit:
    return ScheduledVisit(
        visit_name=visit_name,
        study_day=study_day,
        procedures=["HbA1c blood draw"] if procedures is None else procedures,
        citation=_citation(VERIFIABLE_QUOTE),
    )


def test_visits_sorted_by_study_day_with_unknown_days_last() -> None:
    raw = ScheduleOfActivities(
        visits=[
            _visit("Follow-up phone call", study_day=None),
            _visit("Week 26 Visit", study_day=182),
            _visit("Early Withdrawal", study_day=None),
            _visit("Screening Visit", study_day=-14),
            _visit("Baseline Visit B", study_day=1),
            _visit("Baseline Visit A", study_day=1),
        ]
    )

    sorted_schedule = sort_visits(raw)

    assert [v.visit_name for v in sorted_schedule.visits] == [
        "Screening Visit",
        "Baseline Visit B",
        "Baseline Visit A",
        "Week 26 Visit",
        "Follow-up phone call",
        "Early Withdrawal",
    ]
    assert [v.visit_name for v in raw.visits] == [
        "Follow-up phone call",
        "Week 26 Visit",
        "Early Withdrawal",
        "Screening Visit",
        "Baseline Visit B",
        "Baseline Visit A",
    ]


def test_schedule_without_visits_produces_warning() -> None:
    warnings = _run_sanity_rules(
        SCHEDULE_FACET, ScheduleOfActivities(visits=[])
    )

    assert len(warnings) == 1
    assert "visit" in warnings[0].lower()


def test_visit_without_procedures_produces_warning() -> None:
    schedule = ScheduleOfActivities(
        visits=[
            _visit("Screening Visit", study_day=-14, procedures=["Consent"]),
            _visit("Empty Week 12 Visit", study_day=84, procedures=[]),
            _visit("Empty Unscheduled Visit", study_day=None, procedures=[]),
        ]
    )

    warnings = _run_sanity_rules(SCHEDULE_FACET, schedule)

    assert len(warnings) == 2
    assert "Empty Week 12 Visit" in warnings[0]
    assert "Empty Unscheduled Visit" in warnings[1]


def test_statistics_facet_tolerates_all_fields_null() -> None:
    empty_stats = StatisticalAssumptions()

    assert len(STATISTICS_FACET.sanity_rules) == 4
    assert _run_sanity_rules(STATISTICS_FACET, empty_stats) == []


def test_power_outside_unit_interval_produces_warning() -> None:
    zero_power = StatisticalAssumptions(
        power=CitedValue[float](
            value=0.0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    one_power = StatisticalAssumptions(
        power=CitedValue[float](
            value=1.0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    valid_power = StatisticalAssumptions(
        power=CitedValue[float](
            value=0.8, citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    assert len(_run_sanity_rules(STATISTICS_FACET, zero_power)) == 1
    assert len(_run_sanity_rules(STATISTICS_FACET, one_power)) == 1
    assert _run_sanity_rules(STATISTICS_FACET, valid_power) == []


def test_alpha_outside_unit_interval_produces_warning() -> None:
    zero_alpha = StatisticalAssumptions(
        alpha=CitedValue[float](
            value=0.0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    one_alpha = StatisticalAssumptions(
        alpha=CitedValue[float](
            value=1.0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    valid_alpha = StatisticalAssumptions(
        alpha=CitedValue[float](
            value=0.05, citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    assert len(_run_sanity_rules(STATISTICS_FACET, zero_alpha)) == 1
    assert len(_run_sanity_rules(STATISTICS_FACET, one_alpha)) == 1
    assert _run_sanity_rules(STATISTICS_FACET, valid_alpha) == []


def test_dropout_rate_of_one_or_more_produces_warning() -> None:
    zero_dropout = StatisticalAssumptions(
        dropout_rate=CitedValue[float](
            value=0.0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    negative_dropout = StatisticalAssumptions(
        dropout_rate=CitedValue[float](
            value=-0.05, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    one_dropout = StatisticalAssumptions(
        dropout_rate=CitedValue[float](
            value=1.0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    over_one_dropout = StatisticalAssumptions(
        dropout_rate=CitedValue[float](
            value=10.0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    assert _run_sanity_rules(STATISTICS_FACET, zero_dropout) == []
    assert len(_run_sanity_rules(STATISTICS_FACET, negative_dropout)) == 1
    assert len(_run_sanity_rules(STATISTICS_FACET, one_dropout)) == 1
    assert len(_run_sanity_rules(STATISTICS_FACET, over_one_dropout)) == 1


def test_non_positive_sample_size_produces_warning() -> None:
    zero_sample = StatisticalAssumptions(
        sample_size=CitedValue[int](
            value=0, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    negative_sample = StatisticalAssumptions(
        sample_size=CitedValue[int](
            value=-200, citation=_citation(VERIFIABLE_QUOTE)
        )
    )
    valid_sample = StatisticalAssumptions(
        sample_size=CitedValue[int](
            value=200, citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    assert len(_run_sanity_rules(STATISTICS_FACET, zero_sample)) == 1
    assert len(_run_sanity_rules(STATISTICS_FACET, negative_sample)) == 1
    assert _run_sanity_rules(STATISTICS_FACET, valid_sample) == []


def test_registry_contains_all_six_facets() -> None:
    assert FACETS == (
        ELIGIBILITY_FACET,
        DESIGN_FACET,
        SECTIONS_FACET,
        ENDPOINTS_FACET,
        SCHEDULE_FACET,
        STATISTICS_FACET,
    )
    assert [facet.name for facet in FACETS] == [
        FacetName.ELIGIBILITY,
        FacetName.DESIGN,
        FacetName.SECTIONS,
        FacetName.ENDPOINTS,
        FacetName.SCHEDULE,
        FacetName.STATISTICS,
    ]


def test_derive_protocol_id_prefers_nct_id_then_file_stem() -> None:
    pdf_path = Path("/tmp/fame_d_protocol.pdf")
    with_nct = TrialDesignFacts(
        nct_id=CitedValue[str](
            value="NCT04828785", citation=_citation(VERIFIABLE_QUOTE)
        )
    )

    assert derive_protocol_id(with_nct, pdf_path) == "NCT04828785"
    assert derive_protocol_id(TrialDesignFacts(), pdf_path) == (
        "fame_d_protocol"
    )
    assert derive_protocol_id(None, pdf_path) == "fame_d_protocol"


def test_derive_title_prefers_official_title_then_file_stem() -> None:
    pdf_path = Path("/tmp/fame_d_protocol.pdf")
    with_title = TrialDesignFacts(
        official_title=CitedValue[str](
            value="Food As Medicine for Diabetes",
            citation=_citation(VERIFIABLE_QUOTE),
        )
    )

    assert derive_title(with_title, pdf_path) == (
        "Food As Medicine for Diabetes"
    )
    assert derive_title(TrialDesignFacts(), pdf_path) == "fame_d_protocol"
    assert derive_title(None, pdf_path) == "fame_d_protocol"


def test_citation_stats_counts_across_results_and_skips_missing() -> None:
    verified = verify_result(_nested_result(VERIFIABLE_QUOTE), PAGES)

    stats = citation_stats(verified, None, verified)

    assert (stats.verified, stats.total) == (4, 6)
    assert stats.verified_share == 4 / 6


def test_citation_stats_share_is_zero_without_citations() -> None:
    stats = citation_stats(None)

    assert (stats.verified, stats.total, stats.verified_share) == (0, 0, 0.0)
