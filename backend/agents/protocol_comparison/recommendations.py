"""Turn comparison results into the API's Recommendation records. Pure.

Every compared dimension becomes one record, so a reviewer sees what
was checked, not only what flagged. Stefan's severities map onto the
API's: S1 critical, S2 warning, S3 info. Category-only flags, same-drug
notes and in-line dimensions are info. Everything a reviewer needs
(draft value, categories, suggestions, evidence, the LLM's reasoning)
goes in details.
"""

from collections.abc import Sequence
from enum import StrEnum

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
    RangePosition,
    Severity,
    Verdict,
)
from backend.agents.protocol_comparison.review import (
    SuggestionCard,
    describe_comparison,
)
from backend.api.schemas import PipelineStep, Recommendation
from backend.api.schemas import Severity as ApiSeverity
from backend.clients.clinicaltrials_gov import (
    NCT_ID_PATTERN,
    STUDY_PAGE_URL_TEMPLATE,
)

RECOMMENDATION_ID_PREFIX = "comparison"


class Finding(StrEnum):
    """What the comparison found for one dimension, for the UI."""

    FLAGGED = "FLAGGED"  # official or category flag
    NOTE = "NOTE"  # same-drug note only
    IN_LINE = "IN_LINE"
    INSUFFICIENT_PEERS = "INSUFFICIENT_PEERS"
    NOT_STATED = "NOT_STATED"  # the draft does not state a value


API_SEVERITY = {
    Severity.S1: ApiSeverity.CRITICAL,
    Severity.S2: ApiSeverity.WARNING,
    Severity.S3: ApiSeverity.INFO,
}


def recommendation_id(result: DimensionComparison) -> str:
    """Stable per dimension, so re-running never duplicates a finding."""
    dimension_id = result.dimension.dimension_id
    return f"{RECOMMENDATION_ID_PREFIX}-{dimension_id.value.lower()}"


def _position(card: SuggestionCard) -> RangePosition | None:
    """Official result first, then any flagging category, then the note."""
    result = card.comparison
    for flagged in result.flagged_categories:
        return flagged.range_position
    if result.same_drug_note is not None:
        return result.same_drug_note.position
    return None


def formatted_value(result: DimensionComparison, value: float) -> str:
    unit = result.dimension.unit
    return f"{value:g}{unit}" if unit == "%" else f"{value:g} {unit}"


def _title(card: SuggestionCard) -> str:
    result = card.comparison
    assert result.draft_value is not None
    position = _position(card)
    direction = "out of line" if position is None else position.value.lower()
    compared_with = (
        "comparable trials"
        if result.flagged_categories
        else "every same-drug trial"
    )
    return (
        f"{result.dimension.label}: "
        f"{formatted_value(result, result.draft_value.value)} is "
        f"{direction} than {compared_with}"
    )


def _fallback_description(card: SuggestionCard) -> str:
    """A plain sentence from the facts, for when there is no LLM text."""
    result = card.comparison
    assert result.draft_value is not None
    sentences = [_title(card) + "."]
    for suggestion in card.suggestions:
        sentences.append(
            "Suggested: "
            f"{formatted_value(result, suggestion.suggested_value)}, in line "
            f"with {suggestion.category.value.lower().replace('_', ' ')} "
            f"peers ({len(suggestion.peer_ids)} trials)."
        )
    return " ".join(sentences)


def _with_study_links(peers: object) -> object:
    if not isinstance(peers, list):
        return peers
    return [
        {
            **peer,
            "url": (
                STUDY_PAGE_URL_TEMPLATE.format(nct_id=peer["trial_id"])
                if NCT_ID_PATTERN.fullmatch(str(peer.get("trial_id")))
                else None
            ),
        }
        for peer in peers
        if isinstance(peer, dict)
    ]


def to_recommendation(
    protocol_id: str, card: SuggestionCard
) -> Recommendation:
    """One card as one pending comparison recommendation."""
    result = card.comparison
    facts = describe_comparison(result, card.suggestions)
    facts["peers"] = _with_study_links(facts["peers"])
    severity = (
        API_SEVERITY[result.severity]
        if card.is_official_flag and result.severity is not None
        else ApiSeverity.INFO
    )
    return Recommendation(
        recommendation_id=recommendation_id(result),
        protocol_id=protocol_id,
        source_step=PipelineStep.COMPARISON,
        severity=severity,
        title=_title(card),
        description=(
            card.reasoning.summary
            if card.reasoning is not None
            else _fallback_description(card)
        ),
        details={
            "dimension_id": result.dimension.dimension_id.value,
            "finding": (
                Finding.FLAGGED if result.flagged_categories else Finding.NOTE
            ),
            "is_official_flag": card.is_official_flag,
            "comparison_severity": result.severity,
            **facts,
            "reasoning": (
                None
                if card.reasoning is None
                else card.reasoning.model_dump(mode="json")
            ),
            "reasoning_status": card.reasoning_status.value,
            "unknown_cited_trial_ids": list(card.unknown_cited_trial_ids),
        },
    )


def _unflagged_finding(result: DimensionComparison) -> Finding:
    if result.verdict == Verdict.NO_DRAFT_VALUE:
        return Finding.NOT_STATED
    if result.verdict == Verdict.INSUFFICIENT_PEERS:
        return Finding.INSUFFICIENT_PEERS
    return Finding.IN_LINE


def _unflagged_title(result: DimensionComparison, finding: Finding) -> str:
    label = result.dimension.label
    if finding == Finding.NOT_STATED:
        return f"{label}: not stated in the draft"
    assert result.draft_value is not None
    value = formatted_value(result, result.draft_value.value)
    if finding == Finding.INSUFFICIENT_PEERS:
        return f"{label}: too few comparable trials to judge {value}"
    return f"{label}: {value} is in line with comparable trials"


def unflagged_recommendation(
    protocol_id: str, result: DimensionComparison
) -> Recommendation:
    """A dimension with nothing to act on, recorded as info."""
    finding = _unflagged_finding(result)
    facts = describe_comparison(result, ())
    facts["peers"] = _with_study_links(facts["peers"])
    title = _unflagged_title(result, finding)
    return Recommendation(
        recommendation_id=recommendation_id(result),
        protocol_id=protocol_id,
        source_step=PipelineStep.COMPARISON,
        severity=ApiSeverity.INFO,
        title=title,
        description=title + ".",
        details={
            "dimension_id": result.dimension.dimension_id.value,
            "finding": finding,
            "is_official_flag": False,
            "comparison_severity": None,
            **facts,
            "reasoning": None,
            "reasoning_status": None,
            "unknown_cited_trial_ids": [],
        },
    )


def to_recommendations(
    protocol_id: str,
    results: Sequence[DimensionComparison],
    cards: Sequence[SuggestionCard],
) -> list[Recommendation]:
    """One recommendation per compared dimension, in the results' order.

    Dimensions with a card (a flag or a note) use it; the rest are info.
    """
    cards_by_dimension = {
        card.comparison.dimension.dimension_id: card for card in cards
    }
    return [
        to_recommendation(protocol_id, card)
        if (card := cards_by_dimension.get(result.dimension.dimension_id))
        else unflagged_recommendation(protocol_id, result)
        for result in results
    ]
