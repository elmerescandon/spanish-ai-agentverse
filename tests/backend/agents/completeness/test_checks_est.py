"""Unit tests for Family EST deterministic checks (15 rules)."""

import pytest

from backend.agents.completeness.checks.estimands import (
    check_est_02,
    check_est_03,
    check_est_04,
    check_est_06,
    check_est_10,
    check_est_11,
    check_est_14,
    check_est_16,
    check_est_17,
    check_est_18,
    check_est_19,
    check_est_20,
    check_est_21,
    check_est_22,
    check_est_26,
)
from backend.shared.messages import (
    AnalysisPlanExtraction,
    AnalysisSetType,
    CommitteeType,
    EndpointKind,
    EstimandExtraction,
    EstimandStrategy,
    IntercurrentEventType,
    InterventionExtraction,
    RuleStatus,
    SafetyMonitoringExtraction,
    StatisticalAssumptions,
    StratificationFactorType,
    SubgroupDimension,
    SynopsisConsistencyExtraction,
)
from tests.backend.agents.completeness.factories import (
    cited,
    make_analysis_sets,
    make_committees,
    make_document,
    make_endpoint,
    make_estimand,
    make_ice,
    make_profile,
    make_strata,
    make_subgroups,
)


def test_est_02_passes_with_four_core_attributes_and_fires_when_missing() -> (
    None
):
    complete = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()])
    )
    missing_summary = make_document(
        estimands=EstimandExtraction(
            estimands=[make_estimand(population_level_summary=None)]
        )
    )

    passed = check_est_02(complete, make_profile())
    fired = check_est_02(missing_summary, make_profile())
    unassessed = check_est_02(make_document(estimands=None), make_profile())

    assert passed.status == RuleStatus.PASSED
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True
    assert "population_level_summary" in fired.finding
    assert unassessed.status == RuleStatus.CANNOT_ASSESS


def test_est_03_passes_with_timepoint_and_fires_without_timepoint() -> None:
    with_time = make_document(
        estimands=EstimandExtraction(
            estimands=[
                make_estimand(
                    variable="Change from baseline in HbA1c at Week 26"
                )
            ]
        )
    )
    without_time = make_document(
        estimands=EstimandExtraction(
            estimands=[
                make_estimand(
                    endpoint_description="Change from baseline in HbA1c",
                    variable="Change from baseline in HbA1c",
                )
            ]
        )
    )

    passed = check_est_03(with_time, make_profile())
    fired = check_est_03(without_time, make_profile())

    assert passed.status == RuleStatus.PASSED
    assert fired.status == RuleStatus.FIRED
    assert len(fired.evidence) == 1


def test_est_04_handles_strategies_missing_strategy_and_other() -> None:
    valid = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()])
    )
    no_strategy = make_document(
        estimands=EstimandExtraction(
            estimands=[
                make_estimand(
                    intercurrent_events=[
                        make_ice(
                            IntercurrentEventType.RESCUE_MEDICATION,
                            strategy=None,
                        )
                    ]
                )
            ]
        )
    )
    other_strategy = make_document(
        estimands=EstimandExtraction(
            estimands=[
                make_estimand(
                    intercurrent_events=[
                        make_ice(
                            IntercurrentEventType.RESCUE_MEDICATION,
                            strategy=EstimandStrategy.OTHER,
                        )
                    ]
                )
            ]
        )
    )

    assert check_est_04(valid, make_profile()).status == RuleStatus.PASSED
    fired = check_est_04(no_strategy, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True
    assert (
        check_est_04(other_strategy, make_profile()).status
        == RuleStatus.CANNOT_ASSESS
    )


def test_est_06_checks_secondary_estimands() -> None:
    sec_ep = make_endpoint(
        description="Change from baseline in FPG at Week 26",
        kind=EndpointKind.SECONDARY,
    )
    sec_est = make_estimand(
        endpoint_kind=EndpointKind.SECONDARY,
        endpoint_description="Change from baseline in FPG at Week 26",
        variable="Change from baseline in FPG at Week 26",
    )
    passed_doc = make_document(
        endpoints=[sec_ep],
        estimands=EstimandExtraction(estimands=[sec_est]),
    )
    fired_doc = make_document(
        endpoints=[sec_ep],
        estimands=EstimandExtraction(estimands=[make_estimand()]),
    )
    no_sec_doc = make_document(
        endpoints=[make_endpoint(kind=EndpointKind.PRIMARY)],
        estimands=EstimandExtraction(estimands=[make_estimand()]),
    )

    assert check_est_06(passed_doc, make_profile()).status == RuleStatus.PASSED
    fired = check_est_06(fired_doc, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True
    assert (
        check_est_06(no_sec_doc, make_profile()).status
        == RuleStatus.NOT_APPLICABLE
    )


def test_est_10_checks_four_analysis_sets_and_other() -> None:
    all_four = make_document(
        analysis=AnalysisPlanExtraction(
            analysis_sets=make_analysis_sets(
                (AnalysisSetType.RANDOMIZED, "Randomized Set"),
                (AnalysisSetType.FULL_ANALYSIS, "Full Analysis Set"),
                (AnalysisSetType.PER_PROTOCOL, "Per-Protocol Set"),
                (AnalysisSetType.SAFETY, "Safety Set"),
            )
        )
    )
    missing_pp = make_document(
        analysis=AnalysisPlanExtraction(
            analysis_sets=make_analysis_sets(
                (AnalysisSetType.FULL_ANALYSIS, "Full Analysis Set"),
                (AnalysisSetType.SAFETY, "Safety Set"),
            )
        )
    )
    with_other = make_document(
        analysis=AnalysisPlanExtraction(
            analysis_sets=make_analysis_sets(
                (AnalysisSetType.FULL_ANALYSIS, "Full Analysis Set"),
                (AnalysisSetType.OTHER, "Modified Completers Set"),
            )
        )
    )

    assert check_est_10(all_four, make_profile()).status == RuleStatus.PASSED
    fired = check_est_10(missing_pp, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert "PER_PROTOCOL" in fired.finding
    assert fired.needs_second_opinion is True
    assert (
        check_est_10(with_other, make_profile()).status
        == RuleStatus.CANNOT_ASSESS
    )


def test_est_11_checks_primary_model_covariates_and_baseline() -> None:
    complete = make_document(
        analysis=AnalysisPlanExtraction(
            primary_analysis_method=cited("MMRM"),
            primary_analysis_covariates=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "Baseline HbA1c")
            ),
            adjusts_for_baseline=cited(True),
        )
    )
    incomplete = make_document(
        analysis=AnalysisPlanExtraction(
            primary_analysis_method=cited("MMRM"),
            primary_analysis_covariates=[],
            adjusts_for_baseline=None,
        )
    )

    assert check_est_11(complete, make_profile()).status == RuleStatus.PASSED
    fired = check_est_11(incomplete, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True


def test_est_14_checks_sensitivity_analyses_present() -> None:
    present = make_document(
        analysis=AnalysisPlanExtraction(
            sensitivity_analyses=[cited("Tipping-point multiple imputation")]
        )
    )
    absent = make_document(
        analysis=AnalysisPlanExtraction(sensitivity_analyses=[])
    )

    assert check_est_14(present, make_profile()).status == RuleStatus.PASSED
    fired = check_est_14(absent, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True


def test_est_16_checks_multiplicity_control_across_hypotheses() -> None:
    controlled = make_document(
        endpoints=[
            make_endpoint(kind=EndpointKind.PRIMARY),
            make_endpoint(
                description="Change from baseline in body weight",
                kind=EndpointKind.SECONDARY,
            ),
        ],
        analysis=AnalysisPlanExtraction(
            controls_type_i_error=cited(True),
            confirmatory_hierarchy=cited("Fixed-sequence testing"),
        ),
    )
    uncontrolled = make_document(
        endpoints=[
            make_endpoint(kind=EndpointKind.PRIMARY),
            make_endpoint(
                description="Change from baseline in FPG",
                kind=EndpointKind.PRIMARY,
            ),
        ],
        analysis=AnalysisPlanExtraction(controls_type_i_error=None),
    )
    single_primary = make_document(
        endpoints=[make_endpoint(kind=EndpointKind.PRIMARY)],
        analysis=AnalysisPlanExtraction(),
    )

    assert check_est_16(controlled, make_profile()).status == RuleStatus.PASSED
    fired = check_est_16(uncontrolled, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True
    assert (
        check_est_16(single_primary, make_profile()).status
        == RuleStatus.NOT_APPLICABLE
    )


def test_est_17_checks_interim_analysis_alpha_spending_and_dmc() -> None:
    no_interim = make_document(
        analysis=AnalysisPlanExtraction(has_interim_analysis=cited(False))
    )
    valid_interim = make_document(
        analysis=AnalysisPlanExtraction(
            has_interim_analysis=cited(True),
            alpha_spending_function=cited("Lan-DeMets O'Brien-Fleming"),
        ),
        synopsis_check=SynopsisConsistencyExtraction(
            governance_committees=make_committees(
                (CommitteeType.DATA_MONITORING, "Independent DMC")
            )
        ),
    )
    missing_alpha = make_document(
        analysis=AnalysisPlanExtraction(
            has_interim_analysis=cited(True),
            alpha_spending_function=None,
        )
    )

    assert (
        check_est_17(no_interim, make_profile()).status
        == RuleStatus.NOT_APPLICABLE
    )
    assert (
        check_est_17(valid_interim, make_profile()).status == RuleStatus.PASSED
    )
    fired = check_est_17(missing_alpha, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True


def test_est_18_checks_randomisation_strata_in_model_covariates() -> None:
    aligned = make_document(
        interventions=InterventionExtraction(
            stratification_factors=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "HbA1c"),
                (StratificationFactorType.REGION, "Region"),
            )
        ),
        analysis=AnalysisPlanExtraction(
            primary_analysis_covariates=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "HbA1c"),
                (StratificationFactorType.REGION, "Region"),
                (StratificationFactorType.AGE, "Age"),
            )
        ),
    )
    missing_stratum = make_document(
        interventions=InterventionExtraction(
            stratification_factors=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "HbA1c"),
                (StratificationFactorType.REGION, "Region"),
            )
        ),
        analysis=AnalysisPlanExtraction(
            primary_analysis_covariates=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "HbA1c")
            )
        ),
    )
    other_stratum = make_document(
        interventions=InterventionExtraction(
            stratification_factors=make_strata(
                (StratificationFactorType.OTHER, "Baseline C-peptide")
            )
        ),
        analysis=AnalysisPlanExtraction(
            primary_analysis_covariates=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "HbA1c")
            )
        ),
    )

    assert check_est_18(aligned, make_profile()).status == RuleStatus.PASSED
    fired = check_est_18(missing_stratum, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert "REGION" in fired.finding
    assert (
        check_est_18(other_stratum, make_profile()).status
        == RuleStatus.CANNOT_ASSESS
    )


def test_est_19_checks_six_prespecified_subgroups_and_other() -> None:
    all_six = make_document(
        analysis=AnalysisPlanExtraction(
            prespecified_subgroups=make_subgroups(
                (SubgroupDimension.SEX, "Sex"),
                (SubgroupDimension.AGE, "Age"),
                (SubgroupDimension.RACE, "Race"),
                (SubgroupDimension.ETHNICITY, "Ethnicity"),
                (SubgroupDimension.BASELINE_HBA1C, "Baseline HbA1c"),
                (SubgroupDimension.DIABETES_DURATION, "Diabetes duration"),
            )
        )
    )
    incomplete = make_document(
        analysis=AnalysisPlanExtraction(
            prespecified_subgroups=make_subgroups(
                (SubgroupDimension.SEX, "Sex"),
                (SubgroupDimension.AGE, "Age"),
            )
        )
    )
    with_other = make_document(
        analysis=AnalysisPlanExtraction(
            prespecified_subgroups=make_subgroups(
                (SubgroupDimension.OTHER, "Geographical sub-region")
            )
        )
    )

    assert check_est_19(all_six, make_profile()).status == RuleStatus.PASSED
    fired = check_est_19(incomplete, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert "DIABETES_DURATION" in fired.finding
    assert fired.needs_second_opinion is True
    empty_subgroups = make_document(
        analysis=AnalysisPlanExtraction(prespecified_subgroups=[])
    )
    fired_all_six = check_est_19(empty_subgroups, make_profile())
    assert fired_all_six.status == RuleStatus.FIRED
    assert "and 1 more" in fired_all_six.finding
    assert (
        check_est_19(with_other, make_profile()).status
        == RuleStatus.CANNOT_ASSESS
    )


def test_est_20_checks_safety_analysis_set_and_hypoglycemia_plan() -> None:
    complete = make_document(
        analysis=AnalysisPlanExtraction(
            analysis_sets=make_analysis_sets(
                (AnalysisSetType.SAFETY, "Safety Analysis Set")
            )
        ),
        safety_monitoring=SafetyMonitoringExtraction(
            defines_hypoglycemia_levels=cited(True)
        ),
    )
    missing_hypo = make_document(
        analysis=AnalysisPlanExtraction(
            analysis_sets=make_analysis_sets(
                (AnalysisSetType.SAFETY, "Safety Analysis Set")
            )
        ),
        safety_monitoring=SafetyMonitoringExtraction(
            defines_hypoglycemia_levels=None
        ),
    )

    assert check_est_20(complete, make_profile()).status == RuleStatus.PASSED
    fired = check_est_20(missing_hypo, make_profile())
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True


def test_est_21_and_est_22_check_sample_size_calculation_and_inputs() -> None:
    complete_stats = StatisticalAssumptions(
        sample_size=cited(216),
        power=cited(0.90),
        alpha=cited(0.05),
        dropout_rate=cited(0.10),
        effect_size=cited("0.5%"),
        effect_size_value=cited(0.5),
        standard_deviation=cited(1.0),
        allocation_ratio=cited(1.0),
        is_two_sided=cited(True),
        has_sample_size_calculation=cited(True),
    )
    complete_doc = make_document(statistics=complete_stats)
    no_calc_doc = make_document(
        statistics=StatisticalAssumptions(
            sample_size=cited(200),
            has_sample_size_calculation=None,
            power=None,
        )
    )

    assert (
        check_est_21(complete_doc, make_profile()).status == RuleStatus.PASSED
    )
    assert (
        check_est_22(complete_doc, make_profile()).status == RuleStatus.PASSED
    )

    fired_21 = check_est_21(no_calc_doc, make_profile())
    fired_22 = check_est_22(no_calc_doc, make_profile())
    assert fired_21.status == RuleStatus.FIRED
    assert fired_21.needs_second_opinion is True
    assert fired_22.status == RuleStatus.FIRED
    assert fired_22.needs_second_opinion is True
    assert "standard_deviation" in fired_22.finding


def test_est_26_recomputes_sample_size_and_flags_over_five_percent_diff() -> (
    None
):
    # For delta=0.5, sd=1.0, alpha=0.05 (2-sided), power=0.90, r=1.0,
    # dropout=0.10: n_complete ~= 4 * (1.96 + 1.2816)^2 * (1.0/0.5)^2 ~= 168.1;
    # n_enrolled = 168.1 / 0.90 ~= 187.
    consistent_doc = make_document(
        statistics=StatisticalAssumptions(
            sample_size=cited(188),
            power=cited(0.90),
            alpha=cited(0.05),
            dropout_rate=cited(0.10),
            effect_size_value=cited(0.5),
            standard_deviation=cited(1.0),
            allocation_ratio=cited(1.0),
            is_two_sided=cited(True),
        )
    )
    discrepant_doc = make_document(
        statistics=StatisticalAssumptions(
            sample_size=cited(120),
            power=cited(0.90),
            alpha=cited(0.05),
            dropout_rate=cited(0.10),
            effect_size_value=cited(0.5),
            standard_deviation=cited(1.0),
            allocation_ratio=cited(1.0),
            is_two_sided=cited(True),
        )
    )

    passed = check_est_26(consistent_doc, make_profile())
    fired = check_est_26(discrepant_doc, make_profile())

    assert passed.status == RuleStatus.PASSED
    assert fired.status == RuleStatus.FIRED
    assert fired.needs_second_opinion is True
    assert "120" in fired.finding
    assert "187" in fired.finding


@pytest.mark.parametrize(
    "missing_field",
    [
        "sample_size",
        "alpha",
        "power",
        "effect_size_value",
        "standard_deviation",
        "is_two_sided",
        "allocation_ratio",
        "dropout_rate",
    ],
)
def test_est_26_cannot_assess_when_any_required_input_is_none(
    missing_field: str,
) -> None:
    """EST-26 returns CANNOT_ASSESS naming any missing input."""
    base_kwargs = {
        "sample_size": cited(188),
        "power": cited(0.90),
        "alpha": cited(0.05),
        "dropout_rate": cited(0.10),
        "effect_size_value": cited(0.5),
        "standard_deviation": cited(1.0),
        "allocation_ratio": cited(1.0),
        "is_two_sided": cited(True),
    }
    base_kwargs[missing_field] = None
    doc = make_document(statistics=StatisticalAssumptions(**base_kwargs))

    outcome = check_est_26(doc, make_profile())

    assert outcome.status == RuleStatus.CANNOT_ASSESS
    assert outcome.status_reason is not None
    assert missing_field in outcome.status_reason
