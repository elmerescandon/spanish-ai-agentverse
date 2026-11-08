"""Protocol comparison agent: flags draft values out of line with peers.

Other parts of the backend call review_flags() directly with the
comparison results; it returns one suggestion card per flag.
"""

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
)
from backend.agents.protocol_comparison.eligibility import (
    LabLimitReply,
    LabReading,
    ReadingStatus,
    StoredLabReading,
    build_lab_prompt,
    clean_registry_text,
    interpret_reply,
    reading_cache_key,
)
from backend.agents.protocol_comparison.review import (
    FlagReasoning,
    ReasoningStatus,
    SuggestionCard,
    build_reasoning_prompt,
    needs_review,
    unknown_cited_trials,
)
from backend.agents.protocol_comparison.suggestions import suggest_values
from backend.clients.clinicaltrials_gov import StudyRecord
from backend.clients.gemini import JsonGenerator, LlmCallFailedError

logger = logging.getLogger(__name__)

AGENT_NAME = "protocol_comparison"


class LabReadingCache(Protocol):
    """Where LLM readings are kept between runs, e.g. the PeerStore."""

    def load_lab_reading(self, trial_id: str) -> StoredLabReading | None: ...

    def save_lab_reading(self, stored: StoredLabReading) -> None: ...


async def _read_one(
    study: StudyRecord, llm: JsonGenerator, cache: LabReadingCache
) -> LabReading:
    eligibility = study.protocol_section.eligibility_module
    raw_text = eligibility.eligibility_criteria if eligibility else None
    if not raw_text:
        return LabReading(
            trial_id=study.nct_id,
            values={},
            rejected=(),
            status=ReadingStatus.NO_TEXT,
        )
    text = clean_registry_text(raw_text)
    cache_key = reading_cache_key(text)
    stored = cache.load_lab_reading(study.nct_id)
    if stored is None or stored.cache_key != cache_key:
        try:
            reply = await llm.generate_json(
                build_lab_prompt(text), LabLimitReply
            )
        except LlmCallFailedError:
            logger.exception(
                "lab limit reading failed: agent=%s trial_id=%s",
                AGENT_NAME,
                study.nct_id,
            )
            return LabReading(
                trial_id=study.nct_id,
                values={},
                rejected=(),
                status=ReadingStatus.FAILED,
            )
        stored = StoredLabReading(
            trial_id=study.nct_id,
            cache_key=cache_key,
            read_at=datetime.now(UTC),
            reply=reply,
        )
        cache.save_lab_reading(stored)
    reading = interpret_reply(study.nct_id, text, stored.reply)
    for rejected in reading.rejected:
        logger.warning(
            "lab limit rejected: agent=%s trial_id=%s reason=%s quote=%r",
            AGENT_NAME,
            study.nct_id,
            rejected.reason,
            rejected.predicate.source_text,
        )
    return reading


async def read_lab_limits(
    studies: Sequence[StudyRecord],
    llm: JsonGenerator,
    cache: LabReadingCache,
) -> tuple[LabReading, ...]:
    """Read every study's lab limits from its eligibility text.

    The LLM's raw reply is cached per trial and reused while the text
    and instructions are unchanged, so values stay the same between
    runs. A failed call gives that trial a FAILED reading with no values
    (it then counts as not stating them) and is not cached.
    """
    return tuple(
        await asyncio.gather(
            *(_read_one(study, llm, cache) for study in studies)
        )
    )


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
    """Build a suggestion card for every dimension that needs review.

    A dimension needs review when Stefan's weighted rule flags it, when
    any category (all, recent, same drug) flags it, or when the draft
    is beyond every same-drug peer.

    Suggested values come from peers; the LLM, when given, only writes
    the reasoning. A failed LLM call marks that card FAILED instead of
    raising, so one bad call never hides the other flags. With llm=None
    the cards carry suggestions and evidence but no reasoning.
    """
    flagged = [result for result in results if needs_review(result)]
    cards = await asyncio.gather(
        *(_review_flag(result, llm) for result in flagged)
    )
    return tuple(cards)
