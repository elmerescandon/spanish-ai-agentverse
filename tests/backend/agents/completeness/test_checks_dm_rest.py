"""Unit tests for the remaining Family DM code checks and pre-checks."""

from backend.agents.completeness.checks.diabetes import (
    check_dm_04,
    check_dm_07,
    check_dm_08,
    check_dm_24,
    check_dm_25,
    check_dm_26,
    check_dm_29,
    check_dm_39,
    check_dm_40,
)
from backend.agents.completeness.checks.prechecks import (
    precheck_dm_09,
    precheck_dm_10,
    precheck_dm_30,
    precheck_dm_33,
    precheck_dm_35,
    precheck_dm_36,
    precheck_dm_38,
    precheck_dm_42,
)
from backend.shared.messages import (
    AnalysisPlanExtraction,
    DrugClass,
    EndpointKind,
    InterventionExtraction,
    InterventionType,
    PageText,
    ProtocolDocument,
    RuleStatus,
    SafetyMonitoringExtraction,
    StratificationFactorType,
    SubgroupDimension,
    TrialPhase,
)
from tests.backend.agents.completeness.factories import (
    cited,
    make_document,
    make_endpoint,
    make_profile,
    make_strata,
    make_subgroups,
    make_visit,
)


def _pages_doc(text: str) -> ProtocolDocument:
    return make_document(pages=[PageText(page_number=1, text=text)])


# --- DM-04 central NGSP lab --------------------------------------------


def test_dm_04_passes_with_central_lab_and_certified_assay() -> None:
    doc = _pages_doc(
        "HbA1c will be analysed by the central laboratory using an "
        "NGSP-certified method."
    )

    outcome = check_dm_04(doc, make_profile())

    assert outcome.status == RuleStatus.PASSED
    assert len(outcome.evidence) == 2


def test_dm_04_fires_when_certification_is_not_stated() -> None:
    doc = _pages_doc("HbA1c will be analysed by the central laboratory.")

    outcome = check_dm_04(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert "NGSP" in outcome.finding
    assert outcome.needs_second_opinion is True


# --- DM-07 responder primary --------------------------------------------


def test_dm_07_fires_on_responder_rate_primary_only() -> None:
    responder = make_document(
        endpoints=[
            make_endpoint(
                description="Proportion of participants achieving HbA1c <7%",
                kind=EndpointKind.PRIMARY,
            )
        ]
    )
    change = make_document(
        endpoints=[
            make_endpoint(
                description="Change from baseline in HbA1c",
                kind=EndpointKind.PRIMARY,
            )
        ]
    )

    assert check_dm_07(responder, make_profile()).status == RuleStatus.FIRED
    assert check_dm_07(change, make_profile()).status == RuleStatus.PASSED


# --- DM-08 FPG units ----------------------------------------------------


def test_dm_08_not_applicable_without_fpg() -> None:
    doc = _pages_doc("HbA1c is measured at every visit by the central lab.")

    assert check_dm_08(doc, make_profile()).status == (
        RuleStatus.NOT_APPLICABLE
    )


def test_dm_08_needs_central_lab_and_mg_dl_for_fpg() -> None:
    complete = _pages_doc(
        "Fasting plasma glucose (FPG) is measured by the central "
        "laboratory and reported in mg/dL."
    )
    no_units = _pages_doc(
        "Fasting plasma glucose (FPG) is measured by the central laboratory."
    )

    assert check_dm_08(complete, make_profile()).status == RuleStatus.PASSED
    outcome = check_dm_08(no_units, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert "mg/dL" in outcome.finding


# --- DM-24 strata -------------------------------------------------------


def test_dm_24_passes_with_hba1c_or_prior_therapy_strata() -> None:
    doc = make_document(
        interventions=InterventionExtraction(
            stratification_factors=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "HbA1c <=8%")
            )
        )
    )

    assert check_dm_24(doc, make_profile()).status == RuleStatus.PASSED


def test_dm_24_fires_when_strata_omit_hba1c_and_prior_therapy() -> None:
    doc = make_document(
        interventions=InterventionExtraction(
            stratification_factors=make_strata(
                (StratificationFactorType.REGION, "Region")
            )
        )
    )

    outcome = check_dm_24(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert outcome.evidence


# --- DM-25 / DM-26 subgroups --------------------------------------------


def test_dm_25_requires_all_three_elderly_bands() -> None:
    bands = make_document(
        analysis=AnalysisPlanExtraction(
            prespecified_subgroups=make_subgroups(
                (SubgroupDimension.AGE, "65-74, 75-84 and >=85 years")
            )
        )
    )
    split_at_65 = make_document(
        analysis=AnalysisPlanExtraction(
            prespecified_subgroups=make_subgroups(
                (SubgroupDimension.AGE, "<65 vs >=65 years")
            )
        )
    )

    assert check_dm_25(bands, make_profile()).status == RuleStatus.PASSED
    assert check_dm_25(split_at_65, make_profile()).status == (
        RuleStatus.FIRED
    )


def test_dm_26_names_the_missing_subgroup_dimensions() -> None:
    doc = make_document(
        analysis=AnalysisPlanExtraction(
            prespecified_subgroups=make_subgroups(
                (SubgroupDimension.SEX, "Sex"),
                (SubgroupDimension.BASELINE_HBA1C, "Baseline HbA1c"),
            )
        )
    )

    outcome = check_dm_26(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert "RACE" in outcome.finding
    assert "DIABETES_DURATION" in outcome.finding
    assert "SEX" not in outcome.finding


# --- DM-29 meter --------------------------------------------------------


def test_dm_29_passes_when_a_meter_is_named_and_fires_otherwise() -> None:
    named = _pages_doc("Participants receive a blood glucose meter for SMBG.")
    unnamed = _pages_doc("Hypoglycaemia is recorded in a paper diary.")

    assert check_dm_29(named, make_profile()).status == RuleStatus.PASSED
    outcome = check_dm_29(unnamed, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is True


# --- DM-39 / DM-40 schedule content -------------------------------------


def test_dm_39_lists_cv_risk_factors_missing_from_the_schedule() -> None:
    doc = make_document(
        schedule=[
            make_visit(
                procedures=["Body weight", "Vital signs (blood pressure)"]
            )
        ]
    )

    outcome = check_dm_39(doc, make_profile())

    assert outcome.status == RuleStatus.FIRED
    assert "lipids" in outcome.finding
    assert "waist" in outcome.finding
    assert "body weight" not in outcome.finding


def test_dm_39_passes_when_every_cv_risk_factor_is_scheduled() -> None:
    doc = make_document(
        schedule=[
            make_visit(
                procedures=[
                    "Fasting lipid panel",
                    "Body weight",
                    "Waist circumference",
                    "Vital signs: blood pressure, pulse",
                ]
            )
        ]
    )

    assert check_dm_39(doc, make_profile()).status == RuleStatus.PASSED


def test_dm_40_needs_eye_exam_and_urine_albumin_in_schedule() -> None:
    both = make_document(
        schedule=[make_visit(procedures=["Fundoscopy", "UACR"])]
    )
    eye_only = make_document(
        schedule=[make_visit(procedures=["Dilated eye examination"])]
    )

    assert check_dm_40(both, make_profile()).status == RuleStatus.PASSED
    outcome = check_dm_40(eye_only, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert "albumin" in outcome.finding


def test_schedule_checks_cannot_assess_without_a_schedule() -> None:
    doc = make_document()

    assert check_dm_39(doc, make_profile()).status == (
        RuleStatus.CANNOT_ASSESS
    )
    assert check_dm_40(doc, make_profile()).status == (
        RuleStatus.CANNOT_ASSESS
    )


# --- pre-checks ---------------------------------------------------------


def test_dm_09_not_applicable_when_primary_is_at_least_8_weeks() -> None:
    long_trial = make_document(endpoints=[make_endpoint(time_frame="Week 26")])
    short_trial = make_document(endpoints=[make_endpoint(time_frame="Week 4")])

    outcome = precheck_dm_09(long_trial, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.NOT_APPLICABLE
    assert precheck_dm_09(short_trial, make_profile()) is None


def test_dm_10_not_applicable_in_confirmatory_phases() -> None:
    doc = make_document()

    phase_3 = precheck_dm_10(doc, make_profile(phase=TrialPhase.PHASE3))
    phase_2 = precheck_dm_10(doc, make_profile(phase=TrialPhase.PHASE2))

    assert phase_3 is not None
    assert phase_3.status == RuleStatus.NOT_APPLICABLE
    assert phase_2 is None


def test_dm_30_and_dm_33_not_applicable_without_matching_endpoints() -> None:
    hba1c_only = make_document(
        endpoints=[make_endpoint(description="Change in HbA1c")]
    )
    hypo_and_cgm = make_document(
        endpoints=[
            make_endpoint(description="Rate of level 3 hypoglycaemia"),
            make_endpoint(
                description="CGM time in range", kind=EndpointKind.SECONDARY
            ),
        ]
    )

    for precheck in (precheck_dm_30, precheck_dm_33):
        outcome = precheck(hba1c_only, make_profile())
        assert outcome is not None
        assert outcome.status == RuleStatus.NOT_APPLICABLE
        assert precheck(hypo_and_cgm, make_profile()) is None


def test_dm_35_passes_with_cv_adjudication_else_defers() -> None:
    adjudicated = make_document(
        safety_monitoring=SafetyMonitoringExtraction(
            has_cv_adjudication=cited(True, "MACE will be adjudicated")
        )
    )

    outcome = precheck_dm_35(adjudicated, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.PASSED
    assert precheck_dm_35(make_document(), make_profile()) is None


def test_dm_36_passes_on_hys_law_rules_else_defers() -> None:
    hys_law = _pages_doc(
        "Potential Hy's law cases will be followed with repeat liver tests."
    )

    outcome = precheck_dm_36(hys_law, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.PASSED
    assert precheck_dm_36(_pages_doc("No liver text."), make_profile()) is None


def test_dm_38_not_applicable_for_small_molecule_classes() -> None:
    doc = make_document()

    small = precheck_dm_38(doc, make_profile(drug_class=DrugClass.METFORMIN))
    peptide = precheck_dm_38(
        doc, make_profile(drug_class=DrugClass.GLP1_RECEPTOR_AGONIST)
    )
    biologic = precheck_dm_38(
        doc,
        make_profile(
            intervention_type=InterventionType.BIOLOGIC,
            drug_class=DrugClass.OTHER,
        ),
    )

    assert small is not None
    assert small.status == RuleStatus.NOT_APPLICABLE
    assert peptide is None
    assert biologic is None


def test_dm_42_passes_on_a_named_diabetes_pro_else_defers() -> None:
    named = _pages_doc(
        "Treatment satisfaction is measured with the DTSQ questionnaire."
    )

    outcome = precheck_dm_42(named, make_profile())

    assert outcome is not None
    assert outcome.status == RuleStatus.PASSED
    assert precheck_dm_42(_pages_doc("No PRO text."), make_profile()) is None
