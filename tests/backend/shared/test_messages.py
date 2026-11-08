"""Unit tests for the shared parser contract models."""

import pytest
from pydantic import ValidationError

from backend.shared.messages import (
    CheckMethod,
    Citation,
    CitedValue,
    ComplianceReport,
    ControlType,
    DiabetesType,
    DrugClass,
    FindingLocation,
    GateResult,
    GateStatus,
    InterventionType,
    M11Heading,
    PageText,
    ProtocolDocument,
    RuleFamily,
    RuleFinding,
    RuleSeverity,
    RuleStatus,
    RunResult,
    SearchedLocation,
    SourceTier,
    TrialDesignFacts,
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
