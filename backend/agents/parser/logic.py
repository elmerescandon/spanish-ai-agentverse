"""Pure facet logic for the parser: prompts, citation walks and assembly.

A facet is data (instructions, result schema, thinking level, sanity
rules), so adding a key point to extract never needs new engine code.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from backend.agents.parser.prompts import (
    COMMON_EXTRACTION_RULES,
    DESIGN_INSTRUCTIONS,
    ELIGIBILITY_INSTRUCTIONS,
    ENDPOINTS_INSTRUCTIONS,
    INSTRUCTIONS_SEPARATOR,
    REPAIR_INSTRUCTIONS,
    SECTIONS_INSTRUCTIONS,
)
from backend.clients.gemini import ThinkingLevel
from backend.shared.citations import verify_citation
from backend.shared.messages import (
    Citation,
    CriterionKind,
    EligibilityCriterion,
    EligibilityExtraction,
    EndpointKind,
    EndpointList,
    ExtractionWarning,
    FacetName,
    PageText,
    ProtocolDocument,
    ScheduleOfActivities,
    SectionMap,
    StatisticalAssumptions,
    TrialDesignFacts,
)

PAGE_MARKER_TEMPLATE = "=== PAGE {page_number} ==="
EMPTY_FACET_WARNING = "facet ran but found no items in the document"
INCLUSION_ID_PREFIX = "IN"
EXCLUSION_ID_PREFIX = "EX"
MIN_ARM_COUNT = 1

type SanityRule[ResultT: BaseModel] = Callable[[ResultT, int], list[str]]
"""Takes a facet result and the page count; returns warning messages."""


@dataclass(frozen=True)
class Facet[ResultT: BaseModel]:
    """One kind of key point to extract, with its schema and checks."""

    name: FacetName
    instructions: str
    result_model: type[ResultT]
    thinking_level: ThinkingLevel
    sanity_rules: tuple[SanityRule[ResultT], ...] = field(default=())
    normalize: Callable[[ResultT], ResultT] | None = None


@dataclass
class FacetOutcome:
    """A facet's verified result (None if it failed) and its warnings."""

    facet: FacetName
    result: BaseModel | None
    warnings: list[str]


def format_pages_for_prompt(pages: list[PageText]) -> str:
    """Render pages with 1-based markers that citations refer to."""
    return "\n".join(
        f"{PAGE_MARKER_TEMPLATE.format(page_number=page.page_number)}\n"
        f"{page.text}"
        for page in pages
    )


def build_facet_prompt(facet_instructions: str, pages: list[PageText]) -> str:
    """Build a facet prompt with the page text first.

    Every facet sends identical page text as its prefix, which is what
    Gemini's implicit context caching discounts.
    """
    return (
        f"{format_pages_for_prompt(pages)}{INSTRUCTIONS_SEPARATOR}"
        f"{facet_instructions}\n\n{COMMON_EXTRACTION_RULES}"
    )


def build_repair_prompt(base_prompt: str, failed: list[Citation]) -> str:
    """Append the repair request, listing each failed quote and page."""
    failed_lines = "\n".join(
        f'- page {citation.page_number}: "{citation.quote}"'
        for citation in failed
    )
    return f"{base_prompt}\n\n{REPAIR_INSTRUCTIONS}\n{failed_lines}"


def _collect_from(value: object, found: list[Citation]) -> None:
    if isinstance(value, Citation):
        found.append(value)
    elif isinstance(value, BaseModel):
        for field_name in type(value).model_fields:
            _collect_from(getattr(value, field_name), found)
    elif isinstance(value, list | tuple):
        for item in value:
            _collect_from(item, found)


def collect_citations(result: BaseModel) -> list[Citation]:
    """Return every Citation inside result, in field order."""
    found: list[Citation] = []
    _collect_from(result, found)
    return found


def _map_citations(
    value: object, transform: Callable[[Citation], Citation]
) -> object:
    if isinstance(value, Citation):
        return transform(value)
    if isinstance(value, BaseModel):
        return value.model_copy(
            update={
                field_name: _map_citations(
                    getattr(value, field_name), transform
                )
                for field_name in type(value).model_fields
            }
        )
    if isinstance(value, list):
        return [_map_citations(item, transform) for item in value]
    if isinstance(value, tuple):
        return tuple(_map_citations(item, transform) for item in value)
    return value


def verify_result[ResultT: BaseModel](
    result: ResultT, pages: list[PageText]
) -> ResultT:
    """Return a copy of result with every citation checked against pages."""
    verified = _map_citations(
        result, lambda citation: verify_citation(citation, pages)
    )
    assert isinstance(verified, type(result))
    return verified


def count_verified(result: BaseModel) -> int:
    """Count the citations in result that passed verification."""
    return sum(
        1 for citation in collect_citations(result) if citation.is_verified
    )


def unverified_citations(result: BaseModel) -> list[Citation]:
    """Return the citations in result that failed verification."""
    return [
        citation
        for citation in collect_citations(result)
        if not citation.is_verified
    ]


def assemble_document(
    protocol_id: str,
    title: str,
    pages: list[PageText],
    outcomes: dict[FacetName, FacetOutcome],
) -> ProtocolDocument:
    """Combine facet outcomes into one ProtocolDocument.

    A failed facet leaves its field None; a facet that found nothing gives
    an empty list. Both cases carry an ExtractionWarning.
    """
    document = ProtocolDocument(
        protocol_id=protocol_id,
        title=title,
        page_count=len(pages),
        pages=pages,
    )
    warnings: list[ExtractionWarning] = []
    for facet_name, outcome in outcomes.items():
        warnings.extend(
            ExtractionWarning(facet=facet_name, message=message)
            for message in outcome.warnings
        )
        if outcome.result is None:
            continue
        found_items = _store_facet_result(document, outcome.result)
        if found_items == []:
            warnings.append(
                ExtractionWarning(
                    facet=facet_name, message=EMPTY_FACET_WARNING
                )
            )
    document.extraction_warnings = warnings
    return document


def _store_facet_result(
    document: ProtocolDocument, result: BaseModel
) -> list[object] | None:
    """Put result in its document field; return the list it holds, if any."""
    match result:
        case TrialDesignFacts():
            document.design = result
            return None
        case StatisticalAssumptions():
            document.statistics = result
            return None
        case EligibilityExtraction():
            document.eligibility_criteria = result.criteria
            return list(result.criteria)
        case SectionMap():
            document.sections = result.sections
            return list(result.sections)
        case EndpointList():
            document.endpoints = result.endpoints
            return list(result.endpoints)
        case ScheduleOfActivities():
            document.schedule = result.visits
            return list(result.visits)
    raise TypeError(
        "expected a facet result model defined in messages.py, "
        f"got {type(result).__name__}"
    )


def assign_criterion_ids(
    extraction: EligibilityExtraction,
) -> EligibilityExtraction:
    """Renumber eligibility criteria in document order as IN-01 and EX-01."""
    inclusion_index = 0
    exclusion_index = 0
    renumbered: list[EligibilityCriterion] = []
    for criterion in extraction.criteria:
        if criterion.kind == CriterionKind.INCLUSION:
            inclusion_index += 1
            criterion_id = f"{INCLUSION_ID_PREFIX}-{inclusion_index:02d}"
        else:
            exclusion_index += 1
            criterion_id = f"{EXCLUSION_ID_PREFIX}-{exclusion_index:02d}"
        renumbered.append(
            criterion.model_copy(update={"criterion_id": criterion_id})
        )
    return extraction.model_copy(update={"criteria": renumbered})


def normalize_design_facts(facts: TrialDesignFacts) -> TrialDesignFacts:
    """Normalize extracted design facts.

    Strips spaces from and uppercases the NCT ID, and clears an age
    inclusivity flag whose age limit is missing (it would describe nothing).
    """
    updates: dict[str, object] = {}
    if facts.nct_id is not None:
        cleaned_nct = "".join(facts.nct_id.value.split()).upper()
        updates["nct_id"] = facts.nct_id.model_copy(
            update={"value": cleaned_nct}
        )
    if facts.min_age_years is None:
        updates["is_min_age_inclusive"] = None
    if facts.max_age_years is None:
        updates["is_max_age_inclusive"] = None
    return facts.model_copy(update=updates)


def _check_has_inclusion_criterion(
    extraction: EligibilityExtraction, _page_count: int
) -> list[str]:
    if any(c.kind == CriterionKind.INCLUSION for c in extraction.criteria):
        return []
    return ["eligibility criteria contain no INCLUSION items"]


def _check_age_range(facts: TrialDesignFacts, _page_count: int) -> list[str]:
    if facts.min_age_years is None or facts.max_age_years is None:
        return []
    min_age = facts.min_age_years.value
    max_age = facts.max_age_years.value
    if min_age >= max_age:
        message = (
            f"min_age_years ({min_age}) must be less than "
            f"max_age_years ({max_age})"
        )
        return [message]
    return []


def _check_target_enrollment(
    facts: TrialDesignFacts, _page_count: int
) -> list[str]:
    if facts.target_enrollment is None:
        return []
    enrollment = facts.target_enrollment.value
    if enrollment <= 0:
        return [f"target_enrollment ({enrollment}) must be positive"]
    return []


def _check_arm_count(facts: TrialDesignFacts, _page_count: int) -> list[str]:
    if facts.arm_count is None:
        return []
    arms = facts.arm_count.value
    if arms < MIN_ARM_COUNT:
        return [f"arm_count ({arms}) must be at least {MIN_ARM_COUNT}"]
    return []


def sort_sections(section_map: SectionMap) -> SectionMap:
    """Order protocol sections by start_page, then title."""
    ordered = sorted(
        section_map.sections,
        key=lambda section: (section.start_page, section.title),
    )
    return section_map.model_copy(update={"sections": ordered})


def _check_section_page_ranges(
    section_map: SectionMap, page_count: int
) -> list[str]:
    warnings: list[str] = []
    for section in section_map.sections:
        if not (1 <= section.start_page <= section.end_page <= page_count):
            message = (
                f"section '{section.title}' has invalid page range "
                f"{section.start_page}..{section.end_page} "
                f"(document has {page_count} pages)"
            )
            warnings.append(message)
    return warnings


def _check_has_sections(
    section_map: SectionMap, _page_count: int
) -> list[str]:
    if section_map.sections:
        return []
    return ["section map contains no sections"]


def _check_has_primary_endpoint(
    endpoint_list: EndpointList, _page_count: int
) -> list[str]:
    if any(e.kind == EndpointKind.PRIMARY for e in endpoint_list.endpoints):
        return []
    return ["endpoints contain no PRIMARY endpoint"]


ELIGIBILITY_FACET: Facet[EligibilityExtraction] = Facet(
    name=FacetName.ELIGIBILITY,
    instructions=ELIGIBILITY_INSTRUCTIONS,
    result_model=EligibilityExtraction,
    thinking_level=ThinkingLevel.HIGH,
    sanity_rules=(_check_has_inclusion_criterion,),
    normalize=assign_criterion_ids,
)

DESIGN_FACET: Facet[TrialDesignFacts] = Facet(
    name=FacetName.DESIGN,
    instructions=DESIGN_INSTRUCTIONS,
    result_model=TrialDesignFacts,
    thinking_level=ThinkingLevel.MEDIUM,
    sanity_rules=(
        _check_age_range,
        _check_target_enrollment,
        _check_arm_count,
    ),
    normalize=normalize_design_facts,
)

SECTIONS_FACET: Facet[SectionMap] = Facet(
    name=FacetName.SECTIONS,
    instructions=SECTIONS_INSTRUCTIONS,
    result_model=SectionMap,
    thinking_level=ThinkingLevel.MEDIUM,
    sanity_rules=(_check_section_page_ranges, _check_has_sections),
    normalize=sort_sections,
)

ENDPOINTS_FACET: Facet[EndpointList] = Facet(
    name=FacetName.ENDPOINTS,
    instructions=ENDPOINTS_INSTRUCTIONS,
    result_model=EndpointList,
    thinking_level=ThinkingLevel.MEDIUM,
    sanity_rules=(_check_has_primary_endpoint,),
)

type AnyFacet = (
    Facet[EligibilityExtraction]
    | Facet[TrialDesignFacts]
    | Facet[SectionMap]
    | Facet[EndpointList]
)

FACETS: tuple[AnyFacet, ...] = (
    ELIGIBILITY_FACET,
    DESIGN_FACET,
    SECTIONS_FACET,
    ENDPOINTS_FACET,
)


def derive_protocol_id(design: TrialDesignFacts | None, pdf_path: Path) -> str:
    """Return the normalized NCT ID when present, otherwise the file stem."""
    if design is not None and design.nct_id is not None:
        nct_value = design.nct_id.value.strip()
        if nct_value:
            return nct_value
    return pdf_path.stem


def derive_title(design: TrialDesignFacts | None, pdf_path: Path) -> str:
    """Return the extracted official title when present, else the file stem."""
    if design is not None and design.official_title is not None:
        title_value = design.official_title.value.strip()
        if title_value:
            return title_value
    return pdf_path.stem


def all_facets_failed(outcomes: dict[FacetName, FacetOutcome]) -> bool:
    """Return True if outcomes is non-empty and all facet results are None."""
    return bool(outcomes) and all(
        outcome.result is None for outcome in outcomes.values()
    )
