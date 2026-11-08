"""Compact factories for synthetic ProtocolDocuments in completeness tests."""

from backend.shared.messages import (
    AllocationType,
    AnalysisPlanExtraction,
    AnalysisSetItem,
    AnalysisSetType,
    Citation,
    CitedValue,
    CommitteeItem,
    CommitteeType,
    ControlType,
    DiabetesType,
    DrugClass,
    EligibilityCriterion,
    Endpoint,
    EndpointKind,
    EpochType,
    Estimand,
    EstimandExtraction,
    EstimandStrategy,
    IntercurrentEvent,
    IntercurrentEventType,
    InterventionArm,
    InterventionExtraction,
    InterventionType,
    M11Heading,
    MaskingType,
    PageText,
    ProtocolDocument,
    ProtocolSection,
    ProtocolSubsection,
    SafetyMonitoringExtraction,
    ScaleDirection,
    ScheduledVisit,
    StatisticalAssumptions,
    StratificationFactorItem,
    StratificationFactorType,
    SubgroupDimension,
    SubgroupItem,
    SynopsisConsistencyExtraction,
    TrialDesignFacts,
    TrialEpoch,
    TrialPhase,
    TrialProfile,
)

DEFAULT_QUOTE = "Verbatim protocol text supporting the extracted value."


def make_citation(
    quote: str = DEFAULT_QUOTE,
    page_number: int = 1,
    is_verified: bool = True,
) -> Citation:
    """Create a verified Citation for unit tests."""
    return Citation(
        page_number=page_number, quote=quote, is_verified=is_verified
    )


def cited[ValueT](
    value: ValueT,
    quote: str = DEFAULT_QUOTE,
    page_number: int = 1,
) -> CitedValue[ValueT]:
    """Wrap a typed value in a CitedValue with a verified citation."""
    return CitedValue[ValueT](
        value=value,
        citation=make_citation(quote=quote, page_number=page_number),
    )


def make_section(
    heading: M11Heading = M11Heading.PROTOCOL_SUMMARY,
    title: str = "1 Protocol Summary",
    start_page: int = 1,
    end_page: int = 2,
) -> ProtocolSection:
    """Create a ProtocolSection."""
    return ProtocolSection(
        heading=heading,
        title=title,
        start_page=start_page,
        end_page=end_page,
        summary="Section summary.",
        citation=make_citation(page_number=start_page),
    )


def make_subsection(
    number: str = "1.1",
    title: str = "Synopsis",
    page_number: int = 1,
) -> ProtocolSubsection:
    """Create a ProtocolSubsection."""
    return ProtocolSubsection(
        number=number,
        title=title,
        page_number=page_number,
        citation=make_citation(page_number=page_number),
    )


def make_endpoint(
    description: str = "Change from baseline in HbA1c",
    time_frame: str | None = "Baseline and Week 26",
    kind: EndpointKind = EndpointKind.PRIMARY,
    scale_name: str | None = None,
    scale_min: float | None = None,
    scale_max: float | None = None,
    scale_better_direction: ScaleDirection | None = None,
    quote: str = DEFAULT_QUOTE,
    page_number: int = 3,
) -> Endpoint:
    """Create an Endpoint with optional rating-scale metadata."""
    return Endpoint(
        kind=kind,
        description=description,
        time_frame=time_frame,
        scale_name=cited(scale_name, quote, page_number)
        if scale_name is not None
        else None,
        scale_min=cited(scale_min, quote, page_number)
        if scale_min is not None
        else None,
        scale_max=cited(scale_max, quote, page_number)
        if scale_max is not None
        else None,
        scale_better_direction=(
            cited(scale_better_direction, quote, page_number)
            if scale_better_direction is not None
            else None
        ),
        citation=make_citation(quote=quote, page_number=page_number),
    )


def make_visit(
    visit_name: str = "Week 26 Visit",
    study_day: int | None = 182,
    epoch: EpochType | None = EpochType.TREATMENT,
    procedures: list[str] | None = None,
    page_number: int = 4,
) -> ScheduledVisit:
    """Create a ScheduledVisit."""
    return ScheduledVisit(
        visit_name=visit_name,
        study_day=study_day,
        epoch=epoch,
        procedures=["HbA1c"] if procedures is None else procedures,
        citation=make_citation(page_number=page_number),
    )


def make_ice(
    event_type: IntercurrentEventType = (
        IntercurrentEventType.RESCUE_MEDICATION
    ),
    event: str = "Initiation of glycaemic rescue therapy",
    strategy: EstimandStrategy | None = EstimandStrategy.TREATMENT_POLICY,
    page_number: int = 3,
) -> IntercurrentEvent:
    """Create an IntercurrentEvent."""
    return IntercurrentEvent(
        event_type=event_type,
        event=event,
        strategy=strategy,
        citation=make_citation(page_number=page_number),
    )


def make_estimand(
    endpoint_kind: EndpointKind = EndpointKind.PRIMARY,
    endpoint_description: str = "Change from baseline in HbA1c at Week 26",
    population: str | None = "Adults with T2D and HbA1c 7.0% to 10.5%",
    variable: str | None = "Change from baseline in HbA1c at Week 26",
    intercurrent_events: list[IntercurrentEvent] | None = None,
    population_level_summary: str | None = "Difference in mean change",
    treatment_condition: str | None = "Canagliflozin 100 mg vs placebo",
) -> Estimand:
    """Create a complete or partial Estimand."""
    default_ices = [
        make_ice(IntercurrentEventType.RESCUE_MEDICATION),
        make_ice(
            IntercurrentEventType.TREATMENT_DISCONTINUATION,
            "Premature treatment discontinuation",
        ),
        make_ice(
            IntercurrentEventType.BACKGROUND_THERAPY_CHANGE,
            "Change in background antidiabetic therapy",
        ),
    ]
    return Estimand(
        endpoint_kind=endpoint_kind,
        endpoint_description=endpoint_description,
        population=cited(population) if population is not None else None,
        variable=cited(variable) if variable is not None else None,
        intercurrent_events=(
            default_ices
            if intercurrent_events is None
            else intercurrent_events
        ),
        population_level_summary=(
            cited(population_level_summary)
            if population_level_summary is not None
            else None
        ),
        treatment_condition=(
            cited(treatment_condition)
            if treatment_condition is not None
            else None
        ),
    )


def make_arm(
    name: str = "Canagliflozin 100 mg",
    intervention_type: InterventionType = InterventionType.DRUG,
    drug_class: DrugClass | None = DrugClass.SGLT2_INHIBITOR,
    dose_and_regimen: str | None = "100 mg once daily",
    is_control: bool = False,
    control_type: ControlType | None = None,
) -> InterventionArm:
    """Create an InterventionArm."""
    return InterventionArm(
        name=name,
        intervention_type=intervention_type,
        drug_class=drug_class,
        dose_and_regimen=dose_and_regimen,
        is_control=is_control,
        control_type=control_type,
        citation=make_citation(page_number=5),
    )


def make_strata(
    *categories: tuple[StratificationFactorType, str],
) -> list[StratificationFactorItem]:
    """Build StratificationFactorItems from (category, label) pairs."""
    return [
        StratificationFactorItem(
            category=category,
            label=label,
            citation=make_citation(
                quote=f"Stratified by {label}.", page_number=5
            ),
        )
        for category, label in categories
    ]


def make_analysis_sets(
    *categories: tuple[AnalysisSetType, str],
) -> list[AnalysisSetItem]:
    """Build AnalysisSetItems from (category, label) pairs."""
    return [
        AnalysisSetItem(
            category=category,
            label=label,
            citation=make_citation(
                quote=f"Defined set: {label}.", page_number=7
            ),
        )
        for category, label in categories
    ]


def make_subgroups(
    *categories: tuple[SubgroupDimension, str],
) -> list[SubgroupItem]:
    """Build SubgroupItems from (category, label) pairs."""
    return [
        SubgroupItem(
            category=category,
            label=label,
            citation=make_citation(quote=f"Subgroup: {label}.", page_number=7),
        )
        for category, label in categories
    ]


def make_committees(
    *categories: tuple[CommitteeType, str],
) -> list[CommitteeItem]:
    """Build CommitteeItems from (category, label) pairs."""
    return [
        CommitteeItem(
            category=category,
            label=label,
            citation=make_citation(
                quote=f"Committee: {label}.", page_number=8
            ),
        )
        for category, label in categories
    ]


def make_epoch(
    epoch_type: EpochType = EpochType.TREATMENT,
    name: str = "Treatment Period",
    duration_weeks: float | None = 26.0,
) -> TrialEpoch:
    """Create a TrialEpoch."""
    return TrialEpoch(
        epoch_type=epoch_type,
        name=name,
        duration_weeks=duration_weeks,
        citation=make_citation(page_number=2),
    )


def make_profile(
    intervention_type: InterventionType = InterventionType.DRUG,
    diabetes_type: DiabetesType = DiabetesType.T2D,
    drug_class: DrugClass = DrugClass.SGLT2_INHIBITOR,
    phase: TrialPhase = TrialPhase.PHASE3,
    control_type: ControlType = ControlType.PLACEBO,
    is_non_inferiority: bool = False,
    is_add_on: bool = True,
) -> TrialProfile:
    """Create a populated TrialProfile."""
    return TrialProfile(
        intervention_type=cited(intervention_type),
        diabetes_type=cited(diabetes_type),
        drug_class=cited(drug_class),
        phase=cited(phase),
        control_type=cited(control_type),
        is_non_inferiority=cited(is_non_inferiority),
        is_add_on=cited(is_add_on),
    )


def make_document(
    *,
    pages: list[PageText] | None = None,
    design: TrialDesignFacts | None = None,
    eligibility_criteria: list[EligibilityCriterion] | None = None,
    sections: list[ProtocolSection] | None = None,
    subsections: list[ProtocolSubsection] | None = None,
    endpoints: list[Endpoint] | None = None,
    schedule: list[ScheduledVisit] | None = None,
    statistics: StatisticalAssumptions | None = None,
    estimands: EstimandExtraction | None = None,
    interventions: InterventionExtraction | None = None,
    analysis: AnalysisPlanExtraction | None = None,
    synopsis_check: SynopsisConsistencyExtraction | None = None,
    safety_monitoring: SafetyMonitoringExtraction | None = None,
) -> ProtocolDocument:
    """Create a synthetic ProtocolDocument with sensible defaults."""
    default_pages = pages or [
        PageText(page_number=1, text=DEFAULT_QUOTE),
    ]
    default_design = (
        TrialDesignFacts(
            allocation=cited(AllocationType.RANDOMIZED),
            masking=cited(MaskingType.DOUBLE),
            target_enrollment=cited(200),
            arm_count=cited(2),
            min_age_years=cited(18.0),
            max_age_years=cited(75.0),
            is_min_age_inclusive=True,
            is_max_age_inclusive=True,
        )
        if design is None
        else design
    )
    return ProtocolDocument(
        protocol_id="NCT00000001",
        title="Synthetic Diabetes Protocol",
        page_count=len(default_pages),
        pages=default_pages,
        design=default_design,
        eligibility_criteria=eligibility_criteria,
        sections=sections,
        subsections=subsections,
        endpoints=endpoints,
        schedule=schedule,
        statistics=statistics,
        estimands=estimands,
        interventions=interventions,
        analysis=analysis,
        synopsis_check=synopsis_check,
        safety_monitoring=safety_monitoring,
    )
