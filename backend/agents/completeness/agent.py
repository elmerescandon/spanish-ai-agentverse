"""Completeness agent: checks a parsed protocol against the rule catalogue.

Other parts of the backend call check_protocol() directly.
"""

import asyncio
import logging
from collections.abc import Mapping

from backend.agents.completeness.checks import (
    DETERMINISTIC_CHECKS,
    JUDGEMENT_PRECHECKS,
    JudgementPrecheck,
)
from backend.agents.completeness.logic import (
    DeterministicCheck,
    EvaluatedRule,
    JudgementBatch,
    JudgementVerdicts,
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
    format_pages_for_prompt,
    format_second_opinion_prompt,
    pre_decide,
    resolve_judgement_batch,
    select_profile_pages,
)
from backend.agents.completeness.prompts import (
    INSTRUCTIONS_SEPARATOR,
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
    RuleFinding,
    RuleStatus,
    TrialProfile,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "completeness"


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
            prompt, TrialProfile, ThinkingLevel.MEDIUM
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
            prompt, JudgementVerdicts, ThinkingLevel.HIGH
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
            prompt, SecondOpinionVerdicts, ThinkingLevel.HIGH
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


async def _run_second_opinion(
    document: ProtocolDocument,
    catalogue: RuleCatalogue,
    evaluated: list[EvaluatedRule],
    llm: JsonGenerator,
) -> list[RuleFinding]:
    """Second-check judgement and absence flags, in concurrent groups."""
    groups = chunk_second_opinion_candidates(evaluated)
    rules_by_id = {rule.id: rule for rule in catalogue.rules}
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
    logger.info(
        "completeness stage=second_opinion protocol_id=%s groups=%d "
        "candidates=%d confirmed=%d",
        document.protocol_id,
        len(groups),
        len(reviewed),
        sum(1 for f in reviewed.values() if f.status == RuleStatus.FIRED),
    )
    return [
        reviewed.get(item.finding.rule_id, item.finding) for item in evaluated
    ]


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
    -> judgement batches -> second opinion -> assemble_report.

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

    # 5. Batched Gemini judgement
    batches = build_judgement_batches(unresolved_judgement)
    batch_results = await asyncio.gather(
        *(
            _run_judgement_batch(batch, document, profile, llm)
            for batch in batches
        )
    )
    judged_items = [
        item for batch_items in batch_results for item in batch_items
    ]
    for item in judged_items:
        evaluated_by_id[item.finding.rule_id] = item
    logger.info(
        "completeness stage=judgement_batches protocol_id=%s batches=%d "
        "rules=%d fired=%d",
        document.protocol_id,
        len(batches),
        len(judged_items),
        sum(1 for e in judged_items if e.finding.status == RuleStatus.FIRED),
    )

    # 6. Second opinion pass
    evaluated = [evaluated_by_id[rule.id] for rule in rule_catalogue.rules]
    findings = await _run_second_opinion(
        document, rule_catalogue, evaluated, llm
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
