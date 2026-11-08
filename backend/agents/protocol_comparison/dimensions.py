"""Comparison dimensions and how to read them from a registry record.

A trial (draft or peer) is reduced to a TrialProfile: the value of each
dimension it states, where that value came from, its start date and its
drug classes. The comparison only sees profiles, so the draft's values
can later come from the parsed protocol instead of the registry.
"""

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from backend.agents.protocol_comparison.logic import classify_drug_classes
from backend.agents.protocol_comparison.rules import DrugClass
from backend.clients.clinicaltrials_gov import StudyRecord

logger = logging.getLogger(__name__)

# The registry writes ages as "<number> <unit>", e.g. "10 Years".
REGISTRY_AGE_PATTERN = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s+(year|month|week|day)s?\s*$", re.IGNORECASE
)
UNITS_PER_YEAR = {"year": 1.0, "month": 12.0, "week": 52.18, "day": 365.25}
# Registry start dates are "YYYY-MM-DD" or, less precisely, "YYYY-MM".
MONTH_PRECISION_DATE_LENGTH = len("YYYY-MM")


class DimensionId(StrEnum):
    """A protocol property compared against peers."""

    MINIMUM_AGE = "MINIMUM_AGE"
    MAXIMUM_AGE = "MAXIMUM_AGE"
    ENROLLMENT = "ENROLLMENT"


class StricterWhen(StrEnum):
    """Which direction makes a value harder to recruit for."""

    HIGHER = "HIGHER"
    LOWER = "LOWER"


@dataclass(frozen=True)
class DimensionValue:
    """One trial's value for a dimension, and where it was read from."""

    value: float
    source: str


@dataclass(frozen=True)
class Dimension:
    """What a dimension measures and how to read it from the registry."""

    dimension_id: DimensionId
    label: str
    unit: str
    stricter_when: StricterWhen
    read_from_registry: Callable[[StudyRecord], DimensionValue | None]


@dataclass(frozen=True)
class TrialProfile:
    """Everything the comparison needs to know about one trial."""

    trial_id: str
    start_date: date | None
    drug_classes: frozenset[DrugClass]
    values: Mapping[DimensionId, DimensionValue]


def parse_registry_age_years(registry_age: str) -> float | None:
    """Convert a registry age like "18 Months" to years, or None."""
    match = REGISTRY_AGE_PATTERN.match(registry_age)
    if match is None:
        return None
    amount, unit = match.groups()
    return float(amount) / UNITS_PER_YEAR[unit.lower()]


def parse_registry_date(registry_date: str) -> date:
    """Parse a registry date; a month-only date means its first day."""
    if len(registry_date) == MONTH_PRECISION_DATE_LENGTH:
        registry_date = f"{registry_date}-01"
    return date.fromisoformat(registry_date)


def _read_age(
    study: StudyRecord, field_name: str, registry_key: str
) -> DimensionValue | None:
    eligibility = study.protocol_section.eligibility_module
    if eligibility is None:
        return None
    registry_age: str | None = getattr(eligibility, field_name)
    if registry_age is None:
        return None
    years = parse_registry_age_years(registry_age)
    if years is None:
        logger.warning(
            "unreadable registry age: nct_id=%s field=%s value=%r",
            study.nct_id,
            registry_key,
            registry_age,
        )
        return None
    return DimensionValue(
        value=years,
        source=f'registry {registry_key} "{registry_age}"',
    )


def read_minimum_age(study: StudyRecord) -> DimensionValue | None:
    return _read_age(study, "minimum_age", "minimumAge")


def read_maximum_age(study: StudyRecord) -> DimensionValue | None:
    return _read_age(study, "maximum_age", "maximumAge")


def read_enrollment(study: StudyRecord) -> DimensionValue | None:
    """Read enrollment; the source says if it is a target or actual."""
    design = study.protocol_section.design_module
    if design is None or design.enrollment_info is None:
        return None
    enrollment = design.enrollment_info
    if enrollment.count is None:
        return None
    return DimensionValue(
        value=float(enrollment.count),
        source=(
            f"registry enrollmentInfo {enrollment.count} "
            f"({enrollment.type or 'type not stated'})"
        ),
    )


REGISTRY_DIMENSIONS: tuple[Dimension, ...] = (
    Dimension(
        dimension_id=DimensionId.MINIMUM_AGE,
        label="Minimum age",
        unit="years",
        stricter_when=StricterWhen.HIGHER,
        read_from_registry=read_minimum_age,
    ),
    Dimension(
        dimension_id=DimensionId.MAXIMUM_AGE,
        label="Maximum age",
        unit="years",
        stricter_when=StricterWhen.LOWER,
        read_from_registry=read_maximum_age,
    ),
    Dimension(
        dimension_id=DimensionId.ENROLLMENT,
        label="Enrollment",
        unit="participants",
        # More participants to find is harder to recruit for.
        stricter_when=StricterWhen.HIGHER,
        read_from_registry=read_enrollment,
    ),
)


def profile_registry_study(study: StudyRecord) -> TrialProfile:
    """Reduce a registry record to the values the comparison uses."""
    values: dict[DimensionId, DimensionValue] = {}
    for dimension in REGISTRY_DIMENSIONS:
        dimension_value = dimension.read_from_registry(study)
        if dimension_value is not None:
            values[dimension.dimension_id] = dimension_value
    start = study.protocol_section.status_module.start_date_struct
    return TrialProfile(
        trial_id=study.nct_id,
        start_date=parse_registry_date(start.date) if start else None,
        drug_classes=classify_drug_classes(study),
        values=values,
    )
