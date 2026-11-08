"""HTTP routes for clinical protocol gap analysis and recommendations."""

import logging
import tempfile
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, UploadFile, status

from backend.agents.protocol_comparison.demo import demo_recommendations
from backend.agents.protocol_comparison.peer_store import PeerStoreError
from backend.api.agent_runners import (
    build_ingest_step,
    run_checklist_agent,
    run_cohort_agent,
    run_protocol_comparison_agent,
)
from backend.api.protocol_fields import (
    ChangeRejectedError,
    document_fields,
    format_number,
    match_offer,
    offered_values,
    starting_comparison_fields,
)
from backend.api.protocol_pipeline import get_protocol_pipeline
from backend.api.schemas import (
    FieldChange,
    FieldChangeRequest,
    FieldChangeResponse,
    HealthResponse,
    PipelineStep,
    ProtocolCreateRequest,
    ProtocolField,
    ProtocolFieldsResponse,
    ProtocolStatus,
    ProtocolSummary,
    Recommendation,
    RecommendationDecisionRequest,
    Severity,
    StepData,
    StepRecommendationRequest,
    UploadFileResponse,
)
from backend.clients.document_store import get_document_store
from backend.clients.pdf_reader import UnreadablePdfError
from backend.clients.protocol_db import (
    ProtocolRecord,
    StoredField,
    get_protocol_db,
)
from backend.shared.messages import ProtocolDocument

logger = logging.getLogger(__name__)

DEMO_PROTOCOL_ID = "proto-diabetes-001"
DEMO_PROTOCOL_TITLE = "Type 2 Diabetes Glycemic Control Trial Protocol"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # protocol PDFs are ~1-5 MB

PDF_MAGIC_BYTES = b"%PDF"
PDF_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}

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


def _validate_pdf_upload(file: UploadFile, content: bytes) -> None:
    """Reject uploads that are not a non-empty PDF.

    Raises:
        HTTPException: 415 for a wrong type, 422 for an empty file.
    """
    filename = file.filename or ""
    is_pdf_name = filename.lower().endswith(".pdf")
    is_pdf_type = file.content_type in PDF_CONTENT_TYPES
    if not (is_pdf_name or is_pdf_type):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "expected a PDF (.pdf or application/pdf), got "
                f"filename='{filename}' content_type='{file.content_type}'"
            ),
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"expected a non-empty PDF, got 0 bytes in '{filename}'",
        )
    if not content.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"expected file to start with {PDF_MAGIC_BYTES!r}, "
                f"got {content[:4]!r}"
            ),
        )


@router.post("/upload-file", response_model=UploadFileResponse)
async def upload_file(file: UploadFile) -> UploadFileResponse:
    """Parse an uploaded protocol PDF and return the INGEST step.

    The first upload of a PDF takes minutes (one Gemini call per parser
    facet); the same file uploaded again is served from the parse cache.
    The completeness check then starts in the background, so the CHECK
    step is ready sooner.

    Raises:
        HTTPException: 413 for a file over MAX_UPLOAD_BYTES, 415 for a
            non-PDF, 422 for an empty or unreadable PDF.
        AnalysisFailedError: Gemini is not configured or every parser
            facet failed (answered with 503 by the app's error handler).
    """
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"expected a PDF of at most {MAX_UPLOAD_BYTES} bytes",
        )
    _validate_pdf_upload(file, content)
    filename = file.filename or "protocol.pdf"
    pipeline = get_protocol_pipeline()
    with tempfile.TemporaryDirectory() as temp_directory:
        pdf_path = Path(temp_directory) / "upload.pdf"
        pdf_path.write_bytes(content)
        try:
            parsed = await pipeline.parse(pdf_path)
        except UnreadablePdfError as error:
            logger.warning(
                "upload unreadable: filename=%s error=%s", filename, error
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
    document = parsed.model_copy(
        update={
            "protocol_id": f"proto-{uuid4().hex[:8]}",
            "title": Path(filename).stem,
        }
    )
    await get_document_store().save(document)
    await get_protocol_db().save_protocol(
        ProtocolRecord(
            protocol_id=document.protocol_id,
            title=document.title,
            page_count=document.page_count,
            uploaded_at=datetime.now(UTC),
        ),
        document_fields(document),
    )
    pipeline.start_check(document)
    logger.info(
        "upload stored: protocol_id=%s page_count=%d",
        document.protocol_id,
        document.page_count,
    )
    return UploadFileResponse(
        protocol_id=document.protocol_id,
        title=document.title,
        page_count=document.page_count,
        step=build_ingest_step(document),
        filename=filename,
        file_size_bytes=len(content),
    )


async def _get_document(protocol_id: str) -> ProtocolDocument:
    """Return the uploaded document or raise a 404 naming the id.

    The document is read from the shared store, not process memory:
    another server instance may have handled the upload.

    Raises:
        DocumentStoreError: the store failed (answered with 503).
    """
    document = await get_document_store().load(protocol_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Uploaded protocol '{protocol_id}' not found",
        )
    return document


async def _run_step(
    request: StepRecommendationRequest,
    runner: Callable[[ProtocolDocument], Awaitable[StepData]],
) -> StepData:
    """Look up the document and run one step's adapter."""
    return await runner(await _get_document(request.protocol_id))


async def _ensure_protocol_in_database(document: ProtocolDocument) -> None:
    """Seed this instance's database with a protocol uploaded elsewhere.

    The database is a local file, so an instance that did not handle the
    upload has no row for the protocol, and offers need one. A row that
    already exists is left alone: re-saving would overwrite the fields a
    reviewer accepted.
    """
    protocol_db = get_protocol_db()
    if await protocol_db.has_protocol(document.protocol_id):
        return
    await protocol_db.save_protocol(
        ProtocolRecord(
            protocol_id=document.protocol_id,
            title=document.title,
            page_count=document.page_count,
            uploaded_at=datetime.now(UTC),
        ),
        document_fields(document),
    )


@router.post("/checklist-recommendation", response_model=StepData)
async def checklist_recommendation(
    request: StepRecommendationRequest,
) -> StepData:
    """Return the CHECK step (owner: alex)."""
    return await _run_step(request, run_checklist_agent)


@router.post("/protocol-recommendation", response_model=StepData)
async def protocol_recommendation(
    request: StepRecommendationRequest,
) -> StepData:
    """Return the PEERS step (owner: theo) and store what it offers.

    The seven comparison fields start at the draft's values (never
    overwriting an accepted change), and the values Theo's options offer
    become the only values POST /protocols/{id}/changes accepts.

    Raises:
        ProtocolStoreError: the database failed (answered with 503).
    """
    document = await _get_document(request.protocol_id)
    run = await run_protocol_comparison_agent(document)
    await _ensure_protocol_in_database(document)
    await get_protocol_db().save_offers(
        document.protocol_id,
        starting_comparison_fields(run.comparison.results),
        offered_values(run.comparison.cards, run.step),
    )
    return run.step


@router.post("/cohort-recommendation", response_model=StepData)
async def cohort_recommendation(
    request: StepRecommendationRequest,
) -> StepData:
    """Return the COHORT step (owner: alvaro)."""
    return await _run_step(request, run_cohort_agent)


def _protocol_not_found(protocol_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Stored protocol '{protocol_id}' not found",
    )


@router.post(
    "/protocols/{protocol_id}/changes", response_model=FieldChangeResponse
)
async def accept_change(
    protocol_id: str, request: FieldChangeRequest
) -> FieldChangeResponse:
    """Apply one change the reviewer accepted to a stored field.

    Only a value the PEERS step offered for that field is accepted, so a
    stored value always comes from real data. Sending the same change
    again returns the field without logging it twice.

    Raises:
        HTTPException: 404 for an unknown protocol, 422 for a field that
            cannot change or a value that was not offered.
        ProtocolStoreError: the database failed (answered with 503).
    """
    protocol_db = get_protocol_db()
    if not await protocol_db.has_protocol(protocol_id):
        raise _protocol_not_found(protocol_id)
    offers = await protocol_db.offers_for(protocol_id, request.field)
    try:
        offer = match_offer(request.field, request.value, offers)
    except ChangeRejectedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    new_field = StoredField(
        field=offer.field, value=format_number(offer.value), unit=offer.unit
    )
    change = await protocol_db.apply_change(
        protocol_id, new_field, offer, datetime.now(UTC)
    )
    return FieldChangeResponse(
        field=ProtocolField.model_validate(new_field, from_attributes=True),
        change=(
            None
            if change is None
            else FieldChange.model_validate(change, from_attributes=True)
        ),
    )


@router.get(
    "/protocols/{protocol_id}/fields", response_model=ProtocolFieldsResponse
)
async def get_protocol_fields(protocol_id: str) -> ProtocolFieldsResponse:
    """Return a protocol's current fields and its accepted changes.

    Raises:
        HTTPException: 404 for an unknown protocol.
        ProtocolStoreError: the database failed (answered with 503).
    """
    review = await get_protocol_db().load_review(protocol_id)
    if review is None:
        raise _protocol_not_found(protocol_id)
    return ProtocolFieldsResponse(
        protocol_id=review.protocol.protocol_id,
        title=review.protocol.title,
        page_count=review.protocol.page_count,
        uploaded_at=review.protocol.uploaded_at,
        fields=[
            ProtocolField.model_validate(item, from_attributes=True)
            for item in review.fields
        ],
        changes=[
            FieldChange.model_validate(item, from_attributes=True)
            for item in review.changes
        ],
    )
