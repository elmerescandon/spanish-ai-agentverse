"""Protocol comparison agent: flags draft values out of line with peers.

The draft is the parsed protocol under review (compare_protocol_draft);
its peers are ClinicalTrials.gov records. Each flag gets a suggestion
card from review_flags().
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
    compare_draft,
)
from backend.agents.protocol_comparison.dimensions import (
    ALL_DIMENSIONS,
    profile_protocol_document,
    profile_registry_study,
    with_values,
)
from backend.agents.protocol_comparison.eligibility import (
    LabLimitReply,
    LabReading,
    ReadingStatus,
    StoredLabReading,
    build_lab_prompt,
    clean_registry_text,
    interpret_reply,
    protocol_eligibility_text,
    reading_cache_key,
)
from backend.agents.protocol_comparison.logic import (
    peer_query_for,
    protocol_nct_id,
    screen_peers,
)
from backend.agents.protocol_comparison.peer_store import PeerSource
from backend.agents.protocol_comparison.review import (
    FlagReasoning,
    ReasoningStatus,
    SuggestionCard,
    build_reasoning_prompt,
    needs_review,
    unknown_cited_trials,
)
from backend.agents.protocol_comparison.rules import (
    TYPE_2_DIABETES_PEER_CRITERIA,
    PeerCriteria,
)
from backend.agents.protocol_comparison.suggestions import suggest_values
from backend.clients.clinicaltrials_gov import PeerSearchQuery, StudyRecord
from backend.clients.gemini import JsonGenerator, LlmCallFailedError
from backend.shared.messages import ProtocolDocument

logger = logging.getLogger(__name__)

AGENT_NAME = "protocol_comparison"


class LabReadingCache(Protocol):
    """Where LLM readings are kept between runs, e.g. the PeerStore."""

    def load_lab_reading(self, trial_id: str) -> StoredLabReading | None: ...

    def save_lab_reading(self, stored: StoredLabReading) -> None: ...


class SessionLabReadingCache:
    """Reads from a backing cache; keeps new readings in memory only.

    For callers that must not write to disk (the deployed filesystem is
    read-only): the committed peer readings are still used, and a draft
    read once is reused for the rest of the process.
    """

    def __init__(self, backing: LabReadingCache) -> None:
        self._backing = backing
        self._readings: dict[str, StoredLabReading] = {}

    def load_lab_reading(self, trial_id: str) -> StoredLabReading | None:
        stored = self._readings.get(trial_id)
        return stored or self._backing.load_lab_reading(trial_id)

    def save_lab_reading(self, stored: StoredLabReading) -> None:
        self._readings[stored.trial_id] = stored


async def _read_text(
    trial_id: str,
    text: str | None,
    llm: JsonGenerator | None,
    cache: LabReadingCache,
) -> LabReading:
    if not text:
        return LabReading(
            trial_id=trial_id,
            values={},
            rejected=(),
            status=ReadingStatus.NO_TEXT,
        )
    cache_key = reading_cache_key(text)
    stored = cache.load_lab_reading(trial_id)
    if stored is None or stored.cache_key != cache_key:
        if llm is None:
            return LabReading(
                trial_id=trial_id,
                values={},
                rejected=(),
                status=ReadingStatus.NOT_READ,
            )
        try:
            reply = await llm.generate_json(
                build_lab_prompt(text), LabLimitReply
            )
        except LlmCallFailedError:
            logger.exception(
                "lab limit reading failed: agent=%s trial_id=%s",
                AGENT_NAME,
                trial_id,
            )
            return LabReading(
                trial_id=trial_id,
                values={},
                rejected=(),
                status=ReadingStatus.FAILED,
            )
        stored = StoredLabReading(
            trial_id=trial_id,
            cache_key=cache_key,
            read_at=datetime.now(UTC),
            reply=reply,
        )
        cache.save_lab_reading(stored)
    reading = interpret_reply(trial_id, text, stored.reply)
    for rejected in reading.rejected:
        logger.warning(
            "lab limit rejected: agent=%s trial_id=%s reason=%s quote=%r",
            AGENT_NAME,
            trial_id,
            rejected.reason,
            rejected.predicate.source_text,
        )
    return reading


async def _read_one(
    study: StudyRecord, llm: JsonGenerator | None, cache: LabReadingCache
) -> LabReading:
    eligibility = study.protocol_section.eligibility_module
    raw_text = eligibility.eligibility_criteria if eligibility else None
    text = clean_registry_text(raw_text) if raw_text else None
    return await _read_text(study.nct_id, text, llm, cache)


async def read_lab_limits(
    studies: Sequence[StudyRecord],
    llm: JsonGenerator | None,
    cache: LabReadingCache,
) -> tuple[LabReading, ...]:
    """Read every study's lab limits from its eligibility text.

    With llm=None only cached readings are used; a trial with none gets
    a NOT_READ reading with no values. That keeps API calls fast and
    free of LLM latency.

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


async def compare_registry_draft(
    draft_study: StudyRecord,
    protocol_date: date,
    peer_studies: Sequence[StudyRecord],
    cache: LabReadingCache,
    llm: JsonGenerator | None = None,
    criteria: PeerCriteria = TYPE_2_DIABETES_PEER_CRITERIA,
) -> tuple[tuple[DimensionComparison, ...], tuple[SuggestionCard, ...]]:
    """Run the whole comparison for a draft given as a registry record.

    Screens the peers, reads lab limits (cached readings only when llm
    is None), compares every dimension and builds the review cards. The
    LLM, when given, also reads uncached text and writes card reasoning.
    """
    screening = screen_peers(list(peer_studies), criteria)
    readings = await read_lab_limits(
        [draft_study, *screening.peers], llm, cache
    )
    lab_values = {reading.trial_id: reading.values for reading in readings}
    draft = with_values(
        profile_registry_study(draft_study), lab_values[draft_study.nct_id]
    )
    peers = [
        with_values(profile_registry_study(peer), lab_values[peer.nct_id])
        for peer in screening.peers
    ]
    results = compare_draft(
        draft, protocol_date, peers, dimensions=ALL_DIMENSIONS
    )
    logger.info(
        "comparison done: agent=%s draft=%s peers=%d excluded=%d flags=%d",
        AGENT_NAME,
        draft_study.nct_id,
        len(peers),
        len(screening.excluded),
        sum(bool(result.flagged_categories) for result in results),
    )
    return results, await review_flags(results, llm)


@dataclass(frozen=True)
class ProtocolComparison:
    """The parsed protocol compared with its peers.

    peer_search is the registry search the peers came from, and
    review_date the date peers were weighted for recency against.
    draft_lab_reading says whether the draft's lab limits could be read
    from its eligibility criteria (they are missing from results if not).
    """

    review_date: date
    peer_search: PeerSearchQuery
    results: tuple[DimensionComparison, ...]
    cards: tuple[SuggestionCard, ...]
    draft_lab_reading: LabReading


async def compare_protocol_draft(
    document: ProtocolDocument,
    review_date: date,
    peer_search: PeerSearchQuery,
    peer_studies: Sequence[StudyRecord],
    cache: LabReadingCache,
    lab_llm: JsonGenerator | None,
    reasoning_llm: JsonGenerator | None = None,
    criteria: PeerCriteria = TYPE_2_DIABETES_PEER_CRITERIA,
) -> ProtocolComparison:
    """Compare the parsed protocol under review with registry peers.

    The draft's values come only from the parsed document: ages and
    enrollment from its design facet, lab limits read by lab_llm from
    its eligibility criteria. Peers keep their registry values; a peer
    with the protocol's own NCT ID is dropped so it is never its own
    peer. lab_llm also reads peers missing from the cache; with None,
    only cached readings are used. reasoning_llm, when given, writes
    each card's reasoning.

    A failed LLM call never raises: the draft's lab dimensions are left
    without a value and draft_lab_reading says why.
    """
    own_nct_id = protocol_nct_id(document)
    screening = screen_peers(
        [study for study in peer_studies if study.nct_id != own_nct_id],
        criteria,
    )
    draft_text = protocol_eligibility_text(document.eligibility_criteria or [])
    draft_reading, *peer_readings = await asyncio.gather(
        _read_text(document.protocol_id, draft_text, lab_llm, cache),
        *(_read_one(peer, lab_llm, cache) for peer in screening.peers),
    )
    draft = with_values(
        profile_protocol_document(document), draft_reading.values
    )
    peers = [
        with_values(profile_registry_study(peer), reading.values)
        for peer, reading in zip(screening.peers, peer_readings, strict=True)
    ]
    results = compare_draft(
        draft, review_date, peers, dimensions=ALL_DIMENSIONS
    )
    logger.info(
        "comparison done: agent=%s protocol_id=%s draft_labs=%s peers=%d "
        "excluded=%d flags=%d",
        AGENT_NAME,
        document.protocol_id,
        draft_reading.status,
        len(peers),
        len(screening.excluded),
        sum(bool(result.flagged_categories) for result in results),
    )
    return ProtocolComparison(
        review_date=review_date,
        peer_search=peer_search,
        results=results,
        cards=await review_flags(results, reasoning_llm),
        draft_lab_reading=draft_reading,
    )


async def compare_with_registry_peers(
    document: ProtocolDocument,
    review_date: date,
    peer_source: PeerSource,
    cache: LabReadingCache,
    lab_llm: JsonGenerator | None,
) -> ProtocolComparison:
    """Find the protocol's peers from its parsed values, then compare.

    The registry search uses the protocol's phase and age range (see
    peer_query_for); lab_llm reads the lab limits of the draft and of
    any peer not already in cache.

    Raises:
        ClinicalTrialsGovError: the live registry search failed.
        PeerStoreError: the committed peer snapshot is unreadable.
    """
    peer_search = peer_query_for(document, review_date)
    peer_studies = await peer_source.studies_for(peer_search)
    logger.info(
        "peers found: agent=%s protocol_id=%s phases=%s population=%s "
        "since=%s studies=%d",
        AGENT_NAME,
        document.protocol_id,
        ",".join(peer_search.phases),
        peer_search.population,
        peer_search.started_on_or_after,
        len(peer_studies),
    )
    return await compare_protocol_draft(
        document, review_date, peer_search, peer_studies, cache, lab_llm
    )
