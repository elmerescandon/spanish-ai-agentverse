"""Adapters that plug each agent into the /demo page.

Each function here is the single seam between one /demo section and the
agent behind it. The owner replaces the body of their function with a call
to their agent and maps the agent's output to ``StepData``; the route,
the schema and the frontend stay untouched. Runners only read the
document, never write shared state, so the three recommendation steps can
run in parallel and a retried call is safe.
"""

import logging
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
from backend.api.schemas import (
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
