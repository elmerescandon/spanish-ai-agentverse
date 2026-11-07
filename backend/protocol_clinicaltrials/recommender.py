"""Recommendation engine evaluating candidate clinical protocols against peer cluster benchmarks.

Generates actionable defect-prevention recommendations across accrual feasibility,
eligibility complexity, endpoint burden, and regulatory governance.
"""

import math

from backend.protocol_clinicaltrials.models import (
    ClusterProfile,
    ProtocolEvaluationReport,
    ProtocolFeatures,
    ProtocolRecommendation,
    TrialPhase,
)

# Benchmark thresholds for protocol defect detection
HIGH_PATIENT_SITE_MULTIPLIER = 2.5
MIN_PATIENT_SITE_ABSOLUTE = 15.0
HIGH_EXCLUSION_RATIO_THRESHOLD = 0.8
SECONDARY_OUTCOME_MULTIPLIER = 2.0
MIN_SECONDARY_OUTCOME_ABSOLUTE = 8
NARROW_AGE_SPAN_THRESHOLD_YEARS = 15.0


def evaluate_candidate_protocol(
    candidate: ProtocolFeatures,
    cluster: ClusterProfile,
    similarity_score: float = 1.0,
) -> ProtocolEvaluationReport:
    """Evaluate candidate protocol features against a peer cluster statistical profile.

    Parameters
    ----------
    candidate:
        Normalized feature vector of the candidate trial protocol.
    cluster:
        Statistical profile of the matched peer cluster.
    similarity_score:
        Cosine similarity or affinity score to the cluster centroid (0.0 to 1.0).

    Returns
    -------
    ProtocolEvaluationReport
        Defect evaluation containing ranked, evidence-based recommendations.
    """
    if not isinstance(candidate, ProtocolFeatures):
        raise TypeError(
            f"candidate must be a ProtocolFeatures instance, got {type(candidate).__name__}"
        )
    if not isinstance(cluster, ClusterProfile):
        raise TypeError(
            f"cluster must be a ClusterProfile instance, got {type(cluster).__name__}"
        )

    recommendations: list[ProtocolRecommendation] = []

    # 1. Accrual & Site Capacity Evaluation
    if (
        cluster.median_patients_per_site > 0
        and candidate.patients_per_site
        > cluster.median_patients_per_site * HIGH_PATIENT_SITE_MULTIPLIER
        and candidate.patients_per_site >= MIN_PATIENT_SITE_ABSOLUTE
    ):
        recommended_sites = math.ceil(
            candidate.target_enrollment / cluster.median_patients_per_site
        )
        recommendations.append(
            ProtocolRecommendation(
                category="ACCRUAL_BURDEN",
                severity="HIGH",
                message=(
                    f"Candidate expects {candidate.patients_per_site:.1f} patients per site across "
                    f"{candidate.site_count} sites, which is "
                    f"{candidate.patients_per_site / cluster.median_patients_per_site:.1f}x higher "
                    f"than the peer cohort median of {cluster.median_patients_per_site:.1f}."
                ),
                evidence_cluster_metric=(
                    f"Cluster median patients/site: {cluster.median_patients_per_site:.1f}; "
                    f"Cohort termination rate: {cluster.termination_rate * 100:.1f}%."
                ),
                recommended_action=(
                    f"Expand active investigative sites from {candidate.site_count} to at least "
                    f"{recommended_sites} sites to avoid accrual stall."
                ),
            )
        )

    # 2. Eligibility & Exclusion Burden Evaluation
    if (
        candidate.num_exclusion_criteria > cluster.p90_exclusion_count
        and candidate.num_exclusion_criteria > cluster.median_exclusion_count
    ):
        recommendations.append(
            ProtocolRecommendation(
                category="ELIGIBILITY_COMPLEXITY",
                severity="HIGH",
                message=(
                    f"Protocol defines {candidate.num_exclusion_criteria} exclusion criteria, exceeding "
                    f"the 90th percentile ({cluster.p90_exclusion_count:.0f}) of peer trials in this cluster."
                ),
                evidence_cluster_metric=(
                    f"Cluster median exclusions: {cluster.median_exclusion_count:.0f}; "
                    f"P90 exclusions: {cluster.p90_exclusion_count:.0f}."
                ),
                recommended_action=(
                    "Streamline exclusion criteria by consolidating routine laboratory cut-offs "
                    "or replacing strict boundaries with investigator discretion to lower screen failure rates."
                ),
            )
        )
    elif (
        candidate.exclusion_ratio > HIGH_EXCLUSION_RATIO_THRESHOLD
        and candidate.num_exclusion_criteria >= 12
    ):
        recommendations.append(
            ProtocolRecommendation(
                category="ELIGIBILITY_COMPLEXITY",
                severity="MEDIUM",
                message=(
                    f"High exclusion ratio ({candidate.exclusion_ratio:.2f}): protocol has "
                    f"{candidate.num_exclusion_criteria} exclusions vs {candidate.num_inclusion_criteria} inclusions."
                ),
                evidence_cluster_metric=f"Exclusion ratio {candidate.exclusion_ratio:.2f} > {HIGH_EXCLUSION_RATIO_THRESHOLD}.",
                recommended_action="Review exclusion list for outdated or redundant restrictions to broaden candidate pool.",
            )
        )

    # 3. Assessment & Secondary Outcome Burden
    if (
        cluster.median_secondary_outcomes > 0
        and candidate.num_secondary_outcomes
        > cluster.median_secondary_outcomes * SECONDARY_OUTCOME_MULTIPLIER
        and candidate.num_secondary_outcomes >= MIN_SECONDARY_OUTCOME_ABSOLUTE
    ):
        recommendations.append(
            ProtocolRecommendation(
                category="ASSESSMENT_BURDEN",
                severity="MEDIUM",
                message=(
                    f"Candidate protocol lists {candidate.num_secondary_outcomes} secondary outcomes "
                    f"(peer cluster median: {cluster.median_secondary_outcomes:.0f})."
                ),
                evidence_cluster_metric=f"Cluster median secondary outcomes: {cluster.median_secondary_outcomes:.0f}.",
                recommended_action=(
                    "Reduce patient and site assessment burden by moving exploratory endpoints "
                    "into optional exploratory sub-studies."
                ),
            )
        )

    # 4. Governance & Safety Oversight (DMC)
    is_pivotal = candidate.phase in (TrialPhase.PHASE3, TrialPhase.PHASE2_PHASE3)
    if is_pivotal and not candidate.has_dmc:
        recommendations.append(
            ProtocolRecommendation(
                category="GOVERNANCE_SAFETY",
                severity="HIGH",
                message="Pivotal Phase 2/3 or Phase 3 trial protocol lacks an independent Data Monitoring Committee (DMC).",
                evidence_cluster_metric="Regulatory standard (FDA 21 CFR / EMA) for pivotal randomized trials.",
                recommended_action=(
                    "Charter an independent Data Monitoring Committee (DMC / DSMB) to oversee patient safety "
                    "and interim efficacy."
                ),
            )
        )

    # 5. Demographic Inclusivity & Age Restriction
    if (
        candidate.age_span_years is not None
        and candidate.age_span_years < NARROW_AGE_SPAN_THRESHOLD_YEARS
        and candidate.min_age_years is not None
        and candidate.min_age_years >= 18.0
    ):
        recommendations.append(
            ProtocolRecommendation(
                category="DEMOGRAPHIC_ACCESSIBILITY",
                severity="LOW",
                message=(
                    f"Narrow adult age window: protocol limits enrollment to {candidate.age_span_years:.0f} years "
                    f"({candidate.min_age_years:.0f} to {candidate.max_age_years:.0f} years)."
                ),
                evidence_cluster_metric=f"Age span {candidate.age_span_years:.0f} years < {NARROW_AGE_SPAN_THRESHOLD_YEARS:.0f} years.",
                recommended_action="Verify if the narrow age cohort is medically necessary or if it can be expanded.",
            )
        )

    return ProtocolEvaluationReport(
        candidate_nct_id=candidate.nct_id,
        candidate_title=candidate.title,
        matched_cluster_id=cluster.cluster_id,
        matched_cluster_name=cluster.name,
        peer_similarity_score=similarity_score,
        cluster_termination_rate=cluster.termination_rate,
        recommendations=recommendations,
    )
