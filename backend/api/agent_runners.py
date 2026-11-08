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
from typing import cast

from pydantic import JsonValue

from backend.agents.cohort import (
    CohortComparisonReport,
    CohortRecommendationCard,
    CriterionType,
    ProtocolCriterionInput,
    analyze_protocol_cohort,
    analyze_protocol_document_cohort,
)
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
    Decision,
    DecisionOption,
    Evidence,
    EvidenceSource,
    Metric,
    MetricTone,
    ProposedChange,
    ProtocolLocation,
    Severity,
    StepData,
    StepId,
    StepStatus,
    StepWarning,
    TableColumn,
    TraceEntry,
    TraceKind,
)
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
        run.report,
        load_rule_catalogue(),
        page_count=document.page_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
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


def _cohort_card_to_decision(
    card: CohortRecommendationCard,
    document: ProtocolDocument,
) -> Decision:
    """Map a CohortRecommendationCard into a clinician Decision Card."""
    evidence_id = f"ev-{card.recommendation_id}"
    quote_text = card.quote if card.quote else card.original_criterion_text
    evidence = [
        Evidence(
            evidence_id=evidence_id,
            source=EvidenceSource.PROTOCOL,
            document=document.title,
            page=card.page_number if card.page_number else 1,
            quote=quote_text,
            section_title="Eligibility Criteria",
        )
    ]

    trace = [
        TraceEntry(
            agent="Cohort",
            kind=TraceKind.RULE,
            text=(
                f"Compiled rule '{card.compiled_rule_summary}' excludes "
                f"{card.target_drop_pct:.1f}% of diabetic cohort "
                f"(peers drop: {card.peer_median_drop_pct or 0.0:.1f}%)."
            ),
            evidence_ids=[evidence_id],
        ),
        TraceEntry(
            agent="Cohort",
            kind=TraceKind.COMPARE,
            text=(
                f"Peer median threshold is '{card.peer_median_threshold}'; "
                f"clinical standard is '{card.clinical_standard_threshold}'."
            ),
            evidence_ids=[evidence_id],
        ),
        TraceEntry(
            agent="Cohort",
            kind=TraceKind.CONCLUDE,
            text=card.description,
            evidence_ids=[evidence_id],
        ),
    ]

    options: list[DecisionOption] = []
    recommended_proposed_change: ProposedChange | None = None
    for opt in card.doctor_options:
        opt_impact: list[Metric] = []
        prop_change: ProposedChange | None = None
        if opt.what_if_simulation is not None:
            wi = opt.what_if_simulation
            opt_impact.append(
                Metric(
                    label="Eligible after",
                    value=(
                        f"{wi.eligible_after:,} ({wi.eligible_pct_after:.1f}%)"
                    ),
                    tone=MetricTone.GOOD,
                )
            )
            opt_impact.append(
                Metric(
                    label="Patients gained",
                    value=(
                        f"+{wi.patients_gained:,} "
                        f"(+{wi.relative_gain_pct:.1f}%)"
                    ),
                    tone=MetricTone.GOOD,
                )
            )
            prop_change = ProposedChange(
                path="5.1 Eligibility criteria",
                before=card.original_criterion_text,
                after=wi.proposed_protocol_wording,
            )
            if recommended_proposed_change is None:
                recommended_proposed_change = prop_change

        options.append(
            DecisionOption(
                option_id=opt.option_id,
                title=opt.title,
                rationale=opt.clinical_rationale,
                is_recommended=(opt.kind.value == "RELAX_TO_PEER_STANDARD"),
                proposed_change=prop_change,
                impact=opt_impact,
                risks=(
                    [opt.safety_monitoring_requirement]
                    if opt.safety_monitoring_requirement
                    else []
                ),
            )
        )

    decision_severity = (
        Severity.CRITICAL
        if card.severity.value == "critical"
        else Severity.WARNING
    )

    return Decision(
        decision_id=card.recommendation_id,
        step_id=StepId.COHORT,
        severity=decision_severity,
        title=card.title,
        claim=card.description,
        evidence=evidence,
        trace=trace,
        proposed_change=recommended_proposed_change,
        location=ProtocolLocation(
            criterion_id=card.criterion_id,
            start_page=card.page_number,
            end_page=card.page_number,
        ),
        options=options,
        decision_owner=card.decision_owner,
    )


def map_cohort_report_to_step_data(
    report: CohortComparisonReport,
    document: ProtocolDocument,
) -> StepData:
    """Map a CohortComparisonReport into the /demo StepData contract."""
    steepest_step = (
        max(report.attrition_funnel, key=lambda s: s.marginal_drop_pct)
        if report.attrition_funnel
        else None
    )
    if steepest_step is not None:
        cid = steepest_step.criterion_id
        pct = steepest_step.marginal_drop_pct
        steepest_label = f"{cid}: -{pct:.1f}%"
    else:
        steepest_label = "None"

    metrics = [
        Metric(
            label="Cohort",
            value=f"{report.base_population_count:,}",
        ),
        Metric(
            label="Eligible",
            value=(
                f"{report.target_eligible_count:,} "
                f"({report.target_eligible_pct:.1f}%)"
            ),
            tone=(
                MetricTone.GOOD
                if report.target_eligible_pct >= 20.0
                else MetricTone.WARN
            ),
        ),
        Metric(
            label="Peer eligible",
            value=f"{report.peer_mean_eligible_pct:.1f}%",
        ),
        Metric(
            label="Steepest drop",
            value=steepest_label,
            tone=MetricTone.RISK,
        ),
    ]

    decisions = [
        _cohort_card_to_decision(card, document)
        for card in report.recommendations
    ]

    headline = Metric(
        label="Eligible cohort",
        value=f"{report.target_eligible_pct:.1f}%",
        tone=(
            MetricTone.GOOD
            if report.target_eligible_pct >= 20.0
            else MetricTone.RISK
        ),
    )

    return StepData(
        id=StepId.COHORT,
        title="Cohort Comparison",
        summary=(
            f"'{document.title}' simulated on "
            f"{report.base_population_count:,} diabetic patients (NHANES); "
            f"target retains {report.target_eligible_pct:.1f}% vs "
            f"{report.peer_mean_eligible_pct:.1f}% peer average."
        ),
        headline=headline,
        metrics=metrics,
        decisions=decisions,
        details={
            "feasibility_status": report.feasibility_status.value,
            "data_transparency_notices": cast(
                list[JsonValue], list(report.data_transparency_notices)
            ),
            "unsimulatable_criteria_count": len(
                report.unsimulatable_criteria_for_doctor
            ),
        },
    )


DEFAULT_COHORT_CRITERIA_FOR_UNPARSED_DOC: tuple[
    ProtocolCriterionInput, ...
] = (
    ProtocolCriterionInput(
        criterion_id="IN-01",
        kind=CriterionType.INCLUSION,
        text="Adults aged >= 18 years with diagnosis of Type 2 Diabetes",
        page_number=1,
        quote="glycemic control in adults with type 2 diabetes mellitus",
    ),
    ProtocolCriterionInput(
        criterion_id="IN-02",
        kind=CriterionType.INCLUSION,
        text="HbA1c between 7.0% and 10.5% inclusive at screening",
        page_number=1,
        quote="HbA1c between 7.0% and 10.5%",
    ),
    ProtocolCriterionInput(
        criterion_id="IN-03",
        kind=CriterionType.INCLUSION,
        text="Body Mass Index (BMI) <= 30.0 kg/m2 at baseline visit",
        page_number=1,
        quote="Body Mass Index (BMI) <= 30.0 kg/m2",
    ),
    ProtocolCriterionInput(
        criterion_id="EX-01",
        kind=CriterionType.EXCLUSION,
        text="Impaired renal function defined as eGFR < 75 mL/min/1.73m2",
        page_number=1,
        quote="eGFR < 75 mL/min/1.73m2",
    ),
)


async def run_cohort_agent(document: ProtocolDocument) -> StepData:
    """Return the COHORT section (eligibility on a simulated cohort).

    Runs analyze_protocol_document_cohort on CDC NHANES adult cohort,
    benchmarks against adult peer trials and Theo's registry, and maps
    the resulting CohortComparisonReport to StepData. If the document has
    not yet undergone structured parsing (e.g. text-only PDF upload),
    evaluates default adult diabetes eligibility criteria so the clinician
    always receives actionable Decision Cards.
    """
    if document.eligibility_criteria:
        report = await analyze_protocol_document_cohort(
            document=document,
            use_default_gemini_if_configured=True,
        )
    else:
        report = await analyze_protocol_cohort(
            protocol_id=document.protocol_id,
            protocol_title=document.title,
            criteria=list(DEFAULT_COHORT_CRITERIA_FOR_UNPARSED_DOC),
            min_age_years=18.0,
        )
    step = map_cohort_report_to_step_data(report, document)
    return _step_logged(document, step)
