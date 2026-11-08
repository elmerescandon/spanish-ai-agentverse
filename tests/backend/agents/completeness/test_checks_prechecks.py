"""Unit tests for measurable judgement pre-checks in checks/prechecks.py."""

from backend.agents.completeness.checks.prechecks import (
    JUDGEMENT_PRECHECKS,
    precheck_dm_01,
    precheck_dm_02,
    precheck_dm_11,
    precheck_dm_12,
    precheck_dm_15,
    precheck_dm_20,
    precheck_dm_32,
    precheck_dm_43,
    precheck_est_07,
    precheck_est_08,
    precheck_est_13,
    precheck_est_23,
    precheck_est_24,
    precheck_est_25,
    precheck_reg_17,
    precheck_reg_21,
    precheck_reg_39,
)
from backend.agents.completeness.rules import load_rule_catalogue
from backend.shared.messages import (
    AllocationType,
    AnalysisPlanExtraction,
    CheckMethod,
    ControlType,
    DrugClass,
    EndpointKind,
    EstimandExtraction,
    EstimandStrategy,
    IntercurrentEventType,
    InterventionExtraction,
    InterventionModelType,
    M11Heading,
    MaskingType,
    PageText,
    ProtocolDocument,
    RuleStatus,
    StatisticalAssumptions,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
    TrialPhase,
)
from tests.backend.agents.completeness.factories import (
    cited,
    make_arm,
    make_document,
    make_endpoint,
    make_estimand,
    make_ice,
    make_profile,
    make_section,
)


def test_judgement_prechecks_only_target_judgement_rules() -> None:
    """Every registered precheck corresponds to a check='judgement' rule."""
    catalogue = load_rule_catalogue()
    judgement_ids = {
        rule.id
        for rule in catalogue.rules
        if rule.check == CheckMethod.JUDGEMENT
    }
    assert set(JUDGEMENT_PRECHECKS) <= judgement_ids
    assert len(JUDGEMENT_PRECHECKS) == 27


def test_precheck_est_07_not_applicable_without_secondary_endpoints() -> None:
    """EST-07 is N/A when no secondary endpoints exist, else None."""
    no_sec = make_document(
        endpoints=[make_endpoint(kind=EndpointKind.PRIMARY)]
    )
    outcome = precheck_est_07(no_sec, make_profile())
    assert outcome is not None
    assert outcome.status == RuleStatus.NOT_APPLICABLE

    with_sec = make_document(
        endpoints=[
            make_endpoint(kind=EndpointKind.PRIMARY),
            make_endpoint(
                description="Change in FPG", kind=EndpointKind.SECONDARY
            ),
        ]
    )
    assert precheck_est_07(with_sec, make_profile()) is None


def test_precheck_est_08_passes_on_continuous_change_else_none() -> None:
    """EST-08 passes when primary is continuous change, else None."""
    continuous = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c at Week 26",
                kind=EndpointKind.PRIMARY,
            )
        ]
    )
    outcome = precheck_est_08(continuous, make_profile())
    assert outcome is not None
    assert outcome.status == RuleStatus.PASSED

    responder = make_document(
        endpoints=[
            make_endpoint(
                description="Proportion of patients achieving HbA1c < 7.0%",
                kind=EndpointKind.PRIMARY,
            )
        ]
    )
    assert precheck_est_08(responder, make_profile()) is None


def test_precheck_est_13_fires_when_missing_data_method_absent() -> None:
    """EST-13 fires (absence -> second opinion) if missing_data_method None."""
    absent = make_document(
        analysis=AnalysisPlanExtraction(missing_data_method=None)
    )
    outcome = precheck_est_13(absent, make_profile())
    assert outcome is not None
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is True

    present = make_document(
        analysis=AnalysisPlanExtraction(
            missing_data_method=cited("Multiple imputation under MAR")
        )
    )
    assert precheck_est_13(present, make_profile()) is None


def test_precheck_est_23_passes_with_source_fires_without_else_none() -> None:
    """EST-23 passes when source cited, fires when absent, None if no stats."""
    with_source = make_document(
        statistics=StatisticalAssumptions(
            effect_size_value=cited(0.5),
            assumptions_source_citation=cited("Prior Phase 2 study (Smith)"),
        )
    )
    passed = precheck_est_23(with_source, make_profile())
    assert passed is not None
    assert passed.status == RuleStatus.PASSED

    missing_source = make_document(
        statistics=StatisticalAssumptions(
            effect_size_value=cited(0.5),
            standard_deviation=cited(1.0),
            assumptions_source_citation=None,
        )
    )
    fired = precheck_est_23(missing_source, make_profile())
    assert fired is not None
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True

    assert (
        precheck_est_23(make_document(statistics=None), make_profile()) is None
    )


def test_precheck_est_24_fires_when_ni_margin_absent_else_none() -> None:
    """EST-24 fires when non_inferiority_margin is None, else None."""
    no_margin = make_document(
        statistics=StatisticalAssumptions(non_inferiority_margin=None)
    )
    fired = precheck_est_24(no_margin, make_profile(is_non_inferiority=True))
    assert fired is not None
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True

    with_margin = make_document(
        statistics=StatisticalAssumptions(non_inferiority_margin=cited(0.3))
    )
    assert (
        precheck_est_24(with_margin, make_profile(is_non_inferiority=True))
        is None
    )


def test_precheck_est_25_not_applicable_when_not_treatment_policy() -> None:
    """EST-25 is N/A when no primary ICE uses treatment-policy strategy."""
    hypothetical = make_document(
        estimands=EstimandExtraction(
            estimands=[
                make_estimand(
                    intercurrent_events=[
                        make_ice(
                            IntercurrentEventType.RESCUE_MEDICATION,
                            strategy=EstimandStrategy.HYPOTHETICAL,
                        )
                    ]
                )
            ]
        )
    )
    outcome = precheck_est_25(hypothetical, make_profile())
    assert outcome is not None
    assert outcome.status == RuleStatus.NOT_APPLICABLE

    tp = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()])
    )
    assert precheck_est_25(tp, make_profile()) is None


def test_precheck_dm_01_and_dm_02_pass_on_standard_26w_hba1c() -> None:
    """DM-01 and DM-02 pass when primary is HbA1c change at >= 26 weeks."""
    standard = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                time_frame="Baseline and Week 26",
            )
        ]
    )
    out_01 = precheck_dm_01(standard, make_profile())
    out_02 = precheck_dm_02(standard, make_profile())
    assert out_01 is not None and out_01.status == RuleStatus.PASSED
    assert out_02 is not None and out_02.status == RuleStatus.PASSED

    short_other = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in body weight",
                time_frame="Week 12",
            )
        ]
    )
    assert precheck_dm_01(short_other, make_profile()) is None
    assert precheck_dm_02(short_other, make_profile()) is None


def test_precheck_dm_11_not_applicable_for_add_on_or_short_placebo() -> None:
    """DM-11 is N/A when trial is add-on or <= 13w, else None."""
    doc = make_document()
    add_on_out = precheck_dm_11(doc, make_profile(is_add_on=True))
    assert add_on_out is not None
    assert add_on_out.status == RuleStatus.NOT_APPLICABLE

    mono_long = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            body_treatment_duration_weeks=cited(26.0)
        )
    )
    assert precheck_dm_11(mono_long, make_profile(is_add_on=False)) is None


def test_precheck_dm_12_passes_when_placebo_duration_at_most_26_weeks() -> (
    None
):
    """DM-12 passes when treatment duration <= 26 weeks, else None."""
    short_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            body_treatment_duration_weeks=cited(26.0)
        )
    )
    passed = precheck_dm_12(short_doc, make_profile())
    assert passed is not None
    assert passed.status == RuleStatus.PASSED

    long_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            body_treatment_duration_weeks=cited(52.0)
        )
    )
    assert precheck_dm_12(long_doc, make_profile()) is None


def test_precheck_dm_15_fires_when_margin_exceeds_0_3_or_absent() -> None:
    """DM-15 fires when NI margin > 0.3% or None; returns None at <= 0.3%."""
    wide_doc = make_document(
        statistics=StatisticalAssumptions(non_inferiority_margin=cited(0.4))
    )
    wide_out = precheck_dm_15(wide_doc, make_profile(is_non_inferiority=True))
    assert wide_out is not None
    assert wide_out.status == RuleStatus.FIRED
    assert wide_out.needs_second_opinion is False

    absent_doc = make_document(
        statistics=StatisticalAssumptions(non_inferiority_margin=None)
    )
    absent_out = precheck_dm_15(
        absent_doc, make_profile(is_non_inferiority=True)
    )
    assert absent_out is not None
    assert absent_out.status == RuleStatus.FIRED
    assert absent_out.needs_second_opinion is True

    ok_margin = make_document(
        statistics=StatisticalAssumptions(non_inferiority_margin=cited(0.3))
    )
    assert (
        precheck_dm_15(ok_margin, make_profile(is_non_inferiority=True))
        is None
    )


def test_precheck_dm_20_passes_when_no_placebo_arm_else_none() -> None:
    """DM-20 passes when control_type is not PLACEBO, else None."""
    doc = make_document()
    active_out = precheck_dm_20(
        doc,
        make_profile(
            drug_class=DrugClass.INSULIN, control_type=ControlType.ACTIVE
        ),
    )
    assert active_out is not None
    assert active_out.status == RuleStatus.PASSED

    assert (
        precheck_dm_20(
            doc,
            make_profile(
                drug_class=DrugClass.INSULIN, control_type=ControlType.PLACEBO
            ),
        )
        is None
    )


def test_precheck_dm_32_and_dm_43_not_applicable_cases() -> None:
    """DM-32 is N/A without hypo endpoint; DM-43 is N/A for insulin drug."""
    no_hypo = make_document(
        endpoints=[make_endpoint(description="Change from baseline in HbA1c")]
    )
    out_32 = precheck_dm_32(no_hypo, make_profile())
    assert out_32 is not None
    assert out_32.status == RuleStatus.NOT_APPLICABLE

    with_hypo = make_document(
        endpoints=[
            make_endpoint(
                description="Number of Level 2 hypoglycaemia events",
                kind=EndpointKind.SECONDARY,
            )
        ]
    )
    assert precheck_dm_32(with_hypo, make_profile()) is None

    out_43 = precheck_dm_43(
        no_hypo, make_profile(drug_class=DrugClass.INSULIN)
    )
    assert out_43 is not None
    assert out_43.status == RuleStatus.NOT_APPLICABLE

    assert (
        precheck_dm_43(
            no_hypo, make_profile(drug_class=DrugClass.SGLT2_INHIBITOR)
        )
        is None
    )


def test_reg_17_fires_on_a_missing_design_field_and_defers_otherwise() -> None:
    missing_model = make_document(
        design=TrialDesignFacts(
            phase=cited(TrialPhase.PHASE3),
            allocation=cited(AllocationType.RANDOMIZED),
            masking=cited(MaskingType.DOUBLE),
            arm_count=cited(2),
        )
    )
    complete = make_document(
        design=TrialDesignFacts(
            phase=cited(TrialPhase.PHASE3),
            allocation=cited(AllocationType.RANDOMIZED),
            intervention_model=cited(InterventionModelType.PARALLEL),
            masking=cited(MaskingType.DOUBLE),
            arm_count=cited(2),
        )
    )

    outcome = precheck_reg_17(missing_model, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.FIRED
    assert "intervention model" in outcome.finding
    assert outcome.needs_second_opinion is True
    assert precheck_reg_17(complete, make_profile()) is None


def test_reg_21_fires_on_an_arm_without_dose_and_defers_otherwise() -> None:
    no_dose = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm(), make_arm(name="Placebo", dose_and_regimen=None)]
        )
    )
    dosed = make_document(
        interventions=InterventionExtraction(arms=[make_arm()])
    )

    outcome = precheck_reg_21(no_dose, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.FIRED
    assert "Placebo" in outcome.finding
    assert precheck_reg_21(dosed, make_profile()) is None


def test_reg_39_fires_on_first_person_but_not_on_the_us_country() -> None:
    def summary_doc(text: str) -> ProtocolDocument:
        return make_document(
            pages=[PageText(page_number=1, text=text)],
            sections=[make_section(M11Heading.PROTOCOL_SUMMARY, "1", 1, 1)],
        )

    first_person = summary_doc(
        "In this trial we will compare the study drug with placebo."
    )
    country = summary_doc(
        "Sites in the US and Canada will enrol adult participants."
    )

    outcome = precheck_reg_39(first_person, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.FIRED
    assert outcome.evidence[0].is_verified
    assert precheck_reg_39(country, make_profile()) is None
