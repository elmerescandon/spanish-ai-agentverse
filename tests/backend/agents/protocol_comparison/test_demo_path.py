"""End to end on the committed demo data: cached peers, cached lab
readings, comparison, recommendations. No network; the parsed draft's
lab reading uses a scripted LLM."""

from backend.agents.protocol_comparison.agent import (
    SessionLabReadingCache,
    compare_with_registry_peers,
)
from backend.agents.protocol_comparison.demo import demo_recommendations
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.agents.protocol_comparison.peer_store import (
    PeerSource,
    PeerStore,
)
from backend.agents.protocol_comparison.step_data import to_step_data
from backend.api.schemas import PipelineStep, Severity, StepStatus
from backend.shared.messages import CriterionKind
from tests.backend.agents.protocol_comparison.protocols import (
    HBA1C_CRITERION,
    HBA1C_REPLY,
    REVIEW_DATE,
    criterion,
    parsed_protocol,
)
from tests.conftest import FakeJsonGenerator, search_committed_demo_peers

PROTOCOL_ID = "proto-demo"


async def test_demo_returns_one_comparison_record_per_dimension() -> None:
    recommendations = await demo_recommendations(PROTOCOL_ID)

    assert [r.details["dimension_id"] for r in recommendations] == [
        "MINIMUM_AGE",
        "MAXIMUM_AGE",
        "ENROLLMENT",
        "HBA1C_LOWER_BOUND",
        "HBA1C_UPPER_BOUND",
        "ALT_AST_LIMIT",
        "EGFR_CUTOFF",
    ]
    assert {r.source_step for r in recommendations} == {
        PipelineStep.COMPARISON
    }
    assert {r.protocol_id for r in recommendations} == {PROTOCOL_ID}


async def test_demo_reads_the_drafts_lab_limits_from_the_cache() -> None:
    recommendations = await demo_recommendations(PROTOCOL_ID)

    by_dimension = {r.details["dimension_id"]: r for r in recommendations}
    hba1c = by_dimension["HBA1C_UPPER_BOUND"].details["draft_value"]
    assert isinstance(hba1c, dict)
    assert hba1c["value"] == 11.0
    assert by_dimension["EGFR_CUTOFF"].details["finding"] == "NOT_STATED"


async def test_demo_registry_draft_has_no_flags_today() -> None:
    # The registry shows the protocol after Amendment 4 loosened its
    # limits; under Stefan's weighted rules nothing is out of line.
    recommendations = await demo_recommendations(PROTOCOL_ID)

    assert {r.severity for r in recommendations} == {Severity.INFO}


async def test_parsed_protocol_is_compared_with_its_peers() -> None:
    document = parsed_protocol(
        [criterion("IN-01", CriterionKind.INCLUSION, HBA1C_CRITERION)]
    )
    cache = SessionLabReadingCache(PeerStore())

    comparison = await compare_with_registry_peers(
        document,
        REVIEW_DATE,
        PeerSource(PeerStore(), search=search_committed_demo_peers),
        cache,
        FakeJsonGenerator([HBA1C_REPLY]),
    )
    step = to_step_data(document, comparison)

    by_dimension = {
        result.dimension.dimension_id: result for result in comparison.results
    }
    hba1c = by_dimension[DimensionId.HBA1C_UPPER_BOUND]
    assert hba1c.draft_value is not None
    assert hba1c.draft_value.value == 10.5
    assert any(peer.value is not None for peer in hba1c.evidence)
    assert step.status == StepStatus.COMPLETED
    draft_evidence = [
        evidence
        for decision in step.decisions
        for evidence in decision.evidence
        if evidence.evidence_id.endswith("-draft")
    ]
    assert draft_evidence
    assert {evidence.document for evidence in draft_evidence} == {"my_trial"}
