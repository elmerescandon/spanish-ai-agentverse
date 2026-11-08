"""Pure mapping from the completeness report to the /demo CHECK step.

Every fired rule becomes a Decision; every rule appears in the checklist
table. Fired rules are sorted most important first (severity weight times
confidence), matching the guidelines' summary order.
"""

from collections import Counter
from collections.abc import Sequence
from enum import StrEnum

from pydantic import JsonValue

from backend.agents.completeness.logic import (
    SEVERITY_WEIGHTS,
    compute_run_result,
)
from backend.agents.completeness.rules import RuleCatalogue
from backend.api.protocol_pipeline import CheckRun
from backend.api.schemas import (
    ChangeType,
    Chart,
    ChartKind,
    ChartPoint,
    ChartSeries,
    DataSource,
    DataTable,
    Decision,
    DecisionOption,
    Evidence,
    EvidenceSource,
    GuidelineReference,
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
from backend.shared.messages import (
    CheckMethod,
    ComplianceReport,
    GateResult,
    GateStatus,
    RuleFamily,
    RuleFinding,
    RuleSeverity,
    RuleStatus,
)

AGENT_LABEL = "Completeness"
STEP_TITLE = "Completeness & Consistency"
GOOD_SCORE = 80.0  # score at or above which the protocol reads as ready
FAIR_SCORE = 60.0  # score at or above which gaps are fixable, below: risk
MILLISECONDS_PER_SECOND = 1000
CRITERION_FAMILIES = frozenset({RuleFamily.ELQ, RuleFamily.EX})

SEVERITY_BY_RULE_SEVERITY: dict[RuleSeverity, Severity] = {
    RuleSeverity.S1: Severity.CRITICAL,
    RuleSeverity.S2: Severity.WARNING,
    RuleSeverity.S3: Severity.INFO,
}
FAMILY_LABELS: dict[RuleFamily, str] = {
    RuleFamily.REG: "Trial registration (ClinicalTrials.gov)",
    RuleFamily.M11: "ICH M11 structure",
    RuleFamily.EST: "Estimands and statistics",
    RuleFamily.XS: "Cross-section consistency",
    RuleFamily.DM: "Diabetes trial design",
    RuleFamily.ELQ: "Eligibility criteria quality",
    RuleFamily.EX: "Eligibility exclusion library",
    RuleFamily.AMD: "Amendments",
}
METHOD_LABELS: dict[CheckMethod, str] = {
    CheckMethod.DETERMINISTIC: "decided in code from the parsed protocol",
    CheckMethod.JUDGEMENT: "judged by Gemini and checked by a second opinion",
}
CHECKLIST_COLUMNS = (
    TableColumn(key="rule_id", label="Rule"),
    TableColumn(key="family", label="Family"),
    TableColumn(key="severity", label="Severity"),
    TableColumn(key="status", label="Status"),
    TableColumn(key="title", label="Check"),
    TableColumn(key="finding", label="Finding"),
    TableColumn(key="page", label="Page"),
    TableColumn(key="confidence", label="Confidence"),
    TableColumn(key="method", label="Method"),
)


class GapKind(StrEnum):
    """How a fired rule shows up in the protocol."""

    MISSING = "missing"  # required content not found
    WEAK = "weak"  # content present but deficient
    CONTRADICTION = "contradiction"  # sections disagree


def gap_kind(finding: RuleFinding) -> GapKind:
    """Classify a fired finding as missing, weak or a contradiction."""
    if finding.family == RuleFamily.XS:
        return GapKind.CONTRADICTION
    if not finding.evidence:
        return GapKind.MISSING
    return GapKind.WEAK


def _score_tone(score: float) -> MetricTone:
    if score >= GOOD_SCORE:
        return MetricTone.GOOD
    if score >= FAIR_SCORE:
        return MetricTone.WARN
    return MetricTone.RISK


def _gate_label(gate: GateResult) -> str:
    label = "Pass" if gate.status == GateStatus.PASS else "Fail"
    return f"{label} (partial)" if gate.is_partial else label


def _gate_metric(label: str, gate: GateResult) -> Metric:
    is_pass = gate.status == GateStatus.PASS
    return Metric(
        label=label,
        value=_gate_label(gate),
        tone=MetricTone.GOOD if is_pass else MetricTone.RISK,
        description=(
            "Partial: some S1 rules could not be assessed."
            if gate.is_partial
            else None
        ),
    )


def _rank(findings: Sequence[RuleFinding]) -> list[RuleFinding]:
    """Fired findings, most important first."""
    fired = [f for f in findings if f.status == RuleStatus.FIRED]
    return sorted(
        fired,
        key=lambda f: (
            -SEVERITY_WEIGHTS[f.severity] * f.confidence,
            f.rule_id,
        ),
    )


def _location(finding: RuleFinding) -> ProtocolLocation:
    pages = [c.page_number for c in finding.evidence]
    if finding.location.page is not None:
        pages.append(finding.location.page)
    is_criterion = finding.family in CRITERION_FAMILIES
    return ProtocolLocation(
        section_heading=finding.location.heading,
        section_title=None if is_criterion else finding.location.section,
        start_page=min(pages, default=None),
        end_page=max(pages, default=None),
        criterion_id=finding.location.section if is_criterion else None,
    )


def _evidence(finding: RuleFinding, document_title: str) -> list[Evidence]:
    return [
        Evidence(
            evidence_id=f"ev-{finding.rule_id}-{index}",
            source=EvidenceSource.PROTOCOL,
            document=document_title,
            page=citation.page_number,
            quote=citation.quote,
            is_verified=citation.is_verified,
            confidence=finding.confidence,
        )
        for index, citation in enumerate(finding.evidence, start=1)
    ]


def _trace(
    finding: RuleFinding, flag_if: str, evidence: Sequence[Evidence]
) -> list[TraceEntry]:
    evidence_ids = [item.evidence_id for item in evidence]
    if finding.searched_locations:
        searched = "; ".join(
            f"{loc.section_title or loc.heading.value} "
            f"(pages {loc.start_page}-{loc.end_page})"
            for loc in finding.searched_locations
        )
        retrieved = f"Searched {searched}."
    else:
        retrieved = f"Found {len(evidence)} supporting quote(s)."
    trace = [
        TraceEntry(
            agent=AGENT_LABEL,
            kind=TraceKind.RETRIEVE,
            text=retrieved,
            evidence_ids=evidence_ids,
        ),
        TraceEntry(
            agent=AGENT_LABEL,
            kind=TraceKind.RULE,
            text=f"{finding.rule_id}: flag if {flag_if}",
        ),
        TraceEntry(
            agent=AGENT_LABEL,
            kind=TraceKind.CONCLUDE,
            text=(
                f"{finding.finding} ({METHOD_LABELS[finding.check_method]})"
            ),
            evidence_ids=evidence_ids,
        ),
    ]
    if finding.second_opinion_reason:
        trace.append(
            TraceEntry(
                agent=AGENT_LABEL,
                kind=TraceKind.CONCLUDE,
                text=(
                    "Second opinion confirmed: "
                    f"{finding.second_opinion_reason}"
                ),
            )
        )
    return trace


def _proposed_change(finding: RuleFinding) -> ProposedChange | None:
    if finding.proposed_fix is None:
        return None
    location = finding.location
    path = location.section or (
        location.heading.value if location.heading else "Protocol"
    )
    has_quote = bool(finding.evidence)
    return ProposedChange(
        path=path,
        before=finding.evidence[0].quote if has_quote else "",
        after=finding.proposed_fix,
        change_type=ChangeType.MODIFY if has_quote else ChangeType.ADD,
        section_title=location.heading.value if location.heading else None,
        page=location.page,
        rationale=finding.title,
    )


def _impact_if_fixed(
    finding: RuleFinding, report: ComplianceReport
) -> list[Metric]:
    """Score and gates as they would be with this one rule passing."""
    fixed = compute_run_result(
        [
            f.model_copy(update={"status": RuleStatus.PASSED})
            if f.rule_id == finding.rule_id
            else f
            for f in report.findings
        ]
    )
    impact = [
        Metric(
            label="Score if fixed",
            value=f"{fixed.score:.0f}/100",
            tone=_score_tone(fixed.score),
            numeric_value=round(fixed.score, 1),
            unit="/100",
        )
    ]
    gates = (
        (
            "Registration gate",
            report.before.registration_gate,
            fixed.registration_gate,
        ),
        ("Review gate", report.before.review_gate, fixed.review_gate),
    )
    for label, before, after in gates:
        if before.status != after.status:
            impact.append(_gate_metric(f"{label} if fixed", after))
    return impact


def _decision(
    finding: RuleFinding,
    report: ComplianceReport,
    catalogue: RuleCatalogue,
) -> Decision:
    decision_id = f"chk-{finding.rule_id}"
    evidence = _evidence(finding, report.protocol_title)
    proposed_change = _proposed_change(finding)
    impact = _impact_if_fixed(finding, report)
    severity_label = finding.severity.value
    return Decision(
        decision_id=decision_id,
        step_id=StepId.CHECK,
        severity=SEVERITY_BY_RULE_SEVERITY[finding.severity],
        title=finding.title,
        claim=finding.finding,
        evidence=evidence,
        trace=_trace(
            finding, catalogue.get(finding.rule_id).flag_if, evidence
        ),
        proposed_change=proposed_change,
        category=FAMILY_LABELS[finding.family],
        confidence=finding.confidence,
        location=_location(finding),
        impact=impact,
        options=[
            DecisionOption(
                option_id=f"{decision_id}-fix",
                title="Apply the fix",
                rationale=finding.proposed_fix or finding.title,
                is_recommended=True,
                proposed_change=proposed_change,
                impact=impact,
            ),
            DecisionOption(
                option_id=f"{decision_id}-justify",
                title="Keep the text and record a justification",
                rationale=(
                    "Keep the protocol as it is and document why this "
                    "rule does not apply."
                ),
                risks=[
                    (
                        f"Stays an open {severity_label} finding for "
                        f"reviewers ({finding.source})."
                    )
                ],
            ),
        ],
        references=[GuidelineReference(label=finding.source)],
        decision_owner=(
            "Medical Monitor"
            if finding.requires_medical_review
            else "Protocol author"
        ),
        tags=[
            finding.rule_id,
            finding.family.value,
            severity_label,
            gap_kind(finding).value,
            finding.source_tier.value,
        ],
        details={
            "rule_id": finding.rule_id,
            "source_tier": finding.source_tier.value,
            "check_method": finding.check_method.value,
            "searched_locations": [
                loc.model_dump(mode="json")
                for loc in finding.searched_locations
            ],
        },
    )


def _checklist_table(findings: Sequence[RuleFinding]) -> DataTable:
    rows: list[dict[str, JsonValue]] = [
        {
            "rule_id": f.rule_id,
            "family": f.family.value,
            "severity": f.severity.value,
            "status": f.status.value,
            "title": f.title,
            "finding": f.finding,
            "page": f.location.page,
            "confidence": round(f.confidence, 2),
            "method": f.check_method.value,
        }
        for f in findings
    ]
    return DataTable(
        table_id="check-checklist",
        title="Full checklist",
        description="Every rule with its outcome, in catalogue order.",
        columns=list(CHECKLIST_COLUMNS),
        rows=rows,
    )


def _family_chart(findings: Sequence[RuleFinding]) -> Chart:
    groups = {
        "Fired": {RuleStatus.FIRED},
        "Passed": {RuleStatus.PASSED},
        "Not assessed": {
            RuleStatus.CANNOT_ASSESS,
            RuleStatus.INSUFFICIENT_COMPARATORS,
        },
        "Not applicable": {RuleStatus.NOT_APPLICABLE},
    }
    families = [
        family
        for family in RuleFamily
        if any(f.family == family for f in findings)
    ]
    counts = Counter((f.family, f.status) for f in findings)
    return Chart(
        chart_id="check-families",
        kind=ChartKind.STACKED_BAR,
        title="Rule outcomes by family",
        y_label="Rules",
        series=[
            ChartSeries(
                name=name,
                points=[
                    ChartPoint(
                        label=family.value,
                        value=sum(counts[(family, s)] for s in statuses),
                        annotation=FAMILY_LABELS[family],
                    )
                    for family in families
                ],
            )
            for name, statuses in groups.items()
        ],
    )


def _gate_details(gate: GateResult) -> dict[str, JsonValue]:
    return {
        "status": gate.status.value,
        "is_partial": gate.is_partial,
        "failing_rule_ids": list(gate.failing_rule_ids),
    }


def to_check_step(
    run: CheckRun, catalogue: RuleCatalogue, page_count: int
) -> StepData:
    """Map a completeness check run to the /demo CHECK section."""
    report = run.report
    findings = report.findings
    ranked = _rank(findings)
    statuses = Counter(f.status for f in findings)
    gaps = Counter(gap_kind(f) for f in ranked)
    not_assessed = (
        statuses[RuleStatus.CANNOT_ASSESS]
        + statuses[RuleStatus.INSUFFICIENT_COMPARATORS]
    )
    score = report.before.score
    registration = report.before.registration_gate
    review = report.before.review_gate
    is_partial = registration.is_partial or review.is_partial
    warnings = []
    if is_partial:
        warnings.append(
            StepWarning(
                code="partial_gate",
                message=(
                    "A gate is partial: some S1 rules could not be assessed, "
                    "so a pass is provisional."
                ),
            )
        )
    if not_assessed:
        warnings.append(
            StepWarning(
                code="not_assessed",
                message=(
                    f"{not_assessed} rules could not be assessed; see the "
                    "checklist table for each reason."
                ),
                severity=Severity.INFO,
            )
        )
    return StepData(
        id=StepId.CHECK,
        title=STEP_TITLE,
        summary=(
            f"'{report.protocol_title}' checked against "
            f"{report.rules_evaluated} rules: {len(ranked)} findings, score "
            f"{score:.0f}/100, registration gate "
            f"{_gate_label(registration).lower()}, review gate "
            f"{_gate_label(review).lower()}."
        ),
        headline=Metric(
            label="completeness score",
            value=f"{score:.0f}/100",
            tone=_score_tone(score),
            numeric_value=round(score, 1),
            unit="/100",
        ),
        metrics=[
            Metric(
                label="Present",
                value=str(statuses[RuleStatus.PASSED]),
                tone=MetricTone.GOOD,
            ),
            Metric(
                label="Weak",
                value=str(gaps[GapKind.WEAK]),
                tone=MetricTone.WARN,
            ),
            Metric(
                label="Missing",
                value=str(gaps[GapKind.MISSING]),
                tone=MetricTone.RISK,
            ),
            Metric(
                label="Contradictions",
                value=str(gaps[GapKind.CONTRADICTION]),
                tone=MetricTone.WARN,
            ),
            Metric(
                label="Score",
                value=f"{score:.0f}/100",
                tone=_score_tone(score),
                numeric_value=round(score, 1),
            ),
            _gate_metric("Registration gate", registration),
            _gate_metric("Review gate", review),
            Metric(label="Not assessed", value=str(not_assessed)),
            Metric(
                label="Not applicable",
                value=str(statuses[RuleStatus.NOT_APPLICABLE]),
            ),
        ],
        decisions=[_decision(f, report, catalogue) for f in ranked],
        status=StepStatus.PARTIAL if is_partial else StepStatus.COMPLETED,
        agent=AGENT_LABEL,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_ms=round(run.duration_seconds * MILLISECONDS_PER_SECOND),
        warnings=warnings,
        data_sources=[
            DataSource(
                source=EvidenceSource.PROTOCOL,
                name=report.protocol_title,
                description="The uploaded protocol, parsed by Gemini.",
                record_count=page_count,
            ),
            DataSource(
                source=EvidenceSource.GUIDELINE,
                name="Completeness rule catalogue",
                description=(
                    "ICH M11 and E9(R1), FDAAA 801 and ClinicalTrials.gov "
                    "criteria, EMA and FDA diabetes guidance, FDA "
                    "eligibility guidance."
                ),
                record_count=report.rules_evaluated,
            ),
        ],
        tables=[_checklist_table(findings)],
        charts=[_family_chart(findings)],
        details={
            "score": round(score, 1),
            "registration_gate": _gate_details(registration),
            "review_gate": _gate_details(review),
            "status_counts": {s.value: statuses[s] for s in RuleStatus},
            "top_rule_ids": [f.rule_id for f in ranked],
            "trial_profile": report.trial_profile.model_dump(
                mode="json", exclude_none=True
            ),
            "protocol_version": report.protocol_version,
        },
    )
