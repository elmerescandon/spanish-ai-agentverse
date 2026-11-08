"""Completeness agent: checks a parsed protocol against the rule catalogue.

Other parts of the backend call check_protocol() directly.
"""

import logging
from collections.abc import Mapping

from backend.agents.completeness.checks import DETERMINISTIC_CHECKS
from backend.agents.completeness.logic import (
    DeterministicCheck,
    assemble_report,
    evaluate_rule,
    format_pages_for_prompt,
    select_profile_pages,
)
from backend.agents.completeness.prompts import (
    INSTRUCTIONS_SEPARATOR,
    TRIAL_PROFILE_INSTRUCTIONS,
)
from backend.agents.completeness.rules import (
    RequiredInput,
    RuleCatalogue,
    load_rule_catalogue,
)
from backend.clients.gemini import (
    JsonGenerator,
    LlmCallFailedError,
    ThinkingLevel,
)
from backend.shared.citations import make_citation_verifier
from backend.shared.messages import (
    ComplianceReport,
    ProtocolDocument,
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


async def check_protocol(
    document: ProtocolDocument,
    llm: JsonGenerator,
    catalogue: RuleCatalogue | None = None,
    available_inputs: frozenset[RequiredInput] = frozenset(),
    checks: Mapping[str, DeterministicCheck] = DETERMINISTIC_CHECKS,
) -> ComplianceReport:
    """Check a parsed protocol against every rule; one finding per rule.

    Raises:
        ValueError: the catalogue file is invalid (see rules.py).
    """
    rule_catalogue = catalogue or load_rule_catalogue()
    profile = await extract_trial_profile(document, llm)
    findings = [
        evaluate_rule(rule, document, profile, available_inputs, checks)
        for rule in rule_catalogue.rules
    ]
    report = assemble_report(document, profile, rule_catalogue, findings)
    logger.info(
        "protocol checked: agent=%s protocol_id=%s score=%.1f",
        AGENT_NAME,
        document.protocol_id,
        report.before.score,
    )
    return report
