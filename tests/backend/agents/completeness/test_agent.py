"""Tests for the completeness agent: trial profile and full check run."""

import pytest

from backend.agents.completeness.agent import (
    check_protocol,
    extract_trial_profile,
)
from backend.agents.completeness.logic import (
    JudgementStatus,
    JudgementVerdict,
    JudgementVerdicts,
    SecondOpinionVerdict,
    SecondOpinionVerdicts,
)
from backend.agents.completeness.rules import (
    ApplicabilityCondition,
    RuleCatalogue,
    RuleDefinition,
)
from backend.clients.gemini import LlmCallFailedError, ThinkingLevel
from backend.shared.messages import (
    AnalysisPlanExtraction,
    CheckMethod,
    Citation,
    CitedValue,
    ControlType,
    DiabetesType,
    Endpoint,
    EndpointKind,
    InterventionType,
    M11Heading,
    PageText,
    ProtocolDocument,
    RuleFamily,
    RuleSeverity,
    RuleStatus,
    SourceTier,
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
    llm = FakeJsonGenerator(
        [_profile_answer(), *(JudgementVerdicts() for _ in range(8))]
    )

    report = await check_protocol(_document(), llm)

    assert report.rules_evaluated == len(report.findings) == 72
    statuses = {finding.status for finding in report.findings}
    assert statuses <= {RuleStatus.NOT_APPLICABLE, RuleStatus.CANNOT_ASSESS}
    type_1_rule = next(f for f in report.findings if f.rule_id == "DM-43")
    assert type_1_rule.status == RuleStatus.NOT_APPLICABLE
    assert report.before.registration_gate.is_partial


def _make_test_catalogue() -> RuleCatalogue:
    return RuleCatalogue(
        rules=(
            RuleDefinition(
                id="DM-45",
                family=RuleFamily.DM,
                severity=RuleSeverity.S1,
                detection=("F",),
                applies_when=(ApplicabilityCondition.DIABETES_TYPE_T1D,),
                needs_inputs=(),
                sections=(M11Heading.ASSESSMENTS_AND_PROCEDURES,),
                check=CheckMethod.DETERMINISTIC,
                title="T1D DKA monitoring",
                flag_if="T1D lacks DKA rules.",
                fix="Add DKA monitoring.",
                source="EMA CPMP/EWP/1080/00 Rev. 2",
                source_tier=SourceTier.FINAL_GUIDANCE,
            ),
            RuleDefinition(
                id="REG-24",
                family=RuleFamily.REG,
                severity=RuleSeverity.S1,
                detection=("F",),
                applies_when=(),
                needs_inputs=(),
                sections=(M11Heading.OBJECTIVES_AND_ESTIMANDS,),
                check=CheckMethod.DETERMINISTIC,
                title="Primary outcome defined",
                flag_if="No primary endpoint.",
                fix="Define primary endpoint.",
                source="FDAAA 801",
                source_tier=SourceTier.LAW,
            ),
            RuleDefinition(
                id="EST-13",
                family=RuleFamily.EST,
                severity=RuleSeverity.S1,
                detection=("F", "J"),
                applies_when=(),
                needs_inputs=(),
                sections=(M11Heading.STATISTICAL_CONSIDERATIONS,),
                check=CheckMethod.JUDGEMENT,
                title="Missing-data imputation",
                flag_if="Missing-data method omitted.",
                fix="Specify imputation.",
                source="ICH E9(R1)",
                source_tier=SourceTier.ICH,
            ),
            RuleDefinition(
                id="EST-01",
                family=RuleFamily.EST,
                severity=RuleSeverity.S1,
                detection=("J",),
                applies_when=(),
                needs_inputs=(),
                sections=(M11Heading.OBJECTIVES_AND_ESTIMANDS,),
                check=CheckMethod.JUDGEMENT,
                title="Primary objective phrasing",
                flag_if="Primary objective is not a treatment effect.",
                fix="Rewrite objective.",
                source="ICH E9(R1)",
                source_tier=SourceTier.ICH,
            ),
            RuleDefinition(
                id="XS-06",
                family=RuleFamily.XS,
                severity=RuleSeverity.S2,
                detection=("X",),
                applies_when=(),
                needs_inputs=(),
                sections=(M11Heading.ASSESSMENTS_AND_PROCEDURES,),
                check=CheckMethod.JUDGEMENT,
                title="SoA matches Section 8",
                flag_if="SoA procedures mismatch Section 8.",
                fix="Align SoA and Section 8.",
                source="ICH M11",
                source_tier=SourceTier.ICH,
            ),
        )
    )


async def test_check_protocol_end_to_end_order_and_statuses() -> None:
    doc = _document().model_copy(
        update={
            "endpoints": [
                Endpoint(
                    kind=EndpointKind.PRIMARY,
                    description="Change from baseline in HbA1c",
                    time_frame="Week 26",
                    citation=Citation(
                        page_number=1, quote=DESIGN_QUOTE, is_verified=True
                    ),
                )
            ],
            "analysis": AnalysisPlanExtraction(missing_data_method=None),
        }
    )
    catalogue = _make_test_catalogue()
    batch_1 = JudgementVerdicts(
        verdicts=[
            JudgementVerdict(
                rule_id="EST-01",
                status=JudgementStatus.FIRED,
                finding="Primary objective is not a treatment effect.",
                evidence=[Citation(page_number=1, quote=DESIGN_QUOTE)],
                confidence=0.90,
            )
        ]
    )
    batch_2 = JudgementVerdicts(
        verdicts=[
            JudgementVerdict(
                rule_id="XS-06",
                status=JudgementStatus.PASSED,
                finding="SoA matches Section 8.",
                evidence=[Citation(page_number=2, quote=PHASE_QUOTE)],
                confidence=0.95,
            )
        ]
    )
    second_opinion = SecondOpinionVerdicts(
        verdicts=[
            SecondOpinionVerdict(
                rule_id="EST-13",
                confirmed=False,
                reason="Imputation is described in Section 10.4.",
                confidence=0.85,
            ),
            SecondOpinionVerdict(
                rule_id="EST-01",
                confirmed=True,
                reason="Objective is vague.",
                confidence=0.75,
            ),
        ]
    )
    llm = FakeJsonGenerator(
        [_profile_answer(), batch_1, batch_2, second_opinion]
    )

    report = await check_protocol(doc, llm, catalogue=catalogue)

    assert [f.rule_id for f in report.findings] == [
        "DM-45",
        "REG-24",
        "EST-13",
        "EST-01",
        "XS-06",
    ]
    by_id = {f.rule_id: f for f in report.findings}
    assert by_id["DM-45"].status == RuleStatus.NOT_APPLICABLE
    assert by_id["REG-24"].status == RuleStatus.PASSED
    assert by_id["EST-13"].status == RuleStatus.CANNOT_ASSESS
    assert by_id["EST-13"].status_reason is not None
    assert "second opinion did not confirm" in by_id["EST-13"].status_reason
    assert by_id["EST-01"].status == RuleStatus.FIRED
    assert by_id["EST-01"].confidence == pytest.approx(0.75)
    assert by_id["XS-06"].status == RuleStatus.PASSED

    # Prompt order: profile (MEDIUM) -> 2 batches (HIGH) -> 2nd opinion (HIGH)
    assert llm.thinking_levels == [
        ThinkingLevel.MEDIUM,
        ThinkingLevel.HIGH,
        ThinkingLevel.HIGH,
        ThinkingLevel.HIGH,
    ]
    assert "TrialProfile" in llm.prompts[0]
    assert "Rules to evaluate:" in llm.prompts[1]
    assert "Rules to evaluate:" in llm.prompts[2]
    assert "Flags to verify:" in llm.prompts[3]


async def test_check_protocol_handles_failed_batch_and_second_opinion() -> (
    None
):
    doc = _document().model_copy(
        update={
            "endpoints": [
                Endpoint(
                    kind=EndpointKind.PRIMARY,
                    description="Change from baseline in HbA1c",
                    time_frame="Week 26",
                    citation=Citation(
                        page_number=1, quote=DESIGN_QUOTE, is_verified=True
                    ),
                )
            ],
            "analysis": AnalysisPlanExtraction(missing_data_method=None),
        }
    )
    catalogue = _make_test_catalogue()
    batch_2 = JudgementVerdicts(
        verdicts=[
            JudgementVerdict(
                rule_id="XS-06",
                status=JudgementStatus.FIRED,
                finding="SoA mismatches Section 8.",
                evidence=[Citation(page_number=2, quote=PHASE_QUOTE)],
                confidence=0.90,
            )
        ]
    )
    llm = FakeJsonGenerator(
        [
            _profile_answer(),
            LlmCallFailedError("batch 1 timeout"),
            batch_2,
            LlmCallFailedError("second opinion down"),
        ]
    )

    report = await check_protocol(doc, llm, catalogue=catalogue)

    by_id = {f.rule_id: f for f in report.findings}
    assert by_id["EST-01"].status == RuleStatus.CANNOT_ASSESS
    assert by_id["XS-06"].status == RuleStatus.FIRED
    assert by_id["XS-06"].confidence == pytest.approx(0.5)
    assert "second opinion unavailable" in by_id["XS-06"].finding
    assert by_id["EST-13"].status == RuleStatus.FIRED
    assert by_id["EST-13"].confidence == pytest.approx(0.5)
