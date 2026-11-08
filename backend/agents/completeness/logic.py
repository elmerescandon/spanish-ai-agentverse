"""Pure engine of the completeness checker: applicability, findings, score.

No I/O here: agent.py extracts the trial profile with Gemini and runs the
rule checks; this module decides which rules apply, turns check outcomes
into findings, and computes the score and gates from the guidelines.
"""

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field

from backend.agents.completeness.prompts import (
    JUDGEMENT_BATCH_INSTRUCTIONS,
    LIBRARY_MATCH_INSTRUCTIONS,
    SECOND_OPINION_INSTRUCTIONS,
)
from backend.agents.completeness.rules import (
    ApplicabilityCondition,
    LibraryTag,
    RequiredInput,
    RuleCatalogue,
    RuleDefinition,
    load_rule_catalogue,
)
from backend.shared.citations import make_citation_verifier
from backend.shared.messages import (
    NON_SCORED_RULE_STATUSES,
    AllocationType,
    CheckMethod,
    Citation,
    CitedValue,
    ComplianceReport,
    ControlType,
    DiabetesType,
    DrugClass,
    EligibilityCriterion,
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
    TrialPhase,
    TrialProfile,
)
from backend.shared.prompting import (
    INSTRUCTIONS_SEPARATOR,
    format_pages_for_prompt,
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
DRUG_INTERVENTIONS = frozenset(
    {InterventionType.DRUG, InterventionType.BIOLOGIC}
)
INCRETIN_CLASSES = frozenset(
    {DrugClass.GLP1_RECEPTOR_AGONIST, DrugClass.DPP4_INHIBITOR}
)
PHASE_3_PHASES = frozenset({TrialPhase.PHASE3, TrialPhase.PHASE2_PHASE3})
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
    ApplicabilityCondition.DRUG_CLASS_IS_SGLT2: (
        "the investigational drug is an SGLT2 inhibitor"
    ),
    ApplicabilityCondition.DRUG_CLASS_IS_INCRETIN: (
        "the investigational drug is a GLP-1 RA or DPP-4 inhibitor"
    ),
    ApplicabilityCondition.DRUG_CLASS_IS_GLP1_RA: (
        "the investigational drug is a GLP-1 receptor agonist"
    ),
    ApplicabilityCondition.IS_AMENDED: "the protocol is an amendment",
    ApplicabilityCondition.IS_PHASE_3: "the trial is phase 3",
    ApplicabilityCondition.IS_SINGLE_ARM: "the trial has a single arm",
}
INPUT_LABELS: dict[RequiredInput, str] = {
    RequiredInput.INVESTIGATORS_BROCHURE: "the Investigator's Brochure",
    RequiredInput.REGISTRY_RECORD: "the registry record",
    RequiredInput.COMPARATOR_CORPUS: "prior protocols of the same drug",
}

NOT_IMPLEMENTED_REASON = "This rule's check is not implemented yet."
UNVERIFIED_EVIDENCE_REASON = "evidence did not verify"
MISSING_VERDICT_REASON = "Rule omitted from judgement batch response."
SECOND_OPINION_FAILURE_CONFIDENCE_CAP = 0.5
SECOND_OPINION_FAILURE_NOTE = (
    " (second opinion unavailable; confidence capped at 0.5)"
)
MAX_RULES_PER_BATCH = 8
MAX_JUDGEMENT_BATCHES = 8
LIBRARY_ITEMS_PER_CALL = 10  # exclusion-library items matched per call
SECOND_OPINION_BATCH_SIZE = 10  # flags per call, so one failure stays local
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


class JudgementStatus(StrEnum):
    """Allowed rule statuses returned by a Gemini judgement batch."""

    FIRED = "fired"
    PASSED = "passed"
    NOT_APPLICABLE = "not_applicable"
    CANNOT_ASSESS = "cannot_assess"


class JudgementVerdict(BaseModel):
    """Single rule verdict inside a Gemini judgement batch response."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    status: JudgementStatus
    finding: str
    evidence: list[Citation] = Field(default_factory=list)
    status_reason: str | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    criterion_ids: list[str] = Field(default_factory=list)


class JudgementVerdicts(BaseModel):
    """Response schema for a Gemini judgement batch call."""

    model_config = ConfigDict(extra="forbid")

    verdicts: list[JudgementVerdict] = Field(default_factory=list)


class SecondOpinionVerdict(BaseModel):
    """Single verification verdict from the second-opinion pass."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    confirmed: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class SecondOpinionVerdicts(BaseModel):
    """Response schema for the batched second-opinion verification call."""

    model_config = ConfigDict(extra="forbid")

    verdicts: list[SecondOpinionVerdict] = Field(default_factory=list)


class LibraryItemMatch(BaseModel):
    """Whether one exclusion-library item appears among the criteria."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    is_present: bool
    criterion_ids: list[str] = Field(default_factory=list)
    is_operable: bool | None = None
    has_rationale: bool | None = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class LibraryMatches(BaseModel):
    """Response schema for one exclusion-library matching call."""

    model_config = ConfigDict(extra="forbid")

    matches: list[LibraryItemMatch] = Field(default_factory=list)


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
    needs_second_opinion: bool = False


@dataclass(frozen=True)
class EvaluatedRule:
    """Evaluated rule finding and whether an absence fire needs review."""

    finding: RuleFinding
    needs_second_opinion: bool = False


@dataclass(frozen=True)
class JudgementBatch:
    """A batch of judgement rules sharing protocol sections."""

    rules: tuple[RuleDefinition, ...]
    headings: tuple[M11Heading, ...]


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
        case ApplicabilityCondition.DRUG_CLASS_IS_SGLT2:
            return _evaluate_cited(
                profile.drug_class, lambda v: v == DrugClass.SGLT2_INHIBITOR
            )
        case ApplicabilityCondition.DRUG_CLASS_IS_INCRETIN:
            return _evaluate_cited(
                profile.drug_class, lambda v: v in INCRETIN_CLASSES
            )
        case ApplicabilityCondition.DRUG_CLASS_IS_GLP1_RA:
            return _evaluate_cited(
                profile.drug_class,
                lambda v: v == DrugClass.GLP1_RECEPTOR_AGONIST,
            )
        case ApplicabilityCondition.IS_AMENDED:
            return _evaluate_cited(profile.is_amended, bool)
        case ApplicabilityCondition.IS_PHASE_3:
            return _evaluate_cited(
                profile.phase, lambda v: v in PHASE_3_PHASES
            )
        case ApplicabilityCondition.IS_SINGLE_ARM:
            return _evaluate_cited(
                design.arm_count if design else None, lambda v: v == 1
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


def _default_searched_locations(
    rule: RuleDefinition, document: ProtocolDocument
) -> tuple[SearchedLocation, ...]:
    """Build searched_locations from rule.sections using document.sections."""
    wanted = set(rule.sections)
    matched = tuple(
        SearchedLocation(
            heading=section.heading,
            section_title=section.title,
            start_page=section.start_page,
            end_page=section.end_page,
        )
        for section in document.sections or []
        if section.heading in wanted
    )
    if matched:
        return matched
    end_page = max(1, document.page_count)
    return tuple(
        SearchedLocation(
            heading=heading,
            section_title=None,
            start_page=1,
            end_page=end_page,
        )
        for heading in rule.sections
    )


def _with_default_searched_locations(
    rule: RuleDefinition, document: ProtocolDocument, outcome: CheckOutcome
) -> CheckOutcome:
    if (
        outcome.status in SCORED_STATUSES
        and not outcome.evidence
        and not outcome.searched_locations
    ):
        return CheckOutcome(
            status=outcome.status,
            finding=outcome.finding,
            evidence=outcome.evidence,
            searched_locations=_default_searched_locations(rule, document),
            location=outcome.location,
            status_reason=outcome.status_reason,
            confidence=outcome.confidence,
            needs_second_opinion=outcome.needs_second_opinion,
        )
    return outcome


def evaluate_rule(
    rule: RuleDefinition,
    document: ProtocolDocument,
    profile: TrialProfile,
    available_inputs: frozenset[RequiredInput],
    checks: Mapping[str, DeterministicCheck],
) -> EvaluatedRule:
    """Decide one rule: pre-decision, else its code check, else unassessed.

    A rule with no registered check yet is reported as cannot_assess rather
    than silently passed.
    """
    pre_decision = pre_decide(rule, profile, document.design, available_inputs)
    if pre_decision is not None:
        return EvaluatedRule(
            finding=finding_from_outcome(rule, pre_decision, rule.check),
            needs_second_opinion=pre_decision.needs_second_opinion,
        )
    check = checks.get(rule.id)
    if check is None:
        not_implemented = CheckOutcome(
            status=RuleStatus.CANNOT_ASSESS,
            finding="Not assessed yet.",
            status_reason=NOT_IMPLEMENTED_REASON,
        )
        return EvaluatedRule(
            finding=finding_from_outcome(rule, not_implemented, rule.check),
            needs_second_opinion=False,
        )
    outcome = _with_default_searched_locations(
        rule, document, check(document, profile)
    )
    return EvaluatedRule(
        finding=finding_from_outcome(rule, outcome, CheckMethod.DETERMINISTIC),
        needs_second_opinion=outcome.needs_second_opinion,
    )


def evaluate_precheck(
    rule: RuleDefinition,
    document: ProtocolDocument,
    profile: TrialProfile,
    prechecks: Mapping[
        str, Callable[[ProtocolDocument, TrialProfile], CheckOutcome | None]
    ],
) -> EvaluatedRule | None:
    """Run a measurable pre-check for a judgement rule, or return None."""
    precheck = prechecks.get(rule.id)
    if precheck is None:
        return None
    outcome = precheck(document, profile)
    if outcome is None:
        return None
    filled = _with_default_searched_locations(rule, document, outcome)
    return EvaluatedRule(
        finding=finding_from_outcome(rule, filled, CheckMethod.DETERMINISTIC),
        needs_second_opinion=filled.needs_second_opinion,
    )


def _merge_headings(
    first: Sequence[M11Heading], second: Sequence[M11Heading]
) -> tuple[M11Heading, ...]:
    seen: list[M11Heading] = []
    for heading in (*first, *second):
        if heading not in seen:
            seen.append(heading)
    return tuple(seen)


def build_judgement_batches(
    rules: Sequence[RuleDefinition],
    max_rules_per_batch: int = MAX_RULES_PER_BATCH,
    max_batches: int = MAX_JUDGEMENT_BATCHES,
) -> list[JudgementBatch]:
    """Group judgement rules by section, capped at max rules per batch.

    Small batches that share a section are merged towards max_batches;
    batches with no section in common never are, so each call reads only
    its own part of the protocol.
    """
    if not rules:
        return []
    groups: dict[frozenset[M11Heading], list[RuleDefinition]] = {}
    heading_order: dict[frozenset[M11Heading], tuple[M11Heading, ...]] = {}
    for rule in rules:
        key = frozenset(rule.sections)
        if key not in groups:
            groups[key] = []
            heading_order[key] = tuple(rule.sections)
        groups[key].append(rule)

    batches: list[JudgementBatch] = []
    for key, group_rules in groups.items():
        headings = heading_order[key]
        for idx in range(0, len(group_rules), max_rules_per_batch):
            chunk = tuple(group_rules[idx : idx + max_rules_per_batch])
            batches.append(JudgementBatch(rules=chunk, headings=headings))

    while len(batches) > max_batches:
        best_pair: tuple[int, int] | None = None
        best_score: tuple[int, int, int] | None = None
        for i in range(len(batches)):
            for j in range(i + 1, len(batches)):
                combined_rules = len(batches[i].rules) + len(batches[j].rules)
                if combined_rules > max_rules_per_batch:
                    continue
                set_i = set(batches[i].headings)
                set_j = set(batches[j].headings)
                overlap = len(set_i & set_j)
                # Merging unrelated sections makes the call read both
                # sections' pages, so only batches sharing one merge.
                if overlap == 0:
                    continue
                union_size = len(set_i | set_j)
                score = (overlap, -union_size, -combined_rules)
                if best_score is None or score > best_score:
                    best_score = score
                    best_pair = (i, j)
        if best_pair is None:
            break
        i, j = best_pair
        merged = JudgementBatch(
            rules=(*batches[i].rules, *batches[j].rules),
            headings=_merge_headings(batches[i].headings, batches[j].headings),
        )
        batches[i] = merged
        del batches[j]

    return batches


def select_batch_pages(
    document: ProtocolDocument, headings: Sequence[M11Heading]
) -> list[PageText]:
    """Return pages in the union of headings, or all pages if unmapped.

    The protocol summary also covers the title page and front matter before
    the first mapped section, where IDs, sponsor and titles are stated.
    """
    if not headings or not document.sections:
        return list(document.pages)
    wanted_headings = set(headings)
    wanted_pages = {
        page_num
        for sec in document.sections
        if sec.heading in wanted_headings
        for page_num in range(sec.start_page, sec.end_page + 1)
    }
    if M11Heading.PROTOCOL_SUMMARY in wanted_headings:
        first_section_page = min(sec.start_page for sec in document.sections)
        wanted_pages.update(range(1, first_section_page))
    if not wanted_pages:
        return list(document.pages)
    return [
        page for page in document.pages if page.page_number in wanted_pages
    ]


def rule_extracted_context(
    rule: RuleDefinition, document: ProtocolDocument, profile: TrialProfile
) -> dict[str, object]:
    """Extract compact JSON-serializable facet context relevant to rule."""
    context: dict[str, object] = {
        "trial_profile": profile.model_dump(mode="json", exclude_none=True),
    }
    headings = set(rule.sections)
    if (
        M11Heading.OBJECTIVES_AND_ESTIMANDS in headings
        and document.endpoints is not None
    ):
        context["endpoints"] = [
            ep.model_dump(mode="json", exclude={"citation"})
            for ep in document.endpoints
        ]
    if (
        M11Heading.OBJECTIVES_AND_ESTIMANDS in headings
        and document.estimands is not None
    ):
        context["estimands"] = document.estimands.model_dump(
            mode="json", exclude_none=True
        )
    if (
        headings & {M11Heading.TRIAL_DESIGN, M11Heading.PROTOCOL_SUMMARY}
        and document.design is not None
    ):
        context["design"] = document.design.model_dump(
            mode="json", exclude_none=True
        )
    if (
        M11Heading.TRIAL_POPULATION in headings
        and document.eligibility_criteria is not None
    ):
        context["eligibility_criteria"] = [
            crit.model_dump(mode="json", exclude={"citation"})
            for crit in document.eligibility_criteria
        ]
    if (
        M11Heading.TRIAL_INTERVENTION in headings
        and document.interventions is not None
    ):
        context["interventions"] = document.interventions.model_dump(
            mode="json", exclude_none=True
        )
    if M11Heading.STATISTICAL_CONSIDERATIONS in headings:
        if document.statistics is not None:
            context["statistics"] = document.statistics.model_dump(
                mode="json", exclude_none=True
            )
        if document.analysis is not None:
            context["analysis"] = document.analysis.model_dump(
                mode="json", exclude_none=True
            )
    if M11Heading.ASSESSMENTS_AND_PROCEDURES in headings:
        if document.schedule is not None:
            context["schedule"] = [
                v.model_dump(mode="json", exclude={"citation"})
                for v in document.schedule
            ]
        if document.safety_monitoring is not None:
            context["safety_monitoring"] = (
                document.safety_monitoring.model_dump(
                    mode="json", exclude_none=True
                )
            )
    if (
        M11Heading.PROTOCOL_SUMMARY in headings
        and document.synopsis_check is not None
    ):
        context["synopsis_check"] = document.synopsis_check.model_dump(
            mode="json", exclude_none=True
        )
    return context


def compact_json(value: object) -> str:
    """JSON without indentation: prompts are read by the model, not people,
    and every character is input Gemini has to read."""
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def _without_citations(value: object) -> object:
    """Drop citation blocks; the pages they quote are already in the prompt."""
    if isinstance(value, dict):
        return {
            key: _without_citations(item)
            for key, item in value.items()
            if key != "citation"
        }
    if isinstance(value, list):
        return [_without_citations(item) for item in value]
    return value


def format_judgement_batch_prompt(
    batch: JudgementBatch,
    document: ProtocolDocument,
    profile: TrialProfile,
) -> str:
    """Build the Gemini prompt for one judgement batch.

    The extracted facts the batch's rules need are sent once, shared, and
    each rule names the facts it uses; repeating them under every rule
    made the facts larger than the pages themselves.
    """
    pages = select_batch_pages(document, batch.headings)
    facts: dict[str, object] = {}
    rules_payload = []
    for rule in batch.rules:
        context = rule_extracted_context(rule, document, profile)
        facts.update(context)
        rules_payload.append(
            {
                "rule_id": rule.id,
                "title": rule.title,
                "flag_if": rule.flag_if,
                "sections": [h.value for h in rule.sections],
                "uses_facts": sorted(context),
            }
        )
    return (
        format_pages_for_prompt(pages)
        + INSTRUCTIONS_SEPARATOR
        + "Extracted facts (shared by the rules below):\n"
        + compact_json(_without_citations(facts))
        + INSTRUCTIONS_SEPARATOR
        + "Rules to evaluate:\n"
        + compact_json(rules_payload)
        + INSTRUCTIONS_SEPARATOR
        + JUDGEMENT_BATCH_INSTRUCTIONS
    )


def resolve_judgement_batch(
    batch: JudgementBatch,
    response: JudgementVerdicts,
    document: ProtocolDocument,
) -> list[EvaluatedRule]:
    """Verify quotes and convert batch verdicts into EvaluatedRules."""
    verify = make_citation_verifier(document.pages)
    by_id = {v.rule_id: v for v in response.verdicts}
    results: list[EvaluatedRule] = []

    for rule in batch.rules:
        verdict = by_id.get(rule.id)
        if verdict is None:
            missing_outcome = CheckOutcome(
                status=RuleStatus.CANNOT_ASSESS,
                finding=f"Cannot assess: rule {rule.id} omitted by model.",
                status_reason=MISSING_VERDICT_REASON,
            )
            results.append(
                EvaluatedRule(
                    finding=finding_from_outcome(
                        rule, missing_outcome, CheckMethod.JUDGEMENT
                    ),
                    needs_second_opinion=False,
                )
            )
            continue

        verified_citations = tuple(
            checked
            for raw_cit in verdict.evidence
            if (checked := verify(raw_cit)).is_verified
        )
        status = RuleStatus(verdict.status.value)

        if status == RuleStatus.FIRED:
            is_absence_claim = (
                "absent" in verdict.finding.lower() and not verdict.evidence
            )
            if not verified_citations and not is_absence_claim:
                unverified_outcome = CheckOutcome(
                    status=RuleStatus.CANNOT_ASSESS,
                    finding=(
                        f"Cannot assess {rule.id}: model evidence did not "
                        "verify against the protocol pages."
                    ),
                    status_reason=UNVERIFIED_EVIDENCE_REASON,
                    confidence=verdict.confidence,
                )
                results.append(
                    EvaluatedRule(
                        finding=finding_from_outcome(
                            rule, unverified_outcome, CheckMethod.JUDGEMENT
                        ),
                        needs_second_opinion=False,
                    )
                )
                continue

        status_reason = verdict.status_reason
        if status in NON_SCORED_RULE_STATUSES and (
            status_reason is None or not status_reason.strip()
        ):
            status_reason = verdict.finding or f"Marked {status.value}."

        first_page = (
            verified_citations[0].page_number if verified_citations else None
        )
        default_heading = rule.sections[0] if rule.sections else None
        location = FindingLocation(
            section=", ".join(verdict.criterion_ids) or None,
            heading=default_heading,
            page=first_page,
        )
        outcome = _with_default_searched_locations(
            rule,
            document,
            CheckOutcome(
                status=status,
                finding=verdict.finding,
                evidence=verified_citations,
                location=location,
                status_reason=status_reason,
                confidence=verdict.confidence,
                needs_second_opinion=(status == RuleStatus.FIRED),
            ),
        )
        results.append(
            EvaluatedRule(
                finding=finding_from_outcome(
                    rule, outcome, CheckMethod.JUDGEMENT
                ),
                needs_second_opinion=outcome.needs_second_opinion,
            )
        )

    return results


def failed_judgement_batch(
    batch: JudgementBatch, error_message: str
) -> list[EvaluatedRule]:
    """Turn a failed batch LLM call into cannot_assess rule findings."""
    return unassessable_batch(
        batch, f"Judgement batch call failed: {error_message}"
    )


def unassessable_batch(
    batch: JudgementBatch, reason: str
) -> list[EvaluatedRule]:
    """Report every rule in a batch as cannot_assess for one reason."""
    return [
        EvaluatedRule(
            finding=finding_from_outcome(
                rule,
                CheckOutcome(
                    status=RuleStatus.CANNOT_ASSESS,
                    finding=f"Cannot assess: {reason}",
                    status_reason=reason,
                ),
                CheckMethod.JUDGEMENT,
            ),
            needs_second_opinion=False,
        )
        for rule in batch.rules
    ]


def criteria_location(
    criteria: Sequence[EligibilityCriterion],
) -> FindingLocation:
    """Point a finding at criterion IDs, e.g. section="EX-03, IN-02"."""
    first_page = next(
        (c.citation.page_number for c in criteria if c.citation is not None),
        None,
    )
    return FindingLocation(
        section=", ".join(c.criterion_id for c in criteria) or None,
        heading=M11Heading.TRIAL_POPULATION,
        page=first_page,
    )


def verified_criterion_citations(
    criteria: Sequence[EligibilityCriterion],
) -> list[Citation]:
    """The verified source quotes of the given criteria."""
    return [
        c.citation
        for c in criteria
        if c.citation is not None and c.citation.is_verified
    ]


def format_library_prompt(
    batch: JudgementBatch, document: ProtocolDocument
) -> str:
    """Build the Gemini prompt matching library items to the criteria."""
    pages = select_batch_pages(document, batch.headings)
    criteria_payload = [
        criterion.model_dump(mode="json", exclude={"citation"})
        for criterion in document.eligibility_criteria or []
    ]
    items_payload = [
        {
            "rule_id": rule.id,
            "tag": rule.library_tag,
            "item": rule.title,
            "flag_if": rule.flag_if,
        }
        for rule in batch.rules
    ]
    return (
        format_pages_for_prompt(pages)
        + INSTRUCTIONS_SEPARATOR
        + "Eligibility criteria:\n"
        + compact_json(criteria_payload)
        + INSTRUCTIONS_SEPARATOR
        + "Library items:\n"
        + compact_json(items_payload)
        + INSTRUCTIONS_SEPARATOR
        + LIBRARY_MATCH_INSTRUCTIONS
    )


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"


def _library_outcome(
    rule: RuleDefinition,
    match: LibraryItemMatch,
    criteria_by_id: Mapping[str, EligibilityCriterion],
    profile: TrialProfile,
    design: TrialDesignFacts | None,
) -> CheckOutcome:
    """Apply the guidelines' Part G firing logic to one item match."""
    if not match.is_present:
        if rule.library_tag == LibraryTag.BREADTH:
            return CheckOutcome(
                status=RuleStatus.PASSED,
                finding="Not excluded, so the population stays broad.",
                confidence=match.confidence,
            )
        is_class_confirmed = all(
            condition_holds(condition, profile, design).holds is True
            for condition in rule.applies_when
        )
        if rule.library_tag == LibraryTag.CLASS and not is_class_confirmed:
            reason = "the drug class this item depends on is not confirmed"
            return CheckOutcome(
                status=RuleStatus.CANNOT_ASSESS,
                finding=f"Cannot assess: {reason}.",
                status_reason=reason,
            )
        return CheckOutcome(
            status=RuleStatus.FIRED,
            finding="No eligibility criterion covers this item.",
            confidence=match.confidence,
            needs_second_opinion=True,
        )

    matched = [
        criteria_by_id[criterion_id]
        for criterion_id in match.criterion_ids
        if criterion_id in criteria_by_id
    ]
    if not matched:
        reason = (
            "the matched criterion IDs are not among the extracted "
            f"criteria: {match.criterion_ids}"
        )
        return CheckOutcome(
            status=RuleStatus.CANNOT_ASSESS,
            finding=f"Cannot assess: {reason}.",
            status_reason=reason,
        )
    ids = ", ".join(c.criterion_id for c in matched)
    quality = (
        f"operable: {_yes_no(match.is_operable)}, "
        f"justified: {_yes_no(match.has_rationale)}"
    )
    evidence = tuple(verified_criterion_citations(matched))
    location = criteria_location(matched)
    if rule.library_tag == LibraryTag.BREADTH and not match.has_rationale:
        return CheckOutcome(
            status=RuleStatus.FIRED,
            finding=(
                f"Excluded in {ids} without a stated reason (see ELQ-11); "
                f"{quality}."
            ),
            evidence=evidence,
            location=location,
            confidence=match.confidence,
            needs_second_opinion=True,
        )
    return CheckOutcome(
        status=RuleStatus.PASSED,
        finding=f"Covered by {ids}; {quality}.",
        evidence=evidence,
        location=location,
        confidence=match.confidence,
    )


def resolve_library_batch(
    batch: JudgementBatch,
    response: LibraryMatches,
    document: ProtocolDocument,
    profile: TrialProfile,
) -> list[EvaluatedRule]:
    """Turn library matches into findings; evidence comes from criteria."""
    criteria_by_id = {
        c.criterion_id: c for c in document.eligibility_criteria or []
    }
    by_id = {match.rule_id: match for match in response.matches}
    results: list[EvaluatedRule] = []
    for rule in batch.rules:
        match = by_id.get(rule.id)
        if match is None:
            outcome = CheckOutcome(
                status=RuleStatus.CANNOT_ASSESS,
                finding=f"Cannot assess: item {rule.id} omitted by model.",
                status_reason=MISSING_VERDICT_REASON,
            )
        else:
            outcome = _with_default_searched_locations(
                rule,
                document,
                _library_outcome(
                    rule, match, criteria_by_id, profile, document.design
                ),
            )
        results.append(
            EvaluatedRule(
                finding=finding_from_outcome(
                    rule, outcome, CheckMethod.JUDGEMENT
                ),
                needs_second_opinion=outcome.needs_second_opinion,
            )
        )
    return results


def needs_second_opinion_review(item: EvaluatedRule) -> bool:
    """Return True if an evaluated rule must go to the second-opinion pass."""
    return item.finding.status == RuleStatus.FIRED and (
        item.finding.check_method == CheckMethod.JUDGEMENT
        or item.needs_second_opinion
    )


def chunk_second_opinion_candidates(
    evaluated: Sequence[EvaluatedRule],
    batch_size: int = SECOND_OPINION_BATCH_SIZE,
) -> list[list[EvaluatedRule]]:
    """Split the flags that need a second opinion into call-sized groups."""
    candidates = [
        item for item in evaluated if needs_second_opinion_review(item)
    ]
    return [
        candidates[start : start + batch_size]
        for start in range(0, len(candidates), batch_size)
    ]


def select_second_opinion_pages(
    document: ProtocolDocument,
    candidates: Sequence[EvaluatedRule],
) -> list[PageText]:
    """Collect the pages cited or searched by all second-opinion candidates."""
    wanted_pages: set[int] = set()
    for item in candidates:
        for cit in item.finding.evidence:
            wanted_pages.add(cit.page_number)
        for loc in item.finding.searched_locations:
            wanted_pages.update(range(loc.start_page, loc.end_page + 1))
    if not wanted_pages:
        return select_profile_pages(document)
    selected = [p for p in document.pages if p.page_number in wanted_pages]
    return selected if selected else select_profile_pages(document)


def format_second_opinion_prompt(
    document: ProtocolDocument,
    candidates: Sequence[EvaluatedRule],
    rules_by_id: Mapping[str, RuleDefinition],
) -> str:
    """Build the Gemini prompt for the batched second-opinion pass."""
    pages = select_second_opinion_pages(document, candidates)
    flags_payload = [
        {
            "rule_id": item.finding.rule_id,
            "flag_if": (
                rules_by_id[item.finding.rule_id].flag_if
                if item.finding.rule_id in rules_by_id
                else item.finding.title
            ),
            "finding": item.finding.finding,
            "evidence": [
                cit.model_dump(mode="json") for cit in item.finding.evidence
            ],
            "searched_locations": [
                loc.model_dump(mode="json")
                for loc in item.finding.searched_locations
            ],
        }
        for item in candidates
    ]
    return (
        format_pages_for_prompt(pages)
        + INSTRUCTIONS_SEPARATOR
        + "Flags to verify:\n"
        + compact_json(flags_payload)
        + INSTRUCTIONS_SEPARATOR
        + SECOND_OPINION_INSTRUCTIONS
    )


def apply_second_opinion(
    evaluated: Sequence[EvaluatedRule],
    response: SecondOpinionVerdicts,
) -> list[RuleFinding]:
    """Update candidate findings from the second-opinion verdicts."""
    by_id = {v.rule_id: v for v in response.verdicts}
    final_findings: list[RuleFinding] = []

    for item in evaluated:
        if not needs_second_opinion_review(item):
            final_findings.append(item.finding)
            continue

        verdict = by_id.get(item.finding.rule_id)
        if verdict is None:
            reason = (
                "second opinion did not confirm: "
                "rule omitted from second-opinion response"
            )
            final_findings.append(
                item.finding.model_copy(
                    update={
                        "status": RuleStatus.CANNOT_ASSESS,
                        "status_reason": reason,
                        "finding": f"Cannot assess: {reason}.",
                        "proposed_fix": None,
                    }
                )
            )
            continue

        if not verdict.confirmed:
            reason = f"second opinion did not confirm: {verdict.reason}"
            final_findings.append(
                item.finding.model_copy(
                    update={
                        "status": RuleStatus.CANNOT_ASSESS,
                        "status_reason": reason,
                        "finding": f"Cannot assess: {reason}.",
                        "proposed_fix": None,
                        "confidence": verdict.confidence,
                    }
                )
            )
            continue

        final_findings.append(
            item.finding.model_copy(
                update={
                    "confidence": min(
                        item.finding.confidence, verdict.confidence
                    ),
                    "second_opinion_reason": verdict.reason,
                }
            )
        )

    return final_findings


def apply_second_opinion_failure(
    evaluated: Sequence[EvaluatedRule],
) -> list[RuleFinding]:
    """Keep fired flags when second opinion fails; cap confidence at 0.5."""
    final_findings: list[RuleFinding] = []
    for item in evaluated:
        if not needs_second_opinion_review(item):
            final_findings.append(item.finding)
            continue
        final_findings.append(
            item.finding.model_copy(
                update={
                    "confidence": min(
                        item.finding.confidence,
                        SECOND_OPINION_FAILURE_CONFIDENCE_CAP,
                    ),
                    "finding": (
                        f"{item.finding.finding}{SECOND_OPINION_FAILURE_NOTE}"
                    ),
                }
            )
        )
    return final_findings


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


@cache
def _catalogue_s1_counts() -> Counter[RuleFamily]:
    """S1 rules per family in the default catalogue.

    Gates only look at S1 rules, so a gate is complete once every S1 rule
    of its families has been evaluated.
    """
    return Counter(
        rule.family
        for rule in load_rule_catalogue().rules
        if rule.severity == RuleSeverity.S1
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
        evaluated_per_family[family] < _catalogue_s1_counts()[family]
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
