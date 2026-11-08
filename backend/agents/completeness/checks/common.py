"""Shared pure helpers for deterministic completeness and consistency rules."""

import re
from collections.abc import Iterable, Sequence
from enum import StrEnum
from typing import Protocol

from backend.agents.completeness.logic import (
    CheckOutcome,
    select_batch_pages,
)
from backend.shared.citations import make_citation_verifier
from backend.shared.messages import (
    Citation,
    FindingLocation,
    M11Heading,
    PageText,
    ProtocolDocument,
    RuleStatus,
)

WEEKS_PER_YEAR = 52.0
WEEKS_PER_MONTH = WEEKS_PER_YEAR / 12.0
DAYS_PER_WEEK = 7.0
HOURS_PER_WEEK = 168.0
DEFAULT_WEEK_TOLERANCE = 0.5
MIN_QUOTE_LENGTH = 25
QUOTE_PADDING_CHARS = 35
OTHER_CATEGORY_VALUE = "OTHER"
MAX_OFFENDERS_IN_FINDING = 5

# Matches single timepoints or durations: e.g. "Week 26", "26 weeks",
# "6 months", "Month 6", "1 year", "Day 182", "182 days", "24 hours".
SINGLE_TIMEPOINT_PATTERN = re.compile(
    r"(?:\b(?P<prefix_unit>week|wk|month|mo|year|yr|day)s?\s+"
    r"(?P<prefix_num>\d+(?:\.\d+)?)\b)"
    r"|(?:\b(?P<suffix_num>\d+(?:\.\d+)?)\s*(?:-\s*)?"
    r"(?P<suffix_unit>week|wk|month|mo|year|yr|day|hour|hr)s?\b)",
    re.IGNORECASE,
)

# Matches comma/and-separated number lists before a shared unit:
# e.g. "at 3, 6, and 12 months" or "Weeks 12, 26, and 52".
SHARED_UNIT_LIST_PATTERN = re.compile(
    r"\b(?:(?P<lead_unit>week|wk|month|mo|year|yr|day)s?\s+"
    r"(?P<lead_nums>\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*"
    r"\s*(?:,\s*)?(?:and|or)\s+\d+(?:\.\d+)?)\b)"
    r"|(?:\b(?P<trail_nums>\d+(?:\.\d+)?(?:\s*,\s*\d+(?:\.\d+)?)*"
    r"\s*(?:,\s*)?(?:and|or)\s+\d+(?:\.\d+)?)\s*"
    r"(?P<trail_unit>week|wk|month|mo|year|yr|day)s?\b)",
    re.IGNORECASE,
)


# Clinical wording shared by several diabetes and eligibility checks.
CONTINUOUS_CHANGE_PATTERN = re.compile(
    r"\bchange\s+from\s+baseline\b", re.IGNORECASE
)
RESPONDER_TERM_PATTERN = re.compile(
    r"(?:\b(?:proportion|percentage|rate|responder|achieving)\b|[<≤])",
    re.IGNORECASE,
)
HBA1C_PATTERN = re.compile(
    r"\b(?:hba1c|a1c|glycated\s+ha?emoglobin)\b", re.IGNORECASE
)
HYPOGLYCEMIA_ENDPOINT_PATTERN = re.compile(
    r"\bhypoglyc(?:a?emia|emic)\b", re.IGNORECASE
)
CGM_TIR_PATTERN = re.compile(
    r"\b(?:time[\s\-]+in[\s\-]+range|tir|"
    r"continuous\s+glucose\s+monitoring|cgm)\b",
    re.IGNORECASE,
)
CENTRAL_LAB_PATTERN = re.compile(
    r"\bcentral\s+lab(?:orator(?:y|ies)|s)?\b"
    r"|\b(?:analy[sz]ed|measured|assessed)\s+centrally\b",
    re.IGNORECASE,
)


class CategorizedItem[CategoryT: StrEnum](Protocol):
    """Extracted item carrying a canonical StrEnum category and citation."""

    @property
    def category(self) -> CategoryT: ...

    @property
    def label(self) -> str: ...

    @property
    def citation(self) -> Citation: ...


def _unit_to_weeks(number: float, unit: str) -> float:
    lowered = unit.lower()
    if lowered.startswith(("week", "wk")):
        return number
    if lowered.startswith(("month", "mo")):
        return number * WEEKS_PER_MONTH
    if lowered.startswith(("year", "yr")):
        return number * WEEKS_PER_YEAR
    if lowered.startswith("day"):
        return number / DAYS_PER_WEEK
    if lowered.startswith(("hour", "hr")):
        return number / HOURS_PER_WEEK
    return number


def extract_all_timepoints_weeks(text: str) -> list[float]:
    """Extract all positive post-baseline timepoints in weeks from text."""
    found: list[float] = []

    for list_match in SHARED_UNIT_LIST_PATTERN.finditer(text):
        unit = list_match.group("lead_unit") or list_match.group("trail_unit")
        nums_str = list_match.group("lead_nums") or list_match.group(
            "trail_nums"
        )
        for num_token in re.findall(r"\d+(?:\.\d+)?", nums_str):
            weeks = _unit_to_weeks(float(num_token), unit)
            if weeks > 0 and not any(weeks_match(weeks, w) for w in found):
                found.append(weeks)

    for match in SINGLE_TIMEPOINT_PATTERN.finditer(text):
        if match.group("prefix_unit") is not None:
            unit = match.group("prefix_unit")
            number = float(match.group("prefix_num"))
        else:
            unit = match.group("suffix_unit")
            number = float(match.group("suffix_num"))
        weeks = _unit_to_weeks(number, unit)
        if weeks > 0 and not any(weeks_match(weeks, w) for w in found):
            found.append(weeks)

    return found


def parse_duration_to_weeks(text: str) -> float | None:
    """Parse the first positive duration or assessment timepoint into weeks."""
    timepoints = extract_all_timepoints_weeks(text)
    return timepoints[0] if timepoints else None


def weeks_match(
    first: float,
    second: float,
    tolerance_weeks: float = DEFAULT_WEEK_TOLERANCE,
) -> bool:
    """Return True when two durations in weeks match within tolerance."""
    return abs(first - second) <= tolerance_weeks


def location_for_page(
    document: ProtocolDocument,
    page_number: int | None,
    default_heading: M11Heading | None = None,
) -> FindingLocation:
    """Build a FindingLocation from a 1-based page number and section map."""
    if page_number is None:
        return FindingLocation(heading=default_heading)
    section_num: str | None = None
    for sub in document.subsections or []:
        if sub.page_number == page_number:
            section_num = sub.number
            break
    heading = default_heading
    for sec in document.sections or []:
        if sec.start_page <= page_number <= sec.end_page:
            heading = sec.heading
            if section_num is None:
                section_num = sec.title.split()[0] if sec.title else None
            break
    return FindingLocation(
        section=section_num, heading=heading, page=page_number
    )


def format_offenders(
    descriptions: Sequence[str],
    max_items: int = MAX_OFFENDERS_IN_FINDING,
) -> str:
    """Join offender descriptions, capping at max_items with 'and N more'."""
    shown = list(descriptions[:max_items])
    extra = len(descriptions) - len(shown)
    joined = "; ".join(shown)
    if extra > 0:
        return f"{joined}; and {extra} more"
    return joined


def cap_citations(
    citations: Iterable[Citation],
    max_items: int = MAX_OFFENDERS_IN_FINDING,
) -> tuple[Citation, ...]:
    """Return at most max_items citations in order."""
    return tuple(citations)[:max_items]


def passed_outcome(
    finding: str,
    evidence: Iterable[Citation] = (),
    location: FindingLocation | None = None,
) -> CheckOutcome:
    """Build a PASSED CheckOutcome with optional supporting citations."""
    citations = tuple(evidence)
    return CheckOutcome(
        status=RuleStatus.PASSED,
        finding=finding,
        evidence=citations,
        location=location or FindingLocation(),
    )


def fired_outcome(
    finding: str,
    evidence: Iterable[Citation],
    location: FindingLocation | None = None,
    needs_second_opinion: bool = False,
) -> CheckOutcome:
    """Build a FIRED CheckOutcome with supporting citations capped at 5."""
    return CheckOutcome(
        status=RuleStatus.FIRED,
        finding=finding,
        evidence=cap_citations(evidence),
        location=location or FindingLocation(),
        needs_second_opinion=needs_second_opinion,
    )


def absence_fired_outcome(
    finding: str,
    location: FindingLocation | None = None,
) -> CheckOutcome:
    """Build an absence-based FIRED CheckOutcome flagged for second opinion."""
    return CheckOutcome(
        status=RuleStatus.FIRED,
        finding=finding,
        evidence=(),
        location=location or FindingLocation(),
        needs_second_opinion=True,
    )


def not_applicable_outcome(
    reason: str,
    evidence: Iterable[Citation] = (),
) -> CheckOutcome:
    """Build a NOT_APPLICABLE CheckOutcome when a trigger is absent."""
    return CheckOutcome(
        status=RuleStatus.NOT_APPLICABLE,
        finding=f"Not applicable: {reason}",
        evidence=tuple(evidence),
        status_reason=reason,
    )


def cannot_assess_outcome(
    reason: str,
    evidence: Iterable[Citation] = (),
) -> CheckOutcome:
    """Build a CANNOT_ASSESS CheckOutcome for missing facets or OTHER."""
    return CheckOutcome(
        status=RuleStatus.CANNOT_ASSESS,
        finding=f"Cannot assess: {reason}",
        evidence=tuple(evidence),
        status_reason=reason,
    )


def find_other_items[CategoryT: StrEnum](
    items: Sequence[CategorizedItem[CategoryT]],
) -> list[CategorizedItem[CategoryT]]:
    """Return items whose canonical category is OTHER."""
    return [
        item for item in items if item.category.value == OTHER_CATEGORY_VALUE
    ]


def compare_category_sets[CategoryT: StrEnum](
    left_name: str,
    left: Sequence[CategorizedItem[CategoryT]],
    right_name: str,
    right: Sequence[CategorizedItem[CategoryT]],
    document: ProtocolDocument | None = None,
) -> CheckOutcome:
    """Compare two sequences of categorized items without guessing on OTHER."""
    other_items = [*find_other_items(left), *find_other_items(right)]
    if other_items:
        labels = ", ".join(f"'{item.label}'" for item in other_items)
        return cannot_assess_outcome(
            f"Unclassified OTHER category for {labels}; cannot compare "
            f"{left_name} and {right_name} deterministically.",
            evidence=[item.citation for item in other_items],
        )

    left_cats = {item.category for item in left}
    right_cats = {item.category for item in right}
    all_citations = [
        *(item.citation for item in left),
        *(item.citation for item in right),
    ]
    first_page = all_citations[0].page_number if all_citations else None
    loc = (
        location_for_page(document, first_page)
        if document is not None
        else FindingLocation(page=first_page)
    )

    if left_cats != right_cats:
        offending_items = [
            *(item for item in left if item.category not in right_cats),
            *(item for item in right if item.category not in left_cats),
        ]
        offender_labels = [
            f"{item.category.value} ('{item.label}')"
            for item in offending_items
        ]
        offender_citations = [
            *(item.citation for item in offending_items),
            *all_citations,
        ]
        left_desc = ", ".join(sorted(cat.value for cat in left_cats)) or "none"
        right_desc = (
            ", ".join(sorted(cat.value for cat in right_cats)) or "none"
        )
        summary = format_offenders(offender_labels)
        return fired_outcome(
            f"{left_name} lists [{left_desc}], whereas {right_name} lists "
            f"[{right_desc}] (mismatched: {summary}).",
            evidence=offender_citations,
            location=loc,
        )

    matched_desc = ", ".join(sorted(cat.value for cat in left_cats)) or "none"
    return passed_outcome(
        f"{left_name} and {right_name} match on [{matched_desc}].",
        evidence=all_citations[:2],
        location=loc,
    )


def section_pages(
    document: ProtocolDocument, headings: Sequence[M11Heading]
) -> list[PageText]:
    """Return pages belonging to sections with the given headings, or all."""
    return select_batch_pages(document, headings)


def _extract_verbatim_snippet(text: str, start: int, end: int) -> str:
    """Expand match bounds [start, end) to a clean verbatim quote."""
    left = max(0, start - QUOTE_PADDING_CHARS)
    right = min(len(text), end + QUOTE_PADDING_CHARS)
    while left > 0 and not text[left].isspace() and text[left - 1] != "\n":
        left -= 1
    while (
        right < len(text)
        and not text[right - 1].isspace()
        and text[right] != "\n"
    ):
        right += 1
    snippet = text[left:right].strip()
    if len(re.sub(r"[\s\-]+", "", snippet)) < MIN_QUOTE_LENGTH:
        snippet = text[max(0, start - 60) : min(len(text), end + 60)].strip()
    return snippet


def find_pattern_citation(
    document: ProtocolDocument,
    pattern: re.Pattern[str],
    headings: Sequence[M11Heading] = (),
) -> Citation | None:
    """Search section pages for pattern and return a verified Citation."""
    verifier = make_citation_verifier(document.pages)
    for page in section_pages(document, headings):
        match = pattern.search(page.text)
        if match is None:
            continue
        quote = _extract_verbatim_snippet(
            page.text, match.start(), match.end()
        )
        candidate = verifier(
            Citation(page_number=page.page_number, quote=quote)
        )
        if candidate.is_verified:
            return candidate
    return None
