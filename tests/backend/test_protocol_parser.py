"""Unit tests for protocol feature parsing and categorization."""

import pytest

from backend.protocol_clinicaltrials.models import (
    AllocationType,
    InterventionModelType,
    MaskingType,
    OverallStatus,
    TerminationCategory,
    TrialPhase,
)
from backend.protocol_clinicaltrials.parser import (
    categorize_termination_reason,
    extract_protocol_features,
    parse_age_to_years,
    parse_eligibility_criteria_text,
)


def test_parse_eligibility_criteria_text_with_bullets() -> None:
    text = """
    Inclusion Criteria:
    * Age >= 18 years
    * Documented Type 2 Diabetes
    * HbA1c between 7.5% and 10.5%

    Exclusion Criteria:
    - History of diabetic ketoacidosis
    - Severe renal impairment (eGFR < 30)
    - Pregnancy or breastfeeding
    - Known hypersensitivity to study drug
    """
    inc, exc = parse_eligibility_criteria_text(text)
    assert inc == 3
    assert exc == 4


def test_parse_eligibility_criteria_text_empty_or_none() -> None:
    assert parse_eligibility_criteria_text(None) == (0, 0)
    assert parse_eligibility_criteria_text("   ") == (0, 0)


def test_parse_eligibility_criteria_text_numbered() -> None:
    text = """
    Inclusion Criteria:
    1. Patient diagnosed with T2D
    2. Body mass index >= 25 kg/m2

    Exclusion Criteria:
    1. Prior use of GLP-1 receptor agonist within 3 months
    """
    inc, exc = parse_eligibility_criteria_text(text)
    assert inc == 2
    assert exc == 1


def test_parse_age_to_years() -> None:
    assert parse_age_to_years("18 Years") == 18.0
    assert parse_age_to_years("65 years") == 65.0
    assert parse_age_to_years("6 Months") == 0.5
    assert parse_age_to_years("12 Weeks") == 0.23
    assert parse_age_to_years("365 Days") == 1.0
    assert parse_age_to_years(None) is None
    assert parse_age_to_years("N/A") is None


def test_categorize_termination_reason() -> None:
    assert (
        categorize_termination_reason("Slow accrual")
        == TerminationCategory.ENROLLMENT_SHORTFALL
    )
    assert (
        categorize_termination_reason(
            "Recruitment significantly lagged behind projections, unable to recruit"
        )
        == TerminationCategory.ENROLLMENT_SHORTFALL
    )
    assert (
        categorize_termination_reason(
            "Terminated due to adverse events and safety concerns"
        )
        == TerminationCategory.SAFETY_TOXICITY
    )
    assert (
        categorize_termination_reason("Closed due to futility at interim analysis")
        == TerminationCategory.FUTILITY_EFFICACY
    )
    assert (
        categorize_termination_reason("Business decision to reprioritize pipeline")
        == TerminationCategory.SPONSOR_BUSINESS
    )
    assert (
        categorize_termination_reason("Halted during COVID-19 pandemic")
        == TerminationCategory.COVID_PANDEMIC
    )
    assert (
        categorize_termination_reason(
            "Drug supply shortage from manufacturing facility"
        )
        == TerminationCategory.REGULATORY_CMC
    )
    assert (
        categorize_termination_reason(
            "Scheduling complexities and protocol infeasibility"
        )
        == TerminationCategory.STUDY_DESIGN
    )
    assert (
        categorize_termination_reason("Other miscellaneous reason")
        == TerminationCategory.UNSPECIFIED_OR_OTHER
    )
    assert categorize_termination_reason(None) is None


def test_extract_protocol_features_complete_study() -> None:
    study = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT01234567",
                "briefTitle": "Glycemic Control in T2D Patients",
            },
            "statusModule": {
                "overallStatus": "COMPLETED",
            },
            "conditionsModule": {
                "conditions": ["Diabetes Mellitus, Type 2"],
            },
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "phases": ["PHASE3"],
                "designInfo": {
                    "allocation": "RANDOMIZED",
                    "interventionModel": "PARALLEL",
                    "maskingInfo": {"masking": "DOUBLE"},
                },
                "enrollmentInfo": {"count": 600},
            },
            "armsInterventionsModule": {
                "armGroups": [{"label": "Drug Arm"}, {"label": "Placebo Arm"}],
            },
            "outcomesModule": {
                "primaryOutcomes": [{"measure": "Change in HbA1c at 24 weeks"}],
                "secondaryOutcomes": [
                    {"measure": "Fasting plasma glucose"},
                    {"measure": "Body weight"},
                ],
            },
            "eligibilityModule": {
                "eligibilityCriteria": "Inclusion Criteria:\n* T2D\n* Age 18+\nExclusion Criteria:\n* Renal failure\n* Heart failure",
                "minimumAge": "18 Years",
                "maximumAge": "75 Years",
                "healthyVolunteers": False,
            },
            "contactsLocationsModule": {
                "locations": [
                    {"facility": "Site 1", "country": "United States"},
                    {"facility": "Site 2", "country": "United States"},
                    {"facility": "Site 3", "country": "Canada"},
                ],
            },
            "oversightModule": {
                "oversightHasDmc": True,
                "isFdaRegulatedDrug": True,
            },
        },
        "derivedSection": {
            "conditionBrowseModule": {
                "meshes": [{"term": "Diabetes Mellitus, Type 2"}],
            },
        },
    }

    features = extract_protocol_features(study)

    assert features.nct_id == "NCT01234567"
    assert features.phase == TrialPhase.PHASE3
    assert features.status == OverallStatus.COMPLETED
    assert features.is_successful is True
    assert features.allocation == AllocationType.RANDOMIZED
    assert features.intervention_model == InterventionModelType.PARALLEL
    assert features.masking == MaskingType.DOUBLE
    assert features.target_enrollment == 600
    assert features.arm_count == 2
    assert features.num_primary_outcomes == 1
    assert features.num_secondary_outcomes == 2
    assert features.num_inclusion_criteria == 2
    assert features.num_exclusion_criteria == 2
    assert features.exclusion_ratio == 1.0
    assert features.min_age_years == 18.0
    assert features.max_age_years == 75.0
    assert features.age_span_years == 57.0
    assert features.site_count == 3
    assert features.country_count == 2
    assert features.patients_per_site == 200.0
    assert features.has_dmc is True
    assert features.is_fda_regulated is True


def test_extract_protocol_features_missing_protocol_section_raises_error() -> None:
    with pytest.raises(TypeError, match="Missing or invalid 'protocolSection'"):
        extract_protocol_features({})
