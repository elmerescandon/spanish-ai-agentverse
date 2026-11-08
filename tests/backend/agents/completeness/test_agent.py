"""Tests for the completeness agent: trial profile and full check run."""

from backend.agents.completeness.agent import (
    check_protocol,
    extract_trial_profile,
)
from backend.clients.gemini import LlmCallFailedError
from backend.shared.messages import (
    Citation,
    CitedValue,
    ControlType,
    DiabetesType,
    InterventionType,
    PageText,
    ProtocolDocument,
    RuleStatus,
    TrialDesignFacts,
    TrialPhase,
    TrialProfile,
)
from tests.conftest import FakeJsonGenerator

DESIGN_QUOTE = "a randomized trial of medically tailored meals"
POPULATION_QUOTE = "adults with type 2 diabetes mellitus"
PHASE_QUOTE = "single-site, open-label, Phase II trial"
INVENTED_QUOTE = "a double-blind placebo-controlled insulin study"


def _document(design: TrialDesignFacts | None = None) -> ProtocolDocument:
    pages = [
        PageText(
            page_number=1,
            text=f"This is {DESIGN_QUOTE} for {POPULATION_QUOTE}.",
        ),
        PageText(page_number=2, text=f"The {PHASE_QUOTE} runs 12 months."),
    ]
    return ProtocolDocument(
        protocol_id="NCT04828785",
        title="Example protocol",
        page_count=len(pages),
        pages=pages,
        design=design,
    )


def _cited[ValueT](value: ValueT, quote: str, page: int) -> CitedValue[ValueT]:
    return CitedValue[ValueT](
        value=value, citation=Citation(page_number=page, quote=quote)
    )


def _profile_answer() -> TrialProfile:
    return TrialProfile(
        intervention_type=_cited(InterventionType.BEHAVIORAL, DESIGN_QUOTE, 1),
        diabetes_type=_cited(DiabetesType.T2D, POPULATION_QUOTE, 1),
        control_type=_cited(ControlType.PLACEBO, INVENTED_QUOTE, 1),
        phase=_cited(TrialPhase.PHASE3, INVENTED_QUOTE, 2),
    )


async def test_profile_keeps_only_facts_whose_quotes_verify() -> None:
    llm = FakeJsonGenerator([_profile_answer()])

    profile = await extract_trial_profile(_document(), llm)

    assert profile.intervention_type is not None
    assert profile.intervention_type.value == InterventionType.BEHAVIORAL
    assert profile.intervention_type.citation.is_verified
    assert profile.diabetes_type is not None
    assert profile.control_type is None  # invented quote: dropped


async def test_profile_phase_comes_from_the_parsed_design_facts() -> None:
    design = TrialDesignFacts(phase=_cited(TrialPhase.PHASE2, PHASE_QUOTE, 2))
    llm = FakeJsonGenerator([_profile_answer()])

    profile = await extract_trial_profile(_document(design), llm)

    assert profile.phase is not None
    assert profile.phase.value == TrialPhase.PHASE2


async def test_profile_prompt_lists_allowed_values_and_page_text() -> None:
    llm = FakeJsonGenerator([_profile_answer()])

    await extract_trial_profile(_document(), llm)

    prompt = llm.prompts[0]
    assert prompt.startswith("=== PAGE 1 ===")
    assert '"BEHAVIORAL"' in prompt
    assert '"GLP1_RECEPTOR_AGONIST"' in prompt


async def test_failed_profile_call_returns_an_empty_profile() -> None:
    llm = FakeJsonGenerator([LlmCallFailedError("LLM down")])

    profile = await extract_trial_profile(_document(), llm)

    assert profile == TrialProfile()


async def test_check_protocol_returns_one_finding_per_catalogue_rule() -> None:
    llm = FakeJsonGenerator([_profile_answer()])

    report = await check_protocol(_document(), llm)

    assert report.rules_evaluated == len(report.findings) == 72
    statuses = {finding.status for finding in report.findings}
    assert statuses <= {RuleStatus.NOT_APPLICABLE, RuleStatus.CANNOT_ASSESS}
    type_1_rule = next(f for f in report.findings if f.rule_id == "DM-43")
    assert type_1_rule.status == RuleStatus.NOT_APPLICABLE
    assert report.before.registration_gate.is_partial
