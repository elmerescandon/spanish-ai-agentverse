"""Script to gather real diabetes protocol data, extract features, and run clustering."""

import json
import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path for direct script execution
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.clients.clinical_trials import ClinicalTrialsClient
from backend.protocols import (
    AllocationType,
    InterventionModelType,
    MaskingType,
    OverallStatus,
    ProtocolClusteringEngine,
    ProtocolFeatures,
    TrialPhase,
    evaluate_candidate_protocol,
    extract_protocol_features,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

DATA_DIR = Path("data/protocols")
RAW_DATA_FILE = DATA_DIR / "diabetes_studies.json"
CLUSTERED_DATA_FILE = DATA_DIR / "diabetes_clusters.json"


def gather_diabetes_studies(
    client: ClinicalTrialsClient, max_completed: int = 60, max_terminated: int = 40
) -> list[dict[str, object]]:
    """Gathers completed and terminated diabetes clinical trials."""
    if RAW_DATA_FILE.exists():
        logger.info("Loading cached study data from %s", RAW_DATA_FILE)
        with RAW_DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data

    logger.info("Fetching completed diabetes protocols...")
    completed_res = client.search_studies(
        condition="diabetes",
        status="COMPLETED",
        page_size=max_completed,
        study_type="INTERVENTIONAL",
    )
    logger.info("Fetched %d completed studies", len(completed_res.studies))

    logger.info("Fetching terminated/withdrawn diabetes protocols...")
    terminated_res = client.search_studies(
        condition="diabetes",
        status="TERMINATED,WITHDRAWN",
        page_size=max_terminated,
        study_type="INTERVENTIONAL",
    )
    logger.info("Fetched %d terminated/withdrawn studies", len(terminated_res.studies))

    all_studies = completed_res.studies + terminated_res.studies
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with RAW_DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(all_studies, f, indent=2)
    logger.info("Saved %d total studies to %s", len(all_studies), RAW_DATA_FILE)
    return all_studies


def main() -> None:
    """Executes diabetes protocol gathering, feature extraction, and clustering analysis."""
    client = ClinicalTrialsClient(request_interval_seconds=1.0)
    raw_studies = gather_diabetes_studies(client, max_completed=60, max_terminated=40)

    features_list: list[ProtocolFeatures] = []
    for study in raw_studies:
        try:
            features = extract_protocol_features(study)
            features_list.append(features)
        except (ValueError, TypeError, KeyError) as err:
            logger.warning("Skipping study due to parsing error: %s", err)

    logger.info("Successfully parsed features for %d protocols", len(features_list))

    # Fit clustering engine
    num_clusters = 4
    engine = ProtocolClusteringEngine(num_clusters=num_clusters)
    engine.fit(features_list)
    profiles = engine.compute_cluster_profiles()

    print("\n" + "=" * 80)
    print("CLUSTERING ANALYSIS REPORT: DIABETES CLINICAL PROTOCOLS")
    print("=" * 80)

    profiles_output: list[dict[str, object]] = []

    for profile in profiles:
        print(f"\n--- {profile.name} ---")
        print(
            f"  Total Studies: {profile.study_count} "
            f"(Completed: {profile.completed_count}, Terminated: {profile.terminated_count})"
        )
        print(f"  Cluster Termination Rate: {profile.termination_rate * 100:.1f}%")
        print(f"  Phases: {', '.join(profile.top_phases)}")
        print(f"  Top MeSH Indication: {', '.join(profile.top_mesh_conditions)}")
        print(f"  Median Target Enrollment: {profile.median_enrollment:.0f} patients")
        print(
            f"  Exclusion Criteria Count: Median={profile.median_exclusion_count:.0f}, "
            f"P90={profile.p90_exclusion_count:.0f}"
        )
        print(
            f"  Endpoints: Primary={profile.median_primary_outcomes:.0f}, "
            f"Secondary={profile.median_secondary_outcomes:.0f}"
        )
        print(
            f"  Site Network: Median Sites={profile.median_site_count:.0f}, "
            f"Patients/Site={profile.median_patients_per_site:.1f}"
        )

        profiles_output.append(profile.model_dump())

    with CLUSTERED_DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(profiles_output, f, indent=2)
    print(f"\nCluster profiles saved to {CLUSTERED_DATA_FILE}")

    # Demonstrate Candidate Protocol Matching
    print("\n" + "=" * 80)
    print("DEMO: TESTING CANDIDATE PROTOCOL FIT & GAP DETECTION")
    print("=" * 80)

    candidate = ProtocolFeatures(
        nct_id="DRAFT-T2D-2026",
        title="Double-Blind Phase 3 Randomized Study of Novel SGLT2 Inhibitor in Type 2 Diabetes",
        conditions=["Type 2 Diabetes Mellitus"],
        mesh_conditions=["Diabetes Mellitus, Type 2"],
        phase=TrialPhase.PHASE3,
        allocation=AllocationType.RANDOMIZED,
        intervention_model=InterventionModelType.PARALLEL,
        masking=MaskingType.DOUBLE,
        target_enrollment=800,
        arm_count=2,
        num_primary_outcomes=1,
        num_secondary_outcomes=18,  # Deliberately heavy endpoint burden
        num_inclusion_criteria=4,
        num_exclusion_criteria=28,  # Deliberately excessive exclusion count
        exclusion_ratio=7.0,
        site_count=4,  # Deliberately under-sited (200 pts/site)
        patients_per_site=200.0,
        has_dmc=False,  # Deliberately missing DMC in Phase 3
        is_fda_regulated=True,
        status=OverallStatus.OTHER,
    )

    matched_cluster_id = engine.predict_cluster(candidate)
    matched_profile = next(p for p in profiles if p.cluster_id == matched_cluster_id)
    peer_cohort = engine.find_peer_cohort(candidate, top_k=3)
    similarity = peer_cohort[0][1] if peer_cohort else 1.0

    report = evaluate_candidate_protocol(
        candidate, matched_profile, similarity_score=similarity
    )

    print(f"Candidate: {candidate.title}")
    print(
        f"Assigned Cluster: Cluster {matched_profile.cluster_id} ({matched_profile.name})"
    )
    print(
        f"Cluster Baseline Termination Risk: {matched_profile.termination_rate * 100:.1f}%\n"
    )

    print(f"Defect & Feasibility Warnings ({len(report.recommendations)} detected):")
    for rec in report.recommendations:
        print(f"  [{rec.severity}] {rec.category}: {rec.message}")
        print(f"         Action: {rec.recommended_action}")

    print("\nTop-3 Most Structurally Similar Historical Trials:")
    for peer, score in peer_cohort:
        print(
            f"  - [{peer.nct_id}] {peer.title[:65]}... (Similarity: {score:.2f}, Status: {peer.status}, "
            f"Target: {peer.target_enrollment}, Sites: {peer.site_count})"
        )


if __name__ == "__main__":
    main()
