"""HTTP routes for clinical protocol gap analysis and recommendations."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

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

DEMO_PROTOCOL_ID = "proto-diabetes-001"
DEMO_PROTOCOL_TITLE = "Type 2 Diabetes Glycemic Control Trial Protocol"

router = APIRouter(prefix="/api")

_protocols: dict[str, ProtocolSummary] = {}
_recommendations: dict[str, dict[str, Recommendation]] = {}


def _build_default_recommendations(
    protocol_id: str,
) -> dict[str, Recommendation]:
    """Build default pipeline recommendations for a protocol."""
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
            source_step=PipelineStep.COMPARISON,
            severity=Severity.WARNING,
            title="Comparator dosage mismatch with SOC",
            description=(
                "Metformin control arm dose is lower than current "
                "standard of care guidelines."
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
def list_recommendations(protocol_id: str) -> list[Recommendation]:
    """List all recommendations associated with a given protocol."""
    if protocol_id not in _protocols:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_id}' not found",
        )
    return list(_recommendations.get(protocol_id, {}).values())


@router.patch(
    "/protocols/{protocol_id}/recommendations/{recommendation_id}",
    response_model=Recommendation,
)
def update_recommendation(
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
