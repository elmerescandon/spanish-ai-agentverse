"""Parser agent: turns a protocol PDF into a citation-verified document.

Other parts of the backend call parse_protocol() directly.
"""

import asyncio
import hashlib
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from pydantic import BaseModel

from backend.agents.parser.facets import (
    ELIGIBILITY_FACET,
    FACETS,
    AnyFacet,
)
from backend.agents.parser.logic import (
    Facet,
    FacetOutcome,
    all_facets_failed,
    assemble_document,
    build_facet_prompt,
    build_repair_prompt,
    count_verified,
    derive_protocol_id,
    derive_title,
    unverified_citations,
    verify_result,
)
from backend.clients.gemini import JsonGenerator, LlmCallFailedError
from backend.clients.pdf_reader import read_pdf_pages
from backend.shared.messages import (
    EligibilityCriterion,
    EligibilityExtraction,
    FacetName,
    PageText,
    ProtocolDocument,
    TrialDesignFacts,
)
from backend.shared.task_cache import SharedTaskCache

logger = logging.getLogger(__name__)

AGENT_NAME = "parser"
MAX_CITATION_REPAIR_ROUNDS = 1  # one re-ask; a third call rarely helps
HASH_CHUNK_BYTES = 1024 * 1024  # stream large PDFs while hashing


class AllFacetsFailedError(RuntimeError):
    """Raised when every requested parser facet failed to extract a result."""


async def extract_facet[ResultT: BaseModel](
    facet: Facet[ResultT], pages: list[PageText], llm: JsonGenerator
) -> FacetOutcome:
    """Extract one facet, verify its citations and run its sanity rules.

    Never raises for LLM failures: a facet that can't be extracted returns
    result=None with a warning, so one facet can't fail the whole parse.
    """
    prompt = build_facet_prompt(facet.instructions, pages)
    try:
        raw_result = await llm.generate_json(
            prompt, facet.result_model, facet.thinking_level
        )
    except LlmCallFailedError as error:
        logger.warning(
            "facet extraction failed: agent=%s facet=%s error=%s",
            AGENT_NAME,
            facet.name,
            error,
        )
        return FacetOutcome(
            facet=facet.name,
            result=None,
            warnings=[f"facet failed after retries: {error}"],
        )

    best_result = verify_result(raw_result, pages)
    warnings: list[str] = []
    for _ in range(MAX_CITATION_REPAIR_ROUNDS):
        failed = unverified_citations(best_result)
        if not failed:
            break
        try:
            repaired_raw = await llm.generate_json(
                build_repair_prompt(prompt, failed),
                facet.result_model,
                facet.thinking_level,
            )
        except LlmCallFailedError as error:
            warnings.append(f"citation repair failed: {error}")
            break
        repaired = verify_result(repaired_raw, pages)
        if count_verified(repaired) >= count_verified(best_result):
            best_result = repaired

    still_failed = unverified_citations(best_result)
    if still_failed:
        warnings.append(
            f"{len(still_failed)} citation(s) could not be verified "
            "against the PDF and are flagged is_verified=False"
        )
    if facet.normalize is not None:
        best_result = facet.normalize(best_result)
    page_count = len(pages)
    for rule in facet.sanity_rules:
        warnings.extend(rule(best_result, page_count))

    logger.info(
        "facet extracted: agent=%s facet=%s verified=%d unverified=%d "
        "warnings=%d",
        AGENT_NAME,
        facet.name,
        count_verified(best_result),
        len(still_failed),
        len(warnings),
    )
    return FacetOutcome(
        facet=facet.name, result=best_result, warnings=warnings
    )


async def parse_protocol(
    pdf_path: Path,
    llm: JsonGenerator,
    facets: Sequence[AnyFacet] = FACETS,
) -> ProtocolDocument:
    """Parse a protocol PDF across all facets into a ProtocolDocument.

    One failed facet leaves its field None with a warning; the call only
    fails as a whole when it can't produce a document at all.

    Raises:
        UnreadablePdfError: the file is scanned, corrupt or not a PDF.
        ValueError: the PDF has more pages than the parser accepts.
        OSError: the file doesn't exist or can't be read.
        AllFacetsFailedError: every facet failed (e.g. Gemini is down).
    """
    pages = await asyncio.to_thread(read_pdf_pages, pdf_path)
    outcome_list = await asyncio.gather(
        # Each facet has its own result type; mypy can't infer one type
        # for the mixed tuple, and every result is only used as a
        # BaseModel from here on, so widening is safe.
        *(
            extract_facet(cast(Facet[BaseModel], facet), pages, llm)
            for facet in facets
        )
    )
    outcomes = {outcome.facet: outcome for outcome in outcome_list}
    if all_facets_failed(outcomes):
        raise AllFacetsFailedError(
            f"all {len(outcomes)} parser facet(s) failed for {pdf_path}"
        )

    design_outcome = outcomes.get(FacetName.DESIGN)
    design = (
        design_outcome.result
        if design_outcome is not None
        and isinstance(design_outcome.result, TrialDesignFacts)
        else None
    )
    protocol_id = derive_protocol_id(design, pdf_path)
    title = derive_title(design, pdf_path)
    return assemble_document(protocol_id, title, pages, outcomes)


async def extract_eligibility_criteria(
    eligibility_text: str, llm: JsonGenerator
) -> list[EligibilityCriterion]:
    """Extract uncited eligibility criteria from raw peer-trial text.

    Quotes are still checked against the text; citations are then
    dropped because a page number is meaningless without a PDF.

    Raises:
        AllFacetsFailedError: the eligibility facet failed.
    """
    pages = [PageText(page_number=1, text=eligibility_text)]
    outcome = await extract_facet(ELIGIBILITY_FACET, pages, llm)
    if outcome.result is None or not isinstance(
        outcome.result, EligibilityExtraction
    ):
        raise AllFacetsFailedError(
            "ELIGIBILITY facet failed on peer-trial text"
        )
    return [
        criterion.model_copy(update={"citation": None})
        for criterion in outcome.result.criteria
    ]


def _hash_file_contents(pdf_path: Path) -> str:
    """Return the SHA-256 hex digest of a file's bytes."""
    digest = hashlib.sha256()
    with pdf_path.open("rb") as pdf_file:
        while chunk := pdf_file.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


class CachedProtocolParser:
    """Parses each distinct PDF once and shares the result.

    PDFs are keyed by a hash of their bytes, so a renamed copy of the same
    file is still a cache hit (its ID and title come from the first parse).
    Requests for a PDF that is already being parsed wait for that parse
    instead of starting another. Failed parses are forgotten so a retry
    really re-parses. The cache lives in memory for this process only.
    """

    def __init__(
        self, llm: JsonGenerator, facets: Sequence[AnyFacet] = FACETS
    ) -> None:
        self._llm = llm
        self._facets = facets
        self._parses = SharedTaskCache[ProtocolDocument]("parse")

    async def parse(self, pdf_path: Path) -> ProtocolDocument:
        """Return the parsed document, parsing only on the first request.

        Each caller gets its own deep copy, so one review editing its
        document can't change another's.

        Raises:
            The same errors as parse_protocol (UnreadablePdfError,
            ValueError, OSError, AllFacetsFailedError).
        """
        content_hash = await asyncio.to_thread(_hash_file_contents, pdf_path)
        document = await self._parses.get_or_run(
            content_hash,
            lambda: parse_protocol(pdf_path, self._llm, self._facets),
        )
        return document.model_copy(deep=True)
