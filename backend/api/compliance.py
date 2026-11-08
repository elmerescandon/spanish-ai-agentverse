"""Pure mappers from internal ComplianceReport models to API responses."""

from collections.abc import Sequence

from backend.api.schemas import (
    ComplianceReportResponse,
    FamilySummary,
    FindingView,
    PipelineStep,
    Recommendation,
    RunInfo,
    Severity,
    StatusCounts,
)
from backend.shared.messages import (
    ComplianceReport,
    RuleFamily,
    RuleFinding,
    RuleSeverity,
    RuleStatus,
)

MAX_TOP_FINDINGS = 15  # guidelines summary cap on top fired rules

SEVERITY_WEIGHTS: dict[RuleSeverity, int] = {
    RuleSeverity.S1: 10,
    RuleSeverity.S2: 4,
    RuleSeverity.S3: 1,
}

CARD_SEVERITY_BY_RULE_SEVERITY: dict[RuleSeverity, Severity] = {
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
    RuleFamily.AMD: "Amendments and prior protocols",
}


def format_finding_id(protocol_id: str, rule_id: str) -> str:
    """Build the composite finding/recommendation identifier."""
    return f"{protocol_id}:{rule_id}"


def _to_finding_view(protocol_id: str, finding: RuleFinding) -> FindingView:
    return FindingView(
        finding_id=format_finding_id(protocol_id, finding.rule_id),
        **finding.model_dump(),
    )


def _compute_status_counts(findings: Sequence[RuleFinding]) -> StatusCounts:
    counts_by_status = {status: 0 for status in RuleStatus}
    for item in findings:
        counts_by_status[item.status] += 1
    return StatusCounts(
        fired=counts_by_status[RuleStatus.FIRED],
        passed=counts_by_status[RuleStatus.PASSED],
        not_applicable=counts_by_status[RuleStatus.NOT_APPLICABLE],
        insufficient_comparators=counts_by_status[
            RuleStatus.INSUFFICIENT_COMPARATORS
        ],
        cannot_assess=counts_by_status[RuleStatus.CANNOT_ASSESS],
        total=len(findings),
    )


def _compute_family_summaries(
    findings: Sequence[RuleFinding],
) -> list[FamilySummary]:
    summaries: list[FamilySummary] = []
    for family in RuleFamily:
        family_findings = [item for item in findings if item.family == family]
        if not family_findings:
            continue
        fired = sum(
            1 for item in family_findings if item.status == RuleStatus.FIRED
        )
        applicable = sum(
            1
            for item in family_findings
            if item.status in (RuleStatus.FIRED, RuleStatus.PASSED)
        )
        summaries.append(
            FamilySummary(
                family=family,
                label=FAMILY_LABELS[family],
                fired=fired,
                applicable=applicable,
            )
        )
    return summaries


def _rank_top_finding_ids(
    protocol_id: str, findings: Sequence[RuleFinding]
) -> list[str]:
    fired_findings = [
        item for item in findings if item.status == RuleStatus.FIRED
    ]
    ranked = sorted(
        fired_findings,
        key=lambda item: (
            -SEVERITY_WEIGHTS[item.severity] * item.confidence,
            item.rule_id,
        ),
    )
    return [
        format_finding_id(protocol_id, item.rule_id)
        for item in ranked[:MAX_TOP_FINDINGS]
    ]


def to_compliance_report_response(
    report: ComplianceReport,
) -> ComplianceReportResponse:
    """Convert an internal ComplianceReport into the frontend API schema."""
    return ComplianceReportResponse(
        protocol_id=report.protocol_id,
        protocol_title=report.protocol_title,
        protocol_version=report.protocol_version,
        run=RunInfo(
            rules_evaluated=report.rules_evaluated,
            comparators_used=report.comparators_used,
        ),
        before=report.before,
        after=report.after,
        counts=_compute_status_counts(report.findings),
        families=_compute_family_summaries(report.findings),
        top_finding_ids=_rank_top_finding_ids(
            report.protocol_id, report.findings
        ),
        findings=[
            _to_finding_view(report.protocol_id, item)
            for item in report.findings
        ],
        fixes=report.fixes,
        new_findings_after_fixes=[
            _to_finding_view(report.protocol_id, item)
            for item in report.new_findings_after_fixes
        ],
        sponsor_inputs_needed=report.sponsor_inputs_needed,
    )


def finding_to_recommendation(
    protocol_id: str, finding: RuleFinding
) -> Recommendation:
    """Convert a rule finding into a Decision Card Recommendation."""
    dumped = finding.model_dump(mode="json")
    details: dict[str, object] = {
        "rule_id": dumped["rule_id"],
        "family": dumped["family"],
        "rule_severity": dumped["severity"],
        "location": dumped["location"],
        "evidence": dumped["evidence"],
        "searched_locations": dumped["searched_locations"],
        "proposed_fix": dumped["proposed_fix"],
        "requires_medical_review": dumped["requires_medical_review"],
        "confidence": dumped["confidence"],
        "source": dumped["source"],
        "source_tier": dumped["source_tier"],
        "check_method": dumped["check_method"],
    }
    return Recommendation(
        recommendation_id=format_finding_id(protocol_id, finding.rule_id),
        protocol_id=protocol_id,
        source_step=PipelineStep.COMPLETENESS,
        severity=CARD_SEVERITY_BY_RULE_SEVERITY[finding.severity],
        title=finding.title,
        description=finding.finding,
        details=details,
    )


def to_recommendations(report: ComplianceReport) -> list[Recommendation]:
    """Convert fired findings in a ComplianceReport into Recommendations."""
    return [
        finding_to_recommendation(report.protocol_id, item)
        for item in report.findings
        if item.status == RuleStatus.FIRED
    ]
