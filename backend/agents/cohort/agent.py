"""Cohort comparison agent: rule compiler, NHANES filter, peer benchmark."""

import logging
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


def criteria_from_protocol_document(
    document: ProtocolDocument,
) -> list[ProtocolCriterionInput]:
    """Convert parser ProtocolDocument criteria into Cohort inputs."""
    if document.eligibility_criteria is None:
        return []
    return [
        convert_shared_criterion(item)
        for item in document.eligibility_criteria
    ]


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
