"""The parser's facets: what to extract, how to tidy it, how to check it.

Each facet is data (instructions, result schema, thinking level, sanity
rules, optional normalizer). The generic engine in logic.py and agent.py
runs any facet, so adding a key point to extract only touches this file,
prompts.py and messages.py.
"""

from collections.abc import Callable

from pydantic import BaseModel

from backend.agents.parser.logic import Facet, SanityRule
from backend.agents.parser.prompts import (
    ANALYSIS_INSTRUCTIONS,
    DESIGN_INSTRUCTIONS,
    ELIGIBILITY_INSTRUCTIONS,
    ENDPOINTS_INSTRUCTIONS,
    ESTIMANDS_INSTRUCTIONS,
    INTERVENTIONS_INSTRUCTIONS,
    SAFETY_MONITORING_INSTRUCTIONS,
    SCHEDULE_INSTRUCTIONS,
    SECTIONS_INSTRUCTIONS,
    STATISTICS_INSTRUCTIONS,
    SYNOPSIS_CHECK_INSTRUCTIONS,
)
from backend.clients.gemini import ThinkingLevel
from backend.shared.messages import (
    AnalysisPlanExtraction,
    CriterionKind,
    EligibilityCriterion,
    EligibilityExtraction,
    EndpointKind,
    EndpointList,
    EstimandExtraction,
    FacetName,
    InterventionExtraction,
    SafetyMonitoringExtraction,
    ScheduleOfActivities,
    SectionMap,
    StatisticalAssumptions,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
)

INCLUSION_ID_PREFIX = "IN"
EXCLUSION_ID_PREFIX = "EX"
MIN_ARM_COUNT = 1


def cited_value_rule[ResultT: BaseModel](
    result_model: type[ResultT],
    field_name: str,
    is_valid: Callable[[float], bool],
    expectation: str,
) -> SanityRule[ResultT]:
    """Build a sanity rule for one optional CitedValue field.

    The rule passes when the field is absent or its value is valid, and
    otherwise warns "<field> (<value>) must be <expectation>".

    Raises:
        ValueError: field_name is not a field of result_model, so a typo
            fails at import time instead of silently never checking.
    """
    if field_name not in result_model.model_fields:
        raise ValueError(
            f"expected a field of {result_model.__name__}, got {field_name!r}"
        )

    def check(result: ResultT, _page_count: int) -> list[str]:
        cited = getattr(result, field_name)
        if cited is None or is_valid(cited.value):
            return []
        return [f"{field_name} ({cited.value}) must be {expectation}"]

    return check


def _is_positive(value: float) -> bool:
    return value > 0


def _is_strict_fraction(value: float) -> bool:
    return 0.0 < value < 1.0


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


def sort_sections(section_map: SectionMap) -> SectionMap:
    """Order protocol sections and subsections by page and identifier."""
    ordered_sections = sorted(
        section_map.sections,
        key=lambda section: (section.start_page, section.title),
    )
    ordered_subsections = sorted(
        section_map.subsections,
        key=lambda sub: (sub.page_number, sub.number),
    )
    return section_map.model_copy(
        update={
            "sections": ordered_sections,
            "subsections": ordered_subsections,
        }
    )


def sort_visits(schedule: ScheduleOfActivities) -> ScheduleOfActivities:
    """Order scheduled visits by study_day, keeping unknown days last."""
    ordered = sorted(
        schedule.visits,
        key=lambda visit: (visit.study_day is None, visit.study_day or 0),
    )
    return schedule.model_copy(update={"visits": ordered})


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
    for sub in section_map.subsections:
        if not (1 <= sub.page_number <= page_count):
            message = (
                f"subsection '{sub.number} {sub.title}' has invalid page "
                f"{sub.page_number} (document has {page_count} pages)"
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


def _check_endpoint_scale_ranges(
    endpoint_list: EndpointList, _page_count: int
) -> list[str]:
    warnings: list[str] = []
    for endpoint in endpoint_list.endpoints:
        if endpoint.scale_min is None or endpoint.scale_max is None:
            continue
        low = endpoint.scale_min.value
        high = endpoint.scale_max.value
        if low >= high:
            scale_label = (
                endpoint.scale_name.value
                if endpoint.scale_name is not None
                else endpoint.description
            )
            warnings.append(
                f"endpoint scale '{scale_label}' has scale_min ({low}) >= "
                f"scale_max ({high})"
            )
    return warnings


def _check_has_visits(
    schedule: ScheduleOfActivities, _page_count: int
) -> list[str]:
    if schedule.visits:
        return []
    return ["schedule of activities contains no visits"]


def _check_visits_have_procedures(
    schedule: ScheduleOfActivities, _page_count: int
) -> list[str]:
    return [
        f"visit '{visit.visit_name}' has no procedures"
        for visit in schedule.visits
        if not visit.procedures
    ]


def _check_has_intervention_arm(
    interventions: InterventionExtraction, _page_count: int
) -> list[str]:
    if interventions.arms:
        return []
    return ["interventions contain no arms"]


def _check_hypoglycemia_level_order(
    safety: SafetyMonitoringExtraction, _page_count: int
) -> list[str]:
    if (
        safety.level_1_glucose_mg_dl is None
        or safety.level_2_glucose_mg_dl is None
    ):
        return []
    level_1 = safety.level_1_glucose_mg_dl.value
    level_2 = safety.level_2_glucose_mg_dl.value
    if level_2 >= level_1:
        message = (
            f"level_2_glucose_mg_dl ({level_2}) must be less than "
            f"level_1_glucose_mg_dl ({level_1})"
        )
        return [message]
    return []


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
        cited_value_rule(
            TrialDesignFacts, "target_enrollment", _is_positive, "positive"
        ),
        cited_value_rule(
            TrialDesignFacts,
            "arm_count",
            lambda arms: arms >= MIN_ARM_COUNT,
            f"at least {MIN_ARM_COUNT}",
        ),
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
    sanity_rules=(_check_has_primary_endpoint, _check_endpoint_scale_ranges),
)

SCHEDULE_FACET: Facet[ScheduleOfActivities] = Facet(
    name=FacetName.SCHEDULE,
    instructions=SCHEDULE_INSTRUCTIONS,
    result_model=ScheduleOfActivities,
    thinking_level=ThinkingLevel.HIGH,
    sanity_rules=(_check_has_visits, _check_visits_have_procedures),
    normalize=sort_visits,
)

STATISTICS_FACET: Facet[StatisticalAssumptions] = Facet(
    name=FacetName.STATISTICS,
    instructions=STATISTICS_INSTRUCTIONS,
    result_model=StatisticalAssumptions,
    thinking_level=ThinkingLevel.MEDIUM,
    sanity_rules=(
        cited_value_rule(
            StatisticalAssumptions, "sample_size", _is_positive, "positive"
        ),
        cited_value_rule(
            StatisticalAssumptions, "power", _is_strict_fraction, "in (0, 1)"
        ),
        cited_value_rule(
            StatisticalAssumptions, "alpha", _is_strict_fraction, "in (0, 1)"
        ),
        cited_value_rule(
            StatisticalAssumptions,
            "dropout_rate",
            lambda rate: 0.0 <= rate < 1.0,
            "in [0, 1)",
        ),
        cited_value_rule(
            StatisticalAssumptions,
            "standard_deviation",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            StatisticalAssumptions,
            "allocation_ratio",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            StatisticalAssumptions,
            "non_inferiority_margin",
            _is_positive,
            "positive",
        ),
    ),
)

ESTIMANDS_FACET: Facet[EstimandExtraction] = Facet(
    name=FacetName.ESTIMANDS,
    instructions=ESTIMANDS_INSTRUCTIONS,
    result_model=EstimandExtraction,
    thinking_level=ThinkingLevel.MEDIUM,
)

INTERVENTIONS_FACET: Facet[InterventionExtraction] = Facet(
    name=FacetName.INTERVENTIONS,
    instructions=INTERVENTIONS_INSTRUCTIONS,
    result_model=InterventionExtraction,
    thinking_level=ThinkingLevel.MEDIUM,
    sanity_rules=(
        _check_has_intervention_arm,
        cited_value_rule(
            InterventionExtraction,
            "background_therapy_stable_weeks",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            InterventionExtraction,
            "prior_washout_weeks",
            _is_positive,
            "positive",
        ),
    ),
)

ANALYSIS_FACET: Facet[AnalysisPlanExtraction] = Facet(
    name=FacetName.ANALYSIS,
    instructions=ANALYSIS_INSTRUCTIONS,
    result_model=AnalysisPlanExtraction,
    thinking_level=ThinkingLevel.MEDIUM,
)

SYNOPSIS_CHECK_FACET: Facet[SynopsisConsistencyExtraction] = Facet(
    name=FacetName.SYNOPSIS_CHECK,
    instructions=SYNOPSIS_CHECK_INSTRUCTIONS,
    result_model=SynopsisConsistencyExtraction,
    thinking_level=ThinkingLevel.MEDIUM,
    sanity_rules=(
        cited_value_rule(
            SynopsisConsistencyExtraction,
            "synopsis_enrollment",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            SynopsisConsistencyExtraction,
            "synopsis_arm_count",
            lambda arms: arms >= MIN_ARM_COUNT,
            f"at least {MIN_ARM_COUNT}",
        ),
        cited_value_rule(
            SynopsisConsistencyExtraction,
            "synopsis_treatment_duration_weeks",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            SynopsisConsistencyExtraction,
            "body_treatment_duration_weeks",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            SynopsisConsistencyExtraction,
            "assessments_retention_years",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            SynopsisConsistencyExtraction,
            "icf_retention_years",
            _is_positive,
            "positive",
        ),
    ),
)

SAFETY_MONITORING_FACET: Facet[SafetyMonitoringExtraction] = Facet(
    name=FacetName.SAFETY_MONITORING,
    instructions=SAFETY_MONITORING_INSTRUCTIONS,
    result_model=SafetyMonitoringExtraction,
    thinking_level=ThinkingLevel.MEDIUM,
    sanity_rules=(
        cited_value_rule(
            SafetyMonitoringExtraction,
            "level_1_glucose_mg_dl",
            _is_positive,
            "positive",
        ),
        cited_value_rule(
            SafetyMonitoringExtraction,
            "level_2_glucose_mg_dl",
            _is_positive,
            "positive",
        ),
        _check_hypoglycemia_level_order,
    ),
)

type AnyFacet = (
    Facet[EligibilityExtraction]
    | Facet[TrialDesignFacts]
    | Facet[SectionMap]
    | Facet[EndpointList]
    | Facet[ScheduleOfActivities]
    | Facet[StatisticalAssumptions]
    | Facet[EstimandExtraction]
    | Facet[InterventionExtraction]
    | Facet[AnalysisPlanExtraction]
    | Facet[SynopsisConsistencyExtraction]
    | Facet[SafetyMonitoringExtraction]
)

FACETS: tuple[AnyFacet, ...] = (
    ELIGIBILITY_FACET,
    DESIGN_FACET,
    SECTIONS_FACET,
    ENDPOINTS_FACET,
    SCHEDULE_FACET,
    STATISTICS_FACET,
    ESTIMANDS_FACET,
    INTERVENTIONS_FACET,
    ANALYSIS_FACET,
    SYNOPSIS_CHECK_FACET,
    SAFETY_MONITORING_FACET,
)
