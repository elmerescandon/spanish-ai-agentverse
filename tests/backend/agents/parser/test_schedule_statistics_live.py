"""Live check for SCHEDULE and STATISTICS facets on both demo protocols."""

import asyncio
import logging
from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.agents.parser.agent import extract_facet
from backend.agents.parser.logic import (
    SCHEDULE_FACET,
    STATISTICS_FACET,
    collect_citations,
    count_verified,
)
from backend.clients.gemini import GeminiClient
from backend.clients.pdf_reader import read_pdf_pages
from backend.shared.messages import (
    ScheduleOfActivities,
    StatisticalAssumptions,
)
from tests.conftest import make_live_gemini_client

logger = logging.getLogger(__name__)

FAME_D_PDF_PATH = Path("data/protocols/demo/NCT04828785_protocol.pdf")
CANAGLIFLOZIN_PDF_PATH = Path("data/protocols/demo/NCT03170518_protocol.pdf")
FAME_D_EXPECTED_SAMPLE_SIZE = 200
FAME_D_EXPECTED_DROPOUT_RATE = 0.10
CANAGLIFLOZIN_EXPECTED_ALPHA = 0.05
MIN_EXPECTED_VISITS = 2
MIN_VERIFIED_SHARE = 0.9


def _verified_share(result: BaseModel) -> float:
    citations = collect_citations(result)
    if not citations:
        return 0.0
    return count_verified(result) / len(citations)


async def _extract_schedule_and_statistics(
    pdf_path: Path, llm: GeminiClient
) -> tuple[ScheduleOfActivities, StatisticalAssumptions]:
    pages = read_pdf_pages(pdf_path)
    schedule_outcome, statistics_outcome = await asyncio.gather(
        extract_facet(SCHEDULE_FACET, pages, llm),
        extract_facet(STATISTICS_FACET, pages, llm),
    )

    assert isinstance(schedule_outcome.result, ScheduleOfActivities), (
        f"SCHEDULE facet failed on {pdf_path.name}: "
        f"{schedule_outcome.warnings}"
    )
    assert isinstance(statistics_outcome.result, StatisticalAssumptions), (
        f"STATISTICS facet failed on {pdf_path.name}: "
        f"{statistics_outcome.warnings}"
    )

    schedule = schedule_outcome.result
    statistics = statistics_outcome.result
    schedule_citations = collect_citations(schedule)
    statistics_citations = collect_citations(statistics)
    total_citations = len(schedule_citations) + len(statistics_citations)
    total_verified = count_verified(schedule) + count_verified(statistics)
    overall_share = (
        total_verified / total_citations if total_citations else 0.0
    )

    logger.info(
        "schedule & statistics extracted: pdf=%s visits=%d "
        "verified=%d/%d (%.1f%%) warnings=%s",
        pdf_path.name,
        len(schedule.visits),
        total_verified,
        total_citations,
        overall_share * 100.0,
        schedule_outcome.warnings + statistics_outcome.warnings,
    )

    schedule_share = _verified_share(schedule)
    statistics_share = _verified_share(statistics)
    assert schedule_share >= MIN_VERIFIED_SHARE, (
        f"{pdf_path.name} SCHEDULE verified share {schedule_share:.2%} < "
        f"{MIN_VERIFIED_SHARE:.0%}: {schedule}"
    )
    assert statistics_share >= MIN_VERIFIED_SHARE, (
        f"{pdf_path.name} STATISTICS verified share {statistics_share:.2%} < "
        f"{MIN_VERIFIED_SHARE:.0%}: {statistics}"
    )
    return schedule, statistics


@pytest.mark.live
async def test_schedule_and_statistics_on_both_demo_protocols() -> None:
    for pdf_path in (FAME_D_PDF_PATH, CANAGLIFLOZIN_PDF_PATH):
        if not pdf_path.exists():
            pytest.skip(f"Demo protocol PDF not found at {pdf_path}")

    llm = make_live_gemini_client()

    fame_schedule, fame_stats = await _extract_schedule_and_statistics(
        FAME_D_PDF_PATH, llm
    )
    cana_schedule, cana_stats = await _extract_schedule_and_statistics(
        CANAGLIFLOZIN_PDF_PATH, llm
    )

    assert len(fame_schedule.visits) >= MIN_EXPECTED_VISITS, (
        f"FAME-D schedule returned fewer than {MIN_EXPECTED_VISITS} visits: "
        f"{fame_schedule.visits}"
    )
    assert len(cana_schedule.visits) >= MIN_EXPECTED_VISITS, (
        f"Canagliflozin schedule returned fewer than {MIN_EXPECTED_VISITS} "
        f"visits: {cana_schedule.visits}"
    )

    assert (
        fame_stats.sample_size is not None
        and fame_stats.sample_size.value == FAME_D_EXPECTED_SAMPLE_SIZE
    ), f"FAME-D sample_size != {FAME_D_EXPECTED_SAMPLE_SIZE}: {fame_stats}"

    assert (
        fame_stats.dropout_rate is not None
        and fame_stats.dropout_rate.value
        == pytest.approx(FAME_D_EXPECTED_DROPOUT_RATE)
    ), f"FAME-D dropout_rate != {FAME_D_EXPECTED_DROPOUT_RATE}: {fame_stats}"

    assert (
        cana_stats.alpha is not None
        and cana_stats.alpha.value
        == pytest.approx(CANAGLIFLOZIN_EXPECTED_ALPHA)
    ), f"Canagliflozin alpha != {CANAGLIFLOZIN_EXPECTED_ALPHA}: {cana_stats}"
