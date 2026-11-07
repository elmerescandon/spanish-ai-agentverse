"""Tests for protocol recommendation and defect evaluation engine."""

import pytest

from backend.protocol_clinicaltrials.models import (
    ClusterProfile,
    ProtocolFeatures,
    TrialPhase,
)
from backend.protocol_clinicaltrials.recommender import evaluate_candidate_protocol


@pytest.fixture
def sample_cluster_profile() -> ClusterProfile:
    """Fixture providing a typical Phase 3 cluster profile."""
    return ClusterProfile(
        cluster_id=3,
        name="Phase 3 Multi-Center Efficacy Trials",
        study_count=50,
        completed_count=40,
        terminated_count=10,
        termination_rate=0.20,
        top_mesh_conditions=["Diabetes Mellitus, Type 2"],
        top_phases=["PHASE3"],
        median_enrollment=300.0,
        median_exclusion_count=10.0,
        p90_exclusion_count=18.0,
        median_primary_outcomes=1.0,
        median_secondary_outcomes=4.0,
        median_site_count=30.0,
        median_patients_per_site=10.0,
    )


def test_evaluate_candidate_detects_accrual_burden(
    sample_cluster_profile: ClusterProfile,
) -> None:
    """Detects when patient-per-site ratio exceeds cluster median significantly."""
    candidate = ProtocolFeatures(
        nct_id="NCT00000001",
        title="Overburdened Sites Trial",
        phase=TrialPhase.PHASE3,
        target_enrollment=600,
        site_count=3,
        patients_per_site=200.0,  # 20x median 10.0
        num_inclusion_criteria=5,
        num_exclusion_criteria=10,
        num_secondary_outcomes=3,
        has_dmc=True,
    )

    report = evaluate_candidate_protocol(candidate, sample_cluster_profile)
    assert report.candidate_nct_id == "NCT00000001"
    assert report.matched_cluster_id == 3

    accrual_recs = [r for r in report.recommendations if r.category == "ACCRUAL_BURDEN"]
    assert len(accrual_recs) == 1
    assert accrual_recs[0].severity == "HIGH"
    assert "at least 60 sites" in accrual_recs[0].recommended_action


def test_evaluate_candidate_detects_p90_exclusion_volume(
    sample_cluster_profile: ClusterProfile,
) -> None:
    """Detects when exclusion criteria count exceeds the cohort's 90th percentile."""
    candidate = ProtocolFeatures(
        nct_id="NCT00000002",
        title="Overly Restrictive Protocol",
        phase=TrialPhase.PHASE3,
        target_enrollment=200,
        site_count=20,
        patients_per_site=10.0,
        num_inclusion_criteria=5,
        num_exclusion_criteria=25,  # > p90 of 18.0
        num_secondary_outcomes=4,
        has_dmc=True,
    )

    report = evaluate_candidate_protocol(candidate, sample_cluster_profile)
    eligibility_recs = [
        r for r in report.recommendations if r.category == "ELIGIBILITY_COMPLEXITY"
    ]
    assert len(eligibility_recs) == 1
    assert eligibility_recs[0].severity == "HIGH"
    assert "90th percentile" in eligibility_recs[0].message


def test_evaluate_candidate_detects_high_exclusion_ratio(
    sample_cluster_profile: ClusterProfile,
) -> None:
    """Detects when exclusion ratio is high even if below p90 absolute count."""
    candidate = ProtocolFeatures(
        nct_id="NCT00000003",
        title="Imbalanced Criteria Protocol",
        phase=TrialPhase.PHASE3,
        target_enrollment=200,
        site_count=20,
        patients_per_site=10.0,
        num_inclusion_criteria=2,
        num_exclusion_criteria=12,
        exclusion_ratio=0.857,  # > 0.8
        num_secondary_outcomes=4,
        has_dmc=True,
    )

    report = evaluate_candidate_protocol(candidate, sample_cluster_profile)
    eligibility_recs = [
        r for r in report.recommendations if r.category == "ELIGIBILITY_COMPLEXITY"
    ]
    assert len(eligibility_recs) == 1
    assert eligibility_recs[0].severity == "MEDIUM"
    assert "High exclusion ratio" in eligibility_recs[0].message


def test_evaluate_candidate_detects_excessive_secondary_outcomes(
    sample_cluster_profile: ClusterProfile,
) -> None:
    """Detects when secondary outcome burden is more than double cluster median."""
    candidate = ProtocolFeatures(
        nct_id="NCT00000004",
        title="Overburdened Outcomes Protocol",
        phase=TrialPhase.PHASE3,
        target_enrollment=200,
        site_count=20,
        patients_per_site=10.0,
        num_inclusion_criteria=5,
        num_exclusion_criteria=8,
        num_secondary_outcomes=16,  # 4x median 4.0
        has_dmc=True,
    )

    report = evaluate_candidate_protocol(candidate, sample_cluster_profile)
    outcome_recs = [
        r for r in report.recommendations if r.category == "ASSESSMENT_BURDEN"
    ]
    assert len(outcome_recs) == 1
    assert "16 secondary outcomes" in outcome_recs[0].message


def test_evaluate_candidate_detects_missing_phase3_dmc(
    sample_cluster_profile: ClusterProfile,
) -> None:
    """Flags missing DMC on pivotal Phase 3 trials."""
    candidate = ProtocolFeatures(
        nct_id="NCT00000005",
        title="No DMC Phase 3 Trial",
        phase=TrialPhase.PHASE3,
        target_enrollment=200,
        site_count=20,
        patients_per_site=10.0,
        num_inclusion_criteria=5,
        num_exclusion_criteria=8,
        num_secondary_outcomes=4,
        has_dmc=False,
    )

    report = evaluate_candidate_protocol(candidate, sample_cluster_profile)
    safety_recs = [
        r for r in report.recommendations if r.category == "GOVERNANCE_SAFETY"
    ]
    assert len(safety_recs) == 1
    assert safety_recs[0].severity == "HIGH"
    assert "lacks an independent Data Monitoring Committee" in safety_recs[0].message


def test_evaluate_candidate_detects_narrow_age_span(
    sample_cluster_profile: ClusterProfile,
) -> None:
    """Detects unnecessarily narrow adult age criteria."""
    candidate = ProtocolFeatures(
        nct_id="NCT00000006",
        title="Narrow Age Span Trial",
        phase=TrialPhase.PHASE3,
        target_enrollment=200,
        site_count=20,
        patients_per_site=10.0,
        num_inclusion_criteria=5,
        num_exclusion_criteria=8,
        num_secondary_outcomes=4,
        min_age_years=40.0,
        max_age_years=50.0,
        age_span_years=10.0,  # < 15 years
        has_dmc=True,
    )

    report = evaluate_candidate_protocol(candidate, sample_cluster_profile)
    age_recs = [
        r for r in report.recommendations if r.category == "DEMOGRAPHIC_ACCESSIBILITY"
    ]
    assert len(age_recs) == 1
    assert "Narrow adult age window" in age_recs[0].message


def test_evaluate_candidate_clean_protocol(
    sample_cluster_profile: ClusterProfile,
) -> None:
    """Clean protocol matching cluster norms yields no defect recommendations."""
    candidate = ProtocolFeatures(
        nct_id="NCT00000007",
        title="Well Designed Phase 3 Trial",
        phase=TrialPhase.PHASE3,
        target_enrollment=300,
        site_count=30,
        patients_per_site=10.0,
        num_inclusion_criteria=5,
        num_exclusion_criteria=10,
        exclusion_ratio=0.66,
        num_secondary_outcomes=4,
        min_age_years=18.0,
        max_age_years=75.0,
        age_span_years=57.0,
        has_dmc=True,
    )

    report = evaluate_candidate_protocol(candidate, sample_cluster_profile)
    assert len(report.recommendations) == 0


def test_evaluate_candidate_type_validation() -> None:
    """Fails loudly with TypeError when inputs are of invalid type."""
    with pytest.raises(
        TypeError, match="candidate must be a ProtocolFeatures instance"
    ):
        evaluate_candidate_protocol({}, None)  # type: ignore[arg-type]

    dummy_features = ProtocolFeatures(nct_id="NCT1", title="T")
    with pytest.raises(TypeError, match="cluster must be a ClusterProfile instance"):
        evaluate_candidate_protocol(dummy_features, {})  # type: ignore[arg-type]
