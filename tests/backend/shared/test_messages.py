"""Unit tests for the shared parser contract models."""

import pytest
from pydantic import ValidationError

from backend.shared.messages import (
    AnalysisPlanExtraction,
    AnalysisSetItem,
    AnalysisSetType,
    CheckMethod,
    Citation,
    CitedValue,
    CommitteeItem,
    CommitteeType,
    ComplianceReport,
    ControlType,
    DiabetesType,
    DrugClass,
    Endpoint,
    EndpointKind,
    EpochType,
    Estimand,
    EstimandExtraction,
    EstimandStrategy,
    FacetName,
    FindingLocation,
    GateResult,
    GateStatus,
    IntercurrentEvent,
    IntercurrentEventType,
    InterventionArm,
    InterventionExtraction,
    InterventionType,
    M11Heading,
    PageText,
    ProtocolDocument,
    ProtocolSection,
    ProtocolSubsection,
    RuleFamily,
    RuleFinding,
    RuleSeverity,
    RuleStatus,
    RunResult,
    SafetyMonitoringExtraction,
    ScaleDirection,
    ScheduledVisit,
    SearchedLocation,
    SectionMap,
    SourceTier,
    StatisticalAssumptions,
    StratificationFactorItem,
    StratificationFactorType,
    SubgroupDimension,
    SubgroupItem,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
    TrialEpoch,
    TrialPhase,
    TrialProfile,
)

SAMPLE_PAGE_NUMBER = 4
SAMPLE_PAGE_COUNT = 1
SAMPLE_TARGET_ENROLLMENT = 240


def test_cited_value_validates_typed_value() -> None:
    citation = Citation(
        page_number=SAMPLE_PAGE_NUMBER,
        quote="Approximately 240 participants will be randomized.",
    )
    valid_item = CitedValue[int](
        value=SAMPLE_TARGET_ENROLLMENT, citation=citation
    )
    assert valid_item.value == SAMPLE_TARGET_ENROLLMENT

    with pytest.raises(ValidationError):
        CitedValue[int].model_validate(
            {"value": "abc", "citation": citation.model_dump()}
        )


def test_design_facts_accepts_all_fields_missing() -> None:
    facts = TrialDesignFacts()

    assert facts.phase is None
    assert facts.allocation is None
    assert facts.intervention_model is None
    assert facts.masking is None
    assert facts.target_enrollment is None
    assert facts.arm_count is None
    assert facts.min_age_years is None
    assert facts.max_age_years is None
    assert facts.accepts_healthy_volunteers is None
    assert facts.site_count is None
    assert facts.country_count is None
    assert facts.has_data_monitoring_committee is None
    assert facts.nct_id is None


def test_protocol_document_distinguishes_failed_facet_from_empty_facet() -> (
    None
):
    document = ProtocolDocument(
        protocol_id="proto-001",
        title="Phase 3 Study in Type 2 Diabetes",
        page_count=SAMPLE_PAGE_COUNT,
        pages=[
            PageText(page_number=SAMPLE_PAGE_COUNT, text="Protocol cover page")
        ],
        design=None,
        eligibility_criteria=[],
        sections=None,
        endpoints=[],
        schedule=None,
        statistics=None,
        extraction_warnings=[],
    )

    restored = ProtocolDocument.model_validate_json(document.model_dump_json())

    assert restored.design is None
    assert restored.eligibility_criteria == []
    assert restored.sections is None
    assert restored.endpoints == []
    assert restored.schedule is None
    assert restored.statistics is None


def test_age_inclusivity_is_unknown_by_default() -> None:
    facts = TrialDesignFacts()

    assert facts.is_min_age_inclusive is None
    assert facts.is_max_age_inclusive is None


def _make_sample_finding(
    rule_id: str = "REG-27",
    status: RuleStatus = RuleStatus.FIRED,
    status_reason: str | None = None,
    evidence: list[Citation] | None = None,
    searched_locations: list[SearchedLocation] | None = None,
    confidence: float = 1.0,
) -> RuleFinding:
    default_evidence = [
        Citation(
            page_number=10,
            quote="at the end of treatment (6 months, primary analysis)",
            is_verified=True,
        )
    ]
    return RuleFinding(
        rule_id=rule_id,
        family=RuleFamily.REG,
        severity=RuleSeverity.S1,
        status=status,
        status_reason=status_reason,
        title="Outcome time frame is vague",
        finding="Time frame is not a specific time point from baseline.",
        location=FindingLocation(
            section="1.1",
            heading=M11Heading.PROTOCOL_SUMMARY,
            page=10,
        ),
        evidence=default_evidence if evidence is None else evidence,
        searched_locations=(
            [] if searched_locations is None else searched_locations
        ),
        proposed_fix="Change from baseline in HbA1c at Month 6",
        requires_medical_review=False,
        confidence=confidence,
        source="ClinicalTrials.gov PRS Quality Control Review Criteria",
        source_tier=SourceTier.REGISTRY_QC,
        check_method=CheckMethod.DETERMINISTIC,
    )


def _make_sample_run_result(score: float = 80.0) -> RunResult:
    gate = GateResult(
        status=GateStatus.PASS, is_partial=False, failing_rule_ids=[]
    )
    return RunResult(score=score, registration_gate=gate, review_gate=gate)


def test_rule_finding_rejects_confidence_outside_unit_interval() -> None:
    assert _make_sample_finding(confidence=0.0).confidence == 0.0
    assert _make_sample_finding(confidence=1.0).confidence == 1.0

    with pytest.raises(ValidationError):
        _make_sample_finding(confidence=-0.01)

    with pytest.raises(ValidationError):
        _make_sample_finding(confidence=1.01)


def test_run_result_rejects_score_outside_zero_to_hundred() -> None:
    assert _make_sample_run_result(score=0.0).score == 0.0
    assert _make_sample_run_result(score=100.0).score == 100.0

    with pytest.raises(ValidationError):
        _make_sample_run_result(score=-0.1)

    with pytest.raises(ValidationError):
        _make_sample_run_result(score=100.1)


def test_compliance_report_validates_rules_evaluated_matches_findings() -> (
    None
):
    finding = _make_sample_finding()
    report = ComplianceReport(
        protocol_id="NCT04828785",
        protocol_title="Sample Trial",
        protocol_version="1.0",
        trial_profile=TrialProfile(),
        rules_evaluated=1,
        before=_make_sample_run_result(),
        findings=[finding],
    )
    assert report.rules_evaluated == 1

    with pytest.raises(ValidationError) as exc_info:
        ComplianceReport(
            protocol_id="NCT04828785",
            protocol_title="Sample Trial",
            protocol_version="1.0",
            trial_profile=TrialProfile(),
            rules_evaluated=3,
            before=_make_sample_run_result(),
            findings=[finding],
        )
    error_text = str(exc_info.value)
    assert "3" in error_text
    assert "1" in error_text


def test_fired_finding_requires_evidence_or_searched_locations() -> None:
    searched = [
        SearchedLocation(
            heading=M11Heading.PROTOCOL_SUMMARY,
            section_title="1. Protocol Summary",
            start_page=1,
            end_page=3,
        )
    ]
    finding_with_searched = _make_sample_finding(
        status=RuleStatus.FIRED,
        evidence=[],
        searched_locations=searched,
    )
    assert finding_with_searched.searched_locations == searched

    with pytest.raises(ValidationError) as exc_info:
        _make_sample_finding(
            status=RuleStatus.FIRED,
            evidence=[],
            searched_locations=[],
        )
    assert "evidence" in str(exc_info.value)
    assert "searched_locations" in str(exc_info.value)


def test_non_scored_statuses_require_non_blank_status_reason() -> None:
    non_scored_statuses = (
        RuleStatus.NOT_APPLICABLE,
        RuleStatus.INSUFFICIENT_COMPARATORS,
        RuleStatus.CANNOT_ASSESS,
    )
    for status in non_scored_statuses:
        valid = _make_sample_finding(
            status=status,
            status_reason="Trigger does not exist in this protocol.",
            evidence=[],
        )
        assert valid.status == status

        for invalid_reason in (None, "", "   "):
            with pytest.raises(ValidationError) as exc_info:
                _make_sample_finding(
                    status=status,
                    status_reason=invalid_reason,
                    evidence=[],
                )
            assert "status_reason" in str(exc_info.value)


def test_compliance_report_rejects_duplicate_rule_ids() -> None:
    first = _make_sample_finding(rule_id="REG-27")
    duplicate = _make_sample_finding(rule_id="REG-27")

    with pytest.raises(ValidationError) as exc_info:
        ComplianceReport(
            protocol_id="NCT04828785",
            protocol_title="Sample Trial",
            protocol_version="1.0",
            trial_profile=TrialProfile(),
            rules_evaluated=2,
            before=_make_sample_run_result(),
            findings=[first, duplicate],
        )
    assert "REG-27" in str(exc_info.value)


def test_trial_profile_accepts_cited_values_and_defaults_to_none() -> None:
    empty_profile = TrialProfile()
    assert empty_profile.intervention_type is None
    assert empty_profile.diabetes_type is None
    assert empty_profile.drug_class is None
    assert empty_profile.phase is None
    assert empty_profile.control_type is None
    assert empty_profile.is_non_inferiority is None
    assert empty_profile.is_add_on is None

    citation = Citation(
        page_number=SAMPLE_PAGE_NUMBER,
        quote="Phase 3 randomized placebo-controlled add-on study in T2D.",
        is_verified=True,
    )
    populated = TrialProfile(
        intervention_type=CitedValue[InterventionType](
            value=InterventionType.DRUG, citation=citation
        ),
        diabetes_type=CitedValue[DiabetesType](
            value=DiabetesType.T2D, citation=citation
        ),
        drug_class=CitedValue[DrugClass](
            value=DrugClass.SGLT2_INHIBITOR, citation=citation
        ),
        phase=CitedValue[TrialPhase](
            value=TrialPhase.PHASE3, citation=citation
        ),
        control_type=CitedValue[ControlType](
            value=ControlType.PLACEBO, citation=citation
        ),
        is_non_inferiority=CitedValue[bool](value=False, citation=citation),
        is_add_on=CitedValue[bool](value=True, citation=citation),
    )
    assert populated.diabetes_type is not None
    assert populated.diabetes_type.value == DiabetesType.T2D


def test_facet_name_lists_all_eleven_facets() -> None:
    assert [member.value for member in FacetName] == [
        "DESIGN",
        "ELIGIBILITY",
        "SECTIONS",
        "ENDPOINTS",
        "SCHEDULE",
        "STATISTICS",
        "ESTIMANDS",
        "INTERVENTIONS",
        "ANALYSIS",
        "SYNOPSIS_CHECK",
        "SAFETY_MONITORING",
    ]


def test_canonical_enums_define_expected_members_and_other() -> None:
    assert EstimandStrategy.TREATMENT_POLICY == "TREATMENT_POLICY"
    assert EstimandStrategy.OTHER == "OTHER"
    assert IntercurrentEventType.RESCUE_MEDICATION == "RESCUE_MEDICATION"
    assert IntercurrentEventType.OTHER == "OTHER"
    assert AnalysisSetType.FULL_ANALYSIS == "FULL_ANALYSIS"
    assert AnalysisSetType.OTHER == "OTHER"
    assert SubgroupDimension.BASELINE_HBA1C == "BASELINE_HBA1C"
    assert SubgroupDimension.OTHER == "OTHER"
    assert StratificationFactorType.PRIOR_THERAPY == "PRIOR_THERAPY"
    assert StratificationFactorType.OTHER == "OTHER"
    assert CommitteeType.DATA_MONITORING == "DATA_MONITORING"
    assert CommitteeType.OTHER == "OTHER"
    assert EpochType.TREATMENT == "TREATMENT"
    assert EpochType.OTHER == "OTHER"
    assert [member.value for member in ScaleDirection] == ["HIGHER", "LOWER"]


def test_extended_existing_facet_models_accept_new_fields() -> None:
    citation = Citation(
        page_number=SAMPLE_PAGE_NUMBER,
        quote="4.1 Inclusion Criteria and scale range 0 to 100.",
        is_verified=True,
    )
    subsection = ProtocolSubsection(
        number="4.1",
        title="Inclusion Criteria",
        page_number=SAMPLE_PAGE_NUMBER,
        citation=citation,
    )
    section = ProtocolSection(
        heading=M11Heading.TRIAL_POPULATION,
        title="4 Trial Population",
        start_page=SAMPLE_PAGE_NUMBER,
        end_page=SAMPLE_PAGE_NUMBER,
        summary="Eligibility criteria.",
        citation=citation,
    )
    section_map = SectionMap(sections=[section], subsections=[subsection])
    assert section_map.subsections == [subsection]

    endpoint = Endpoint(
        kind=EndpointKind.SECONDARY,
        description="Change in DTSQ total score at Week 26",
        time_frame="Week 26",
        scale_name=CitedValue[str](value="DTSQ", citation=citation),
        scale_min=CitedValue[float](value=0.0, citation=citation),
        scale_max=CitedValue[float](value=36.0, citation=citation),
        scale_better_direction=CitedValue[ScaleDirection](
            value=ScaleDirection.HIGHER, citation=citation
        ),
        citation=citation,
    )
    assert endpoint.scale_better_direction is not None
    assert endpoint.scale_better_direction.value == ScaleDirection.HIGHER

    visit = ScheduledVisit(
        visit_name="Week 26",
        study_day=182,
        epoch=EpochType.TREATMENT,
        procedures=["HbA1c"],
        citation=citation,
    )
    assert visit.epoch == EpochType.TREATMENT

    stats = StatisticalAssumptions(
        effect_size=CitedValue[str](value="0.5% HbA1c", citation=citation),
        effect_size_value=CitedValue[float](value=0.5, citation=citation),
        standard_deviation=CitedValue[float](value=1.1, citation=citation),
        allocation_ratio=CitedValue[float](value=1.0, citation=citation),
        is_two_sided=CitedValue[bool](value=True, citation=citation),
        has_sample_size_calculation=CitedValue[bool](
            value=True, citation=citation
        ),
        assumptions_source_citation=CitedValue[str](
            value="Phase 2 study XYZ-101", citation=citation
        ),
        non_inferiority_margin=CitedValue[float](value=0.3, citation=citation),
    )
    assert stats.effect_size_value is not None
    assert stats.effect_size_value.value == 0.5
    assert stats.non_inferiority_margin is not None
    assert stats.non_inferiority_margin.value == 0.3


def test_new_facet_models_default_tri_state_booleans_to_none() -> None:
    estimands = EstimandExtraction()
    assert estimands.estimands == []
    assert estimands.lists_all_five_attributes is None

    interventions = InterventionExtraction()
    assert interventions.arms == []
    assert interventions.continues_follow_up_after_discontinuation is None
    assert interventions.collects_hba1c_after_discontinuation is None

    analysis = AnalysisPlanExtraction()
    assert analysis.analysis_sets == []
    assert analysis.adjusts_for_baseline is None
    assert analysis.controls_type_i_error is None
    assert analysis.has_interim_analysis is None

    synopsis = SynopsisConsistencyExtraction()
    assert synopsis.has_lay_summary is None
    assert synopsis.states_no_amendments is None

    safety = SafetyMonitoringExtraction()
    assert safety.defines_hypoglycemia_levels is None
    assert safety.level_3_requires_assistance is None
    assert safety.captures_hypoglycemia_diary is None
    assert safety.defines_dka_criteria is None
    assert safety.defines_sae_escalation is None
    assert safety.monitors_renal_function is None
    assert safety.has_cv_adjudication is None


def test_protocol_document_holds_all_new_facet_results() -> None:
    citation = Citation(
        page_number=SAMPLE_PAGE_NUMBER,
        quote="Primary analysis on Full Analysis Set using MMRM.",
        is_verified=True,
    )
    estimands = EstimandExtraction(
        estimands=[
            Estimand(
                endpoint_kind=EndpointKind.PRIMARY,
                endpoint_description="Change in HbA1c at Week 26",
                intercurrent_events=[
                    IntercurrentEvent(
                        event_type=IntercurrentEventType.RESCUE_MEDICATION,
                        event="Initiation of rescue medication",
                        strategy=EstimandStrategy.TREATMENT_POLICY,
                        citation=citation,
                    )
                ],
            )
        ]
    )
    interventions = InterventionExtraction(
        arms=[
            InterventionArm(
                name="Active Drug 10 mg",
                intervention_type=InterventionType.DRUG,
                drug_class=DrugClass.SGLT2_INHIBITOR,
                is_control=False,
                citation=citation,
            )
        ],
        stratification_factors=[
            StratificationFactorItem(
                category=StratificationFactorType.BASELINE_HBA1C,
                label="Baseline HbA1c (<8.5% vs >=8.5%)",
                citation=citation,
            )
        ],
    )
    analysis = AnalysisPlanExtraction(
        analysis_sets=[
            AnalysisSetItem(
                category=AnalysisSetType.FULL_ANALYSIS,
                label="Full Analysis Set (FAS)",
                citation=citation,
            )
        ],
        prespecified_subgroups=[
            SubgroupItem(
                category=SubgroupDimension.AGE,
                label="Age (<65 vs >=65 years)",
                citation=citation,
            )
        ],
    )
    synopsis = SynopsisConsistencyExtraction(
        synopsis_committees=[
            CommitteeItem(
                category=CommitteeType.DATA_MONITORING,
                label="Independent Data Monitoring Committee",
                citation=citation,
            )
        ],
        schema_epochs=[
            TrialEpoch(
                epoch_type=EpochType.TREATMENT,
                name="Double-blind treatment period",
                duration_weeks=26.0,
                citation=citation,
            )
        ],
    )
    safety = SafetyMonitoringExtraction(
        defines_hypoglycemia_levels=CitedValue[bool](
            value=True, citation=citation
        )
    )
    document = ProtocolDocument(
        protocol_id="proto-002",
        title="Extended Protocol Document",
        page_count=SAMPLE_PAGE_COUNT,
        pages=[PageText(page_number=1, text="Page 1")],
        subsections=[],
        estimands=estimands,
        interventions=interventions,
        analysis=analysis,
        synopsis_check=synopsis,
        safety_monitoring=safety,
    )
    assert document.estimands == estimands
    assert document.interventions == interventions
    assert document.analysis == analysis
    assert document.synopsis_check == synopsis
    assert document.safety_monitoring == safety
