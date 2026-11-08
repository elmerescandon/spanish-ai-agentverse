"""Turn analysis results into stored fields and validate accepted changes.

Pure: no I/O. The upload stores a protocol's parsed facts as short named
fields; the PEERS step stores the seven comparison fields and the values
Theo's agent offers for them. A change is accepted only if it is one of
those offered values, so a stored value always comes from real data.
"""

import logging
import math
from collections.abc import Iterable, Sequence
from enum import Enum

from pydantic import BaseModel

from backend.agents.protocol_comparison.comparison import (
    DimensionComparison,
)
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.agents.protocol_comparison.recommendations import (
    recommendation_id,
)
from backend.agents.protocol_comparison.review import SuggestionCard
from backend.api.schemas import StepData
from backend.clients.protocol_db import OfferedValue, StoredField
from backend.shared.messages import CitedValue, ProtocolDocument

logger = logging.getLogger(__name__)

MAX_FIELD_VALUE_CHARS = 1000  # longer text is a passage, not a field
COMPARISON_PREFIX = "comparison"
# Paragraph-sized text that the database must not hold.
EXCLUDED_ATTRIBUTES = frozenset({"summary"})
# Facets stored as their top-level values (lists inside are skipped).
SCALAR_FACETS = (
    "design",
    "statistics",
    "estimands",
    "interventions",
    "analysis",
    "synopsis_check",
    "safety_monitoring",
)


class ChangeRejectedError(ValueError):
    """Raised when a submitted change is not a value an agent offered."""


def comparison_field(dimension_id: DimensionId) -> str:
    """The stored field name for one of Theo's comparison dimensions."""
    return f"{COMPARISON_PREFIX}.{dimension_id.value.lower()}"


ACCEPTABLE_FIELDS = frozenset(comparison_field(d) for d in DimensionId)


def format_number(value: float) -> str:
    """Whole numbers without a decimal point, others as written."""
    return str(int(value)) if value.is_integer() else repr(value)


def _as_text(raw: object) -> str | None:
    """Short text for a scalar value; None for lists and nested models."""
    if isinstance(raw, bool):
        return "true" if raw else "false"
    if isinstance(raw, Enum):
        return str(raw.value)
    if isinstance(raw, int | float):
        return format_number(float(raw))
    if isinstance(raw, str):
        return raw
    return None


def _stored(field: str, raw: object, page: int | None) -> StoredField | None:
    if isinstance(raw, CitedValue):
        return _stored(field, raw.value, raw.citation.page_number)
    text = _as_text(raw)
    if text is None:
        return None
    if len(text) > MAX_FIELD_VALUE_CHARS:
        logger.warning(
            "field skipped, too long to store: field=%s chars=%d",
            field,
            len(text),
        )
        return None
    return StoredField(field=field, value=text, page=page)


def _model_fields(prefix: str, model: BaseModel) -> list[StoredField]:
    """The model's own scalar values; its lists and sub-models skipped."""
    citation = getattr(model, "citation", None)
    page = getattr(citation, "page_number", None)
    stored = (
        _stored(f"{prefix}.{name}", getattr(model, name), page)
        for name in type(model).model_fields
        if name not in EXCLUDED_ATTRIBUTES
    )
    return [item for item in stored if item is not None]


def _list_fields(
    prefix: str, items: Iterable[tuple[str, BaseModel]]
) -> list[StoredField]:
    return [
        stored
        for key, item in items
        for stored in _model_fields(f"{prefix}.{key}", item)
    ]


def document_fields(document: ProtocolDocument) -> list[StoredField]:
    """A parsed protocol as short named fields, without the page text."""
    fields = [
        stored
        for facet in SCALAR_FACETS
        if (model := getattr(document, facet)) is not None
        for stored in _model_fields(facet, model)
    ]
    fields += _list_fields(
        "eligibility",
        (
            (criterion.criterion_id, criterion)
            for criterion in document.eligibility_criteria or []
        ),
    )
    for facet in ("endpoints", "schedule", "sections"):
        numbered = enumerate(getattr(document, facet) or [], start=1)
        fields += _list_fields(
            facet, ((str(number), item) for number, item in numbered)
        )
    return fields


def starting_comparison_fields(
    results: Sequence[DimensionComparison],
) -> list[StoredField]:
    """Each comparison field at the draft's own value, where it has one."""
    return [
        StoredField(
            field=comparison_field(result.dimension.dimension_id),
            value=format_number(result.draft_value.value),
            unit=result.dimension.unit,
        )
        for result in results
        if result.draft_value is not None
    ]


def offered_values(
    cards: Sequence[SuggestionCard], step: StepData
) -> list[OfferedValue]:
    """Every value Theo's PEERS step offers, with the option that shows it.

    Each card's suggestions are paired, in order, with its decision's
    options that propose a change (the "keep" option proposes none), so
    an offer carries the exact option ID and rationale the user saw.
    """
    decisions = {decision.decision_id: decision for decision in step.decisions}
    offers = []
    for card in cards:
        result = card.comparison
        decision = decisions.get(recommendation_id(result))
        if decision is None:
            continue
        change_options = [
            option
            for option in decision.options
            if option.proposed_change is not None
        ]
        for suggestion, option in zip(
            card.suggestions, change_options, strict=False
        ):
            offers.append(
                OfferedValue(
                    field=comparison_field(result.dimension.dimension_id),
                    value=suggestion.suggested_value,
                    unit=result.dimension.unit,
                    decision_id=decision.decision_id,
                    option_id=option.option_id,
                    rationale=option.rationale,
                )
            )
    return offers


def match_offer(
    field: str, value: float, offers: Sequence[OfferedValue]
) -> OfferedValue:
    """The offer a submitted change corresponds to.

    Raises:
        ChangeRejectedError: the field cannot be changed, nothing is
            offered for it yet, or the value is not one of the offers.
    """
    if field not in ACCEPTABLE_FIELDS:
        raise ChangeRejectedError(
            f"expected field to be one of {sorted(ACCEPTABLE_FIELDS)}, "
            f"got {field!r}"
        )
    if not offers:
        raise ChangeRejectedError(
            f"no values are offered for {field} yet; run the PEERS step "
            "(POST /api/protocol-recommendation) first"
        )
    for offer in offers:
        if math.isclose(offer.value, value):
            return offer
    offered = sorted(offer.value for offer in offers)
    raise ChangeRejectedError(
        f"expected one of the offered values {offered} for {field}, "
        f"got {value}"
    )
