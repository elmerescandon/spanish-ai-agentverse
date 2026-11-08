"""Adapters that plug each agent into the /demo page.

Each function here is the single seam between one /demo section and the
agent behind it. The owner replaces the body of their function with a call
to their agent and maps the agent's output to ``StepData``; the route,
the schema and the frontend stay untouched. Runners only read the
document, never write shared state, so the three recommendation steps can
run in parallel and a retried call is safe.
"""

import logging

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

    Raises:
        Nothing today (mock). Real agents should raise a specific
        exception the route can turn into an HTTP error.
    """
    # [TO REFACTOR:(theo)]: mock until the protocol comparison agent is
    # wired
    decision = _mock_decision(
        step_id=StepId.PEERS,
        key="prs-01",
        document=document,
        severity=Severity.WARNING,
        title="HbA1c exclusion stricter than peers",
        claim=(
            "The HbA1c upper limit excludes more patients than in "
            "similar Phase 3 trials."
        ),
        quote="HbA1c above 9.0% at screening.",
        agent="Comparison",
        rule_text="Compared the exclusion limit with 42 peer trials.",
        proposed_change=ProposedChange(
            path="5.2 Exclusion criteria",
            before="HbA1c above 9.0%",
            after="HbA1c above 10.0%",
        ),
        source=EvidenceSource.AACT,
    )
    return _step_logged(
        document,
        StepData(
            id=StepId.PEERS,
            title="Protocol Comparison",
            summary=(
                f"'{document.title}' compared with similar Phase 3 trials."
            ),
            headline=Metric(label="peer trials", value="42"),
            metrics=[
                Metric(label="Peer trials", value="42"),
                Metric(label="Outliers", value="2", tone=MetricTone.WARN),
                Metric(
                    label="Biggest outlier",
                    value="HbA1c >= 9.0",
                    tone=MetricTone.RISK,
                ),
                Metric(label="Peer median duration", value="36 wk"),
            ],
            decisions=[decision],
        ),
    )


async def run_cohort_agent(document: ProtocolDocument) -> StepData:
    """Return the COHORT section (eligibility on a simulated cohort).

    ``analyze_protocol_document_cohort`` in
    ``backend/agents/cohort/agent.py`` already exists; it still needs a
    mapping from its ``CohortComparisonReport`` to ``StepData``.

    Raises:
        Nothing today (mock). Real agents should raise a specific
        exception the route can turn into an HTTP error.
    """
    # [TO REFACTOR:(alvaro)]: mock until the cohort agent is wired
    decision = _mock_decision(
        step_id=StepId.COHORT,
        key="coh-01",
        document=document,
        severity=Severity.CRITICAL,
        title="eGFR exclusion removes the most patients",
        claim=(
            "The eGFR below 45 exclusion removes 31% of otherwise "
            "eligible patients, far more than in peer trials."
        ),
        quote="eGFR below 45 mL/min/1.73 m2 at screening.",
        agent="Cohort",
        rule_text="Converted the criterion to a computable eGFR filter.",
        proposed_change=ProposedChange(
            path="5.2 Exclusion criteria",
            before="eGFR below 45",
            after="eGFR below 30",
        ),
        source=EvidenceSource.MIMIC,
    )
    return _step_logged(
        document,
        StepData(
            id=StepId.COHORT,
            title="Cohort Comparison",
            summary=(
                f"'{document.title}' eligibility rules applied to a "
                "simulated patient cohort."
            ),
            headline=Metric(
                label="eGFR < 45", value="-31%", tone=MetricTone.RISK
            ),
            metrics=[
                Metric(label="Cohort", value="18,402"),
                Metric(label="Eligible", value="2,115", tone=MetricTone.GOOD),
                Metric(
                    label="Steepest drop",
                    value="eGFR < 45: -31%",
                    tone=MetricTone.RISK,
                ),
                Metric(
                    label="Cannot simulate",
                    value="3",
                    tone=MetricTone.WARN,
                ),
            ],
            decisions=[decision],
        ),
    )
