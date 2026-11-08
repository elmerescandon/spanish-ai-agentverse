"""Adapters that plug each agent into the /demo page.

Each function here is the single seam between one /demo section and the
agent behind it. The owner replaces the body of their function with a call
to their agent and maps the agent's output to ``StepData``; the route,
the schema and the frontend stay untouched. Runners only read the
document, never write shared state, so the three recommendation steps can
run in parallel and a retried call is safe.
"""

import logging
from collections.abc import Sequence

from backend.agents.cohort.agent import (
    AGENT_NAME as COHORT_AGENT_NAME,
)
from backend.agents.cohort.agent import (
    analyze_protocol_document_cohort,
)
from backend.agents.cohort.step_data import to_step_data as cohort_step_data
from backend.agents.completeness.rules import load_rule_catalogue
from backend.agents.protocol_comparison.agent import (
    AGENT_NAME as COMPARISON_AGENT_NAME,
)
from backend.agents.protocol_comparison.demo import compare_demo_draft
from backend.agents.protocol_comparison.peer_store import PeerStoreError
from backend.agents.protocol_comparison.step_data import (
    to_step_data as comparison_step_data,
)
from backend.api.check_step import AGENT_LABEL, to_check_step
from backend.api.protocol_pipeline import (
    AnalysisFailedError,
    get_protocol_pipeline,
)
from backend.api.schemas import (
    DataSource,
    DataTable,
    EvidenceSource,
    Metric,
    MetricTone,
    StepData,
    StepId,
    StepStatus,
    StepWarning,
    TableColumn,
)
from backend.clients.cohort_data import CohortDataError
from backend.shared.messages import ProtocolDocument

logger = logging.getLogger(__name__)


def _step_logged(document: ProtocolDocument, step: StepData) -> StepData:
    """Log which step was produced for which protocol, then return it."""
    logger.info(
        "step built: step_id=%s protocol_id=%s decisions=%d",
        step.id,
        document.protocol_id,
        len(step.decisions),
    )
    return step


def _count_label(items: Sequence[object] | None) -> str:
    """Count extracted items; "n/a" when the parser facet did not run."""
    return "n/a" if items is None else str(len(items))


def build_ingest_step(document: ProtocolDocument) -> StepData:
    """Build the INGEST section from the parsed upload.

    Pure: uses only the parsed document.
    """
    empty_page_count = sum(
        1 for page in document.pages if not page.text.strip()
    )
    criteria = document.eligibility_criteria or []
    metrics = [
        Metric(label="Pages", value=str(document.page_count)),
        Metric(label="Sections", value=_count_label(document.sections)),
        Metric(
            label="Eligibility criteria",
            value=_count_label(document.eligibility_criteria),
        ),
        Metric(label="Endpoints", value=_count_label(document.endpoints)),
        Metric(label="Visits", value=_count_label(document.schedule)),
        Metric(
            label="Empty pages",
            value=str(empty_page_count),
            tone=MetricTone.WARN if empty_page_count else MetricTone.GOOD,
        ),
    ]
    warnings = [
        StepWarning(
            code=f"facet_{item.facet.value.lower()}", message=item.message
        )
        for item in document.extraction_warnings
    ]
    return _step_logged(
        document,
        StepData(
            id=StepId.INGEST,
            title="Data Ingestion",
            summary=(
                f"'{document.title}' parsed into "
                f"{_count_label(document.sections)} sections and "
                f"{_count_label(document.eligibility_criteria)} eligibility "
                "criteria, each fact with a verified page quote."
            ),
            headline=Metric(
                label="pages read",
                value=str(document.page_count),
                tone=MetricTone.GOOD,
            ),
            metrics=metrics,
            status=StepStatus.PARTIAL if warnings else StepStatus.COMPLETED,
            agent="Parser",
            warnings=warnings,
            data_sources=[
                DataSource(
                    source=EvidenceSource.PROTOCOL,
                    name=document.title,
                    record_count=document.page_count,
                )
            ],
            tables=[
                DataTable(
                    table_id="ingest-criteria",
                    title="Eligibility criteria",
                    columns=[
                        TableColumn(key="criterion_id", label="ID"),
                        TableColumn(key="kind", label="Kind"),
                        TableColumn(key="text", label="Criterion"),
                        TableColumn(key="page", label="Page"),
                    ],
                    rows=[
                        {
                            "criterion_id": c.criterion_id,
                            "kind": c.kind.value,
                            "text": c.text,
                            "page": c.citation.page_number
                            if c.citation
                            else None,
                        }
                        for c in criteria
                    ],
                )
            ],
            details={
                "design": (
                    document.design.model_dump(mode="json", exclude_none=True)
                    if document.design
                    else None
                ),
            },
        ),
    )


async def run_checklist_agent(document: ProtocolDocument) -> StepData:
    """Return the CHECK section: the protocol against every rule.

    The check runs once per parsed protocol; repeated calls return the
    same step.

    Raises:
        AnalysisFailedError: Gemini is not configured (the app answers
            with 503).
    """
    try:
        run = await get_protocol_pipeline().check(document)
    except AnalysisFailedError:
        logger.exception(
            "completeness check failed: agent=%s protocol_id=%s",
            AGENT_LABEL,
            document.protocol_id,
        )
        raise
    step = to_check_step(
        run, load_rule_catalogue(), page_count=document.page_count
    )
    return _step_logged(document, step)


async def run_protocol_comparison_agent(
    document: ProtocolDocument,
) -> StepData:
    """Return the PEERS section (comparison with similar trials).

    Compares the demo draft with the committed peer snapshot and no LLM,
    so the step is fast, gives the same result when called twice and
    never writes to disk (the deployed filesystem is read-only).

    Raises:
        PeerStoreError: the peer snapshot in data/peers is missing or
            invalid; the route answers with a server error.
    """
    try:
        comparison = await compare_demo_draft()
    except PeerStoreError:
        logger.exception(
            "comparison failed: agent=%s protocol_id=%s",
            COMPARISON_AGENT_NAME,
            document.protocol_id,
        )
        raise
    step = comparison_step_data(
        document,
        comparison.draft_trial_id,
        comparison.protocol_date,
        comparison.results,
        comparison.cards,
    )
    return _step_logged(document, step)


async def run_cohort_agent(document: ProtocolDocument) -> StepData:
    """Return the COHORT section (eligibility on a simulated cohort).

    Simulates protocol eligibility criteria on the committed CDC NHANES
    adult diabetic cohort and benchmarks against peer trials with no
    disk writes.

    Raises:
        CohortDataError: the NHANES cohort or peer dataset in data/cohort
            is missing or invalid; the route answers with a server error.
    """
    try:
        report = await analyze_protocol_document_cohort(document)
    except CohortDataError:
        logger.exception(
            "cohort simulation failed: agent=%s protocol_id=%s",
            COHORT_AGENT_NAME,
            document.protocol_id,
        )
        raise
    step = cohort_step_data(report, document)
    return _step_logged(document, step)
