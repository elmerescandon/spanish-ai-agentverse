"""Adapters that plug each agent into the /demo page.

Each function here is the single seam between one /demo section and the
agent behind it. The owner replaces the body of their function with a call
to their agent and maps the agent's output to ``StepData``; the route,
the schema and the frontend stay untouched. Runners only read the
document, never write shared state, so the three recommendation steps can
run in parallel and a retried call is safe.
"""

import logging

from backend.agents.cohort.agent import (
    AGENT_NAME as COHORT_AGENT_NAME,
)
from backend.agents.cohort.agent import (
    analyze_protocol_document_cohort,
)
from backend.agents.cohort.step_data import to_step_data as cohort_step_data
from backend.agents.protocol_comparison.agent import (
    AGENT_NAME as COMPARISON_AGENT_NAME,
)
from backend.agents.protocol_comparison.demo import compare_demo_draft
from backend.agents.protocol_comparison.peer_store import PeerStoreError
from backend.agents.protocol_comparison.step_data import (
    to_step_data as comparison_step_data,
)
from backend.api.schemas import (
    Decision,
    Evidence,
    EvidenceSource,
    Metric,
    MetricTone,
    ProposedChange,
    Severity,
    StepData,
    StepId,
    TraceEntry,
    TraceKind,
)
from backend.clients.cohort_data import CohortDataError
from backend.shared.messages import ProtocolDocument

logger = logging.getLogger(__name__)

MOCK_EVIDENCE_PAGE = 1  # mocks cite page 1 so the quote link always resolves


def _step_logged(document: ProtocolDocument, step: StepData) -> StepData:
    """Log which step was produced for which protocol, then return it."""
    logger.info(
        "step built: step_id=%s protocol_id=%s decisions=%d",
        step.id,
        document.protocol_id,
        len(step.decisions),
    )
    return step


def build_ingest_step(document: ProtocolDocument) -> StepData:
    """Build the INGEST section from the text-only read of the upload.

    Pure: uses only the document's pages and counts.
    """
    # [TO REFACTOR:(alex)]: swap text-only read for parse_protocol once
    # Gemini is wired into upload
    character_count = sum(len(page.text) for page in document.pages)
    empty_page_count = sum(
        1 for page in document.pages if not page.text.strip()
    )
    metrics = [
        Metric(label="Pages", value=str(document.page_count)),
        Metric(
            label="Characters",
            value=f"{character_count:,}",
            tone=MetricTone.GOOD,
        ),
        Metric(
            label="Empty pages",
            value=str(empty_page_count),
            tone=MetricTone.WARN if empty_page_count else MetricTone.GOOD,
        ),
    ]
    return _step_logged(
        document,
        StepData(
            id=StepId.INGEST,
            title="Data Ingestion",
            summary=(
                f"'{document.title}' read as text; structured parsing "
                "is not wired in yet."
            ),
            headline=Metric(
                label="pages read",
                value=str(document.page_count),
                tone=MetricTone.GOOD,
            ),
            metrics=metrics,
        ),
    )


def _mock_decision(
    *,
    step_id: StepId,
    key: str,
    document: ProtocolDocument,
    severity: Severity,
    title: str,
    claim: str,
    quote: str,
    agent: str,
    rule_text: str,
    proposed_change: ProposedChange,
    source: EvidenceSource = EvidenceSource.PROTOCOL,
) -> Decision:
    """Assemble one mock Decision with a single evidence and a short trace."""
    evidence_id = f"e-{key}"
    return Decision(
        decision_id=f"d-{key}",
        step_id=step_id,
        severity=severity,
        title=title,
        claim=claim,
        evidence=[
            Evidence(
                evidence_id=evidence_id,
                source=source,
                document=document.title,
                page=MOCK_EVIDENCE_PAGE,
                quote=quote,
            )
        ],
        trace=[
            TraceEntry(
                agent=agent,
                kind=TraceKind.RULE,
                text=rule_text,
                evidence_ids=[evidence_id],
            ),
            TraceEntry(
                agent=agent,
                kind=TraceKind.CONCLUDE,
                text=claim,
                evidence_ids=[evidence_id],
            ),
        ],
        proposed_change=proposed_change,
    )


async def run_checklist_agent(document: ProtocolDocument) -> StepData:
    """Return the CHECK section (completeness and consistency).

    Raises:
        Nothing today (mock). Real agents should raise a specific
        exception the route can turn into an HTTP error.
    """
    # [TO REFACTOR:(alex)]: mock until the checklist agent is wired
    decision = _mock_decision(
        step_id=StepId.CHECK,
        key="chk-01",
        document=document,
        severity=Severity.CRITICAL,
        title="Rescue medication criteria missing",
        claim=(
            "No rescue medication rule is defined, although the "
            "protocol allows glycaemic rescue after Week 12."
        ),
        quote=(
            "Rescue therapy may be initiated at the investigator's "
            "discretion after Week 12."
        ),
        agent="Completeness",
        rule_text="Rubric item R-07 requires explicit rescue thresholds.",
        proposed_change=ProposedChange(
            path="6.4 Rescue therapy",
            before="at the investigator's discretion",
            after="when fasting plasma glucose exceeds 13.3 mmol/L",
        ),
    )
    return _step_logged(
        document,
        StepData(
            id=StepId.CHECK,
            title="Completeness & Consistency",
            summary=f"'{document.title}' checked against the rubric.",
            headline=Metric(
                label="items missing", value="2", tone=MetricTone.RISK
            ),
            metrics=[
                Metric(label="Present", value="9", tone=MetricTone.GOOD),
                Metric(label="Weak", value="3", tone=MetricTone.WARN),
                Metric(label="Missing", value="2", tone=MetricTone.RISK),
                Metric(
                    label="Contradictions", value="1", tone=MetricTone.WARN
                ),
            ],
            decisions=[decision],
        ),
    )


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
