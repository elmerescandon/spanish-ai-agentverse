"""Lab limits read from eligibility text: prompt, checks and mapping.

Pure. The LLM lists each numeric limit as a predicate in Stefan's
canonical form (variable, operator, value, unit, scope, quote); this
module checks each quote against the text, converts units and maps the
predicates onto comparison dimensions. An inclusion bound and its
mirror-image exclusion are the same limit. Anything that cannot be
checked or compared is rejected with a reason, never guessed.
"""

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from backend.agents.protocol_comparison.dimensions import (
    DIMENSIONS_BY_ID,
    DimensionId,
    DimensionValue,
    StricterWhen,
)
from backend.agents.protocol_comparison.prompts import LAB_LIMIT_INSTRUCTIONS
from backend.shared.messages import CriterionKind, EligibilityCriterion

# The registry escapes markdown characters, e.g. "\>=" for ">=".
REGISTRY_ESCAPE_PATTERN = re.compile(r"\\([<>=*~\[\]()_#.+\-])")
WHITESPACE_PATTERN = re.compile(r"\s+")
PROMPT_SECTION_SEPARATOR = "\n---\nEligibility criteria:\n"
CACHE_KEY_LENGTH = 16  # hex characters of a SHA-256; collisions negligible
# Stefan's conversion: mmol/mol = (% - 2.15) x 10.929.
HBA1C_MMOL_PER_PERCENT = 10.929
HBA1C_PERCENT_OFFSET = 2.15
PERCENT_DECIMALS = 2
# Headings that tell the LLM each parsed criterion's scope, written the
# way registry texts head their lists.
CRITERIA_HEADINGS = {
    CriterionKind.INCLUSION: "Inclusion Criteria:",
    CriterionKind.EXCLUSION: "Exclusion Criteria:",
}


class LabVariable(StrEnum):
    """Lab tests whose limits the LLM reads."""

    HBA1C = "HBA1C"
    ALT = "ALT"
    AST = "AST"
    EGFR = "EGFR"


class ComparisonOperator(StrEnum):
    """How a criterion compares the lab value with its limit."""

    GREATER = ">"
    GREATER_OR_EQUAL = ">="
    LESS = "<"
    LESS_OR_EQUAL = "<="


class CriterionScope(StrEnum):
    """Whether a participant must meet the criterion or must not."""

    INCLUSION = "INCLUSION"
    EXCLUSION = "EXCLUSION"


class LabPredicate(BaseModel):
    """One numeric lab limit as the LLM read it."""

    variable: LabVariable
    operator: ComparisonOperator
    value: float
    unit: str
    scope: CriterionScope
    source_text: str = Field(min_length=1)


class LabLimitReply(BaseModel):
    """The LLM's reply: every lab limit found in one trial's criteria."""

    predicates: list[LabPredicate]


class StoredLabReading(BaseModel):
    """A cached LLM reply, valid while its cache key still matches."""

    trial_id: str
    cache_key: str
    read_at: datetime
    reply: LabLimitReply


class RejectionReason(StrEnum):
    """Why a predicate the LLM returned was not used."""

    QUOTE_NOT_FOUND = "QUOTE_NOT_FOUND"
    UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"
    UNSUPPORTED_DIRECTION = "UNSUPPORTED_DIRECTION"


@dataclass(frozen=True)
class RejectedPredicate:
    """A predicate dropped from the comparison, with the reason."""

    predicate: LabPredicate
    reason: RejectionReason


class ReadingStatus(StrEnum):
    """Whether a trial's lab limits could be read."""

    READ = "READ"
    NO_TEXT = "NO_TEXT"  # no eligibility text to read
    FAILED = "FAILED"  # the LLM call failed after its retries
    NOT_READ = "NOT_READ"  # nothing cached and no LLM to read it


@dataclass(frozen=True)
class LabReading:
    """The lab values read for one trial, and what was rejected."""

    trial_id: str
    values: Mapping[DimensionId, DimensionValue]
    rejected: tuple[RejectedPredicate, ...]
    status: ReadingStatus = ReadingStatus.READ


@dataclass(frozen=True)
class _MappedLimit:
    dimension_id: DimensionId
    value: float
    source: str


def clean_registry_text(text: str) -> str:
    """Undo the registry's markdown escapes so quotes match the text."""
    return REGISTRY_ESCAPE_PATTERN.sub(r"\1", text)


def protocol_eligibility_text(
    criteria: Sequence[EligibilityCriterion],
) -> str | None:
    """The parsed criteria as one text, inclusion first, or None.

    Each list gets the heading registry texts use, so the LLM reads the
    draft's criteria exactly as it reads peers'.
    """
    blocks = []
    for kind, heading in CRITERIA_HEADINGS.items():
        lines = [
            f"- {criterion.text.strip()}"
            for criterion in criteria
            if criterion.kind == kind and criterion.text.strip()
        ]
        if lines:
            blocks.append("\n".join([heading, *lines]))
    return "\n\n".join(blocks) if blocks else None


def _normalised(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip().lower()


def reading_cache_key(cleaned_text: str) -> str:
    """Identify one reading: the text and the instructions it used."""
    digest = hashlib.sha256(
        (LAB_LIMIT_INSTRUCTIONS + cleaned_text).encode("utf-8")
    ).hexdigest()
    return digest[:CACHE_KEY_LENGTH]


def build_lab_prompt(cleaned_text: str) -> str:
    """Reading instructions followed by the trial's criteria."""
    return LAB_LIMIT_INSTRUCTIONS + PROMPT_SECTION_SEPARATOR + cleaned_text


def _is_lower_limit(predicate: LabPredicate) -> bool:
    """True if the predicate sets the lowest value a participant may have.

    Inclusion ">= x" and exclusion "< x" both mean "at least x".
    """
    is_greater = predicate.operator in (
        ComparisonOperator.GREATER,
        ComparisonOperator.GREATER_OR_EQUAL,
    )
    return is_greater == (predicate.scope == CriterionScope.INCLUSION)


def _is_upper_limit_of_normal(unit: str) -> bool:
    """Trials write "x ULN", "*ULN" or spell it out in words."""
    unit = unit.lower()
    return "uln" in unit or ("upper" in unit and "normal" in unit)


def _map_hba1c(predicate: LabPredicate) -> _MappedLimit | RejectionReason:
    unit = predicate.unit.strip().lower()
    if "mmol/mol" in unit:
        percent = round(
            predicate.value / HBA1C_MMOL_PER_PERCENT + HBA1C_PERCENT_OFFSET,
            PERCENT_DECIMALS,
        )
        conversion = f" ({predicate.value:g} mmol/mol = {percent:g}%)"
    elif "%" in unit or "percent" in unit:
        percent = predicate.value
        conversion = ""
    else:
        return RejectionReason.UNSUPPORTED_UNIT
    dimension_id = (
        DimensionId.HBA1C_LOWER_BOUND
        if _is_lower_limit(predicate)
        else DimensionId.HBA1C_UPPER_BOUND
    )
    return _MappedLimit(
        dimension_id, percent, f'"{predicate.source_text}"{conversion}'
    )


def _map_liver(predicate: LabPredicate) -> _MappedLimit | RejectionReason:
    # Absolute U/L values depend on each lab's normal range, so only
    # multiples of the upper limit of normal compare across trials.
    if not _is_upper_limit_of_normal(predicate.unit):
        return RejectionReason.UNSUPPORTED_UNIT
    if _is_lower_limit(predicate):
        return RejectionReason.UNSUPPORTED_DIRECTION
    return _MappedLimit(
        DimensionId.ALT_AST_LIMIT,
        predicate.value,
        f'"{predicate.source_text}" ({predicate.variable.value})',
    )


def _map_egfr(predicate: LabPredicate) -> _MappedLimit | RejectionReason:
    if "ml/min" not in predicate.unit.lower():
        return RejectionReason.UNSUPPORTED_UNIT
    if not _is_lower_limit(predicate):
        return RejectionReason.UNSUPPORTED_DIRECTION
    # [TO REFACTOR:(theo)]: Stefan says never compare eGFR cut-offs from
    # different equations; the formula is not captured yet.
    return _MappedLimit(
        DimensionId.EGFR_CUTOFF, predicate.value, f'"{predicate.source_text}"'
    )


def _map_predicate(predicate: LabPredicate) -> _MappedLimit | RejectionReason:
    if predicate.variable == LabVariable.HBA1C:
        return _map_hba1c(predicate)
    if predicate.variable in (LabVariable.ALT, LabVariable.AST):
        return _map_liver(predicate)
    return _map_egfr(predicate)


def _loosest(
    dimension_id: DimensionId, limits: Sequence[_MappedLimit]
) -> DimensionValue:
    """Several limits for one dimension usually cover different
    subgroups (e.g. by background therapy), so the eligible population
    is bounded by the loosest of them."""
    dimension = DIMENSIONS_BY_ID[dimension_id]
    pick = min if dimension.stricter_when == StricterWhen.HIGHER else max
    chosen = pick(limits, key=lambda limit: limit.value)
    note = (
        f" (loosest of {len(limits)} stated limits)" if len(limits) > 1 else ""
    )
    return DimensionValue(
        value=chosen.value,
        source=f"eligibility text {chosen.source}{note}",
    )


def interpret_reply(
    trial_id: str, cleaned_text: str, reply: LabLimitReply
) -> LabReading:
    """Check each predicate against the text and map it to a dimension."""
    normalised_text = _normalised(cleaned_text)
    mapped: dict[DimensionId, list[_MappedLimit]] = {}
    rejected: list[RejectedPredicate] = []
    for predicate in reply.predicates:
        if _normalised(predicate.source_text) not in normalised_text:
            rejected.append(
                RejectedPredicate(predicate, RejectionReason.QUOTE_NOT_FOUND)
            )
            continue
        outcome = _map_predicate(predicate)
        if isinstance(outcome, RejectionReason):
            rejected.append(RejectedPredicate(predicate, outcome))
            continue
        mapped.setdefault(outcome.dimension_id, []).append(outcome)
    return LabReading(
        trial_id=trial_id,
        values={
            dimension_id: _loosest(dimension_id, limits)
            for dimension_id, limits in mapped.items()
        },
        rejected=tuple(rejected),
    )
