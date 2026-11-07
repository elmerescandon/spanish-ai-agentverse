"""Retrospective validation script to quantify the predictive and economic value of protocol recommendations.

Measures:
1. Termination rate for protocols flagged with defect recommendations vs clean protocols.
2. Relative Risk and Odds Ratio of trial failure.
3. Concordance: Sensitivity of ACCRUAL_BURDEN & ELIGIBILITY_COMPLEXITY warnings against
   actual historical failures caused by enrollment shortfalls.
"""

import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.protocol_clinicaltrials import (
    OverallStatus,
    ProtocolClusteringEngine,
    TerminationCategory,
    evaluate_candidate_protocol,
    extract_protocol_features,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("eval_value")


def main() -> None:
    data_path = PROJECT_ROOT / "data/protocols/diabetes_studies.json"
    if not data_path.exists():
        logger.error(
            "Dataset not found at %s. Run gather_and_cluster_diabetes.py first.",
            data_path,
        )
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        raw_studies = json.load(f)

    protocols = [extract_protocol_features(s) for s in raw_studies]
    logger.info("Loaded %d historical protocols for validation", len(protocols))

    # Cluster protocols
    engine = ProtocolClusteringEngine(num_clusters=4)
    engine.fit(protocols)
    profiles = {p.cluster_id: p for p in engine.compute_cluster_profiles()}

    flagged_completed = 0
    flagged_terminated = 0
    clean_completed = 0
    clean_terminated = 0

    accrual_failures_total = 0
    accrual_failures_flagged = 0

    for protocol in protocols:
        cluster_id = engine.predict_cluster(protocol)
        profile = profiles[cluster_id]
        report = evaluate_candidate_protocol(protocol, profile)

        has_recs = len(report.recommendations) > 0
        is_terminated = protocol.status in (
            OverallStatus.TERMINATED,
            OverallStatus.WITHDRAWN,
        )

        if has_recs:
            if is_terminated:
                flagged_terminated += 1
            else:
                flagged_completed += 1
        elif is_terminated:
            clean_terminated += 1
        else:
            clean_completed += 1

        # Check concordance with enrollment shortfall
        if protocol.termination_category == TerminationCategory.ENROLLMENT_SHORTFALL:
            accrual_failures_total += 1
            accrual_flags = [
                r
                for r in report.recommendations
                if r.category in ("ACCRUAL_BURDEN", "ELIGIBILITY_COMPLEXITY")
            ]
            if accrual_flags:
                accrual_failures_flagged += 1

    total_flagged = flagged_completed + flagged_terminated
    total_clean = clean_completed + clean_terminated

    rate_flagged = (flagged_terminated / total_flagged) if total_flagged > 0 else 0.0
    rate_clean = (clean_terminated / total_clean) if total_clean > 0 else 0.0

    # Relative Risk
    relative_risk = (rate_flagged / rate_clean) if rate_clean > 0 else 0.0

    # Odds Ratio
    odds_flagged = (
        (flagged_terminated / flagged_completed) if flagged_completed > 0 else 0.0
    )
    odds_clean = (clean_terminated / clean_completed) if clean_completed > 0 else 0.0
    odds_ratio = (odds_flagged / odds_clean) if odds_clean > 0 else 0.0

    # Accrual Sensitivity
    accrual_sensitivity = (
        (accrual_failures_flagged / accrual_failures_total * 100)
        if accrual_failures_total > 0
        else 0.0
    )

    print("\n" + "=" * 80)
    print("HISTORICAL BACKTESTING VALIDATION REPORT: PROTOCOL RECOMMENDATIONS")
    print("=" * 80)
    print(f"Total Cohort Size: {len(protocols)} trials")
    print(f"Trials Flagged with ≥1 Defect: {total_flagged}")
    print(f"  - Actual Terminated: {flagged_terminated} ({rate_flagged * 100:.1f}%)")
    print(
        f"  - Actual Completed:  {flagged_completed} ({(1 - rate_flagged) * 100:.1f}%)"
    )
    print(f"\nTrials with Clean Design (0 Defect Warnings): {total_clean}")
    print(f"  - Actual Terminated: {clean_terminated} ({rate_clean * 100:.1f}%)")
    print(f"  - Actual Completed:  {clean_completed} ({(1 - rate_clean) * 100:.1f}%)")
    print("\n" + "-" * 80)
    print("STATISTICAL VALUE METRICS:")
    print(
        f"  * Termination Rate (Flagged vs Clean): {rate_flagged * 100:.1f}% vs {rate_clean * 100:.1f}%"
    )
    print(
        f"  * Relative Risk (RR):                  {relative_risk:.2f}x higher probability of termination"
    )
    print(f"  * Odds Ratio (OR):                     {odds_ratio:.2f}")
    print("\nFAILURE ROOT-CAUSE CONCORDANCE (whyStopped):")
    print(f"  * Total Trials Terminated for Accrual: {accrual_failures_total}")
    print(f"  * Correctly Flagged by Engine:         {accrual_failures_flagged}")
    print(f"  * Accrual Defect Sensitivity:          {accrual_sensitivity:.1f}%")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
