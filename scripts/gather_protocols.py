"""Generalized CLI to gather clinical protocols by indication, cluster cohorts, and export profiles.

Usage:
    uv run python scripts/gather_protocols.py --condition "diabetes" --n-clusters 4
    uv run python scripts/gather_protocols.py --condition "breast cancer" --n-clusters 5
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure repository root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.clients.clinical_trials import ClinicalTrialsClient
from backend.protocols.clustering import ProtocolClusteringEngine
from backend.protocols.parser import extract_protocol_features

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("gather_protocols")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Gather clinical protocols from ClinicalTrials.gov and fit cluster benchmarks."
    )
    parser.add_argument(
        "--condition",
        type=str,
        default="diabetes",
        help="Disease or indication name to search (e.g. 'diabetes', 'breast cancer').",
    )
    parser.add_argument(
        "--completed-count",
        type=int,
        default=60,
        help="Number of completed interventional studies to retrieve.",
    )
    parser.add_argument(
        "--terminated-count",
        type=int,
        default=40,
        help="Number of terminated/withdrawn studies to retrieve.",
    )
    parser.add_argument(
        "--n-clusters",
        type=int,
        default=4,
        help="Number of operational clusters to construct.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/protocols",
        help="Target directory to store protocol JSON dumps and cluster benchmarks.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Force re-querying ClinicalTrials.gov API even if local cached file exists.",
    )
    return parser.parse_args()


def main() -> None:
    """Execute protocol gathering, feature extraction, and clustering workflow."""
    args = parse_args()
    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    slug = "".join(c if c.isalnum() else "_" for c in args.condition.lower()).strip("_")
    raw_file = output_dir / f"{slug}_studies.json"
    cluster_file = output_dir / f"{slug}_clusters.json"

    raw_studies: list[dict[str, object]] = []

    if raw_file.exists() and not args.force_refresh:
        logger.info("Loading cached study data from %s", raw_file)
        with open(raw_file, encoding="utf-8") as f:
            raw_studies = json.load(f)
    else:
        logger.info(
            "Fetching %d completed + %d terminated protocols for condition '%s'...",
            args.completed_count,
            args.terminated_count,
            args.condition,
        )
        with ClinicalTrialsClient() as client:
            completed_result = client.search_studies(
                condition=args.condition,
                overall_status=["COMPLETED"],
                study_type=["INTERVENTIONAL"],
                has_results=None,
                page_size=min(args.completed_count, 100),
                count_total=True,
            )
            terminated_result = client.search_studies(
                condition=args.condition,
                overall_status=["TERMINATED", "WITHDRAWN", "SUSPENDED"],
                study_type=["INTERVENTIONAL"],
                has_results=None,
                page_size=min(args.terminated_count, 100),
                count_total=True,
            )

        logger.info(
            "Total available on ClinicalTrials.gov: %d completed, %d terminated/withdrawn",
            completed_result.total_count,
            terminated_result.total_count,
        )
        raw_studies = (
            completed_result.studies[: args.completed_count]
            + terminated_result.studies[: args.terminated_count]
        )

        with open(raw_file, "w", encoding="utf-8") as f:
            json.dump(raw_studies, f, indent=2)
        logger.info("Saved %d raw studies to %s", len(raw_studies), raw_file)

    protocols = [extract_protocol_features(s) for s in raw_studies]
    logger.info("Extracted normalized features for %d protocols", len(protocols))

    engine = ProtocolClusteringEngine(num_clusters=args.n_clusters)
    engine.fit(protocols)
    profiles = engine.compute_cluster_profiles()

    print("\n" + "=" * 80)
    print(f"CLUSTERING PROFILES FOR: {args.condition.upper()} (n={len(protocols)})")
    print("=" * 80)

    for profile in profiles:
        print(f"\n--- Cluster {profile.cluster_id}: {profile.name} ---")
        print(
            f"  Studies: {profile.study_count} (Completed: {profile.completed_count}, "
            f"Terminated: {profile.terminated_count}, Termination Rate: {profile.termination_rate * 100:.1f}%)"
        )
        print(
            f"  Phases: {', '.join(profile.top_phases) if profile.top_phases else 'None'}"
        )
        print(f"  Top Indication MeSH: {', '.join(profile.top_mesh_conditions)}")
        print(f"  Median Target Enrollment: {profile.median_enrollment:.0f} patients")
        print(
            f"  Exclusion Criteria: Median={profile.median_exclusion_count:.0f}, P90={profile.p90_exclusion_count:.0f}"
        )
        print(
            f"  Site Network: Median Sites={profile.median_site_count:.0f}, Patients/Site={profile.median_patients_per_site:.1f}"
        )

    with open(cluster_file, "w", encoding="utf-8") as f:
        json.dump([p.model_dump() for p in profiles], f, indent=2)

    logger.info("Successfully exported cluster profiles to %s", cluster_file)


if __name__ == "__main__":
    main()
