"""The parser's generic, pure engine: prompts, citation walks, assembly.

Nothing here knows about a specific facet; the facets themselves live in
facets.py. No I/O: agent.py does the PDF reading and Gemini calls.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from backend.agents.parser.prompts import (
    COMMON_EXTRACTION_RULES,
    REPAIR_INSTRUCTIONS,
)
from backend.clients.gemini import ThinkingLevel
from backend.shared.citations import make_citation_verifier
from backend.shared.messages import (
    AnalysisPlanExtraction,
    Citation,
    EligibilityExtraction,
    EndpointList,
    EstimandExtraction,
    ExtractionWarning,
    FacetName,
    InterventionExtraction,
    PageText,
    ProtocolDocument,
    SafetyMonitoringExtraction,
    ScheduleOfActivities,
    SectionMap,
    StatisticalAssumptions,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
)
from backend.shared.prompting import (
    INSTRUCTIONS_SEPARATOR,
    format_pages_for_prompt,
)

EMPTY_FACET_WARNING = "facet ran but found no items in the document"

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
    verified = _map_citations(result, make_citation_verifier(pages))
    assert isinstance(verified, type(result))
    return verified


def count_verified(result: BaseModel) -> int:
    """Count the citations in result that passed verification."""
    return sum(
        1 for citation in collect_citations(result) if citation.is_verified
    )


@dataclass(frozen=True)
class CitationStats:
    """How many citations passed verification, across one or more results."""

    verified: int
    total: int

    @property
    def verified_share(self) -> float:
        """Fraction of citations verified; 0.0 when there are none."""
        return self.verified / self.total if self.total else 0.0


def citation_stats(*results: BaseModel | None) -> CitationStats:
    """Count verified citations across results, skipping missing ones."""
    citations = [
        citation
        for result in results
        if result is not None
        for citation in collect_citations(result)
    ]
    verified = sum(1 for citation in citations if citation.is_verified)
    return CitationStats(verified=verified, total=len(citations))


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
        case EstimandExtraction():
            document.estimands = result
            return None
        case InterventionExtraction():
            document.interventions = result
            return None
        case AnalysisPlanExtraction():
            document.analysis = result
            return None
        case SynopsisConsistencyExtraction():
            document.synopsis_check = result
            return None
        case SafetyMonitoringExtraction():
            document.safety_monitoring = result
            return None
        case EligibilityExtraction():
            document.eligibility_criteria = result.criteria
            return list(result.criteria)
        case SectionMap():
            document.sections = result.sections
            document.subsections = result.subsections
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
