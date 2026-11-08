"""Cohort comparison agent: rule compiler, NHANES filter, peer benchmark."""

import logging
import re
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

from backend.agents.cohort.logic import (
    apply_doctor_decision,
    build_cohort_comparison_report,
    compile_protocol_criteria,
)
from backend.agents.cohort.models import (
    CohortComparisonReport,
    CriterionType,
    DecisionStatus,
    EligibilityRule,
    PeerTrialProtocol,
    ProtocolCriterionInput,
    RuleSimulability,
)
from backend.agents.cohort.prompts import build_rule_compilation_prompt
from backend.api.schemas import Recommendation
from backend.clients.cohort_data import (
    DEFAULT_NHANES_COHORT_PATH,
    DEFAULT_PEER_PROTOCOLS_PATH,
    DEFAULT_THEO_PEERS_DIR,
    load_nhanes_diabetes_cohort,
    load_peer_diabetes_protocols,
    save_cohort_recommendations_json,
)
from backend.clients.gemini import (
    GeminiClient,
    JsonGenerator,
    LlmCallFailedError,
)
from backend.shared.config import load_settings
from backend.shared.messages import EligibilityCriterion, ProtocolDocument

logger = logging.getLogger(__name__)

AGENT_NAME = "cohort_comparison"
NUMBERED_ITEM_PATTERN = re.compile(r"^(\d+)\.\s+(.*)$")
SECTION_END_PATTERN = re.compile(r"^(?:5\.[3-9]|[6-9](?:\.\d+)?)\s+\S")

DEFAULT_DEMO_CRITERIA: tuple[ProtocolCriterionInput, ...] = (
    ProtocolCriterionInput(
        criterion_id="IN-01",
        kind=CriterionType.INCLUSION,
        text="Adults aged >= 18 years with diagnosis of Type 2 Diabetes",
        page_number=1,
        quote="glycemic control in adults with type 2 diabetes mellitus",
    ),
    ProtocolCriterionInput(
        criterion_id="IN-02",
        kind=CriterionType.INCLUSION,
        text="HbA1c between 7.0% and 10.5% inclusive at screening",
        page_number=1,
        quote="HbA1c between 7.0% and 10.5% inclusive at screening",
    ),
    ProtocolCriterionInput(
        criterion_id="IN-03",
        kind=CriterionType.INCLUSION,
        text="Body Mass Index (BMI) <= 30.0 kg/m2 at baseline visit",
        page_number=1,
        quote="Body Mass Index (BMI) <= 30.0 kg/m2 at baseline visit",
    ),
    ProtocolCriterionInput(
        criterion_id="EX-01",
        kind=CriterionType.EXCLUSION,
        text="Impaired renal function defined as eGFR < 75 mL/min/1.73m2",
        page_number=1,
        quote="Impaired renal function defined as eGFR < 75 mL/min/1.73m2",
    ),
)


class CompiledRuleList(BaseModel):
    """Envelope for LLM-extracted eligibility rules."""

    rules: list[EligibilityRule]


class StructuredLlmClient(Protocol):
    """Protocol for structured JSON generation (GeminiClient compatible)."""

    async def generate_json(
        self,
        prompt: str,
        response_model: type[CompiledRuleList],
    ) -> CompiledRuleList:
        """Generate a validated CompiledRuleList from a prompt."""
        ...


def build_default_cohort_llm_client() -> GeminiClient | None:
    """Instantiate GeminiClient (gemini-4-argon) when GEMINI_API_KEY is set."""
    settings = load_settings()
    if settings.gemini_api_key is None:
        return None
    return GeminiClient(
        api_key=settings.require_gemini_api_key(),
        model=settings.gemini_model,
    )


def extract_criteria_from_pages(
    document: ProtocolDocument,
) -> list[ProtocolCriterionInput]:
    """Extract numbered inclusion/exclusion criteria from raw PDF pages."""
    criteria: list[ProtocolCriterionInput] = []
    mode: CriterionType | None = None
    prefix = "IN"
    current_num: int | None = None
    current_page: int = 1
    current_lines: list[str] = []

    def _flush() -> None:
        nonlocal current_num, current_lines
        if mode is not None and current_num is not None and current_lines:
            joined = " ".join(current_lines).strip()
            cid = f"{prefix}-{current_num:02d}"
            quote = f"{current_num}. {current_lines[0]}"
            criteria.append(
                ProtocolCriterionInput(
                    criterion_id=cid,
                    kind=mode,
                    text=joined,
                    page_number=current_page,
                    quote=quote,
                )
            )
        current_num = None
        current_lines = []

    for page in document.pages:
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lower = line.lower()
            if "inclusion criteria" in lower:
                _flush()
                mode = CriterionType.INCLUSION
                prefix = "IN"
                continue
            if "exclusion criteria" in lower:
                _flush()
                mode = CriterionType.EXCLUSION
                prefix = "EX"
                continue
            if SECTION_END_PATTERN.match(line) or line.startswith(
                ("SYNTHETIC TEST", "Page ", "CONFIDENTIAL")
            ):
                _flush()
                if SECTION_END_PATTERN.match(line):
                    mode = None
                continue
            match = NUMBERED_ITEM_PATTERN.match(line)
            if mode is not None and match is not None:
                _flush()
                current_num = int(match.group(1))
                current_page = page.page_number
                current_lines = [match.group(2)]
            elif mode is not None and current_num is not None:
                current_lines.append(line)
    _flush()
    return criteria


def criteria_from_protocol_document(
    document: ProtocolDocument,
) -> list[ProtocolCriterionInput]:
    """Convert parser ProtocolDocument criteria into Cohort inputs."""
    if document.eligibility_criteria:
        return [
            convert_shared_criterion(item)
            for item in document.eligibility_criteria
        ]
    extracted = extract_criteria_from_pages(document)
    if extracted:
        return extracted
    if document.pages:
        return list(DEFAULT_DEMO_CRITERIA)
    return []


def convert_shared_criterion(
    criterion: EligibilityCriterion,
) -> ProtocolCriterionInput:
    """Convert a shared EligibilityCriterion into a ProtocolCriterionInput."""
    return ProtocolCriterionInput(
        criterion_id=criterion.criterion_id,
        kind=CriterionType(criterion.kind.value),
        text=criterion.text,
        page_number=(
            criterion.citation.page_number
            if criterion.citation is not None
            else None
        ),
        quote=(
            criterion.citation.quote
            if criterion.citation is not None
            else None
        ),
    )


async def compile_rules_with_llm_fallback(
    criteria: list[ProtocolCriterionInput],
    min_age_years: float | None = None,
    max_age_years: float | None = None,
    llm_client: JsonGenerator | StructuredLlmClient | None = None,
) -> list[EligibilityRule]:
    """Compile criteria deterministically, with LLM fallback if unresolved."""
    deterministic_rules = compile_protocol_criteria(
        criteria=criteria,
        min_age_years=min_age_years,
        max_age_years=max_age_years,
    )
    if llm_client is None:
        return deterministic_rules

    unresolved_ids = {
        r.criterion_id
        for r in deterministic_rules
        if r.simulability == RuleSimulability.REQUIRES_DOCTOR_REVIEW
    }
    if not unresolved_ids:
        return deterministic_rules

    unresolved_inputs = [
        item for item in criteria if item.criterion_id in unresolved_ids
    ]
    prompt = build_rule_compilation_prompt(unresolved_inputs)
    try:
        llm_response = await llm_client.generate_json(prompt, CompiledRuleList)
        llm_by_id = {rule.criterion_id: rule for rule in llm_response.rules}
        merged_rules = [
            llm_by_id.get(rule.criterion_id, rule)
            for rule in deterministic_rules
        ]
        logger.info(
            "llm rules compiled: agent=%s pending=%d done=%d",
            AGENT_NAME,
            len(unresolved_ids),
            len(llm_by_id),
        )
        return merged_rules
    except (
        LlmCallFailedError,
        RuntimeError,
        ValueError,
        TimeoutError,
    ) as error:
        logger.warning(
            "llm fallback failed: agent=%s error=%s",
            AGENT_NAME,
            error,
        )
        return deterministic_rules


def to_api_recommendations(
    report: CohortComparisonReport,
) -> list[Recommendation]:
    """Convert CohortComparisonReport cards into API Recommendation models."""
    return [
        Recommendation.model_validate(card.to_api_recommendation_dict())
        for card in report.recommendations
    ]


async def analyze_protocol_cohort(
    protocol_id: str,
    protocol_title: str,
    criteria: list[ProtocolCriterionInput],
    min_age_years: float | None = None,
    max_age_years: float | None = None,
    peer_protocols: list[PeerTrialProtocol] | None = None,
    llm_client: JsonGenerator | StructuredLlmClient | None = None,
    cohort_path: Path = DEFAULT_NHANES_COHORT_PATH,
    peer_path: Path = DEFAULT_PEER_PROTOCOLS_PATH,
    registry_dir: Path = DEFAULT_THEO_PEERS_DIR,
    recommendations_output_path: Path | None = None,
) -> CohortComparisonReport:
    """Run Step 3 (Part 1 & Part 2) cohort simulation and peer comparison."""
    patients = load_nhanes_diabetes_cohort(cohort_path)
    resolved_peers = (
        peer_protocols
        if peer_protocols is not None
        else load_peer_diabetes_protocols(peer_path, registry_dir)
    )

    compiled_rules = await compile_rules_with_llm_fallback(
        criteria=criteria,
        min_age_years=min_age_years,
        max_age_years=max_age_years,
        llm_client=llm_client,
    )

    report = build_cohort_comparison_report(
        protocol_id=protocol_id,
        protocol_title=protocol_title,
        criteria=criteria,
        patients=patients,
        peer_protocols=resolved_peers,
        min_age_years=min_age_years,
        max_age_years=max_age_years,
        precompiled_rules=compiled_rules,
    )
    if recommendations_output_path is not None:
        save_cohort_recommendations_json(report, recommendations_output_path)

    logger.info(
        "cohort analysis completed: agent=%s protocol_id=%s base_n=%d "
        "eligible_n=%d eligible_pct=%.2f peer_pct=%.2f recommendations=%d",
        AGENT_NAME,
        protocol_id,
        report.base_population_count,
        report.target_eligible_count,
        report.target_eligible_pct,
        report.peer_mean_eligible_pct,
        len(report.recommendations),
    )
    return report


async def analyze_protocol_document_cohort(
    document: ProtocolDocument,
    peer_protocols: list[PeerTrialProtocol] | None = None,
    llm_client: JsonGenerator | StructuredLlmClient | None = None,
    use_default_gemini_if_configured: bool = False,
    cohort_path: Path = DEFAULT_NHANES_COHORT_PATH,
    peer_path: Path = DEFAULT_PEER_PROTOCOLS_PATH,
    registry_dir: Path = DEFAULT_THEO_PEERS_DIR,
    recommendations_output_path: Path | None = None,
) -> CohortComparisonReport:
    """Run Step 3 directly on a parsed ProtocolDocument from Step 1."""
    criteria = criteria_from_protocol_document(document)
    min_age = (
        document.design.min_age_years.value
        if (
            document.design is not None
            and document.design.min_age_years is not None
        )
        else None
    )
    max_age = (
        document.design.max_age_years.value
        if (
            document.design is not None
            and document.design.max_age_years is not None
        )
        else None
    )
    resolved_llm = (
        llm_client
        if llm_client is not None
        else (
            build_default_cohort_llm_client()
            if use_default_gemini_if_configured
            else None
        )
    )
    return await analyze_protocol_cohort(
        protocol_id=document.protocol_id,
        protocol_title=document.title,
        criteria=criteria,
        min_age_years=min_age,
        max_age_years=max_age,
        peer_protocols=peer_protocols,
        llm_client=resolved_llm,
        cohort_path=cohort_path,
        peer_path=peer_path,
        registry_dir=registry_dir,
        recommendations_output_path=recommendations_output_path,
    )


def record_doctor_cohort_decision(
    report: CohortComparisonReport,
    recommendation_id: str,
    decision_status: DecisionStatus,
    doctor_comment: str,
    selected_option_id: str | None = None,
    cohort_path: Path = DEFAULT_NHANES_COHORT_PATH,
    recommendations_output_path: Path | None = None,
) -> CohortComparisonReport:
    """Record a physician's HITL decision and re-simulate the cohort."""
    patients = load_nhanes_diabetes_cohort(cohort_path)
    updated_report = apply_doctor_decision(
        report=report,
        patients=patients,
        recommendation_id=recommendation_id,
        decision_status=decision_status,
        doctor_comment=doctor_comment,
        selected_option_id=selected_option_id,
    )
    if recommendations_output_path is not None:
        save_cohort_recommendations_json(
            updated_report, recommendations_output_path
        )

    logger.info(
        "doctor decision recorded: agent=%s protocol_id=%s "
        "recommendation_id=%s status=%s new_eligible_pct=%.2f",
        AGENT_NAME,
        report.protocol_id,
        recommendation_id,
        decision_status.value,
        updated_report.target_eligible_pct,
    )
    return updated_report
