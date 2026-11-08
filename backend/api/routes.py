"""HTTP routes for clinical protocol gap analysis and recommendations."""

from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from backend.api.compliance import (
    to_compliance_report_response,
    to_recommendations,
)
from backend.api.compliance_service import (
    AnalysisInProgressError,
    AnalysisJob,
    ComplianceService,
    GeminiPipeline,
)
from backend.api.schemas import (
    AnalysisState,
    AnalysisStatusResponse,
    ComplianceReportResponse,
    HealthResponse,
    PipelineStep,
    ProtocolCreateRequest,
    ProtocolStatus,
    ProtocolSummary,
    Recommendation,
    RecommendationDecisionRequest,
    Severity,
)
from backend.shared.messages import ComplianceReport

DEMO_PROTOCOL_ID = "proto-diabetes-001"
DEMO_PROTOCOL_TITLE = "Type 2 Diabetes Glycemic Control Trial Protocol"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # protocol PDFs are ~1-5 MB
PDF_SIGNATURE = b"%PDF-"  # first bytes of every PDF file

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


def _require_protocol(protocol_id: str) -> ProtocolSummary:
    protocol = _protocols.get(protocol_id)
    if protocol is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Protocol '{protocol_id}' not found",
        )
    return protocol


def _set_protocol_status(protocol_id: str, new_status: ProtocolStatus) -> None:
    protocol = _protocols.get(protocol_id)
    if protocol is not None:
        _protocols[protocol_id] = protocol.model_copy(
            update={"status": new_status}
        )


def apply_compliance_report(
    protocol_id: str, report: ComplianceReport
) -> None:
    """Replace the protocol's completeness cards with the real findings.

    Cards from the other pipeline steps are kept.
    """
    cards = _recommendations.setdefault(protocol_id, {})
    for card_id in [
        card_id
        for card_id, card in cards.items()
        if card.source_step == PipelineStep.COMPLETENESS
    ]:
        del cards[card_id]
    for card in to_recommendations(report):
        cards[card.recommendation_id] = card
    _set_protocol_status(protocol_id, ProtocolStatus.READY)


def _mark_analysis_failed(protocol_id: str, error: str) -> None:
    _set_protocol_status(protocol_id, ProtocolStatus.UPLOADED)


_compliance_service = ComplianceService(
    analyse=GeminiPipeline(),
    on_report=apply_compliance_report,
    on_failure=_mark_analysis_failed,
)


def get_compliance_service() -> ComplianceService:
    """Return the process-wide compliance service (overridable in tests)."""
    return _compliance_service


ComplianceServiceDependency = Annotated[
    ComplianceService, Depends(get_compliance_service)
]


def _status_response(
    protocol_id: str, job: AnalysisJob
) -> AnalysisStatusResponse:
    return AnalysisStatusResponse(
        protocol_id=protocol_id, state=job.state, error=job.error
    )


@router.post("/protocols/{protocol_id}/pdf", response_model=ProtocolSummary)
async def upload_protocol_pdf(
    protocol_id: str,
    file: UploadFile,
    service: ComplianceServiceDependency,
) -> ProtocolSummary:
    """Attach the protocol PDF that the compliance analysis will read."""
    _require_protocol(protocol_id)
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"PDF must be at most {MAX_UPLOAD_BYTES} bytes",
        )
    if not content.startswith(PDF_SIGNATURE):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="expected a PDF file (starting with %PDF-)",
        )
    try:
        service.store_pdf(protocol_id, content)
    except AnalysisInProgressError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error
    _set_protocol_status(protocol_id, ProtocolStatus.UPLOADED)
    return _require_protocol(protocol_id)


@router.post(
    "/protocols/{protocol_id}/compliance-report",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisStatusResponse,
)
async def start_compliance_report(
    protocol_id: str,
    service: ComplianceServiceDependency,
) -> AnalysisStatusResponse:
    """Start the protocol's compliance analysis (safe to call twice)."""
    _require_protocol(protocol_id)
    try:
        job = service.start(protocol_id)
    except KeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"upload the protocol PDF first: {error}",
        ) from error
    if job.state == AnalysisState.RUNNING:
        _set_protocol_status(protocol_id, ProtocolStatus.ANALYZING)
    return _status_response(protocol_id, job)


@router.get(
    "/protocols/{protocol_id}/compliance-report/status",
    response_model=AnalysisStatusResponse,
)
def get_compliance_report_status(
    protocol_id: str,
    service: ComplianceServiceDependency,
) -> AnalysisStatusResponse:
    """Return the analysis progress, for the UI to poll."""
    _require_protocol(protocol_id)
    job = service.get(protocol_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no analysis started for protocol '{protocol_id}'",
        )
    return _status_response(protocol_id, job)


@router.get(
    "/protocols/{protocol_id}/compliance-report",
    response_model=ComplianceReportResponse,
)
def get_compliance_report(
    protocol_id: str,
    service: ComplianceServiceDependency,
) -> ComplianceReportResponse:
    """Return the finished compliance report."""
    _require_protocol(protocol_id)
    job = service.get(protocol_id)
    if job is None or job.report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"no finished report for protocol '{protocol_id}'; "
                "check /compliance-report/status"
            ),
        )
    return to_compliance_report_response(job.report)
