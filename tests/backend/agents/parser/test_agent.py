"""Unit tests for the generic facet extraction engine (LLM mocked)."""

from pydantic import BaseModel

from backend.agents.parser.agent import extract_facet
from backend.agents.parser.logic import (
    ELIGIBILITY_FACET,
    SECTIONS_FACET,
    Facet,
)
from backend.clients.gemini import LlmCallFailedError, ThinkingLevel
from backend.shared.messages import (
    Citation,
    CriterionKind,
    EligibilityCriterion,
    EligibilityExtraction,
    FacetName,
    M11Heading,
    PageText,
    ProtocolSection,
    SectionMap,
)
from tests.conftest import FakeJsonGenerator

PAGES = [
    PageText(
        page_number=1,
        text="Food As Medicine for Diabetes study protocol, version 1.",
    ),
    PageText(
        page_number=2,
        text="Participants must have HbA1c ≥ 8.0% at the screening visit.",
    ),
]
FACET_INSTRUCTIONS = "List every statement about glycemic control."
VERIFIABLE_QUOTE = "HbA1c ≥ 8.0% at the screening visit"
OTHER_VERIFIABLE_QUOTE = "Food As Medicine for Diabetes study protocol"
INVENTED_QUOTE = "HbA1c above 9.5% for six months"
SANITY_MESSAGE = "statement list looks suspicious"


class _Statement(BaseModel):
    text: str
    citation: Citation


class _Statements(BaseModel):
    statements: list[_Statement]


def _statements(*quotes_and_pages: tuple[str, int]) -> _Statements:
    return _Statements(
        statements=[
            _Statement(
                text=f"statement {index}",
                citation=Citation(page_number=page_number, quote=quote),
            )
            for index, (quote, page_number) in enumerate(quotes_and_pages)
        ]
    )


def _verified_flags(result: BaseModel | None) -> list[bool]:
    assert isinstance(result, _Statements)
    return [item.citation.is_verified for item in result.statements]


def _facet(
    sanity_message: str | None = None,
) -> Facet[_Statements]:
    def flag_everything(result: _Statements, page_count: int) -> list[str]:
        return [f"{sanity_message} page_count={page_count}"]

    return Facet(
        name=FacetName.ELIGIBILITY,
        instructions=FACET_INSTRUCTIONS,
        result_model=_Statements,
        thinking_level=ThinkingLevel.HIGH,
        sanity_rules=(flag_everything,) if sanity_message else (),
    )


async def test_verified_facet_needs_one_call() -> None:
    llm = FakeJsonGenerator([_statements((VERIFIABLE_QUOTE, 2))])

    outcome = await extract_facet(_facet(), PAGES, llm)

    assert len(llm.prompts) == 1
    assert _verified_flags(outcome.result) == [True]
    assert outcome.warnings == []


async def test_failed_quote_repaired_in_second_call() -> None:
    llm = FakeJsonGenerator(
        [
            _statements((INVENTED_QUOTE, 2)),
            _statements((VERIFIABLE_QUOTE, 2)),
        ]
    )

    outcome = await extract_facet(_facet(), PAGES, llm)

    assert len(llm.prompts) == 2
    assert INVENTED_QUOTE in llm.prompts[1]
    assert _verified_flags(outcome.result) == [True]
    assert outcome.warnings == []


async def test_unrepairable_quote_stays_unverified_after_two_calls() -> None:
    llm = FakeJsonGenerator(
        [_statements((INVENTED_QUOTE, 2)), _statements((INVENTED_QUOTE, 2))]
    )

    outcome = await extract_facet(_facet(), PAGES, llm)

    assert len(llm.prompts) == 2
    assert _verified_flags(outcome.result) == [False]
    assert any("could not be verified" in w for w in outcome.warnings)


async def test_repair_keeps_result_with_more_verified_citations() -> None:
    first = _statements((VERIFIABLE_QUOTE, 2), (INVENTED_QUOTE, 2))
    worse_repair = _statements((INVENTED_QUOTE, 2), (INVENTED_QUOTE, 1))
    llm = FakeJsonGenerator([first, worse_repair])

    outcome = await extract_facet(_facet(), PAGES, llm)

    assert _verified_flags(outcome.result) == [True, False]
    assert isinstance(outcome.result, _Statements)
    assert outcome.result.statements[0].citation.quote == VERIFIABLE_QUOTE


async def test_repair_is_kept_when_equally_verified() -> None:
    first = _statements((VERIFIABLE_QUOTE, 2), (INVENTED_QUOTE, 2))
    equal_repair = _statements(
        (OTHER_VERIFIABLE_QUOTE, 1), (INVENTED_QUOTE, 1)
    )
    llm = FakeJsonGenerator([first, equal_repair])

    outcome = await extract_facet(_facet(), PAGES, llm)

    assert isinstance(outcome.result, _Statements)
    assert outcome.result.statements[0].citation.quote == (
        OTHER_VERIFIABLE_QUOTE
    )


async def test_facet_llm_failure_becomes_none_with_warning() -> None:
    llm = FakeJsonGenerator(
        [LlmCallFailedError("LLM call failed after 3 attempts")]
    )

    outcome = await extract_facet(_facet(), PAGES, llm)

    assert outcome.result is None
    assert outcome.facet == FacetName.ELIGIBILITY
    assert any("failed after retries" in w for w in outcome.warnings)


async def test_failed_repair_call_keeps_first_result_with_warning() -> None:
    llm = FakeJsonGenerator(
        [
            _statements((VERIFIABLE_QUOTE, 2), (INVENTED_QUOTE, 2)),
            LlmCallFailedError("LLM call failed after 3 attempts"),
        ]
    )

    outcome = await extract_facet(_facet(), PAGES, llm)

    assert _verified_flags(outcome.result) == [True, False]
    assert any("repair failed" in w for w in outcome.warnings)


async def test_page_text_comes_before_instructions_in_prompt() -> None:
    llm = FakeJsonGenerator([_statements((VERIFIABLE_QUOTE, 2))])

    await extract_facet(_facet(), PAGES, llm)

    prompt = llm.prompts[0]
    assert prompt.startswith("=== PAGE 1 ===")
    assert prompt.index(PAGES[1].text) < prompt.index(FACET_INSTRUCTIONS)


async def test_thinking_level_comes_from_facet() -> None:
    llm = FakeJsonGenerator([_statements((VERIFIABLE_QUOTE, 2))])

    await extract_facet(_facet(), PAGES, llm)

    assert llm.thinking_levels == [ThinkingLevel.HIGH]


async def test_sanity_rule_violation_becomes_warning() -> None:
    llm = FakeJsonGenerator([_statements((VERIFIABLE_QUOTE, 2))])

    outcome = await extract_facet(_facet(SANITY_MESSAGE), PAGES, llm)

    assert outcome.warnings == [f"{SANITY_MESSAGE} page_count={len(PAGES)}"]


async def test_normalize_runs_before_sanity_rules() -> None:
    def uppercase_statements(result: _Statements) -> _Statements:
        return _Statements(
            statements=[
                statement.model_copy(update={"text": statement.text.upper()})
                for statement in result.statements
            ]
        )

    def require_uppercase(result: _Statements, page_count: int) -> list[str]:
        if any(not s.text.isupper() for s in result.statements):
            return [f"statements not normalized (pages={page_count})"]
        return []

    facet = Facet(
        name=FacetName.ELIGIBILITY,
        instructions=FACET_INSTRUCTIONS,
        result_model=_Statements,
        thinking_level=ThinkingLevel.HIGH,
        sanity_rules=(require_uppercase,),
        normalize=uppercase_statements,
    )
    llm = FakeJsonGenerator([_statements((VERIFIABLE_QUOTE, 2))])

    outcome = await extract_facet(facet, PAGES, llm)

    assert isinstance(outcome.result, _Statements)
    assert outcome.result.statements[0].text == "STATEMENT 0"
    assert outcome.warnings == []


async def test_eligibility_facet_end_to_end_with_fake_llm() -> None:
    raw_extraction = EligibilityExtraction(
        criteria=[
            EligibilityCriterion(
                criterion_id="a",
                kind=CriterionKind.INCLUSION,
                text="Participants must have HbA1c >= 8.0% at screening.",
                citation=Citation(page_number=2, quote=VERIFIABLE_QUOTE),
            ),
            EligibilityCriterion(
                criterion_id="b",
                kind=CriterionKind.EXCLUSION,
                text="Prior enrollment in the Food As Medicine trial.",
                citation=Citation(page_number=1, quote=OTHER_VERIFIABLE_QUOTE),
            ),
        ]
    )
    llm = FakeJsonGenerator([raw_extraction])

    outcome = await extract_facet(ELIGIBILITY_FACET, PAGES, llm)

    assert isinstance(outcome.result, EligibilityExtraction)
    assert [c.criterion_id for c in outcome.result.criteria] == [
        "IN-01",
        "EX-01",
    ]
    assert [
        c.citation.is_verified
        for c in outcome.result.criteria
        if c.citation is not None
    ] == [True, True]
    assert outcome.warnings == []


async def test_sections_facet_end_to_end_with_fake_llm() -> None:
    raw_sections = SectionMap(
        sections=[
            ProtocolSection(
                heading=M11Heading.TRIAL_POPULATION,
                title="5 TARGET POPULATION AND STUDY SAMPLE",
                start_page=2,
                end_page=2,
                summary="Describes the target diabetes study population.",
                citation=Citation(page_number=2, quote=VERIFIABLE_QUOTE),
            ),
            ProtocolSection(
                heading=M11Heading.PROTOCOL_SUMMARY,
                title="1 PROTOCOL SUMMARY",
                start_page=1,
                end_page=1,
                summary="Summarizes the FAME-D trial protocol.",
                citation=Citation(page_number=1, quote=OTHER_VERIFIABLE_QUOTE),
            ),
        ]
    )
    llm = FakeJsonGenerator([raw_sections])

    outcome = await extract_facet(SECTIONS_FACET, PAGES, llm)

    assert isinstance(outcome.result, SectionMap)
    assert [s.title for s in outcome.result.sections] == [
        "1 PROTOCOL SUMMARY",
        "5 TARGET POPULATION AND STUDY SAMPLE",
    ]
    assert [s.citation.is_verified for s in outcome.result.sections] == [
        True,
        True,
    ]
    assert outcome.warnings == []
