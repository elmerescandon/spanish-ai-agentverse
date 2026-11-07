"""Unit tests for ProtocolClusteringEngine."""

import pytest

from backend.protocol_clinicaltrials.clustering import ProtocolClusteringEngine
from backend.protocol_clinicaltrials.models import (
    AllocationType,
    InterventionModelType,
    MaskingType,
    OverallStatus,
    ProtocolFeatures,
    TrialPhase,
)


def _create_dummy_protocol(
    nct_id: str,
    phase: TrialPhase,
    target_enrollment: int,
    num_exclusion: int,
    status: OverallStatus = OverallStatus.COMPLETED,
    mesh: str = "Diabetes Mellitus, Type 2",
) -> ProtocolFeatures:
    return ProtocolFeatures(
        nct_id=nct_id,
        title=f"Clinical study for {mesh} {phase}",
        conditions=["Diabetes"],
        mesh_conditions=[mesh],
        phase=phase,
        allocation=AllocationType.RANDOMIZED,
        intervention_model=InterventionModelType.PARALLEL,
        masking=MaskingType.DOUBLE,
        target_enrollment=target_enrollment,
        arm_count=2,
        num_primary_outcomes=1,
        num_secondary_outcomes=3,
        num_inclusion_criteria=4,
        num_exclusion_criteria=num_exclusion,
        exclusion_ratio=num_exclusion / 4.0,
        site_count=5,
        country_count=1,
        patients_per_site=target_enrollment / 5.0,
        has_dmc=True,
        is_fda_regulated=True,
        status=status,
        is_successful=(status == OverallStatus.COMPLETED),
    )


def test_clustering_engine_fit_and_predict() -> None:
    protocols = [
        _create_dummy_protocol("NCT1", TrialPhase.PHASE1, 20, 5),
        _create_dummy_protocol("NCT2", TrialPhase.PHASE1, 24, 6),
        _create_dummy_protocol("NCT3", TrialPhase.PHASE3, 800, 15),
        _create_dummy_protocol("NCT4", TrialPhase.PHASE3, 900, 18),
    ]

    engine = ProtocolClusteringEngine(num_clusters=2)
    engine.fit(protocols)

    assert engine.is_fitted is True

    candidate_phase1 = _create_dummy_protocol("NCT_CAND_1", TrialPhase.PHASE1, 22, 5)
    candidate_phase3 = _create_dummy_protocol("NCT_CAND_3", TrialPhase.PHASE3, 850, 16)

    cluster_p1 = engine.predict_cluster(candidate_phase1)
    cluster_p3 = engine.predict_cluster(candidate_phase3)

    assert cluster_p1 != cluster_p3

    peers = engine.find_peer_cohort(candidate_phase1, top_k=2)
    assert len(peers) == 2
    assert peers[0][1] >= 0.0  # similarity score in [0, 1]


def test_clustering_engine_compute_profiles() -> None:
    protocols = [
        _create_dummy_protocol(
            "NCT1", TrialPhase.PHASE1, 20, 5, status=OverallStatus.COMPLETED
        ),
        _create_dummy_protocol(
            "NCT2", TrialPhase.PHASE1, 25, 6, status=OverallStatus.TERMINATED
        ),
        _create_dummy_protocol(
            "NCT3", TrialPhase.PHASE3, 800, 15, status=OverallStatus.COMPLETED
        ),
        _create_dummy_protocol(
            "NCT4", TrialPhase.PHASE3, 900, 18, status=OverallStatus.COMPLETED
        ),
    ]

    engine = ProtocolClusteringEngine(num_clusters=2)
    engine.fit(protocols)

    profiles = engine.compute_cluster_profiles()
    assert len(profiles) == 2
    for p in profiles:
        assert p.study_count > 0
        assert p.median_enrollment > 0


def test_clustering_engine_raises_with_insufficient_data() -> None:
    engine = ProtocolClusteringEngine(num_clusters=4)
    with pytest.raises(ValueError, match="Need at least 4 protocols"):
        engine.fit([_create_dummy_protocol("NCT1", TrialPhase.PHASE1, 20, 5)])
