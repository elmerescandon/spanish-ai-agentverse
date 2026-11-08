"""Tests for reading trials' lab limits with the LLM, with caching."""

from pathlib import Path

from backend.agents.protocol_comparison.agent import read_lab_limits
from backend.agents.protocol_comparison.dimensions import DimensionId
from backend.agents.protocol_comparison.eligibility import (
    ComparisonOperator,
    CriterionScope,
    LabLimitReply,
    LabPredicate,
    LabVariable,
    ReadingStatus,
)
from backend.agents.protocol_comparison.peer_store import PeerStore
from backend.clients.gemini import LlmCallFailedError
from tests.backend.agents.protocol_comparison.builders import make_study
from tests.conftest import FakeJsonGenerator

CRITERIA = "Exclusion Criteria:\n\n1. ALT \\> 3 x ULN at screening\n"
ALT_REPLY = LabLimitReply(
    predicates=[
        LabPredicate(
            variable=LabVariable.ALT,
            operator=ComparisonOperator.GREATER,
            value=3,
            unit="x ULN",
            scope=CriterionScope.EXCLUSION,
            source_text="ALT > 3 x ULN",
        )
    ]
)


async def test_reads_limits_once_then_reuses_the_saved_reply(
    tmp_path: Path,
) -> None:
    store = PeerStore(tmp_path)
    study = make_study(nct_id="NCT00000001", eligibility_criteria=CRITERIA)
    first_llm = FakeJsonGenerator([ALT_REPLY])

    [first] = await read_lab_limits([study], first_llm, store)
    [second] = await read_lab_limits([study], FakeJsonGenerator([]), store)

    assert first.values[DimensionId.ALT_AST_LIMIT].value == 3.0
    assert second.values == first.values
    assert len(first_llm.prompts) == 1


async def test_changed_text_is_read_again(tmp_path: Path) -> None:
    store = PeerStore(tmp_path)
    old = make_study(nct_id="NCT00000001", eligibility_criteria=CRITERIA)
    new = make_study(
        nct_id="NCT00000001", eligibility_criteria=CRITERIA + "2. Other\n"
    )
    await read_lab_limits([old], FakeJsonGenerator([ALT_REPLY]), store)
    llm = FakeJsonGenerator([ALT_REPLY])

    await read_lab_limits([new], llm, store)

    assert len(llm.prompts) == 1


async def test_failed_llm_call_gives_an_empty_failed_reading(
    tmp_path: Path,
) -> None:
    study = make_study(eligibility_criteria=CRITERIA)
    llm = FakeJsonGenerator([LlmCallFailedError("retries exhausted")])

    [reading] = await read_lab_limits([study], llm, PeerStore(tmp_path))

    assert reading.status == ReadingStatus.FAILED
    assert reading.values == {}


async def test_failed_reading_is_not_cached(tmp_path: Path) -> None:
    store = PeerStore(tmp_path)
    study = make_study(eligibility_criteria=CRITERIA)
    failing = FakeJsonGenerator([LlmCallFailedError("retries exhausted")])
    await read_lab_limits([study], failing, store)
    llm = FakeJsonGenerator([ALT_REPLY])

    [reading] = await read_lab_limits([study], llm, store)

    assert reading.status == ReadingStatus.READ


async def test_trial_without_criteria_text_makes_no_llm_call(
    tmp_path: Path,
) -> None:
    llm = FakeJsonGenerator([])

    [reading] = await read_lab_limits([make_study()], llm, PeerStore(tmp_path))

    assert reading.status == ReadingStatus.NO_TEXT
    assert llm.prompts == []


async def test_the_llm_sees_the_text_without_registry_escapes(
    tmp_path: Path,
) -> None:
    llm = FakeJsonGenerator([ALT_REPLY])

    await read_lab_limits(
        [make_study(eligibility_criteria=CRITERIA)], llm, PeerStore(tmp_path)
    )

    assert "ALT > 3 x ULN at screening" in llm.prompts[0]


async def test_without_an_llm_only_cached_readings_are_used(
    tmp_path: Path,
) -> None:
    store = PeerStore(tmp_path)
    cached = make_study(nct_id="NCT00000001", eligibility_criteria=CRITERIA)
    unread = make_study(nct_id="NCT00000002", eligibility_criteria=CRITERIA)
    await read_lab_limits([cached], FakeJsonGenerator([ALT_REPLY]), store)

    first, second = await read_lab_limits([cached, unread], None, store)

    assert first.values[DimensionId.ALT_AST_LIMIT].value == 3.0
    assert second.status == ReadingStatus.NOT_READ
    assert second.values == {}
