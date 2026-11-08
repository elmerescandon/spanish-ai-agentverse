"""Parser agent: turns a protocol PDF into a citation-verified document.

This task adds the generic facet engine; the uAgent wiring comes later.
"""

import logging

from pydantic import BaseModel

from backend.agents.parser.logic import (
    Facet,
    FacetOutcome,
    build_facet_prompt,
    build_repair_prompt,
    count_verified,
    unverified_citations,
    verify_result,
)
from backend.clients.gemini import JsonGenerator, LlmCallFailedError
from backend.shared.messages import PageText

logger = logging.getLogger(__name__)

AGENT_NAME = "parser"
MAX_CITATION_REPAIR_ROUNDS = 1  # one re-ask; a third call rarely helps


async def extract_facet[ResultT: BaseModel](
    facet: Facet[ResultT], pages: list[PageText], llm: JsonGenerator
) -> FacetOutcome:
    """Extract one facet, verify its citations and run its sanity rules.

    Never raises for LLM failures: a facet that can't be extracted returns
    result=None with a warning, so one facet can't fail the whole parse.
    """
    prompt = build_facet_prompt(facet.instructions, pages)
    try:
        raw_result = await llm.generate_json(
            prompt, facet.result_model, facet.thinking_level
        )
    except LlmCallFailedError as error:
        logger.warning(
            "facet extraction failed: agent=%s facet=%s error=%s",
            AGENT_NAME,
            facet.name,
            error,
        )
        return FacetOutcome(
            facet=facet.name,
            result=None,
            warnings=[f"facet failed after retries: {error}"],
        )

    best_result = verify_result(raw_result, pages)
    warnings: list[str] = []
    for _ in range(MAX_CITATION_REPAIR_ROUNDS):
        failed = unverified_citations(best_result)
        if not failed:
            break
        try:
            repaired_raw = await llm.generate_json(
                build_repair_prompt(prompt, failed),
                facet.result_model,
                facet.thinking_level,
            )
        except LlmCallFailedError as error:
            warnings.append(f"citation repair failed: {error}")
            break
        repaired = verify_result(repaired_raw, pages)
        if count_verified(repaired) >= count_verified(best_result):
            best_result = repaired

    still_failed = unverified_citations(best_result)
    if still_failed:
        warnings.append(
            f"{len(still_failed)} citation(s) could not be verified "
            "against the PDF and are flagged is_verified=False"
        )
    if facet.normalize is not None:
        best_result = facet.normalize(best_result)
    page_count = len(pages)
    for rule in facet.sanity_rules:
        warnings.extend(rule(best_result, page_count))

    logger.info(
        "facet extracted: agent=%s facet=%s verified=%d unverified=%d "
        "warnings=%d",
        AGENT_NAME,
        facet.name,
        count_verified(best_result),
        len(still_failed),
        len(warnings),
    )
    return FacetOutcome(
        facet=facet.name, result=best_result, warnings=warnings
    )
