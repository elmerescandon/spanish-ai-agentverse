"""HTTP routes for clinical protocol gap analysis and recommendations."""

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from backend.agents.protocol_comparison.demo import demo_recommendations
from backend.agents.protocol_comparison.peer_store import PeerStoreError
from backend.api.schemas import (
    HealthResponse,
    PipelineStep,
    ProtocolCreateRequest,
    ProtocolStatus,
    ProtocolSummary,
    Recommendation,
    RecommendationDecisionRequest,
    Severity,
)

logger = logging.getLogger(__name__)

DEMO_PROTOCOL_ID = "proto-diabetes-001"
DEMO_PROTOCOL_TITLE = "Type 2 Diabetes Glycemic Control Trial Protocol"

router = APIRouter(prefix="/api")

_protocols: dict[str, ProtocolSummary] = {}
_recommendations: dict[str, dict[str, Recommendation]] = {}
# Protocols whose comparison-agent recommendations are already loaded.
_comparison_loaded: set[str] = set()


def _build_default_recommendations(
    protocol_id: str,
) -> dict[str, Recommendation]:
    """Build mock recommendations for the steps not wired to agents yet.

    Comparison recommendations come from the comparison agent instead;
    see _load_comparison.
    """
    items = [
        Recommendation(
            recommendation_id=f"rec-{uuid4().hex[:8]}",
            protocol_id=protocol_id,
            source_step=PipelineStep.COMPLETENESS,
            severity=Severity.CRITICAL,
            title="Missing secondary endpoint definition",
            description=(
                "Protocol lacks HbA1c 24-week follow-up endpoint "
                "specifications."
            ),
        ),
        Recommendation(
            recommendation_id=f"rec-{uuid4().hex[:8]}",
            protocol_id=protocol_id,
            source_step=PipelineStep.COHORT,
            severity=Severity.INFO,
            title="Pediatric cohort exclusion criteria ambiguous",
            description=(
                "Age boundary exclusion requires explicit pediatric "
                "waiver notation."
            ),
        ),
    ]
    return {rec.recommendation_id: rec for rec in items}


def reset_mock_state() -> None:
    """Reset in-memory protocols and recommendations to default demo state."""
    _protocols.clear()
    _recommendations.clear()
    _comparison_loaded.clear()

    demo_proto = ProtocolSummary(
        protocol_id=DEMO_PROTOCOL_ID,
        title=DEMO_PROTOCOL_TITLE,
        status=ProtocolStatus.READY,
        data={"phase": "Phase 3", "condition": "Type 2 Diabetes"},
    )
    _protocols[DEMO_PROTOCOL_ID] = demo_proto
    _recommendations[DEMO_PROTOCOL_ID] = _build_default_recommendations(
        DEMO_PROTOCOL_ID
    )


# Seed initial state upon module import
reset_mock_state()


async def _load_comparison(protocol_id: str) -> None:
    """Add the comparison agent's recommendations, once per protocol.

    Runs on first use rather than at startup, and never overwrites an
    existing item, so reviewer decisions survive later reads.
    """
    if protocol_id in _comparison_loaded:
        return
    try:
        recommendations = await demo_recommendations(protocol_id)
    except PeerStoreError as error:
        logger.exception(
            "comparison agent failed: protocol_id=%s", protocol_id
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Comparison agent unavailable: {error}",
        ) from error
    stored = _recommendations.setdefault(protocol_id, {})
    for recommendation in recommendations:
        stored.setdefault(recommendation.recommendation_id, recommendation)
    _comparison_loaded.add(protocol_id)


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return backend service operational health status."""
    return HealthResponse(status="ok")


@router.get("/protocols", response_model=list[ProtocolSummary])
def list_protocols() -> list[ProtocolSummary]:
    """List all registered clinical protocols."""
    return list(_protocols.values())


@router.post(
    "/protocols",
    status_code=status.HTTP_201_CREATED,
    response_model=ProtocolSummary,
)
def create_protocol(request: ProtocolCreateRequest) -> ProtocolSummary:
    """Register a new protocol and initialize mock analysis recommendations."""
    protocol_id = f"proto-{uuid4().hex[:8]}"
    protocol = ProtocolSummary(
        protocol_id=protocol_id,
        title=request.title,
        status=ProtocolStatus.UPLOADED,
        data=request.data,
    )
    _protocols[protocol_id] = protocol
    _recommendations[protocol_id] = _build_default_recommendations(protocol_id)
    return protocol


@router.get("/protocols/{protocol_id}", response_model=ProtocolSummary)
def get_protocol(protocol_id: str) -> ProtocolSummary:
    """Retrieve details for a specific protocol."""
    protocol = _protocols.get(protocol_id)
    if protocol is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_id}' not found",
        )
    return protocol


@router.get(
    "/protocols/{protocol_id}/recommendations",
    response_model=list[Recommendation],
)
async def list_recommendations(protocol_id: str) -> list[Recommendation]:
    """List all recommendations associated with a given protocol."""
    if protocol_id not in _protocols:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_id}' not found",
        )
    await _load_comparison(protocol_id)
    return list(_recommendations.get(protocol_id, {}).values())


@router.patch(
    "/protocols/{protocol_id}/recommendations/{recommendation_id}",
    response_model=Recommendation,
)
async def update_recommendation(
    protocol_id: str,
    recommendation_id: str,
    request: RecommendationDecisionRequest,
) -> Recommendation:
    """Update reviewer decision and comments on a specific recommendation."""
    if protocol_id not in _protocols:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_id}' not found",
        )
    await _load_comparison(protocol_id)

    proto_recs = _recommendations.get(protocol_id, {})
    recommendation = proto_recs.get(recommendation_id)
    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Recommendation '{recommendation_id}' not found for "
                f"protocol '{protocol_id}'"
            ),
        )

    updates: dict[str, object] = {"status": request.status}
    if request.comment is not None:
        updates["comment"] = request.comment
    updated_rec = recommendation.model_copy(update=updates)
    proto_recs[recommendation_id] = updated_rec
    return updated_rec
