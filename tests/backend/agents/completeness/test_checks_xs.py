"""Unit tests for Family XS (cross-section consistency) checks."""

from backend.agents.completeness.checks.consistency import (
    check_xs_03,
    check_xs_04,
    check_xs_05,
    check_xs_07,
    check_xs_08,
    check_xs_09,
    check_xs_10,
    check_xs_12,
    check_xs_13,
    check_xs_15,
    check_xs_18,
    check_xs_20,
    check_xs_21,
    check_xs_22,
)
from backend.shared.messages import (
    AnalysisPlanExtraction,
    CommitteeType,
    CriterionKind,
    EligibilityCriterion,
    EpochType,
    EstimandExtraction,
    IntercurrentEventType,
    InterventionExtraction,
    PageText,
    RuleStatus,
    StratificationFactorType,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
)
from tests.backend.agents.completeness.factories import (
    cited,
    make_arm,
    make_citation,
    make_committees,
    make_document,
    make_endpoint,
    make_epoch,
    make_estimand,
    make_ice,
    make_profile,
    make_section,
    make_strata,
    make_subsection,
    make_visit,
)


def test_xs_03_passes_when_rescue_ice_has_section_6_criteria() -> None:
    """XS-03 passes when rescue ICE has rescue criteria and regimen."""
    doc = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()]),
        interventions=InterventionExtraction(
            arms=[make_arm()],
            rescue_therapy_criteria=cited("FPG > 270 mg/dL after Week 6"),
            rescue_medication_regimen=cited("Glimepiride 1-4 mg daily"),
        ),
    )
    outcome = check_xs_03(doc, make_profile())
    assert outcome.status == RuleStatus.PASSED


def test_xs_03_fires_when_rescue_ice_lacks_section_6_criteria() -> None:
    """XS-03 fires (second opinion) when rescue ICE has no rescue rules."""
    doc = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()]),
        interventions=InterventionExtraction(
            arms=[make_arm()],
            rescue_therapy_criteria=None,
            rescue_medication_regimen=None,
        ),
    )
    outcome = check_xs_03(doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is True


def test_xs_03_not_applicable_or_cannot_assess_on_other_ice() -> None:
    """XS-03 is N/A without rescue ICE and cannot_assess on OTHER ICE."""
    no_rescue = make_estimand(
        intercurrent_events=[
            make_ice(IntercurrentEventType.TREATMENT_DISCONTINUATION)
        ]
    )
    doc_na = make_document(
        estimands=EstimandExtraction(estimands=[no_rescue]),
        interventions=InterventionExtraction(arms=[make_arm()]),
    )
    assert check_xs_03(doc_na, make_profile()).status == (
        RuleStatus.NOT_APPLICABLE
    )

    other_ice = make_estimand(
        intercurrent_events=[
            make_ice(IntercurrentEventType.OTHER, "Custom event")
        ]
    )
    doc_other = make_document(
        estimands=EstimandExtraction(estimands=[other_ice]),
        interventions=InterventionExtraction(arms=[make_arm()]),
    )
    assert check_xs_03(doc_other, make_profile()).status == (
        RuleStatus.CANNOT_ASSESS
    )


def test_xs_04_passes_when_treatment_policy_continues_follow_up() -> None:
    """XS-04 passes when treatment-policy strategy retains discontinued."""
    doc = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()]),
        interventions=InterventionExtraction(
            arms=[make_arm()],
            continues_follow_up_after_discontinuation=cited(
                True, "Participants remain in follow-up after stopping drug."
            ),
        ),
    )
    outcome = check_xs_04(doc, make_profile())
    assert outcome.status == RuleStatus.PASSED


def test_xs_04_fires_when_discontinued_participants_are_withdrawn() -> None:
    """XS-04 fires when Section 7 withdraws discontinued participants."""
    doc = make_document(
        estimands=EstimandExtraction(estimands=[make_estimand()]),
        interventions=InterventionExtraction(
            arms=[make_arm()],
            continues_follow_up_after_discontinuation=cited(
                False,
                "Participants stopping study drug are withdrawn from study.",
            ),
        ),
    )
    outcome = check_xs_04(doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert len(outcome.evidence) == 2


def test_xs_05_passes_when_primary_timepoint_matches_schedule_visit() -> None:
    """XS-05 passes when primary endpoint timepoint has a scheduled visit."""
    doc = make_document(
        endpoints=[make_endpoint(time_frame="Baseline and Week 26")],
        schedule=[make_visit(visit_name="Week 26 Visit", study_day=182)],
    )
    outcome = check_xs_05(doc, make_profile())
    assert outcome.status == RuleStatus.PASSED


def test_xs_05_fires_when_primary_timepoint_missing_from_schedule() -> None:
    """XS-05 fires when no scheduled visit matches the primary timepoint."""
    doc = make_document(
        endpoints=[make_endpoint(time_frame="Baseline and Week 26")],
        schedule=[
            make_visit(visit_name="Week 12 Visit", study_day=84),
            make_visit(visit_name="Week 52 Visit", study_day=364),
        ],
    )
    outcome = check_xs_05(doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "26" in outcome.finding


def test_xs_07_passes_and_fires_on_synopsis_vs_body_mismatch() -> None:
    """XS-07 compares synopsis enrollment, arms, and duration with body."""
    clean_doc = make_document(
        design=TrialDesignFacts(
            target_enrollment=cited(200, "Target N = 200", page_number=4),
            arm_count=cited(2, "2 study arms", page_number=4),
        ),
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_enrollment=cited(200, "Synopsis N = 200", page_number=1),
            synopsis_arm_count=cited(2, "Synopsis 2 arms", page_number=1),
            synopsis_treatment_duration_weeks=cited(26.0, "26 weeks"),
            body_treatment_duration_weeks=cited(26.0, "26 weeks", 4),
        ),
    )
    assert check_xs_07(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        design=TrialDesignFacts(
            target_enrollment=cited(190, "Body N = 190", page_number=4),
            arm_count=cited(2, "2 study arms", page_number=4),
        ),
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_enrollment=cited(200, "Synopsis N = 200", page_number=1),
            synopsis_arm_count=cited(3, "Synopsis 3 arms", page_number=1),
        ),
    )
    outcome = check_xs_07(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "200" in outcome.finding and "190" in outcome.finding


def test_xs_08_passes_and_fires_on_schema_vs_schedule_epochs() -> None:
    """XS-08 compares trial schema epochs against SoA visit epochs."""
    clean_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            schema_epochs=[
                make_epoch(EpochType.SCREENING, "Screening", 2.0),
                make_epoch(EpochType.TREATMENT, "Treatment", 26.0),
            ]
        ),
        schedule=[
            make_visit("Screening", -14, EpochType.SCREENING),
            make_visit("Week 26", 182, EpochType.TREATMENT),
        ],
    )
    assert check_xs_08(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            schema_epochs=[
                make_epoch(EpochType.SCREENING, "Screening", 2.0),
                make_epoch(EpochType.RUN_IN, "Run-in", 2.0),
                make_epoch(EpochType.TREATMENT, "Treatment", 26.0),
            ]
        ),
        schedule=[
            make_visit("Screening", -14, EpochType.SCREENING),
            make_visit("Week 26", 182, EpochType.TREATMENT),
        ],
    )
    outcome = check_xs_08(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "run_in" in outcome.finding.lower()


def test_xs_09_passes_and_fires_on_stratification_mismatch() -> None:
    """XS-09 checks stratification factors across synopsis, §6, and §10."""
    strata = make_strata(
        (StratificationFactorType.BASELINE_HBA1C, "HbA1c"),
        (StratificationFactorType.REGION, "Region"),
    )
    clean_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_stratification_factors=strata
        ),
        interventions=InterventionExtraction(
            arms=[make_arm()], stratification_factors=strata
        ),
        analysis=AnalysisPlanExtraction(primary_analysis_covariates=strata),
    )
    assert check_xs_09(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_stratification_factors=strata
        ),
        interventions=InterventionExtraction(
            arms=[make_arm()],
            stratification_factors=make_strata(
                (StratificationFactorType.BASELINE_HBA1C, "HbA1c")
            ),
        ),
        analysis=AnalysisPlanExtraction(primary_analysis_covariates=strata),
    )
    outcome = check_xs_09(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "region" in outcome.finding.lower()


def test_xs_10_passes_and_fires_on_prohibited_medication_overlap() -> None:
    """XS-10 checks whether a prohibited drug is also background/rescue."""
    clean_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            background_therapy=cited("Metformin >= 1500 mg/day"),
            rescue_medication_regimen=cited("Glimepiride 1-4 mg/day"),
            prohibited_medications=[
                cited("Systemic corticosteroids"),
                cited("Weight-loss pharmacotherapy"),
            ],
        )
    )
    assert check_xs_10(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        interventions=InterventionExtraction(
            arms=[make_arm()],
            background_therapy=cited("Metformin >= 1500 mg/day"),
            rescue_medication_regimen=cited(
                "Sulfonylurea (glimepiride 2 mg daily)"
            ),
            prohibited_medications=[
                cited("Sulfonylureas are prohibited during the study.")
            ],
        )
    )
    outcome = check_xs_10(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert len(outcome.evidence) == 2


def test_xs_12_passes_and_fires_on_committee_mismatch() -> None:
    """XS-12 compares oversight committees between synopsis and §11.4."""
    both = make_committees(
        (CommitteeType.DATA_MONITORING, "DMC"),
        (CommitteeType.ADJUDICATION, "CEC"),
    )
    clean_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_committees=both,
            governance_committees=both,
        )
    )
    assert check_xs_12(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_committees=both,
            governance_committees=make_committees(
                (CommitteeType.DATA_MONITORING, "DMC")
            ),
        )
    )
    outcome = check_xs_12(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert "adjudication" in outcome.finding.lower()


def test_xs_13_passes_and_fires_when_interim_lacks_stopping_or_dmc() -> None:
    """XS-13 requires stopping boundaries and DMC when interim is planned."""
    clean_doc = make_document(
        design=TrialDesignFacts(has_data_monitoring_committee=cited(True)),
        analysis=AnalysisPlanExtraction(
            has_interim_analysis=cited(True),
            stopping_boundaries=cited("Haybittle-Peto p < 0.001"),
        ),
    )
    assert check_xs_13(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        design=TrialDesignFacts(has_data_monitoring_committee=None),
        analysis=AnalysisPlanExtraction(
            has_interim_analysis=cited(True),
            stopping_boundaries=None,
        ),
    )
    outcome = check_xs_13(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is True


def test_xs_15_passes_and_fires_on_retention_years_mismatch() -> None:
    """XS-15 compares sample retention years in Section 8 and Section 11.3."""
    clean_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            assessments_retention_years=cited(15.0, "Retained for 15 years"),
            icf_retention_years=cited(15.0, "Stored for up to 15 years"),
        )
    )
    assert check_xs_15(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            assessments_retention_years=cited(15.0, "Retained for 15 years"),
            icf_retention_years=cited(5.0, "Stored for up to 5 years"),
        )
    )
    outcome = check_xs_15(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "15" in outcome.finding and "5" in outcome.finding


def test_xs_18_passes_and_fires_on_age_bound_mismatch() -> None:
    """XS-18 compares design age limits against inclusion age criteria."""
    clean_doc = make_document(
        design=TrialDesignFacts(
            min_age_years=cited(18.0, "Minimum age 18 years", page_number=1),
            max_age_years=cited(75.0, "Maximum age 75 years", page_number=1),
        ),
        eligibility_criteria=[
            EligibilityCriterion(
                criterion_id="IN-01",
                kind=CriterionKind.INCLUSION,
                text="Participants aged 18 to 75 years inclusive at Visit 1.",
                citation=make_citation(
                    "Participants aged 18 to 75 years inclusive at Visit 1.", 5
                ),
            )
        ],
    )
    assert check_xs_18(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        design=TrialDesignFacts(
            min_age_years=cited(18.0, "Minimum age 18 years", page_number=1),
            max_age_years=cited(75.0, "Maximum age 75 years", page_number=1),
        ),
        eligibility_criteria=[
            EligibilityCriterion(
                criterion_id="IN-01",
                kind=CriterionKind.INCLUSION,
                text="Participants aged 18 to 65 years inclusive at Visit 1.",
                citation=make_citation(
                    "Participants aged 18 to 65 years inclusive at Visit 1.", 5
                ),
            )
        ],
    )
    outcome = check_xs_18(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "75" in outcome.finding and "65" in outcome.finding


def test_xs_20_passes_and_fires_on_duration_vs_epoch_sum() -> None:
    """XS-20 checks synopsis duration against trial schema epoch durations."""
    clean_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_treatment_duration_weeks=cited(32.0, "Total 32 weeks"),
            schema_epochs=[
                make_epoch(EpochType.SCREENING, "Screening", 2.0),
                make_epoch(EpochType.TREATMENT, "Treatment", 26.0),
                make_epoch(EpochType.FOLLOW_UP, "Follow-up", 4.0),
            ],
        )
    )
    assert check_xs_20(clean_doc, make_profile()).status == RuleStatus.PASSED

    bad_doc = make_document(
        synopsis_check=SynopsisConsistencyExtraction(
            synopsis_treatment_duration_weeks=cited(20.0, "Total 20 weeks"),
            schema_epochs=[
                make_epoch(EpochType.SCREENING, "Screening", 2.0),
                make_epoch(EpochType.TREATMENT, "Treatment", 26.0),
                make_epoch(EpochType.FOLLOW_UP, "Follow-up", 4.0),
            ],
        )
    )
    outcome = check_xs_20(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False


def test_xs_21_passes_and_fires_on_abbreviation_before_definition() -> None:
    """XS-21 detects acronyms used on an earlier page before expansion."""
    clean_doc = make_document(
        pages=[
            PageText(
                page_number=1,
                text=(
                    "Continuous glucose monitoring (CGM) is performed at "
                    "Visit 2."
                ),
            ),
            PageText(
                page_number=2,
                text="Participants wear the CGM sensor for 14 days.",
            ),
        ],
        sections=[make_section()],
    )
    assert check_xs_21(clean_doc, make_profile()).status == RuleStatus.PASSED

    glossary_doc = make_document(
        pages=[
            PageText(
                page_number=1,
                text="Participants wear the CGM sensor during screening.",
            ),
            PageText(
                page_number=2,
                text=(
                    "Continuous glucose monitoring (CGM) is described in "
                    "Section 8."
                ),
            ),
            PageText(
                page_number=3,
                text=(
                    "12.2 List of Abbreviations\n"
                    "CGM  Continuous glucose monitoring\n"
                    "FPG  Fasting plasma glucose"
                ),
            ),
        ],
        sections=[make_section()],
    )
    assert (
        check_xs_21(glossary_doc, make_profile()).status == RuleStatus.PASSED
    )

    bad_doc = make_document(
        pages=[
            PageText(
                page_number=1,
                text="Participants wear the CGM sensor during screening.",
            ),
            PageText(
                page_number=2,
                text=(
                    "Continuous glucose monitoring (CGM) is described in "
                    "Section 8."
                ),
            ),
        ],
        sections=[make_section()],
    )
    outcome = check_xs_21(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "CGM" in outcome.finding
    assert all(ev.is_verified for ev in outcome.evidence)


def test_xs_22_passes_and_fires_on_broken_section_cross_reference() -> None:
    """XS-22 checks subsection map and page heading lines before firing."""
    clean_doc = make_document(
        pages=[
            PageText(
                page_number=1,
                text="Rescue therapy is detailed in Section 6.9.2.",
            )
        ],
        subsections=[
            make_subsection("6.9", "Concomitant Therapy", 5),
            make_subsection("6.9.2", "Rescue Medication", 6),
        ],
    )
    assert check_xs_22(clean_doc, make_profile()).status == RuleStatus.PASSED

    in_page_heading_doc = make_document(
        pages=[
            PageText(
                page_number=1,
                text="Rescue therapy is detailed in Section 6.9.2.",
            ),
            PageText(
                page_number=6,
                text="  6.9.2 Rescue Medication\nGlycaemic rescue criteria.",
            ),
        ],
        subsections=[
            make_subsection("6.9", "Concomitant Therapy", 5),
        ],
    )
    assert (
        check_xs_22(in_page_heading_doc, make_profile()).status
        == RuleStatus.PASSED
    )

    bad_doc = make_document(
        pages=[
            PageText(
                page_number=1,
                text=(
                    "See Section 6.9.1, Section 6.9.2, Section 6.9.3, "
                    "Section 6.9.4, Section 6.9.5, and Section 6.9.9."
                ),
            )
        ],
        subsections=[
            make_subsection("6.9", "Concomitant Therapy", 5),
        ],
    )
    outcome = check_xs_22(bad_doc, make_profile())
    assert outcome.status == RuleStatus.FIRED
    assert outcome.needs_second_opinion is False
    assert "6.9.1" in outcome.finding
    assert "6.9.5" in outcome.finding
    assert "and 1 more" in outcome.finding
    assert len(outcome.evidence) == 5
    assert all(ev.is_verified for ev in outcome.evidence)
