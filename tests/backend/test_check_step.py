"""Unit tests for the completeness report to /demo CHECK step mapping."""

from datetime import UTC, datetime

import pytest

from backend.agents.completeness.logic import (
    CheckOutcome,
    compute_run_result,
    finding_from_outcome,
)
from backend.agents.completeness.rules import load_rule_catalogue
from backend.api.check_step import GapKind, gap_kind, to_check_step
from backend.api.protocol_pipeline import CheckRun
from backend.api.schemas import (
    ChangeType,
    Decision,
    StepData,
    StepId,
    TraceKind,
)
from backend.shared.messages import (
    CheckMethod,
    Citation,
    ComplianceReport,
    FindingLocation,
    M11Heading,
    RuleFinding,
    RuleStatus,
    SearchedLocation,
    TrialProfile,
)

STARTED_AT = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
DURATION_SECONDS = 240.0
ENDPOINT_QUOTE = "The primary endpoint is HbA1c at an unspecified time."
CRITERION_QUOTE = "Poorly controlled hypertension"
SEARCHED = (
    SearchedLocation(
        heading=M11Heading.PROTOCOL_SUMMARY,
        section_title="1 Protocol Summary",
        start_page=2,
        end_page=4,
    ),
)


def _finding(rule_id: str, outcome: CheckOutcome) -> RuleFinding:
    rule = load_rule_catalogue().get(rule_id)
    return finding_from_outcome(rule, outcome, CheckMethod.DETERMINISTIC)


def _fired(
    rule_id: str,
    evidence: tuple[Citation, ...] = (),
    location: FindingLocation | None = None,
) -> RuleFinding:
    return _finding(
        rule_id,
        CheckOutcome(
            status=RuleStatus.FIRED,
            finding=f"{rule_id} fired.",
            evidence=evidence,
            searched_locations=() if evidence else SEARCHED,
            location=location or FindingLocation(),
        ),
    )


def _report() -> ComplianceReport:
    findings = [
        _fired(
            "REG-24",
            (Citation(page_number=3, quote=ENDPOINT_QUOTE, is_verified=True),),
            FindingLocation(
                section="3.1", heading=M11Heading.OBJECTIVES_AND_ESTIMANDS
            ),
        ),
        _fired("XS-07"),
        _fired("M11-21"),
        _fired(
            "ELQ-01",
            (
                Citation(
                    page_number=20, quote=CRITERION_QUOTE, is_verified=True
                ),
            ),
            FindingLocation(
                section="EX-01", heading=M11Heading.TRIAL_POPULATION, page=20
            ),
        ),
        _finding(
            "REG-01",
            CheckOutcome(status=RuleStatus.PASSED, finding="ID present."),
        ),
        _finding(
            "DM-43",
            CheckOutcome(
                status=RuleStatus.NOT_APPLICABLE,
                finding="Not applicable.",
                status_reason="type 2 diabetes trial",
            ),
        ),
        _finding(
            "EST-01",
            CheckOutcome(
                status=RuleStatus.CANNOT_ASSESS,
                finding="Cannot assess.",
                status_reason="judgement batch call failed",
            ),
        ),
    ]
    return ComplianceReport(
        protocol_id="proto-1",
        protocol_title="Example trial",
        trial_profile=TrialProfile(),
        rules_evaluated=len(findings),
        before=compute_run_result(findings),
        findings=findings,
    )


@pytest.fixture
def step() -> StepData:
    return to_check_step(
        CheckRun(
            report=_report(),
            started_at=STARTED_AT,
            duration_seconds=DURATION_SECONDS,
        ),
        load_rule_catalogue(),
        page_count=40,
    )


def _decision(step: StepData, rule_id: str) -> Decision:
    return next(d for d in step.decisions if d.decision_id == f"chk-{rule_id}")


def test_gap_kind_separates_missing_weak_and_contradictions() -> None:
    report = _report()
    kinds = {
        f.rule_id: gap_kind(f)
        for f in report.findings
        if f.status == RuleStatus.FIRED
    }

    assert kinds == {
        "REG-24": GapKind.WEAK,
        "XS-07": GapKind.CONTRADICTION,
        "M11-21": GapKind.MISSING,
        "ELQ-01": GapKind.WEAK,
    }


def test_every_fired_rule_is_a_check_decision_most_important_first(
    step: StepData,
) -> None:
    assert step.id == StepId.CHECK
    assert all(d.step_id == StepId.CHECK for d in step.decisions)
    # All four are S1 at full confidence, so ties break on rule ID.
    assert [d.decision_id for d in step.decisions] == [
        "chk-ELQ-01",
        "chk-M11-21",
        "chk-REG-24",
        "chk-XS-07",
    ]


def test_metrics_count_present_weak_missing_and_contradictions(
    step: StepData,
) -> None:
    values = {metric.label: metric.value for metric in step.metrics}

    assert values["Present"] == "1"
    assert values["Weak"] == "2"
    assert values["Missing"] == "1"
    assert values["Contradictions"] == "1"
    assert values["Not assessed"] == "1"
    assert values["Not applicable"] == "1"


def test_quoted_finding_carries_verbatim_evidence_and_a_modify_change(
    step: StepData,
) -> None:
    decision = _decision(step, "REG-24")

    [evidence] = decision.evidence
    assert (evidence.quote, evidence.page) == (ENDPOINT_QUOTE, 3)
    assert evidence.is_verified
    assert decision.proposed_change is not None
    assert decision.proposed_change.change_type == ChangeType.MODIFY
    assert decision.proposed_change.before == ENDPOINT_QUOTE
    for entry in decision.trace:
        assert set(entry.evidence_ids) <= {evidence.evidence_id}


def test_absence_finding_adds_text_and_shows_where_it_searched(
    step: StepData,
) -> None:
    decision = _decision(step, "M11-21")

    assert decision.evidence == []
    assert decision.proposed_change is not None
    assert decision.proposed_change.change_type == ChangeType.ADD
    assert decision.proposed_change.before == ""
    assert "1 Protocol Summary (pages 2-4)" in decision.trace[0].text


def test_confirmed_flag_shows_why_the_second_opinion_agreed() -> None:
    report = _report()
    reason = "The quoted endpoint has no time frame."
    findings = [
        f.model_copy(update={"second_opinion_reason": reason})
        if f.rule_id == "REG-24"
        else f
        for f in report.findings
    ]
    run = CheckRun(
        report=report.model_copy(update={"findings": findings}),
        started_at=STARTED_AT,
        duration_seconds=DURATION_SECONDS,
    )

    step = to_check_step(run, load_rule_catalogue(), page_count=40)

    last_entry = _decision(step, "REG-24").trace[-1]
    assert last_entry.kind == TraceKind.CONCLUDE
    assert last_entry.text == f"Second opinion confirmed: {reason}"
    assert len(_decision(step, "XS-07").trace) == 3


def test_eligibility_finding_points_at_its_criterion(step: StepData) -> None:
    location = _decision(step, "ELQ-01").location

    assert location is not None
    assert location.criterion_id == "EX-01"
    assert location.section_title is None
    assert (location.start_page, location.end_page) == (20, 20)


def test_impact_shows_the_score_and_gate_after_the_fix(step: StepData) -> None:
    impact = {m.label: m for m in _decision(step, "REG-24").impact}

    assert impact["Score if fixed"].numeric_value is not None
    assert step.headline.numeric_value is not None
    assert impact["Score if fixed"].numeric_value > step.headline.numeric_value
    # REG-24 is the only fired S1 registration rule.
    assert impact["Registration gate if fixed"].value.startswith("Pass")


def test_step_lists_every_rule_and_flags_a_partial_run(step: StepData) -> None:
    [checklist] = step.tables
    [chart] = step.charts

    assert len(checklist.rows) == 7
    assert [series.name for series in chart.series] == [
        "Fired",
        "Passed",
        "Not assessed",
        "Not applicable",
    ]
    assert step.status == "partial"
    assert {w.code for w in step.warnings} == {"partial_gate", "not_assessed"}
    assert step.duration_ms == 240_000


def test_failed_gemini_calls_add_a_retry_warning() -> None:
    run = CheckRun(
        report=_report(),
        started_at=STARTED_AT,
        duration_seconds=DURATION_SECONDS,
        failed_llm_calls=3,
    )

    step = to_check_step(run, load_rule_catalogue(), page_count=40)

    [warning] = [w for w in step.warnings if w.code == "gemini_calls_failed"]
    assert warning.message.startswith("3 Gemini calls failed")


def test_mapping_is_pure_and_repeatable() -> None:
    def build() -> StepData:
        return to_check_step(
            CheckRun(
                report=_report(),
                started_at=STARTED_AT,
                duration_seconds=DURATION_SECONDS,
            ),
            load_rule_catalogue(),
            page_count=40,
        )

    assert build() == build()
