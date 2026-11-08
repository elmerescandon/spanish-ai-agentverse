"""Protocol comparison agent: flags draft values out of line with peers.

Other parts of the backend call review_flags() directly with the
comparison results; it returns one suggestion card per flag.
"""

import asyncio
import logging
from collections.abc import Sequence

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
    Verdict,
)
from backend.agents.protocol_comparison.review import (
    FlagReasoning,
    ReasoningStatus,
    SuggestionCard,
    build_reasoning_prompt,
    unknown_cited_trials,
)
from backend.agents.protocol_comparison.suggestions import suggest_values
from backend.clients.gemini import JsonGenerator, LlmCallFailedError

logger = logging.getLogger(__name__)

AGENT_NAME = "protocol_comparison"


async def _review_flag(
    result: DimensionComparison, llm: JsonGenerator | None
) -> SuggestionCard:
    suggestions = suggest_values(result)
    if llm is None:
        return SuggestionCard(
            comparison=result,
            suggestions=suggestions,
            reasoning=None,
            reasoning_status=ReasoningStatus.SKIPPED,
        )
    prompt = build_reasoning_prompt(result, suggestions)
    try:
        reasoning = await llm.generate_json(prompt, FlagReasoning)
    except LlmCallFailedError:
        logger.exception(
            "flag reasoning failed: agent=%s dimension=%s",
            AGENT_NAME,
            result.dimension.dimension_id,
        )
        return SuggestionCard(
            comparison=result,
            suggestions=suggestions,
            reasoning=None,
            reasoning_status=ReasoningStatus.FAILED,
        )
    unknown_trial_ids = unknown_cited_trials(reasoning, result)
    if unknown_trial_ids:
        logger.warning(
            "reasoning cites trials outside the evidence: agent=%s "
            "dimension=%s trial_ids=%s",
            AGENT_NAME,
            result.dimension.dimension_id,
            unknown_trial_ids,
        )
    return SuggestionCard(
        comparison=result,
        suggestions=suggestions,
        reasoning=reasoning,
        reasoning_status=ReasoningStatus.WRITTEN,
        unknown_cited_trial_ids=unknown_trial_ids,
    )


async def review_flags(
    results: Sequence[DimensionComparison], llm: JsonGenerator | None
) -> tuple[SuggestionCard, ...]:
    """Build a suggestion card for every flagged dimension.

    Suggested values come from peers; the LLM, when given, only writes
    the reasoning. A failed LLM call marks that card FAILED instead of
    raising, so one bad call never hides the other flags. With llm=None
    the cards carry suggestions and evidence but no reasoning.
    """
    flagged = [result for result in results if result.verdict == Verdict.FLAG]
    cards = await asyncio.gather(
        *(_review_flag(result, llm) for result in flagged)
    )
    return tuple(cards)
