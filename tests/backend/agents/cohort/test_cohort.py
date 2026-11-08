"""Tests for Step 3 Cohort Comparison (Part 1 & Part 2) and Doctor HITL."""

import asyncio
from pathlib import Path

import pytest

from backend.agents.cohort.agent import (
    CompiledRuleList,
    analyze_protocol_cohort,
    analyze_protocol_document_cohort,
    compile_rules_with_llm_fallback,
    record_doctor_cohort_decision,
    to_api_recommendations,
)
from backend.agents.cohort.logic import (
    build_cohort_comparison_report,
    compile_criterion_to_rule,
    compile_protocol_criteria,
    filter_cohort,
)
from backend.agents.cohort.models import (
    AtomicPredicate,
    CohortVariable,
    ComparisonOperator,
    CriterionClassification,
    CriterionType,
    DecisionStatus,
    DoctorOptionKind,
    EligibilityRule,
    FeasibilityStatus,
    ProtocolCriterionInput,
    RuleSimulability,
)
from backend.clients.cohort_data import (
    load_nhanes_diabetes_cohort,
    load_peer_diabetes_protocols,
    parse_registry_study_to_peer_protocol,
)


class _MockLlmClient:
    """Deterministic mock LLM client for testing rule compilation fallback."""

    def __init__(self, rules_to_return: list[EligibilityRule]) -> None:
        self._rules = rules_to_return

    async def generate_json(
        self,
        prompt: str,
        response_model: type[CompiledRuleList],
    ) -> CompiledRuleList:
        assert "Criteria to compile:" in prompt
        payload = CompiledRuleList(rules=self._rules)
        return response_model.model_validate(payload.model_dump())


def test_nhanes_cohort_loads_complete_nan_free_patients() -> None:
    patients = load_nhanes_diabetes_cohort()
    peers = load_peer_diabetes_protocols()

    assert len(patients) == 3485
    assert len(peers) == 5

    # Verify cohort is strictly adult (age >= 18) and includes seniors (65+)
    assert all(p.age >= 18 for p in patients)
    assert any(p.age >= 65 for p in patients)


def test_compile_criterion_to_rule_translates_clinical_thresholds() -> None:
    hba1c_crit = ProtocolCriterionInput(
        criterion_id="IN-01",
        kind=CriterionType.INCLUSION,
        text="HbA1c between 7.0% and 10.5% at screening",
        page_number=22,
    )
    hba1c_rule = compile_criterion_to_rule(hba1c_crit)
    assert hba1c_rule.simulability == RuleSimulability.SIMULATABLE
    assert len(hba1c_rule.predicates) == 1
    assert hba1c_rule.predicates[0].variable == CohortVariable.HBA1C
    assert hba1c_rule.predicates[0].operator == ComparisonOperator.BETWEEN
    assert hba1c_rule.predicates[0].value == 7.0
    assert hba1c_rule.predicates[0].upper_value == 10.5

    egfr_crit = ProtocolCriterionInput(
        criterion_id="EX-01",
        kind=CriterionType.EXCLUSION,
        text="Creatinine clearance / eGFR < 60 mL/min/1.73m2",
        page_number=23,
    )
    egfr_rule = compile_criterion_to_rule(egfr_crit)
    assert egfr_rule.simulability == RuleSimulability.SIMULATABLE
    assert egfr_rule.predicates[0].variable == CohortVariable.EGFR
    assert egfr_rule.predicates[0].operator == ComparisonOperator.GTE
    assert egfr_rule.predicates[0].value == 60.0

    uln_crit = ProtocolCriterionInput(
        criterion_id="EX-02",
        kind=CriterionType.EXCLUSION,
        text="Hepatic impairment defined as ALT > 3.0x ULN",
        page_number=23,
    )
    uln_rule = compile_criterion_to_rule(uln_crit)
    assert uln_rule.predicates[0].variable == CohortVariable.ALT
    assert uln_rule.predicates[0].operator == ComparisonOperator.LTE
    assert uln_rule.predicates[0].value == 120.0


def test_compile_criterion_flags_administrative_and_unsimulatable() -> None:
    admin_crit = ProtocolCriterionInput(
        criterion_id="IN-99",
        kind=CriterionType.INCLUSION,
        text="Participant is willing and able to sign informed consent",
        page_number=20,
    )
    admin_rule = compile_criterion_to_rule(admin_crit)
    assert (
        admin_rule.simulability == RuleSimulability.ADMINISTRATIVE_NON_CLINICAL
    )
    assert admin_rule.predicates == []

    exotic_crit = ProtocolCriterionInput(
        criterion_id="EX-99",
        kind=CriterionType.EXCLUSION,
        text="12-lead ECG showing QTcF interval > 450 ms at screening",
        page_number=24,
    )
    exotic_rule = compile_criterion_to_rule(exotic_crit)
    assert exotic_rule.simulability == RuleSimulability.REQUIRES_DOCTOR_REVIEW
    assert exotic_rule.doctor_review_note is not None
    assert "HUMAN-IN-THE-LOOP REQUIRED" in exotic_rule.doctor_review_note


def test_part2_separates_normal_criteria_from_bottlenecks() -> None:
    patients = load_nhanes_diabetes_cohort()
    peers = load_peer_diabetes_protocols()

    # Protocol with normal HbA1c window, overly strict eGFR (< 85 excluded),
    # overly strict BMI (> 28 excluded), and an unsimulatable ECG rule
    criteria = [
        ProtocolCriterionInput(
            criterion_id="IN-01",
            kind=CriterionType.INCLUSION,
            text="Adults with Type 2 diabetes mellitus",
            page_number=10,
        ),
        ProtocolCriterionInput(
            criterion_id="IN-02",
            kind=CriterionType.INCLUSION,
            text="HbA1c between 7.0% and 10.5%",
            page_number=10,
        ),
        ProtocolCriterionInput(
            criterion_id="EX-01",
            kind=CriterionType.EXCLUSION,
            text="Impaired renal function with eGFR < 85 mL/min/1.73m2",
            page_number=11,
            quote="Impaired renal function with eGFR < 85 mL/min/1.73m2",
        ),
        ProtocolCriterionInput(
            criterion_id="IN-03",
            kind=CriterionType.INCLUSION,
            text="BMI <= 28.0 kg/m2 at baseline",
            page_number=11,
        ),
        ProtocolCriterionInput(
            criterion_id="EX-02",
            kind=CriterionType.EXCLUSION,
            text="12-lead ECG QTcF > 450 ms",
            page_number=12,
        ),
    ]

    report = build_cohort_comparison_report(
        protocol_id="PROTO-STRICT-01",
        protocol_title="Strict Phase 3 T2D Trial",
        criteria=criteria,
        patients=patients,
        peer_protocols=peers,
        min_age_years=18.0,
    )

    assert report.base_population_count == len(patients)
    assert report.target_eligible_pct < report.peer_mean_eligible_pct
    assert report.feasibility_status == FeasibilityStatus.HIGH_ACCRUAL_RISK

    funnel_by_id = {
        step.criterion_id: step for step in report.attrition_funnel
    }

    # Standard HbA1c 7.0-10.5% must be classified as NORMAL_FIELD_STANDARD
    assert (
        funnel_by_id["IN-02"].classification
        == CriterionClassification.NORMAL_FIELD_STANDARD
    )

    # Strict eGFR >= 85 and BMI <= 28 must be flagged as PROTOCOL_BOTTLENECK
    assert (
        funnel_by_id["EX-01"].classification
        == CriterionClassification.PROTOCOL_BOTTLENECK
    )
    assert (
        funnel_by_id["IN-03"].classification
        == CriterionClassification.PROTOCOL_BOTTLENECK
    )
    # eGFR >= 85 disproportionately drops Older Adults (Age >= 65)
    assert any(
        "Age >= 65" in imp.subgroup_name
        for imp in funnel_by_id["EX-01"].subgroup_impacts
    )

    # Unsimulatable ECG criterion must be disclosed transparently, not as a
    # fake bottleneck recommendation card without metrics
    assert (
        funnel_by_id["EX-02"].classification
        == CriterionClassification.UNSIMULATABLE_NEEDS_REVIEW
    )
    assert len(report.unsimulatable_criteria_for_doctor) == 1
    assert len(report.data_transparency_notices) == 1
    assert "EX-02" in report.data_transparency_notices[0]

    # Recommendations must only include actionable bottleneck what-if cards
    rec_by_crit = {r.criterion_id: r for r in report.recommendations}
    assert "EX-01" in rec_by_crit
    assert "IN-03" in rec_by_crit
    assert "EX-02" not in rec_by_crit

    egfr_card = rec_by_crit["EX-01"]
    option_kinds = {opt.kind for opt in egfr_card.doctor_options}
    assert DoctorOptionKind.RELAX_TO_PEER_STANDARD in option_kinds
    assert DoctorOptionKind.RELAX_TO_PEER_MEDIAN in option_kinds

    relax_opt = egfr_card.doctor_options[0]
    assert relax_opt.what_if_simulation is not None
    assert relax_opt.what_if_simulation.patients_gained > 50

    peer_med_opt = next(
        opt
        for opt in egfr_card.doctor_options
        if opt.kind == DoctorOptionKind.RELAX_TO_PEER_MEDIAN
    )
    assert peer_med_opt.what_if_simulation is not None
    assert peer_med_opt.what_if_simulation.patients_gained > 50

    api_dict = egfr_card.to_api_recommendation_dict()
    assert api_dict["source_step"] == "cohort"
    assert api_dict["protocol_id"] == "PROTO-STRICT-01"


def test_doctor_human_in_the_loop_decision_and_traceability() -> None:
    criteria = [
        ProtocolCriterionInput(
            criterion_id="IN-01",
            kind=CriterionType.INCLUSION,
            text="HbA1c between 7.0% and 10.5%",
            page_number=22,
        ),
        ProtocolCriterionInput(
            criterion_id="EX-01",
            kind=CriterionType.EXCLUSION,
            text="eGFR < 85 mL/min/1.73m2",
            page_number=22,
        ),
    ]
    report = asyncio.run(
        analyze_protocol_cohort(
            protocol_id="PROTO-HITL",
            protocol_title="HITL Test Protocol",
            criteria=criteria,
            min_age_years=18.0,
        )
    )
    initial_eligible = report.target_eligible_count
    egfr_rec = next(
        r for r in report.recommendations if r.criterion_id == "EX-01"
    )

    # Empty doctor comment must fail loudly for traceability
    with pytest.raises(ValueError, match="doctor_comment is required"):
        record_doctor_cohort_decision(
            report=report,
            recommendation_id=egfr_rec.recommendation_id,
            decision_status=DecisionStatus.REJECTED,
            doctor_comment="   ",
        )

    # Accepting the peer-standard relaxation updates the cohort and logs trace
    updated = record_doctor_cohort_decision(
        report=report,
        recommendation_id=egfr_rec.recommendation_id,
        decision_status=DecisionStatus.ACCEPTED,
        selected_option_id="EX-01-OPT-RELAX",
        doctor_comment=(
            "Approved relaxation to eGFR >= 45 mL/min/1.73m2 with Week-2 "
            "renal safety panel per Medical Monitor review."
        ),
    )
    assert updated.target_eligible_count > initial_eligible
    assert len(updated.decision_audit_log) == 1
    trace = updated.decision_audit_log[0]
    assert trace.criterion_id == "EX-01"
    assert trace.decision_status == DecisionStatus.ACCEPTED
    assert trace.eligible_pct_after > trace.eligible_pct_before


def test_llm_fallback_resolves_custom_criterion() -> None:
    criteria = [
        ProtocolCriterionInput(
            criterion_id="CUSTOM-01",
            kind=CriterionType.INCLUSION,
            text="Glycated hemoglobin level in the 7.5 to 9.5 range",
            page_number=5,
        )
    ]
    mock_rule = EligibilityRule(
        criterion_id="CUSTOM-01",
        kind=CriterionType.INCLUSION,
        original_text=criteria[0].text,
        page_number=5,
        simulability=RuleSimulability.SIMULATABLE,
        predicates=[
            AtomicPredicate(
                variable=CohortVariable.HBA1C,
                operator=ComparisonOperator.BETWEEN,
                value=7.5,
                upper_value=9.5,
                unit="%",
            )
        ],
    )
    rules = asyncio.run(
        compile_rules_with_llm_fallback(
            criteria=criteria,
            llm_client=_MockLlmClient([mock_rule]),
        )
    )
    assert len(rules) == 1
    assert rules[0].simulability == RuleSimulability.SIMULATABLE
    assert rules[0].predicates[0].variable == CohortVariable.HBA1C


def test_filter_cohort_supports_fame_d_demo_protocol() -> None:
    patients = load_nhanes_diabetes_cohort()

    # FAME-D demo protocol (NCT04828785: adults >= 18, food insecurity)
    fame_d_rules = compile_protocol_criteria(
        [
            ProtocolCriterionInput(
                criterion_id="IN-01",
                kind=CriterionType.INCLUSION,
                text="HbA1c >= 7.0% and <= 11.5%",
                page_number=22,
            ),
            ProtocolCriterionInput(
                criterion_id="IN-02",
                kind=CriterionType.INCLUSION,
                text="Positive screen on Hunger Vital Sign (food insecurity)",
                page_number=22,
            ),
        ],
        min_age_years=18.0,
    )
    fame_d_eligible, _ = filter_cohort(patients, fame_d_rules)
    assert len(fame_d_eligible) > 100
    assert all(p.age >= 18 and p.food_insecure for p in fame_d_eligible)


def test_theo_registry_study_parser_and_json_export(tmp_path: Path) -> None:
    adult_study_payload: dict[str, object] = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT09999999",
                "briefTitle": "Adult T2D SGLT2 Comparator Trial",
            },
            "statusModule": {"overallStatus": "COMPLETED"},
            "designModule": {
                "phases": ["PHASE3"],
                "enrollmentInfo": {"count": 850},
            },
            "conditionsModule": {"conditions": ["Type 2 Diabetes"]},
            "eligibilityModule": {
                "minimumAge": "18 Years",
                "maximumAge": "75 Years",
                "stdAges": ["ADULT", "OLDER_ADULT"],
                "eligibilityCriteria": (
                    "Inclusion Criteria:\n"
                    "* Adults with Type 2 Diabetes Mellitus\n"
                    "* HbA1c between 7.0% and 10.0%\n"
                    "Exclusion Criteria:\n"
                    "* eGFR < 45 mL/min/1.73m2\n"
                ),
            },
        },
        "derivedSection": {
            "conditionBrowseModule": {
                "meshes": [{"term": "Diabetes Mellitus, Type 2"}]
            }
        },
    }
    parsed_adult = parse_registry_study_to_peer_protocol(adult_study_payload)
    assert parsed_adult is not None
    assert parsed_adult.nct_id == "NCT09999999"
    assert parsed_adult.min_age_years == 18.0
    assert len(parsed_adult.criteria) == 3

    # Pediatric registry study must be filtered out automatically
    peds_study_payload: dict[str, object] = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT03170518",
                "briefTitle": "Pediatric Canagliflozin Trial",
            },
            "eligibilityModule": {
                "minimumAge": "10 Years",
                "maximumAge": "17 Years",
                "stdAges": ["CHILD"],
                "eligibilityCriteria": "Inclusion Criteria:\n* HbA1c >= 7.0%",
            },
        }
    }
    assert parse_registry_study_to_peer_protocol(peds_study_payload) is None

    # Verify JSON export and API Recommendation conversion
    out_json = tmp_path / "cohort_recommendations.json"
    report = asyncio.run(
        analyze_protocol_cohort(
            protocol_id="PROTO-EXPORT",
            protocol_title="Export Test Protocol",
            criteria=[
                ProtocolCriterionInput(
                    criterion_id="EX-01",
                    kind=CriterionType.EXCLUSION,
                    text="eGFR < 80 mL/min/1.73m2",
                    page_number=15,
                )
            ],
            min_age_years=18.0,
            recommendations_output_path=out_json,
        )
    )
    assert out_json.exists()
    api_recs = to_api_recommendations(report)
    assert len(api_recs) == 1
    assert api_recs[0].source_step.value == "cohort"
    assert api_recs[0].protocol_id == "PROTO-EXPORT"


def test_analyze_protocol_document_cohort_from_parser_output() -> None:
    from backend.shared.messages import (
        Citation,
        CitedValue,
        CriterionKind,
        EligibilityCriterion,
        ProtocolDocument,
        TrialDesignFacts,
    )

    doc = ProtocolDocument(
        protocol_id="NCT04828785",
        title="FAME-D Trial",
        page_count=30,
        pages=[],
        design=TrialDesignFacts(
            min_age_years=CitedValue(
                value=18.0,
                citation=Citation(
                    page_number=22,
                    quote="aged >= 18 years",
                    is_verified=True,
                ),
            ),
        ),
        eligibility_criteria=[
            EligibilityCriterion(
                criterion_id="IN-01",
                kind=CriterionKind.INCLUSION,
                text="HbA1c between 7.0% and 10.5%",
                citation=Citation(
                    page_number=22,
                    quote="HbA1c between 7.0% and 10.5%",
                    is_verified=True,
                ),
            ),
            EligibilityCriterion(
                criterion_id="EX-01",
                kind=CriterionKind.EXCLUSION,
                text="eGFR < 80 mL/min/1.73m2",
                citation=Citation(
                    page_number=23,
                    quote="eGFR < 80 mL/min/1.73m2",
                    is_verified=True,
                ),
            ),
        ],
    )

    report = asyncio.run(analyze_protocol_document_cohort(doc))
    assert report.protocol_id == "NCT04828785"
    assert report.base_population_count == 3485
    assert len(report.recommendations) == 1
    assert report.recommendations[0].criterion_id == "EX-01"
