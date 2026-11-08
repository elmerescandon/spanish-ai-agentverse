"""Deterministic checks for Family EST (estimands and statistics)."""

from collections.abc import Mapping
from statistics import NormalDist

from backend.agents.completeness.checks.common import (
    absence_fired_outcome,
    cannot_assess_outcome,
    find_other_items,
    fired_outcome,
    format_offenders,
    location_for_page,
    not_applicable_outcome,
    parse_duration_to_weeks,
    passed_outcome,
)
from backend.agents.completeness.logic import CheckOutcome, DeterministicCheck
from backend.shared.messages import (
    AnalysisSetType,
    Citation,
    CommitteeType,
    EndpointKind,
    Estimand,
    EstimandStrategy,
    M11Heading,
    ProtocolDocument,
    StatisticalAssumptions,
    SubgroupDimension,
    TrialProfile,
)

REQUIRED_ANALYSIS_SETS: tuple[AnalysisSetType, ...] = (
    AnalysisSetType.RANDOMIZED,
    AnalysisSetType.FULL_ANALYSIS,
    AnalysisSetType.PER_PROTOCOL,
    AnalysisSetType.SAFETY,
)

REQUIRED_SUBGROUPS: tuple[SubgroupDimension, ...] = (
    SubgroupDimension.SEX,
    SubgroupDimension.AGE,
    SubgroupDimension.RACE,
    SubgroupDimension.ETHNICITY,
    SubgroupDimension.BASELINE_HBA1C,
    SubgroupDimension.DIABETES_DURATION,
)

SAMPLE_SIZE_MAX_RELATIVE_ERROR = 0.05


def _estimand_citations(estimand: Estimand) -> list[Citation]:
    citations: list[Citation] = []
    for attr in (
        estimand.population,
        estimand.treatment_condition,
        estimand.variable,
        estimand.population_level_summary,
    ):
        if attr is not None:
            citations.append(attr.citation)
    for ice in estimand.intercurrent_events:
        citations.append(ice.citation)
    return citations


def check_est_02(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-02: Primary estimand must specify all 4 core attributes."""
    if document.estimands is None:
        return cannot_assess_outcome("ESTIMANDS facet did not run.")
    primary = [
        est
        for est in document.estimands.estimands
        if est.endpoint_kind == EndpointKind.PRIMARY
    ]
    if not primary:
        return absence_fired_outcome(
            "No primary estimand specification found in Section 3."
        )
    offenders: list[str] = []
    citations: list[Citation] = []
    for est in primary:
        missing: list[str] = []
        if est.population is None:
            missing.append("population")
        if est.treatment_condition is None:
            missing.append("treatment_condition")
        if est.variable is None:
            missing.append("variable")
        if est.population_level_summary is None:
            missing.append("population_level_summary")
        if missing:
            offenders.append(
                f"'{est.endpoint_description}' (omits {', '.join(missing)})"
            )
            est_cits = _estimand_citations(est)
            if est_cits:
                citations.append(est_cits[0])
    if offenders:
        page = citations[0].page_number if citations else None
        return fired_outcome(
            f"Primary estimand(s) incomplete: {format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document, page, M11Heading.OBJECTIVES_AND_ESTIMANDS
            ),
            needs_second_opinion=True,
        )
    first = primary[0]
    citations = _estimand_citations(first)
    page = citations[0].page_number if citations else None
    return passed_outcome(
        f"Primary estimand for '{first.endpoint_description}' defines "
        "population, treatment, variable, and population-level summary.",
        evidence=citations[:2],
        location=location_for_page(
            document, page, M11Heading.OBJECTIVES_AND_ESTIMANDS
        ),
    )


def check_est_03(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-03: Estimand endpoint attribute must state a specific timepoint."""
    if document.estimands is None:
        return cannot_assess_outcome("ESTIMANDS facet did not run.")
    if not document.estimands.estimands:
        return cannot_assess_outcome(
            "No estimands extracted to check endpoint timepoints."
        )
    offenders: list[str] = []
    citations: list[Citation] = []
    any_missing_var = False
    for est in document.estimands.estimands:
        var_text = (
            est.variable.value
            if est.variable is not None
            else est.endpoint_description
        )
        est_cits = (
            [est.variable.citation]
            if est.variable is not None
            else _estimand_citations(est)[:1]
        )
        if parse_duration_to_weeks(var_text) is None:
            offenders.append(f"'{var_text}'")
            citations.extend(est_cits)
            if est.variable is None:
                any_missing_var = True
    if offenders:
        page = citations[0].page_number if citations else None
        return fired_outcome(
            f"Estimand variable(s) omit a specific evaluation timepoint: "
            f"{format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document, page, M11Heading.OBJECTIVES_AND_ESTIMANDS
            ),
            needs_second_opinion=any_missing_var,
        )
    first = document.estimands.estimands[0]
    first_text = (
        first.variable.value
        if first.variable is not None
        else first.endpoint_description
    )
    citations = (
        [first.variable.citation]
        if first.variable is not None
        else _estimand_citations(first)[:1]
    )
    return passed_outcome(
        f"Estimand variable '{first_text}' states an explicit assessment "
        "timepoint.",
        evidence=citations,
    )


def check_est_04(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-04: Primary estimand must list ICEs with canonical strategies."""
    if document.estimands is None:
        return cannot_assess_outcome("ESTIMANDS facet did not run.")
    primary = [
        est
        for est in document.estimands.estimands
        if est.endpoint_kind == EndpointKind.PRIMARY
    ]
    if not primary:
        return absence_fired_outcome(
            "No primary estimand specification found to check intercurrent "
            "events."
        )
    for est in primary:
        for ice in est.intercurrent_events:
            if ice.strategy == EstimandStrategy.OTHER:
                return cannot_assess_outcome(
                    f"Intercurrent event '{ice.event}' has strategy OTHER; "
                    "cannot verify canonical ICH E9(R1) strategy.",
                    evidence=[ice.citation],
                )
    offenders: list[str] = []
    citations: list[Citation] = []
    for est in primary:
        if not est.intercurrent_events:
            offenders.append(
                f"'{est.endpoint_description}' (lists no intercurrent events)"
            )
            citations.extend(_estimand_citations(est)[:1])
            continue
        for ice in est.intercurrent_events:
            if ice.strategy is None:
                offenders.append(f"'{ice.event}' (omits strategy)")
                citations.append(ice.citation)
    if offenders:
        page = citations[0].page_number if citations else None
        return fired_outcome(
            f"Primary estimand intercurrent-event specification incomplete: "
            f"{format_offenders(offenders)}.",
            evidence=citations,
            location=location_for_page(
                document, page, M11Heading.OBJECTIVES_AND_ESTIMANDS
            ),
            needs_second_opinion=True,
        )
    first_ice = primary[0].intercurrent_events[0]
    return passed_outcome(
        f"Primary estimand specifies handling strategies for all "
        f"{len(primary[0].intercurrent_events)} intercurrent event(s).",
        evidence=[first_ice.citation],
        location=location_for_page(
            document,
            first_ice.citation.page_number,
            M11Heading.OBJECTIVES_AND_ESTIMANDS,
        ),
    )


def check_est_06(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-06: Secondary objectives must have structured estimand specs."""
    if document.endpoints is None or document.estimands is None:
        return cannot_assess_outcome(
            "ENDPOINTS or ESTIMANDS facet did not run."
        )
    sec_eps = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.SECONDARY
    ]
    sec_ests = [
        est
        for est in document.estimands.estimands
        if est.endpoint_kind == EndpointKind.SECONDARY
    ]
    if not sec_eps and not sec_ests:
        return not_applicable_outcome(
            "No secondary endpoints or objectives are defined."
        )
    if not sec_ests:
        return fired_outcome(
            f"Protocol defines {len(sec_eps)} secondary endpoint(s) without "
            "structured secondary estimand specifications.",
            evidence=[sec_eps[0].citation],
            location=location_for_page(
                document,
                sec_eps[0].citation.page_number,
                M11Heading.OBJECTIVES_AND_ESTIMANDS,
            ),
            needs_second_opinion=True,
        )
    offenders = [
        f"'{est.endpoint_description}'"
        for est in sec_ests
        if est.variable is None
    ]
    if offenders:
        citations = [ep.citation for ep in sec_eps]
        return fired_outcome(
            f"Secondary estimand(s) omit the endpoint/variable attribute: "
            f"{format_offenders(offenders)}.",
            evidence=citations,
            needs_second_opinion=True,
        )
    first = sec_ests[0]
    assert first.variable is not None
    return passed_outcome(
        f"Secondary estimands are specified (e.g. '{first.variable.value}').",
        evidence=[first.variable.citation],
    )


def check_est_10(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-10: Statistical section must define all 4 core analysis sets."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    items = document.analysis.analysis_sets
    present = {item.category for item in items}
    missing = [
        cat.value for cat in REQUIRED_ANALYSIS_SETS if cat not in present
    ]
    if missing:
        other_items = find_other_items(items)
        if other_items:
            labels = ", ".join(f"'{i.label}'" for i in other_items)
            return cannot_assess_outcome(
                f"Analysis set {labels} has category OTHER; cannot verify "
                f"whether it covers missing {missing}.",
                evidence=[i.citation for i in other_items],
            )
        present_labels = ", ".join(sorted(c.value for c in present)) or "none"
        return fired_outcome(
            f"Section 10 defines [{present_labels}], omitting "
            f"[{', '.join(missing)}].",
            evidence=[item.citation for item in items],
            needs_second_opinion=True,
        )
    return passed_outcome(
        "Section 10 defines RANDOMIZED, FULL_ANALYSIS, PER_PROTOCOL, and "
        "SAFETY analysis sets.",
        evidence=[item.citation for item in items[:2]],
    )


def check_est_11(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-11: Primary efficacy analysis must name model, covariates, base."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    plan = document.analysis
    missing: list[str] = []
    if plan.primary_analysis_method is None:
        missing.append("statistical model")
    if not plan.primary_analysis_covariates:
        missing.append("model covariates")
    if (
        plan.adjusts_for_baseline is None
        or plan.adjusts_for_baseline.value is False
    ):
        missing.append("baseline adjustment")

    citations: list[Citation] = []
    if plan.primary_analysis_method is not None:
        citations.append(plan.primary_analysis_method.citation)
    citations.extend(c.citation for c in plan.primary_analysis_covariates[:2])
    if plan.adjusts_for_baseline is not None:
        citations.append(plan.adjusts_for_baseline.citation)

    if missing:
        has_absence = (
            plan.primary_analysis_method is None
            or not plan.primary_analysis_covariates
            or plan.adjusts_for_baseline is None
        )
        return fired_outcome(
            f"Primary analysis specification omits: {', '.join(missing)}.",
            evidence=citations,
            needs_second_opinion=has_absence,
        )
    assert plan.primary_analysis_method is not None
    cov_names = ", ".join(c.label for c in plan.primary_analysis_covariates)
    return passed_outcome(
        f"Primary analysis uses '{plan.primary_analysis_method.value}' with "
        f"baseline adjustment and covariates ({cov_names}).",
        evidence=citations[:2],
    )


def check_est_14(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-14: Section 10 must specify a sensitivity analysis."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    analyses = document.analysis.sensitivity_analyses
    if not analyses:
        return absence_fired_outcome(
            "Section 10 specifies no sensitivity analyses for the primary "
            "estimand."
        )
    first = analyses[0]
    return passed_outcome(
        f"Section 10 specifies sensitivity analysis: '{first.value}'.",
        evidence=[first.citation],
        location=location_for_page(
            document,
            first.citation.page_number,
            M11Heading.STATISTICAL_CONSIDERATIONS,
        ),
    )


def check_est_16(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-16: Multiple confirmatory hypotheses require multiplicity plan."""
    if document.analysis is None or document.endpoints is None:
        return cannot_assess_outcome(
            "ANALYSIS or ENDPOINTS facet did not run."
        )
    plan = document.analysis
    primary_eps = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    secondary_eps = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.SECONDARY
    ]
    has_multiple = (
        len(primary_eps) > 1
        or len(secondary_eps) >= 1
        or plan.confirmatory_hierarchy is not None
    )
    if not has_multiple:
        return not_applicable_outcome(
            "Only a single primary hypothesis is defined."
        )
    if (
        plan.controls_type_i_error is not None
        and plan.controls_type_i_error.value is True
    ):
        return passed_outcome(
            "Section 10 specifies familywise Type I error control across "
            "hypotheses.",
            evidence=[plan.controls_type_i_error.citation],
        )
    if plan.confirmatory_hierarchy is not None and (
        plan.controls_type_i_error is None
    ):
        return passed_outcome(
            "Section 10 defines confirmatory testing hierarchy: "
            f"'{plan.confirmatory_hierarchy.value}'.",
            evidence=[plan.confirmatory_hierarchy.citation],
        )
    if plan.controls_type_i_error is not None:
        return fired_outcome(
            "Multiple hypotheses are defined, and Section 10 states no "
            "familywise Type I error control is applied.",
            evidence=[plan.controls_type_i_error.citation],
            needs_second_opinion=False,
        )
    ep_citations = [ep.citation for ep in (*primary_eps, *secondary_eps)[:2]]
    return fired_outcome(
        f"Protocol defines {len(primary_eps)} primary and "
        f"{len(secondary_eps)} secondary endpoint(s) without specifying "
        "familywise Type I error control in Section 10.",
        evidence=ep_citations,
        needs_second_opinion=True,
    )


def check_est_17(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-17: Planned interim analysis requires alpha spending and DMC."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    plan = document.analysis
    if plan.has_interim_analysis is None:
        return cannot_assess_outcome(
            "Whether an interim analysis is planned is not stated."
        )
    if plan.has_interim_analysis.value is False:
        return not_applicable_outcome(
            "No interim analysis is planned in this protocol.",
            evidence=[plan.has_interim_analysis.citation],
        )
    has_dmc = (
        document.design is not None
        and document.design.has_data_monitoring_committee is not None
        and document.design.has_data_monitoring_committee.value is True
    ) or any(
        item.category == CommitteeType.DATA_MONITORING
        for item in (
            document.synopsis_check.governance_committees
            if document.synopsis_check is not None
            else []
        )
    )
    missing: list[str] = []
    if plan.alpha_spending_function is None:
        missing.append("alpha_spending_function")
    if not has_dmc:
        missing.append("independent DMC firewall")
    if missing:
        return fired_outcome(
            "Interim analysis is planned, but protocol omits: "
            f"{', '.join(missing)}.",
            evidence=[plan.has_interim_analysis.citation],
            needs_second_opinion=True,
        )
    assert plan.alpha_spending_function is not None
    return passed_outcome(
        f"Interim analysis specifies alpha-spending function "
        f"'{plan.alpha_spending_function.value}' and an independent DMC.",
        evidence=[
            plan.has_interim_analysis.citation,
            plan.alpha_spending_function.citation,
        ],
    )


def check_est_18(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-18: Randomisation strata must be included as model covariates."""
    if document.interventions is None or document.analysis is None:
        return cannot_assess_outcome(
            "INTERVENTIONS or ANALYSIS facet did not run."
        )
    strata = document.interventions.stratification_factors
    if not strata and document.synopsis_check is not None:
        strata = document.synopsis_check.synopsis_stratification_factors
    if not strata:
        return not_applicable_outcome("Randomisation is not stratified.")
    covariates = document.analysis.primary_analysis_covariates
    other_items = [*find_other_items(strata), *find_other_items(covariates)]
    if other_items:
        labels = ", ".join(f"'{i.label}'" for i in other_items)
        return cannot_assess_outcome(
            f"Unclassified OTHER factor {labels}; cannot compare "
            "randomisation strata with model covariates.",
            evidence=[i.citation for i in other_items],
        )
    cov_cats = {c.category for c in covariates}
    missing = sorted(
        s.category.value for s in strata if s.category not in cov_cats
    )
    citations = [
        *(s.citation for s in strata),
        *(c.citation for c in covariates),
    ]
    if missing:
        cov_desc = sorted(c.value for c in cov_cats)
        return fired_outcome(
            f"Randomisation strata {missing} are omitted from primary model "
            f"covariates {cov_desc}.",
            evidence=citations,
            needs_second_opinion=(not covariates),
        )
    matched = sorted(s.category.value for s in strata)
    return passed_outcome(
        f"All randomisation strata {matched} are included in primary model "
        "covariates.",
        evidence=citations[:2],
    )


def check_est_19(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-19: Section 10 must pre-specify all 6 subgroup dimensions."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    subgroups = document.analysis.prespecified_subgroups
    present = {item.category for item in subgroups}
    missing = [dim.value for dim in REQUIRED_SUBGROUPS if dim not in present]
    if missing:
        other_items = find_other_items(subgroups)
        if other_items:
            labels = ", ".join(f"'{i.label}'" for i in other_items)
            return cannot_assess_outcome(
                f"Subgroup {labels} has category OTHER; cannot verify "
                f"whether it covers missing {missing}.",
                evidence=[i.citation for i in other_items],
            )
        return fired_outcome(
            f"Section 10 omits pre-specified subgroup analyses for: "
            f"{format_offenders(missing)}.",
            evidence=[item.citation for item in subgroups],
            needs_second_opinion=True,
        )
    return passed_outcome(
        "Section 10 pre-specifies subgroup analyses for sex, age, race, "
        "ethnicity, baseline HbA1c, and diabetes duration.",
        evidence=[item.citation for item in subgroups[:2]],
    )


def check_est_20(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-20: Section 10 must cover safety analysis set and hypoglycaemia."""
    if document.analysis is None or document.safety_monitoring is None:
        return cannot_assess_outcome(
            "ANALYSIS or SAFETY_MONITORING facet did not run."
        )
    sets = document.analysis.analysis_sets
    has_safety_set = any(s.category == AnalysisSetType.SAFETY for s in sets)
    if not has_safety_set and find_other_items(sets):
        other = find_other_items(sets)
        return cannot_assess_outcome(
            f"Analysis set '{other[0].label}' has category OTHER; cannot "
            "verify SAFETY analysis set.",
            evidence=[other[0].citation],
        )
    hypo = document.safety_monitoring.defines_hypoglycemia_levels
    has_hypo = hypo is not None and hypo.value is True

    missing: list[str] = []
    if not has_safety_set:
        missing.append("SAFETY analysis population")
    if not has_hypo:
        missing.append("hypoglycaemia event definitions")
    citations: list[Citation] = [s.citation for s in sets[:1]]
    if hypo is not None:
        citations.append(hypo.citation)
    if missing:
        return fired_outcome(
            f"Safety analysis plan omits: {', '.join(missing)}.",
            evidence=citations,
            needs_second_opinion=True,
        )
    return passed_outcome(
        "Safety analysis population and hypoglycaemia definitions are "
        "specified.",
        evidence=citations,
    )


def check_est_21(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-21: Target sample size must be accompanied by power calculation."""
    if document.statistics is None:
        return cannot_assess_outcome("STATISTICS facet did not run.")
    stats = document.statistics
    has_calc = stats.has_sample_size_calculation
    if has_calc is not None and has_calc.value is False:
        return fired_outcome(
            "Protocol states that sample size is not based on a formal power "
            "calculation.",
            evidence=[has_calc.citation],
            needs_second_opinion=False,
        )
    if (has_calc is None or not has_calc.value) and stats.power is None:
        evidence = (
            [stats.sample_size.citation]
            if stats.sample_size is not None
            else []
        )
        return fired_outcome(
            "Target sample size is stated without a power or sample-size "
            "calculation.",
            evidence=evidence,
            needs_second_opinion=True,
        )
    citation = (
        has_calc.citation if has_calc is not None else stats.power.citation  # type: ignore[union-attr]
    )
    return passed_outcome(
        "Sample-size power calculation is present in Section 10.",
        evidence=[citation],
    )


def _stats_citations(stats: StatisticalAssumptions) -> list[Citation]:
    citations: list[Citation] = []
    for field_val in (
        stats.sample_size,
        stats.power,
        stats.alpha,
        stats.dropout_rate,
        stats.effect_size,
        stats.effect_size_value,
        stats.standard_deviation,
        stats.allocation_ratio,
        stats.is_two_sided,
    ):
        if field_val is not None:
            citations.append(field_val.citation)
    return citations


def check_est_22(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-22: Sample-size calculation must state all required assumptions."""
    if document.statistics is None:
        return cannot_assess_outcome("STATISTICS facet did not run.")
    stats = document.statistics
    missing: list[str] = []
    if stats.effect_size is None and stats.effect_size_value is None:
        missing.append("effect_size")
    if stats.standard_deviation is None:
        missing.append("standard_deviation")
    if stats.alpha is None:
        missing.append("alpha")
    if stats.is_two_sided is None:
        missing.append("is_two_sided")
    if stats.power is None:
        missing.append("power")
    if stats.dropout_rate is None:
        missing.append("dropout_rate")
    if stats.allocation_ratio is None:
        missing.append("allocation_ratio")
    citations = _stats_citations(stats)
    if missing:
        return fired_outcome(
            f"Sample-size calculation omits: {', '.join(missing)}.",
            evidence=citations[:2],
            needs_second_opinion=True,
        )
    return passed_outcome(
        "Sample-size calculation specifies effect size, SD, alpha, sidedness, "
        "power, dropout rate, and allocation ratio.",
        evidence=citations[:2],
    )


def _recompute_total_sample_size(
    alpha: float,
    is_two_sided: bool,
    power: float,
    effect_size: float,
    sd: float,
    allocation_ratio: float,
    dropout_rate: float,
) -> int:
    dist = NormalDist()
    alpha_tail = 1.0 - (alpha / 2.0 if is_two_sided else alpha)
    z_alpha = dist.inv_cdf(alpha_tail)
    z_beta = dist.inv_cdf(power)
    ratio_factor = ((1.0 + allocation_ratio) ** 2) / allocation_ratio
    n_completers = (
        ratio_factor * ((z_alpha + z_beta) ** 2) * ((sd / effect_size) ** 2)
    )
    n_enrolled = n_completers / (1.0 - dropout_rate)
    return round(n_enrolled)


def check_est_26(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """EST-26: Stated N must be within 5% of recomputed sample size."""
    if document.statistics is None:
        return cannot_assess_outcome("STATISTICS facet did not run.")
    stats = document.statistics
    required_fields: tuple[tuple[str, object], ...] = (
        ("sample_size", stats.sample_size),
        ("alpha", stats.alpha),
        ("power", stats.power),
        ("effect_size_value", stats.effect_size_value),
        ("standard_deviation", stats.standard_deviation),
        ("is_two_sided", stats.is_two_sided),
        ("allocation_ratio", stats.allocation_ratio),
        ("dropout_rate", stats.dropout_rate),
    )
    missing = [name for name, val in required_fields if val is None]
    if missing:
        return cannot_assess_outcome(
            "Cannot recompute sample size because required inputs are "
            f"missing: {', '.join(missing)}."
        )
    assert stats.sample_size is not None
    assert stats.alpha is not None
    assert stats.power is not None
    assert stats.effect_size_value is not None
    assert stats.standard_deviation is not None
    assert stats.is_two_sided is not None
    assert stats.allocation_ratio is not None
    assert stats.dropout_rate is not None

    stated_n = stats.sample_size.value
    recomputed_n = _recompute_total_sample_size(
        alpha=stats.alpha.value,
        is_two_sided=stats.is_two_sided.value,
        power=stats.power.value,
        effect_size=stats.effect_size_value.value,
        sd=stats.standard_deviation.value,
        allocation_ratio=stats.allocation_ratio.value,
        dropout_rate=stats.dropout_rate.value,
    )
    rel_diff = abs(stated_n - recomputed_n) / stated_n
    citations = [
        stats.sample_size.citation,
        stats.power.citation,
        stats.effect_size_value.citation,
        stats.standard_deviation.citation,
        stats.dropout_rate.citation,
    ]
    if rel_diff > SAMPLE_SIZE_MAX_RELATIVE_ERROR:
        return fired_outcome(
            f"Stated sample size N={stated_n} differs by {rel_diff:.1%} "
            f"(>5%) from recomputed N={recomputed_n}.",
            evidence=citations,
            needs_second_opinion=True,
        )
    return passed_outcome(
        f"Stated sample size N={stated_n} is consistent ({rel_diff:.1%} "
        f"difference) with recomputed N={recomputed_n}.",
        evidence=citations[:2],
    )


ESTIMAND_CHECKS: Mapping[str, DeterministicCheck] = {
    "EST-02": check_est_02,
    "EST-03": check_est_03,
    "EST-04": check_est_04,
    "EST-06": check_est_06,
    "EST-10": check_est_10,
    "EST-11": check_est_11,
    "EST-14": check_est_14,
    "EST-16": check_est_16,
    "EST-17": check_est_17,
    "EST-18": check_est_18,
    "EST-19": check_est_19,
    "EST-20": check_est_20,
    "EST-21": check_est_21,
    "EST-22": check_est_22,
    "EST-26": check_est_26,
}
