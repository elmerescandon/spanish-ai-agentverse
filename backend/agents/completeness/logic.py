"""Pure engine of the completeness checker: applicability, findings, score.

No I/O here: agent.py extracts the trial profile with Gemini and runs the
rule checks; this module decides which rules apply, turns check outcomes
into findings, and computes the score and gates from the guidelines.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import assert_never

from backend.agents.completeness.rules import (
    ApplicabilityCondition,
    RequiredInput,
    RuleCatalogue,
    RuleDefinition,
)
from backend.shared.messages import (
    AllocationType,
    CheckMethod,
    Citation,
    CitedValue,
    ComplianceReport,
    ControlType,
    DiabetesType,
    DrugClass,
    FindingLocation,
    GateResult,
    GateStatus,
    InterventionType,
    M11Heading,
    MaskingType,
    PageText,
    ProtocolDocument,
    RuleFamily,
    RuleFinding,
    RuleSeverity,
    RuleStatus,
    RunResult,
    SearchedLocation,
    TrialDesignFacts,
    TrialProfile,
)

SEVERITY_WEIGHTS: dict[RuleSeverity, int] = {
    RuleSeverity.S1: 10,
    RuleSeverity.S2: 4,
    RuleSeverity.S3: 1,
}
PERFECT_SCORE = 100.0
SCORED_STATUSES = frozenset({RuleStatus.FIRED, RuleStatus.PASSED})
UNASSESSED_STATUSES = frozenset(
    {RuleStatus.CANNOT_ASSESS, RuleStatus.INSUFFICIENT_COMPARATORS}
)
REGISTRATION_GATE_FAMILIES = (RuleFamily.REG,)
REVIEW_GATE_FAMILIES = (RuleFamily.EST, RuleFamily.XS, RuleFamily.DM)
# S1 rules per family in the full guidelines. Gates only look at S1 rules,
# so a gate is complete once all S1 rules of its families are evaluated.
GATE_S1_RULE_TOTALS: dict[RuleFamily, int] = {
    RuleFamily.REG: 19,
    RuleFamily.EST: 14,
    RuleFamily.XS: 10,
    RuleFamily.DM: 16,
}
DRUG_INTERVENTIONS = frozenset(
    {InterventionType.DRUG, InterventionType.BIOLOGIC}
)
BLINDED_MASKING = frozenset(
    {
        MaskingType.SINGLE,
        MaskingType.DOUBLE,
        MaskingType.TRIPLE,
        MaskingType.QUADRUPLE,
    }
)
CONDITION_LABELS: dict[ApplicabilityCondition, str] = {
    ApplicabilityCondition.INTERVENTION_IS_DRUG: (
        "the intervention is a drug or biologic"
    ),
    ApplicabilityCondition.DIABETES_TYPE_T1D: (
        "the population has type 1 diabetes"
    ),
    ApplicabilityCondition.DIABETES_TYPE_T2D: (
        "the population has type 2 diabetes"
    ),
    ApplicabilityCondition.CONTROL_IS_PLACEBO: "the control arm is placebo",
    ApplicabilityCondition.CONTROL_IS_ACTIVE: (
        "the control arm is an active comparator"
    ),
    ApplicabilityCondition.IS_NON_INFERIORITY: (
        "the trial tests non-inferiority"
    ),
    ApplicabilityCondition.IS_ADD_ON: (
        "the treatment is added on to background therapy"
    ),
    ApplicabilityCondition.DRUG_CLASS_IS_INSULIN: (
        "the investigational drug is an insulin"
    ),
    ApplicabilityCondition.IS_RANDOMIZED: "participants are randomised",
    ApplicabilityCondition.IS_BLINDED: "the trial is blinded",
}
INPUT_LABELS: dict[RequiredInput, str] = {
    RequiredInput.INVESTIGATORS_BROCHURE: "the Investigator's Brochure",
    RequiredInput.REGISTRY_RECORD: "the registry record",
    RequiredInput.COMPARATOR_CORPUS: "prior protocols of the same drug",
}


NOT_IMPLEMENTED_REASON = "This rule's check is not implemented yet."
# Where trial-level facts (intervention, population, control) are stated.
PROFILE_HEADINGS = frozenset(
    {
        M11Heading.PROTOCOL_SUMMARY,
        M11Heading.TRIAL_DESIGN,
        M11Heading.TRIAL_POPULATION,
        M11Heading.TRIAL_INTERVENTION,
    }
)
PROFILE_FALLBACK_PAGE_COUNT = 15  # title page + synopsis, without sections
PAGE_MARKER_TEMPLATE = "=== PAGE {page_number} ==="


@dataclass(frozen=True)
class ConditionValue:
    """Whether an applicability condition holds (None = unknown), and why."""

    holds: bool | None
    citation: Citation | None


@dataclass(frozen=True)
class CheckOutcome:
    """A rule check's verdict, before rule metadata is attached."""

    status: RuleStatus
    finding: str
    evidence: tuple[Citation, ...] = ()
    searched_locations: tuple[SearchedLocation, ...] = ()
    location: FindingLocation = field(default_factory=FindingLocation)
    status_reason: str | None = None
    confidence: float = 1.0


type DeterministicCheck = Callable[
    [ProtocolDocument, TrialProfile], CheckOutcome
]
"""A code check for one rule: reads the document, returns its outcome."""


def _evaluate_cited[ValueT](
    cited: CitedValue[ValueT] | None, predicate: Callable[[ValueT], bool]
) -> ConditionValue:
    if cited is None:
        return ConditionValue(holds=None, citation=None)
    return ConditionValue(
        holds=predicate(cited.value), citation=cited.citation
    )


def condition_holds(
    condition: ApplicabilityCondition,
    profile: TrialProfile,
    design: TrialDesignFacts | None,
) -> ConditionValue:
    """Evaluate one applicability condition; holds is None when unknown."""
    match condition:
        case ApplicabilityCondition.INTERVENTION_IS_DRUG:
            return _evaluate_cited(
                profile.intervention_type, lambda v: v in DRUG_INTERVENTIONS
            )
        case ApplicabilityCondition.DIABETES_TYPE_T1D:
            return _evaluate_cited(
                profile.diabetes_type, lambda v: v == DiabetesType.T1D
            )
        case ApplicabilityCondition.DIABETES_TYPE_T2D:
            return _evaluate_cited(
                profile.diabetes_type, lambda v: v == DiabetesType.T2D
            )
        case ApplicabilityCondition.CONTROL_IS_PLACEBO:
            return _evaluate_cited(
                profile.control_type, lambda v: v == ControlType.PLACEBO
            )
        case ApplicabilityCondition.CONTROL_IS_ACTIVE:
            return _evaluate_cited(
                profile.control_type, lambda v: v == ControlType.ACTIVE
            )
        case ApplicabilityCondition.IS_NON_INFERIORITY:
            return _evaluate_cited(profile.is_non_inferiority, bool)
        case ApplicabilityCondition.IS_ADD_ON:
            return _evaluate_cited(profile.is_add_on, bool)
        case ApplicabilityCondition.DRUG_CLASS_IS_INSULIN:
            return _evaluate_cited(
                profile.drug_class, lambda v: v == DrugClass.INSULIN
            )
        case ApplicabilityCondition.IS_RANDOMIZED:
            return _evaluate_cited(
                design.allocation if design else None,
                lambda v: v == AllocationType.RANDOMIZED,
            )
        case ApplicabilityCondition.IS_BLINDED:
            return _evaluate_cited(
                design.masking if design else None,
                lambda v: v in BLINDED_MASKING,
            )
    assert_never(condition)


def pre_decide(
    rule: RuleDefinition,
    profile: TrialProfile,
    design: TrialDesignFacts | None,
    available_inputs: frozenset[RequiredInput],
) -> CheckOutcome | None:
    """Decide a rule without evaluating it, or return None to evaluate.

    A rule is not applicable only when one of its conditions is known to be
    false (guidelines §0.5); an unknown condition means it is evaluated.
    Otherwise a missing input makes it cannot_assess, or
    insufficient_comparators when only the comparator corpus is missing.
    """
    for condition in rule.applies_when:
        value = condition_holds(condition, profile, design)
        if value.holds is False:
            label = CONDITION_LABELS[condition]
            return CheckOutcome(
                status=RuleStatus.NOT_APPLICABLE,
                finding=f"Not applicable: this trial does not meet '{label}'.",
                evidence=(value.citation,) if value.citation else (),
                status_reason=f"Applies only when {label}; this trial "
                "does not meet that.",
            )

    missing = [
        needed
        for needed in rule.needs_inputs
        if needed not in available_inputs
    ]
    if not missing:
        return None
    missing_labels = ", ".join(INPUT_LABELS[needed] for needed in missing)
    status = (
        RuleStatus.INSUFFICIENT_COMPARATORS
        if missing == [RequiredInput.COMPARATOR_CORPUS]
        else RuleStatus.CANNOT_ASSESS
    )
    return CheckOutcome(
        status=status,
        finding=f"Not assessed: needs {missing_labels}.",
        status_reason=f"Needs {missing_labels}, which was not provided.",
    )


def finding_from_outcome(
    rule: RuleDefinition, outcome: CheckOutcome, check_method: CheckMethod
) -> RuleFinding:
    """Attach the rule's metadata (and its fix, if fired) to an outcome."""
    return RuleFinding(
        rule_id=rule.id,
        family=rule.family,
        severity=rule.severity,
        status=outcome.status,
        status_reason=outcome.status_reason,
        title=rule.title,
        finding=outcome.finding,
        location=outcome.location,
        evidence=list(outcome.evidence),
        searched_locations=list(outcome.searched_locations),
        proposed_fix=rule.fix if outcome.status == RuleStatus.FIRED else None,
        confidence=outcome.confidence,
        source=rule.source,
        source_tier=rule.source_tier,
        check_method=check_method,
    )


def evaluate_rule(
    rule: RuleDefinition,
    document: ProtocolDocument,
    profile: TrialProfile,
    available_inputs: frozenset[RequiredInput],
    checks: Mapping[str, DeterministicCheck],
) -> RuleFinding:
    """Decide one rule: pre-decision, else its code check, else unassessed.

    A rule with no registered check yet is reported as cannot_assess rather
    than silently passed.
    """
    pre_decision = pre_decide(rule, profile, document.design, available_inputs)
    if pre_decision is not None:
        return finding_from_outcome(rule, pre_decision, rule.check)
    check = checks.get(rule.id)
    if check is None:
        not_implemented = CheckOutcome(
            status=RuleStatus.CANNOT_ASSESS,
            finding="Not assessed yet.",
            status_reason=NOT_IMPLEMENTED_REASON,
        )
        return finding_from_outcome(rule, not_implemented, rule.check)
    return finding_from_outcome(
        rule, check(document, profile), CheckMethod.DETERMINISTIC
    )


def select_profile_pages(document: ProtocolDocument) -> list[PageText]:
    """Pages stating trial-level facts: summary, design, population, arms.

    Falls back to the first pages when no section map is available.
    """
    wanted = {
        page_number
        for section in document.sections or []
        if section.heading in PROFILE_HEADINGS
        for page_number in range(section.start_page, section.end_page + 1)
    }
    if not wanted:
        return document.pages[:PROFILE_FALLBACK_PAGE_COUNT]
    return [page for page in document.pages if page.page_number in wanted]


# [TO REFACTOR:(alex)]: duplicates the parser's format_pages_for_prompt;
# move both to backend/shared once the parser's step-3 work has merged.
def format_pages_for_prompt(pages: Sequence[PageText]) -> str:
    """Render pages with the 1-based markers citations refer to."""
    return "\n".join(
        f"{PAGE_MARKER_TEMPLATE.format(page_number=page.page_number)}\n"
        f"{page.text}"
        for page in pages
    )


def _compute_gate(
    findings: Sequence[RuleFinding], families: tuple[RuleFamily, ...]
) -> GateResult:
    """Fail on any fired S1 rule of the families.

    Partial while not all S1 rules of the families are evaluated, or while
    one of them could not be assessed.
    """
    gate_findings = [
        item
        for item in findings
        if item.family in families and item.severity == RuleSeverity.S1
    ]
    failing = sorted(
        item.rule_id
        for item in gate_findings
        if item.status == RuleStatus.FIRED
    )
    evaluated_per_family = Counter(item.family for item in gate_findings)
    is_missing_rules = any(
        evaluated_per_family[family] < GATE_S1_RULE_TOTALS[family]
        for family in families
    )
    has_unassessed = any(
        item.status in UNASSESSED_STATUSES for item in gate_findings
    )
    return GateResult(
        status=GateStatus.FAIL if failing else GateStatus.PASS,
        is_partial=is_missing_rules or has_unassessed,
        failing_rule_ids=failing,
    )


def compute_run_result(findings: Sequence[RuleFinding]) -> RunResult:
    """Score and gates per the guidelines' "Scoring, gates and output".

    Only fired and passed rules count. With no such rule there is nothing
    to fail, so the score is PERFECT_SCORE (the gates show partial).
    """
    applicable_weight = sum(
        SEVERITY_WEIGHTS[item.severity]
        for item in findings
        if item.status in SCORED_STATUSES
    )
    fired_weight = sum(
        SEVERITY_WEIGHTS[item.severity]
        for item in findings
        if item.status == RuleStatus.FIRED
    )
    score = (
        PERFECT_SCORE
        if applicable_weight == 0
        else PERFECT_SCORE * (1 - fired_weight / applicable_weight)
    )
    return RunResult(
        score=score,
        registration_gate=_compute_gate(findings, REGISTRATION_GATE_FAMILIES),
        review_gate=_compute_gate(findings, REVIEW_GATE_FAMILIES),
    )


def assemble_report(
    document: ProtocolDocument,
    profile: TrialProfile,
    catalogue: RuleCatalogue,
    findings: Sequence[RuleFinding],
    comparators_used: int = 0,
) -> ComplianceReport:
    """Build the report: one finding per catalogue rule, in catalogue order.

    Raises:
        ValueError: findings miss a catalogue rule, include an unknown rule,
            or repeat one.
    """
    expected_ids = [rule.id for rule in catalogue.rules]
    by_id = {item.rule_id: item for item in findings}
    missing = [rule_id for rule_id in expected_ids if rule_id not in by_id]
    unexpected = sorted(set(by_id) - set(expected_ids))
    if missing or unexpected or len(by_id) != len(findings):
        raise ValueError(
            "expected exactly one finding per catalogue rule, got "
            f"missing={missing} unexpected={unexpected} "
            f"duplicates={len(findings) - len(by_id)}"
        )
    ordered = [by_id[rule_id] for rule_id in expected_ids]
    return ComplianceReport(
        protocol_id=document.protocol_id,
        protocol_title=document.title,
        trial_profile=profile,
        rules_evaluated=len(ordered),
        comparators_used=comparators_used,
        before=compute_run_result(ordered),
        findings=ordered,
    )
