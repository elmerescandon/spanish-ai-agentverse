"""Unit tests for Family DM checks and the deterministic checks registry."""

from backend.agents.completeness.checks import DETERMINISTIC_CHECKS
from backend.agents.completeness.checks.diabetes import (
    check_dm_06,
    check_dm_13,
    check_dm_17,
    check_dm_21,
    check_dm_23,
    check_dm_28,
    check_dm_45,
)
from backend.agents.completeness.rules import load_rule_catalogue
from backend.shared.messages import (
    CheckMethod,
    EstimandExtraction,
    IntercurrentEventType,
    InterventionExtraction,
    RuleStatus,
    SafetyMonitoringExtraction,
)
from tests.backend.agents.completeness.factories import (
    cited,
    make_arm,
    make_document,
    make_endpoint,
    make_estimand,
    make_ice,
    make_profile,
)

EXTERNAL_INPUT_DETERMINISTIC_RULES: frozenset[str] = frozenset(
    {"REG-30", "XS-17", "XS-19"}
)


def test_deterministic_checks_registry_matches_catalogue() -> None:
    """Every in-protocol deterministic rule has a check; no judgement rule."""
    catalogue = load_rule_catalogue()
    deterministic_ids = {
        rule.id
        for rule in catalogue.rules
        if rule.check == CheckMethod.DETERMINISTIC
    }
    judgement_ids = {
        rule.id
        for rule in catalogue.rules
        if rule.check == CheckMethod.JUDGEMENT
    }
    assert len(deterministic_ids) == 45
    assert (
        set(DETERMINISTIC_CHECKS)
        == deterministic_ids - EXTERNAL_INPUT_DETERMINISTIC_RULES
    )
    assert set(DETERMINISTIC_CHECKS).isdisjoint(judgement_ids)


def test_dm_06_passes_for_hba1c_and_fires_for_cgm_time_in_range() -> None:
    """DM-06 fires when CGM time-in-range is the primary endpoint."""
    clean_doc = make_document(
        endpoints=[
            make_endpoint(description="Change from baseline in HbA1c at 26w")
        ]
    )
    assert check_dm_06(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        endpoints=[
            make_endpoint(
                description=(
                    "Percentage of time in range (TIR) 70-180 mg/dL by CGM"
                ),
                quote="Percentage of time in range (TIR) 70-180 mg/dL by CGM",
            )
        ]
    )
    outcome = check_dm_06(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert len(outcome.evidence) == 1


def test_dm_13_passes_and_fires_when_rescue_algorithm_missing() -> None:
    """DM-13 requires both rescue criteria and rescue medication regimen."""
    clean_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            rescue_therapy_criteria=cited("FPG > 270 mg/dL confirmed"),
            rescue_medication_regimen=cited("Glimepiride 1-4 mg daily"),
        )
    )
    assert check_dm_13(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            rescue_therapy_criteria=None,
            rescue_medication_regimen=None,
        )
    )
    outcome = check_dm_13(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is True


def test_dm_17_passes_at_8_weeks_and_fires_when_shorter_or_absent() -> None:
    """DM-17 requires >= 8 weeks of stable background therapy before rand."""
    clean_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            background_therapy_stable_weeks=cited(
                8.0, "Stable metformin dose for >= 8 weeks."
            ),
        )
    )
    assert check_dm_17(clean_doc, make_profile()).status == RuleStatus.PASSED

    short_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            background_therapy_stable_weeks=cited(
                4.0, "Stable metformin dose for 4 weeks."
            ),
        )
    )
    short_outcome = check_dm_17(short_doc, make_profile())
    assert short_outcome.status == RuleStatus.FIRED
    assert short_outcome.needs_second_opinion is False
    assert "4" in short_outcome.finding

    absent_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            background_therapy_stable_weeks=None,
        )
    )
    absent_outcome = check_dm_17(absent_doc, make_profile())
    assert absent_outcome.status == RuleStatus.FIRED
    assert absent_outcome.needs_second_opinion is True


def test_dm_21_passes_with_three_ices_and_fires_or_cannot_assess() -> None:
    """DM-21 checks the 3 core diabetes ICEs and avoids guessing on OTHER."""
    clean_doc = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()])
    )
    assert check_dm_21(clean_doc, make_profile()).status == RuleStatus.PASSED

    missing_doc = make_document(
        estimands=EstimandExtraction(
            estimands=[
                make_estimand(
                    intercurrent_events=[
                        make_ice(IntercurrentEventType.RESCUE_MEDICATION),
                        make_ice(
                            IntercurrentEventType.TREATMENT_DISCONTINUATION
                        ),
                    ]
                )
            ]
        )
    )
    missing_outcome = check_dm_21(missing_doc, make_profile())
    assert missing_outcome.status == RuleStatus.FIRED
    assert missing_outcome.needs_second_opinion is True
    assert "background_therapy_change" in missing_outcome.finding.lower()

    other_doc = make_document(
        estimands=EstimandExtraction(
            estimands=[
                make_estimand(
                    intercurrent_events=[
                        make_ice(IntercurrentEventType.RESCUE_MEDICATION),
                        make_ice(IntercurrentEventType.OTHER, "Custom event"),
                    ]
                )
            ]
        )
    )
    assert check_dm_21(other_doc, make_profile()).status == (
        RuleStatus.CANNOT_ASSESS
    )


def test_dm_23_passes_and_fires_when_post_discontinuation_hba1c_missing() -> (
    None
):
    """DM-23 checks continued HbA1c collection after stopping medication."""
    clean_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            collects_hba1c_after_discontinuation=cited(
                True, "Scheduled HbA1c visits continue after discontinuation."
            ),
        )
    )
    assert check_dm_23(clean_doc, make_profile()).status == RuleStatus.PASSED

    false_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            collects_hba1c_after_discontinuation=cited(
                False, "No HbA1c assessments after treatment discontinuation."
            ),
        )
    )
    false_outcome = check_dm_23(false_doc, make_profile())
    assert false_outcome.status == RuleStatus.FIRED
    assert false_outcome.needs_second_opinion is False

    none_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            collects_hba1c_after_discontinuation=None,
        )
    )
    none_outcome = check_dm_23(none_doc, make_profile())
    assert none_outcome.status == RuleStatus.FIRED
    assert none_outcome.needs_second_opinion is True


def test_dm_28_passes_with_ada_levels_and_fires_on_wrong_cutoffs() -> None:
    """DM-28 checks ADA/IHSG Level 1 (70), Level 2 (54), and Level 3."""
    clean_doc = make_document(
        safety_monitoring=SafetyMonitoringExtraction(
            defines_hypoglycemia_levels=cited(True),
            level_1_glucose_mg_dl=cited(70.0, "Level 1 < 70 mg/dL"),
            level_2_glucose_mg_dl=cited(54.0, "Level 2 < 54 mg/dL"),
            level_3_requires_assistance=cited(
                True, "Level 3 requires third-party assistance"
            ),
        )
    )
    assert check_dm_28(clean_doc, make_profile()).status == RuleStatus.PASSED

    wrong_cutoff_doc = make_document(
        safety_monitoring=SafetyMonitoringExtraction(
            defines_hypoglycemia_levels=cited(True),
            level_1_glucose_mg_dl=cited(60.0, "Hypoglycaemia < 60 mg/dL"),
            level_2_glucose_mg_dl=cited(50.0, "Severe < 50 mg/dL"),
            level_3_requires_assistance=cited(True),
        )
    )
    wrong_outcome = check_dm_28(wrong_cutoff_doc, make_profile())
    assert wrong_outcome.status == RuleStatus.FIRED
    assert wrong_outcome.needs_second_opinion is False
    assert "60" in wrong_outcome.finding

    absent_doc = make_document(
        safety_monitoring=SafetyMonitoringExtraction(
            defines_hypoglycemia_levels=None,
        )
    )
    absent_outcome = check_dm_28(absent_doc, make_profile())
    assert absent_outcome.status == RuleStatus.FIRED
    assert absent_outcome.needs_second_opinion is True


def test_dm_45_passes_and_fires_when_t1d_dka_monitoring_missing() -> None:
    """DM-45 checks DKA monitoring and mitigation procedures in T1D trials."""
    clean_doc = make_document(
        safety_monitoring=SafetyMonitoringExtraction(
            defines_dka_criteria=cited(
                True, "Blood beta-hydroxybutyrate ketone monitoring for DKA."
            )
        )
    )
    assert check_dm_45(clean_doc, make_profile()).status == RuleStatus.PASSED

    absent_doc = make_document(
        safety_monitoring=SafetyMonitoringExtraction(defines_dka_criteria=None)
    )
    absent_outcome = check_dm_45(absent_doc, make_profile())
    assert absent_outcome.status == RuleStatus.FIRED
    assert absent_outcome.needs_second_opinion is True
