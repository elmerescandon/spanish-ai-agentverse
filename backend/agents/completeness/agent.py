"""Completeness agent: checks a parsed protocol against the rule catalogue.

Other parts of the backend call check_protocol() directly.
"""

import asyncio
import logging
from collections.abc import Awaitable, Mapping, Sequence

from backend.agents.completeness.checks import (
    DETERMINISTIC_CHECKS,
    JUDGEMENT_PRECHECKS,
    JudgementPrecheck,
)
from backend.agents.completeness.logic import (
    LIBRARY_ITEMS_PER_CALL,
    DeterministicCheck,
    EvaluatedRule,
    JudgementBatch,
    JudgementVerdicts,
    LibraryMatches,
    SecondOpinionVerdicts,
    apply_second_opinion,
    apply_second_opinion_failure,
    assemble_report,
    build_judgement_batches,
    chunk_second_opinion_candidates,
    evaluate_precheck,
    evaluate_rule,
    failed_judgement_batch,
    finding_from_outcome,
    format_judgement_batch_prompt,
    format_library_prompt,
    format_second_opinion_prompt,
    pre_decide,
    resolve_judgement_batch,
    resolve_library_batch,
    select_profile_pages,
    unassessable_batch,
)
from backend.agents.completeness.prompts import (
    TRIAL_PROFILE_INSTRUCTIONS,
)
from backend.agents.completeness.rules import (
    RequiredInput,
    RuleCatalogue,
    RuleDefinition,
    load_rule_catalogue,
)
from backend.clients.gemini import (
    JsonGenerator,
    LlmCallFailedError,
    ThinkingLevel,
)
from backend.shared.citations import make_citation_verifier
from backend.shared.messages import (
    CheckMethod,
    ComplianceReport,
    ProtocolDocument,
    RuleFamily,
    RuleFinding,
    RuleStatus,
    TrialProfile,
)
from backend.shared.prompting import (
    INSTRUCTIONS_SEPARATOR,
    format_pages_for_prompt,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "completeness"
# Lowest reasoning effort on every call: the check must finish in about a
# minute for the demo, and higher effort roughly multiplies each call's time.
THINKING_LEVEL = ThinkingLevel.LOW


async def extract_trial_profile(
    document: ProtocolDocument, llm: JsonGenerator
) -> TrialProfile:
    """Classify the trial (intervention, population, control, ...).

    A fact whose quote doesn't verify against the PDF is dropped, so an
    unverified fact can never make a rule not_applicable. If the call
    fails, every field is unknown and all rules are evaluated. Phase comes
    from the parser's design facts, not from a second extraction.
    """
    prompt = (
        format_pages_for_prompt(select_profile_pages(document))
        + INSTRUCTIONS_SEPARATOR
        + TRIAL_PROFILE_INSTRUCTIONS
    )
    try:
        raw_profile = await llm.generate_json(
            prompt, TrialProfile, THINKING_LEVEL
        )
    except LlmCallFailedError as error:
        logger.warning(
            "trial profile failed, evaluating all rules: agent=%s "
            "protocol_id=%s error=%s",
            AGENT_NAME,
            document.protocol_id,
            error,
        )
        return TrialProfile()

    verify = make_citation_verifier(document.pages)
    updates: dict[str, object] = {}
    for field_name in TrialProfile.model_fields:
        cited = getattr(raw_profile, field_name)
        if cited is None:
            continue
        citation = verify(cited.citation)
        if citation.is_verified:
            updates[field_name] = cited.model_copy(
                update={"citation": citation}
            )
        else:
            updates[field_name] = None
            logger.info(
                "trial profile fact dropped, quote not verified: agent=%s "
                "protocol_id=%s field=%s",
                AGENT_NAME,
                document.protocol_id,
                field_name,
            )
    design_phase = document.design.phase if document.design else None
    updates["phase"] = design_phase
    return raw_profile.model_copy(update=updates)


async def _run_judgement_batch(
    batch: JudgementBatch,
    document: ProtocolDocument,
    profile: TrialProfile,
    llm: JsonGenerator,
) -> list[EvaluatedRule]:
    """Run one batched Gemini judgement call and verify quote citations."""
    prompt = format_judgement_batch_prompt(batch, document, profile)
    try:
        response = await llm.generate_json(
            prompt, JudgementVerdicts, THINKING_LEVEL
        )
    except LlmCallFailedError as error:
        logger.warning(
            "judgement batch failed: agent=%s protocol_id=%s rules=%s "
            "error=%s",
            AGENT_NAME,
            document.protocol_id,
            [rule.id for rule in batch.rules],
            error,
        )
        return failed_judgement_batch(batch, str(error))
    return resolve_judgement_batch(batch, response, document)


async def _run_library_batch(
    batch: JudgementBatch,
    document: ProtocolDocument,
    profile: TrialProfile,
    llm: JsonGenerator,
) -> list[EvaluatedRule]:
    """Match one group of exclusion-library items against the criteria."""
    if not document.eligibility_criteria:
        return unassessable_batch(
            batch, "no eligibility criteria were extracted"
        )
    prompt = format_library_prompt(batch, document)
    try:
        response = await llm.generate_json(
            prompt, LibraryMatches, THINKING_LEVEL
        )
    except LlmCallFailedError as error:
        logger.warning(
            "library batch failed: agent=%s protocol_id=%s rules=%s error=%s",
            AGENT_NAME,
            document.protocol_id,
            [rule.id for rule in batch.rules],
            error,
        )
        return failed_judgement_batch(batch, str(error))
    return resolve_library_batch(batch, response, document, profile)


async def _run_second_opinion_group(
    document: ProtocolDocument,
    group: list[EvaluatedRule],
    rules_by_id: Mapping[str, RuleDefinition],
    llm: JsonGenerator,
) -> list[RuleFinding]:
    """Verify one group of flags; a failed call caps only this group."""
    prompt = format_second_opinion_prompt(document, group, rules_by_id)
    try:
        response = await llm.generate_json(
            prompt, SecondOpinionVerdicts, THINKING_LEVEL
        )
    except LlmCallFailedError as error:
        logger.warning(
            "second opinion failed, keeping flags at capped confidence: "
            "agent=%s protocol_id=%s candidates=%d error=%s",
            AGENT_NAME,
            document.protocol_id,
            len(group),
            error,
        )
        return apply_second_opinion_failure(group)
    return apply_second_opinion(group, response)


async def _review_flags(
    document: ProtocolDocument,
    items: Sequence[EvaluatedRule],
    rules_by_id: Mapping[str, RuleDefinition],
    llm: JsonGenerator,
) -> list[RuleFinding]:
    """Second-check the flags among items, in concurrent groups.

    Returns one finding per item: reviewed flags updated, the rest as they
    were.
    """
    groups = chunk_second_opinion_candidates(items)
    group_results = await asyncio.gather(
        *(
            _run_second_opinion_group(document, group, rules_by_id, llm)
            for group in groups
        )
    )
    reviewed = {
        finding.rule_id: finding
        for group_findings in group_results
        for finding in group_findings
    }
    return [reviewed.get(item.finding.rule_id, item.finding) for item in items]


async def _judge_then_review(
    judged: Awaitable[list[EvaluatedRule]],
    document: ProtocolDocument,
    rules_by_id: Mapping[str, RuleDefinition],
    llm: JsonGenerator,
) -> list[RuleFinding]:
    """Review one batch's flags as soon as that batch is judged."""
    return await _review_flags(document, await judged, rules_by_id, llm)


async def check_protocol(
    document: ProtocolDocument,
    llm: JsonGenerator,
    catalogue: RuleCatalogue | None = None,
    available_inputs: frozenset[RequiredInput] = frozenset(),
    checks: Mapping[str, DeterministicCheck] = DETERMINISTIC_CHECKS,
    prechecks: Mapping[str, JudgementPrecheck] = JUDGEMENT_PRECHECKS,
) -> ComplianceReport:
    """Check a parsed protocol against every rule; one finding per rule.

    Pipeline order:
    profile -> pre_decide -> deterministic checks -> prechecks
    -> every judgement and library batch at once, each followed by the
    second opinion on its own flags (code-decided flags reviewed at once)
    -> assemble_report.

    Raises:
        ValueError: the catalogue file is invalid (see rules.py).
    """
    rule_catalogue = catalogue or load_rule_catalogue()

    # 1. Trial profile
    profile = await extract_trial_profile(document, llm)
    verified_facts = sum(
        1
        for field_name in TrialProfile.model_fields
        if getattr(profile, field_name) is not None
    )
    logger.info(
        "completeness stage=profile protocol_id=%s verified_facts=%d",
        document.protocol_id,
        verified_facts,
    )

    # 2. Pre-decide applicability and missing inputs
    evaluated_by_id: dict[str, EvaluatedRule] = {}
    deterministic_rules: list[RuleDefinition] = []
    judgement_rules: list[RuleDefinition] = []
    for rule in rule_catalogue.rules:
        outcome = pre_decide(rule, profile, document.design, available_inputs)
        if outcome is not None:
            evaluated_by_id[rule.id] = EvaluatedRule(
                finding=finding_from_outcome(rule, outcome, rule.check),
                needs_second_opinion=False,
            )
        elif rule.check == CheckMethod.DETERMINISTIC:
            deterministic_rules.append(rule)
        else:
            judgement_rules.append(rule)
    logger.info(
        "completeness stage=pre_decide protocol_id=%s decided=%d "
        "deterministic_remaining=%d judgement_remaining=%d",
        document.protocol_id,
        len(evaluated_by_id),
        len(deterministic_rules),
        len(judgement_rules),
    )

    # 3. Deterministic checks
    for rule in deterministic_rules:
        evaluated_by_id[rule.id] = evaluate_rule(
            rule, document, profile, available_inputs, checks
        )
    det_outcomes = [evaluated_by_id[r.id] for r in deterministic_rules]
    logger.info(
        "completeness stage=deterministic_checks protocol_id=%s evaluated=%d "
        "fired=%d passed=%d",
        document.protocol_id,
        len(det_outcomes),
        sum(1 for e in det_outcomes if e.finding.status == RuleStatus.FIRED),
        sum(1 for e in det_outcomes if e.finding.status == RuleStatus.PASSED),
    )

    # 4. Measurable prechecks for judgement rules
    unresolved_judgement: list[RuleDefinition] = []
    for rule in judgement_rules:
        prechecked = evaluate_precheck(rule, document, profile, prechecks)
        if prechecked is not None:
            evaluated_by_id[rule.id] = prechecked
        else:
            unresolved_judgement.append(rule)
    logger.info(
        "completeness stage=prechecks protocol_id=%s decided=%d "
        "needs_gemini=%d",
        document.protocol_id,
        len(judgement_rules) - len(unresolved_judgement),
        len(unresolved_judgement),
    )

    # 5-6. All Gemini work at once: every judgement and library batch, each
    # followed by the second opinion on its own flags as soon as it is
    # judged; flags decided in code go to their second opinion right away.
    library_rules = [
        r for r in unresolved_judgement if r.family == RuleFamily.EX
    ]
    batches = build_judgement_batches(
        [r for r in unresolved_judgement if r.family != RuleFamily.EX]
    )
    library_batches = build_judgement_batches(
        library_rules, max_rules_per_batch=LIBRARY_ITEMS_PER_CALL
    )
    rules_by_id = {rule.id: rule for rule in rule_catalogue.rules}
    decided_in_code = list(evaluated_by_id.values())
    reviewed_groups = await asyncio.gather(
        _review_flags(document, decided_in_code, rules_by_id, llm),
        *(
            _judge_then_review(
                _run_judgement_batch(batch, document, profile, llm),
                document,
                rules_by_id,
                llm,
            )
            for batch in batches
        ),
        *(
            _judge_then_review(
                _run_library_batch(batch, document, profile, llm),
                document,
                rules_by_id,
                llm,
            )
            for batch in library_batches
        ),
    )
    findings_by_id = {
        finding.rule_id: finding
        for group in reviewed_groups
        for finding in group
    }
    findings = [findings_by_id[rule.id] for rule in rule_catalogue.rules]
    logger.info(
        "completeness stage=gemini protocol_id=%s batches=%d "
        "library_batches=%d fired=%d",
        document.protocol_id,
        len(batches),
        len(library_batches),
        sum(1 for f in findings if f.status == RuleStatus.FIRED),
    )

    # 7. Assemble report
    report = assemble_report(document, profile, rule_catalogue, findings)
    logger.info(
        "completeness stage=assemble_report protocol_id=%s rules=%d "
        "fired=%d score=%.1f",
        document.protocol_id,
        report.rules_evaluated,
        sum(1 for f in findings if f.status == RuleStatus.FIRED),
        report.before.score,
    )
    return report
