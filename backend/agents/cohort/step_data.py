"""Turn cohort comparison results into the /demo COHORT step (StepData). Pure.

Maps a ``CohortComparisonReport`` produced by ``backend.agents.cohort``
and the uploaded ``ProtocolDocument`` into the wide ``StepData`` contract
consumed by ``POST /api/cohort-recommendation`` on the ``/demo`` page.
"""

import re

from pydantic import TypeAdapter
from pydantic_core import to_jsonable_python

from backend.agents.cohort.agent import AGENT_NAME
from backend.agents.cohort.models import (
    CohortComparisonReport,
    CohortRecommendationCard,
    DoctorOptionKind,
    RuleSimulability,
)
from backend.api.schemas import (
    ChangeType,
    Chart,
    ChartKind,
    ChartPoint,
    ChartSeries,
    DataSource,
    DataTable,
    Decision,
    DecisionOption,
    DetailMap,
    Evidence,
    EvidenceSource,
    GuidelineReference,
    Metric,
    MetricBenchmark,
    MetricTone,
    ProposedChange,
    ProtocolLocation,
    Severity,
    StepData,
    StepId,
    StepStatus,
    StepWarning,
    TableColumn,
    TraceEntry,
    TraceKind,
)
from backend.shared.messages import M11Heading, ProtocolDocument

TRACE_AGENT = "Cohort"
STEP_TITLE = "Cohort Simulation"
NHANES_DOCUMENT_NAME = "CDC NHANES Adult Diabetic Cohort"
NHANES_URL = "https://wwwn.cdc.gov/nchs/nhanes/"
NHANES_VERSION = "2017-2020"
REGISTRY_URL = "https://clinicaltrials.gov"
INCLUSION_SECTION_TITLE = "5.1 Inclusion Criteria"
EXCLUSION_SECTION_TITLE = "5.2 Exclusion Criteria"
ELIGIBILITY_SECTION_TITLE = "5. Eligibility Criteria"
DECISION_OWNER = "Medical Monitor"
INGEST_DECISION_ID = "d-ing-01"
DEFAULT_DECISION_CONFIDENCE = 0.92
VERIFIED_EVIDENCE_CONFIDENCE = 0.98
UNVERIFIED_EVIDENCE_CONFIDENCE = 0.85
NHANES_EVIDENCE_CONFIDENCE = 0.95
GOOD_ELIGIBLE_PCT_THRESHOLD = 20.0
MIN_PDF_QUOTE_LENGTH = 15
WHITESPACE_PATTERN = re.compile(r"\s+")
DETAIL_MAP_ADAPTER: TypeAdapter[DetailMap] = TypeAdapter(DetailMap)

GUIDELINE_REFERENCES: tuple[GuidelineReference, ...] = (
    GuidelineReference(
        label="ADA Standards of Care in Diabetes",
        url="https://diabetesjournals.org/care",
        quote=(
            "Clinical trial eligibility should reflect the target Type 2 "
            "Diabetes treatment population unless safety requires exclusion."
        ),
    ),
    GuidelineReference(
        label="FDA Diversity Action Plans Guidance",
        url=(
            "https://www.fda.gov/regulatory-information/"
            "search-fda-guidance-documents"
        ),
        quote=(
            "Avoid overly restrictive laboratory or anthropometric cut-offs "
            "that disproportionately exclude older or minority participants."
        ),
    ),
)


def _normalised(text: str) -> str:
    """Collapse whitespace and casefold for robust quote lookup."""
    return WHITESPACE_PATTERN.sub(" ", text).strip().casefold()


def find_quote_page(document: ProtocolDocument, quote: str) -> int | None:
    """Return the first 1-based page whose text contains the quote."""
    cleaned = _normalised(quote)
    if len(cleaned) < MIN_PDF_QUOTE_LENGTH:
        return None
    for page in document.pages:
        if cleaned in _normalised(page.text):
            return page.page_number
    return None


def _section_title_for_criterion(criterion_id: str) -> str:
    """Return the protocol section title for an inclusion/exclusion ID."""
    upper = criterion_id.upper()
    if upper.startswith(("IN", "I-")):
        return INCLUSION_SECTION_TITLE
    if upper.startswith(("EX", "E-")):
        return EXCLUSION_SECTION_TITLE
    return ELIGIBILITY_SECTION_TITLE


def _peer_drop_value(card: CohortRecommendationCard) -> float:
    """Return the card's peer median or peer mean drop percentage."""
    if card.peer_median_drop_pct is not None:
        return card.peer_median_drop_pct
    if card.peer_benchmark_drop_pct is not None:
        return card.peer_benchmark_drop_pct
    return 0.0


def _protocol_evidence(
    card: CohortRecommendationCard,
    decision_id: str,
    document: ProtocolDocument,
) -> Evidence:
    """Build the protocol Evidence item, verifying quote in the PDF."""
    quote_text = card.quote if card.quote else card.original_criterion_text
    matched_page = find_quote_page(document, quote_text)
    if matched_page is None and card.original_criterion_text != quote_text:
        matched_page = find_quote_page(document, card.original_criterion_text)
        if matched_page is not None:
            quote_text = card.original_criterion_text

    is_verified = matched_page is not None
    fallback_page = (
        card.page_number
        if (
            card.page_number is not None
            and 1 <= card.page_number <= max(len(document.pages), 1)
        )
        else (1 if document.pages else None)
    )
    resolved_page = matched_page if is_verified else fallback_page
    section_title = _section_title_for_criterion(card.criterion_id)
    return Evidence(
        evidence_id=f"{decision_id}-protocol",
        source=EvidenceSource.PROTOCOL,
        document=document.title,
        page=resolved_page,
        quote=quote_text,
        is_verified=is_verified,
        section_title=section_title,
        context=card.original_criterion_text,
        confidence=(
            VERIFIED_EVIDENCE_CONFIDENCE
            if is_verified
            else UNVERIFIED_EVIDENCE_CONFIDENCE
        ),
    )


def _cohort_evidence(
    card: CohortRecommendationCard,
    report: CohortComparisonReport,
    decision_id: str,
) -> Evidence:
    """Build the NHANES cohort simulation Evidence item."""
    funnel_step = next(
        (
            s
            for s in report.attrition_funnel
            if s.criterion_id == card.criterion_id
        ),
        None,
    )
    dropped_count = (
        funnel_step.marginal_drop_count if funnel_step is not None else 0
    )
    remaining_count = (
        funnel_step.patients_after
        if funnel_step is not None
        else report.target_eligible_count
    )
    peer_med_drop = _peer_drop_value(card)
    quote = (
        f"Filter '{card.compiled_rule_summary}' removes "
        f"{card.target_drop_pct:.1f}% ({dropped_count:,} patients) of the "
        f"NHANES cohort vs {peer_med_drop:.1f}% peer median drop."
    )
    context = (
        f"Starting from {report.base_population_count:,} adult T2D patients, "
        f"{remaining_count:,} remain after applying {card.criterion_id}. "
        f"Peer median threshold: {card.peer_median_threshold or 'not set'}; "
        f"clinical standard: {card.clinical_standard_threshold or 'not set'}."
    )
    return Evidence(
        evidence_id=f"{decision_id}-nhanes",
        source=EvidenceSource.NHANES,
        document=NHANES_DOCUMENT_NAME,
        page=None,
        quote=quote,
        is_verified=True,
        section_title="Cohort Attrition Simulation",
        context=context,
        url=NHANES_URL,
        confidence=NHANES_EVIDENCE_CONFIDENCE,
    )


def _trace_for_card(
    card: CohortRecommendationCard,
    protocol_ev: Evidence,
    nhanes_ev: Evidence,
) -> list[TraceEntry]:
    """Build the 3-step reasoning trace (rule -> compare -> conclude)."""
    peer_med_drop = _peer_drop_value(card)
    peer_med_thresh = card.peer_median_threshold or "peer range"
    std_thresh = card.clinical_standard_threshold or "clinical standard"
    return [
        TraceEntry(
            agent=TRACE_AGENT,
            kind=TraceKind.RULE,
            text=(
                f"Compiled criterion {card.criterion_id} into computable "
                f"filter '{card.compiled_rule_summary}'."
            ),
            evidence_ids=[protocol_ev.evidence_id],
            details={
                "criterion_id": card.criterion_id,
                "compiled_rule": card.compiled_rule_summary,
            },
        ),
        TraceEntry(
            agent=TRACE_AGENT,
            kind=TraceKind.COMPARE,
            text=(
                f"Filter removes {card.target_drop_pct:.1f}% of the cohort "
                f"compared with {peer_med_drop:.1f}% peer median drop "
                f"(peer median: {peer_med_thresh}; standard: {std_thresh})."
            ),
            evidence_ids=[protocol_ev.evidence_id, nhanes_ev.evidence_id],
            details={
                "target_drop_pct": card.target_drop_pct,
                "peer_median_drop_pct": peer_med_drop,
                "peer_median_threshold": card.peer_median_threshold,
                "clinical_standard_threshold": (
                    card.clinical_standard_threshold
                ),
            },
        ),
        TraceEntry(
            agent=TRACE_AGENT,
            kind=TraceKind.CONCLUDE,
            text=card.description,
            evidence_ids=[nhanes_ev.evidence_id],
        ),
    ]


def _options_for_card(
    card: CohortRecommendationCard,
    page: int | None,
) -> tuple[list[DecisionOption], ProposedChange | None]:
    """Map DoctorOptions into DecisionOptions and pick first ProposedChange."""
    section_title = _section_title_for_criterion(card.criterion_id)
    path = f"{section_title}, {card.criterion_id}"
    options: list[DecisionOption] = []
    first_proposed_change: ProposedChange | None = None

    for opt in card.doctor_options:
        after_text = opt.proposed_protocol_text or (
            opt.what_if_simulation.proposed_protocol_wording
            if opt.what_if_simulation is not None
            else None
        )
        prop_change: ProposedChange | None = None
        if after_text:
            prop_change = ProposedChange(
                path=path,
                before=card.original_criterion_text,
                after=after_text,
                change_type=ChangeType.MODIFY,
                section_title=section_title,
                page=page,
                rationale=opt.clinical_rationale,
            )
            if (
                first_proposed_change is None
                and opt.proposed_protocol_text is not None
            ):
                first_proposed_change = prop_change

        opt_impact: list[Metric] = []
        if opt.what_if_simulation is not None:
            wi = opt.what_if_simulation
            opt_impact.append(
                Metric(
                    label="Eligible after",
                    value=(
                        f"{wi.eligible_after:,} ({wi.eligible_pct_after:.1f}%)"
                    ),
                    tone=MetricTone.GOOD,
                    numeric_value=float(wi.eligible_after),
                    unit="patients",
                )
            )
            opt_impact.append(
                Metric(
                    label="Patients gained",
                    value=(
                        f"+{wi.patients_gained:,} "
                        f"(+{wi.relative_gain_pct:.1f}%)"
                    ),
                    tone=MetricTone.GOOD,
                    numeric_value=float(wi.patients_gained),
                    unit="patients",
                )
            )

        options.append(
            DecisionOption(
                option_id=opt.option_id,
                title=opt.title,
                rationale=opt.clinical_rationale,
                is_recommended=(
                    opt.kind == DoctorOptionKind.RELAX_TO_PEER_STANDARD
                ),
                proposed_change=prop_change,
                impact=opt_impact,
                risks=(
                    [opt.safety_monitoring_requirement]
                    if opt.safety_monitoring_requirement
                    else []
                ),
            )
        )

    if first_proposed_change is None:
        first_proposed_change = next(
            (
                o.proposed_change
                for o in options
                if o.proposed_change is not None
            ),
            None,
        )
    return options, first_proposed_change


def _decision_impact(
    card: CohortRecommendationCard,
    report: CohortComparisonReport,
) -> list[Metric]:
    """Build overview impact metrics for one Decision Card."""
    peer_med_drop = _peer_drop_value(card)
    impact: list[Metric] = [
        Metric(
            label="Cohort drop",
            value=f"-{card.target_drop_pct:.1f}%",
            tone=MetricTone.RISK,
            numeric_value=-card.target_drop_pct,
            unit="%",
            benchmarks=[
                MetricBenchmark(
                    label="Peer median drop",
                    value=f"-{peer_med_drop:.1f}%",
                    numeric_value=-peer_med_drop,
                )
            ],
        )
    ]
    relax_opt = next(
        (
            opt
            for opt in card.doctor_options
            if opt.what_if_simulation is not None
        ),
        None,
    )
    if relax_opt is not None and relax_opt.what_if_simulation is not None:
        wi = relax_opt.what_if_simulation
        impact.append(
            Metric(
                label="Eligible if relaxed",
                value=(
                    f"{wi.eligible_after:,} (+{wi.relative_gain_pct:.1f}%)"
                ),
                tone=MetricTone.GOOD,
                numeric_value=float(wi.eligible_after),
                unit="patients",
                benchmarks=[
                    MetricBenchmark(
                        label="Current eligible",
                        value=f"{report.target_eligible_count:,}",
                        numeric_value=float(report.target_eligible_count),
                    )
                ],
            )
        )
    return impact


def _card_to_decision(
    card: CohortRecommendationCard,
    report: CohortComparisonReport,
    document: ProtocolDocument,
) -> Decision:
    """Convert one CohortRecommendationCard into a /demo Decision."""
    decision_id = card.recommendation_id
    protocol_ev = _protocol_evidence(card, decision_id, document)
    nhanes_ev = _cohort_evidence(card, report, decision_id)
    options, proposed_change = _options_for_card(card, protocol_ev.page)
    section_title = _section_title_for_criterion(card.criterion_id)
    api_dict = card.to_api_recommendation_dict()
    details = DETAIL_MAP_ADAPTER.validate_python(
        to_jsonable_python(api_dict.get("details", {}))
    )
    return Decision(
        decision_id=decision_id,
        step_id=StepId.COHORT,
        severity=Severity(card.severity.value),
        title=card.title,
        claim=card.description,
        evidence=[protocol_ev, nhanes_ev],
        trace=_trace_for_card(card, protocol_ev, nhanes_ev),
        proposed_change=proposed_change,
        derived_from=[INGEST_DECISION_ID],
        category="eligibility",
        confidence=DEFAULT_DECISION_CONFIDENCE,
        location=(
            ProtocolLocation(
                section_heading=M11Heading.TRIAL_POPULATION,
                section_title=section_title,
                start_page=protocol_ev.page,
                end_page=protocol_ev.page,
                criterion_id=card.criterion_id,
            )
            if protocol_ev.page is not None
            else None
        ),
        impact=_decision_impact(card, report),
        options=options,
        references=list(GUIDELINE_REFERENCES),
        decision_owner=DECISION_OWNER,
        tags=["eligibility", "cohort", card.classification.value.lower()],
        details=details,
    )


def _funnel_table(report: CohortComparisonReport) -> DataTable:
    """Build the per-criterion attrition funnel table."""
    rows: list[DetailMap] = []
    for step in report.attrition_funnel:
        rows.append(
            {
                "criterion_id": step.criterion_id,
                "criterion": step.original_text,
                "status": "simulated",
                "rule": step.rule_summary,
                "before": step.patients_before,
                "removed": step.sequential_drop_count,
                "remaining": step.patients_after,
                "percent_removed": step.marginal_drop_pct,
                "peer_median_drop_pct": step.peer_median_drop_pct,
                "classification": step.classification.value,
            }
        )

    for rule in report.compiled_rules:
        if rule.simulability == RuleSimulability.SIMULATABLE:
            continue
        status_label = (
            "assumed met"
            if rule.simulability
            == RuleSimulability.ADMINISTRATIVE_NON_CLINICAL
            else "cannot simulate"
        )
        rows.append(
            {
                "criterion_id": rule.criterion_id,
                "criterion": rule.original_text,
                "status": status_label,
                "rule": "none",
                "before": None,
                "removed": None,
                "remaining": None,
                "percent_removed": None,
                "peer_median_drop_pct": None,
                "classification": (
                    rule.unsimulatable_reason or rule.simulability.value
                ),
            }
        )

    return DataTable(
        table_id="cohort-attrition-funnel",
        title="Every criterion applied to the cohort",
        description=(
            f"{len(report.attrition_funnel)} criteria simulated sequentially "
            f"on {report.base_population_count:,} adult T2D patients."
        ),
        columns=[
            TableColumn(key="criterion_id", label="ID"),
            TableColumn(key="criterion", label="Criterion"),
            TableColumn(key="status", label="Status"),
            TableColumn(key="rule", label="Computable rule"),
            TableColumn(key="before", label="Before", unit="patients"),
            TableColumn(key="removed", label="Removed", unit="patients"),
            TableColumn(key="remaining", label="Remaining", unit="patients"),
            TableColumn(key="percent_removed", label="Drop", unit="%"),
            TableColumn(
                key="peer_median_drop_pct", label="Peer median drop", unit="%"
            ),
            TableColumn(key="classification", label="Classification"),
        ],
        rows=rows,
    )


def _peer_table(report: CohortComparisonReport) -> DataTable:
    """Build the peer trial eligibility benchmark table."""
    rows: list[DetailMap] = [
        {
            "nct_id": peer.nct_id,
            "title": peer.title,
            "phase": peer.phase,
            "eligible_count": peer.eligible_count,
            "eligible_pct": peer.eligible_pct,
            "female_pct": peer.profile.female_pct,
            "age_65_plus_pct": peer.profile.age_65_plus_pct,
        }
        for peer in report.peer_trial_runs
    ]
    return DataTable(
        table_id="cohort-peer-benchmarks",
        title="Peer trial eligibility on the NHANES cohort",
        description=(
            f"Each comparator protocol simulated on the same "
            f"{report.base_population_count:,}-patient NHANES cohort."
        ),
        columns=[
            TableColumn(key="nct_id", label="Trial ID"),
            TableColumn(key="title", label="Title"),
            TableColumn(key="phase", label="Phase"),
            TableColumn(
                key="eligible_count", label="Eligible", unit="patients"
            ),
            TableColumn(key="eligible_pct", label="Eligible", unit="%"),
            TableColumn(key="female_pct", label="Female", unit="%"),
            TableColumn(key="age_65_plus_pct", label="Age 65+", unit="%"),
        ],
        rows=rows,
    )


def _subgroup_table(report: CohortComparisonReport) -> DataTable:
    """Build the subgroup representativeness & FDA diversity audit table."""
    base_p = report.disease_population_profile
    targ_p = report.target_cohort_profile
    peer_p = report.peer_benchmark_profile

    rows: list[DetailMap] = [
        {
            "dimension": "Sex",
            "subgroup": "Female",
            "base_share_pct": base_p.female_pct,
            "eligible_share_pct": targ_p.female_pct,
            "peer_share_pct": peer_p.female_pct,
            "disparity_pp": round(targ_p.female_pct - base_p.female_pct, 1),
        },
        {
            "dimension": "Age",
            "subgroup": "65 and over",
            "base_share_pct": base_p.age_65_plus_pct,
            "eligible_share_pct": targ_p.age_65_plus_pct,
            "peer_share_pct": peer_p.age_65_plus_pct,
            "disparity_pp": round(
                targ_p.age_65_plus_pct - base_p.age_65_plus_pct, 1
            ),
        },
    ]
    for race_key, base_val in base_p.race_distribution_pct.items():
        targ_val = targ_p.race_distribution_pct.get(race_key, 0.0)
        peer_val = peer_p.race_distribution_pct.get(race_key, 0.0)
        rows.append(
            {
                "dimension": "Race / Ethnicity",
                "subgroup": race_key,
                "base_share_pct": base_val,
                "eligible_share_pct": targ_val,
                "peer_share_pct": peer_val,
                "disparity_pp": round(targ_val - base_val, 1),
            }
        )

    return DataTable(
        table_id="cohort-subgroups",
        title="Subgroup representation vs disease baseline (FDA Diversity)",
        description=(
            "Comparison of demographic shares across the base disease "
            "population, the eligible draft cohort, and peer trials."
        ),
        columns=[
            TableColumn(key="dimension", label="Dimension"),
            TableColumn(key="subgroup", label="Subgroup"),
            TableColumn(
                key="base_share_pct", label="Disease baseline", unit="%"
            ),
            TableColumn(key="eligible_share_pct", label="Eligible", unit="%"),
            TableColumn(key="peer_share_pct", label="Peer mean", unit="%"),
            TableColumn(key="disparity_pp", label="Difference", unit="points"),
        ],
        rows=rows,
    )


def _waterfall_chart(report: CohortComparisonReport) -> Chart:
    """Build the sequential attrition waterfall chart."""
    points: list[ChartPoint] = [
        ChartPoint(
            label="Starting cohort",
            value=float(report.base_population_count),
            annotation="Adult NHANES Type 2 Diabetes cohort",
        )
    ]
    for step in report.attrition_funnel:
        points.append(
            ChartPoint(
                label=step.criterion_id,
                value=-float(step.sequential_drop_count),
                annotation=(
                    f"-{step.sequential_drop_pct:.1f}%; "
                    f"{step.patients_after:,} left"
                ),
            )
        )
    return Chart(
        chart_id="cohort-attrition-waterfall",
        kind=ChartKind.WATERFALL,
        title=(
            f"Attrition from {report.base_population_count:,} to "
            f"{report.target_eligible_count:,} eligible"
        ),
        description=(
            "Starting adult T2D cohort followed by patients removed at "
            "each simulated criterion."
        ),
        x_label="Criterion",
        y_label="Patients",
        unit="patients",
        series=[ChartSeries(name="Patients", points=points)],
    )


def _peer_comparison_chart(report: CohortComparisonReport) -> Chart:
    """Build the target vs peer trial eligibility comparison chart."""
    peer_points = [
        ChartPoint(label=peer.nct_id, value=peer.eligible_pct)
        for peer in report.peer_trial_runs
    ]
    draft_point = ChartPoint(
        label="Draft",
        value=report.target_eligible_pct,
        annotation=f"Peer mean: {report.peer_mean_eligible_pct:.1f}%",
    )
    return Chart(
        chart_id="cohort-peer-comparison",
        kind=ChartKind.COMPARISON,
        title="Eligible cohort share: draft vs peer trials",
        x_label="Trial",
        y_label="Eligible share",
        unit="%",
        series=[
            ChartSeries(name="Peers", points=peer_points),
            ChartSeries(name="Draft", points=[draft_point]),
        ],
    )


def _warnings(
    report: CohortComparisonReport,
    decisions: list[Decision],
) -> list[StepWarning]:
    """Collect step-level warnings for unsimulatable criteria and quotes."""
    warnings: list[StepWarning] = []
    unsimulatable = report.unsimulatable_criteria_for_doctor
    if unsimulatable:
        ids = ", ".join(r.criterion_id for r in unsimulatable)
        warnings.append(
            StepWarning(
                code="CRITERIA_NOT_SIMULABLE",
                message=(
                    f"{len(unsimulatable)} criterion/criteria ({ids}) "
                    "cannot be simulated on NHANES variables and require "
                    "manual clinical review."
                ),
                severity=Severity.WARNING,
            )
        )

    protocol_evidences = [
        ev
        for d in decisions
        for ev in d.evidence
        if ev.source == EvidenceSource.PROTOCOL
    ]
    unverified_count = sum(not ev.is_verified for ev in protocol_evidences)
    if unverified_count > 0:
        warnings.append(
            StepWarning(
                code="QUOTE_NOT_IN_PDF",
                message=(
                    f"{unverified_count} of {len(protocol_evidences)} "
                    "criterion quotes were not found verbatim in the "
                    "uploaded PDF."
                ),
                severity=Severity.INFO,
            )
        )

    for notice in report.data_transparency_notices:
        warnings.append(
            StepWarning(
                code="DATA_TRANSPARENCY",
                message=notice,
                severity=Severity.INFO,
            )
        )
    return warnings


def to_step_data(
    report: CohortComparisonReport,
    document: ProtocolDocument,
) -> StepData:
    """Map a CohortComparisonReport into the /demo COHORT StepData."""
    decisions = [
        _card_to_decision(card, report, document)
        for card in report.recommendations
    ]

    steepest = max(
        report.attrition_funnel,
        key=lambda s: s.marginal_drop_pct,
        default=None,
    )
    steepest_label = (
        f"{steepest.criterion_id}: -{steepest.marginal_drop_pct:.1f}%"
        if steepest is not None
        else "None"
    )
    steepest_pct = -steepest.marginal_drop_pct if steepest is not None else 0.0
    steepest_desc = (
        f"{steepest.marginal_drop_count:,} patients removed by "
        f"'{steepest.rule_summary}'."
        if steepest is not None
        else "No patients removed."
    )

    unsimulatable_count = len(report.unsimulatable_criteria_for_doctor)
    unsimulatable_ids = ", ".join(
        r.criterion_id for r in report.unsimulatable_criteria_for_doctor
    )

    peer_benchmark = MetricBenchmark(
        label="Peer mean",
        value=f"{report.peer_mean_eligible_pct:.1f}%",
        numeric_value=report.peer_mean_eligible_pct,
    )
    is_good_eligible = (
        report.target_eligible_pct >= GOOD_ELIGIBLE_PCT_THRESHOLD
    )

    headline = Metric(
        label="Eligible cohort",
        value=f"{report.target_eligible_pct:.1f}%",
        tone=MetricTone.GOOD if is_good_eligible else MetricTone.RISK,
        numeric_value=report.target_eligible_pct,
        unit="%",
        benchmarks=[peer_benchmark],
    )

    metrics = [
        Metric(
            metric_id="m-coh-base",
            label="Cohort",
            value=f"{report.base_population_count:,}",
            numeric_value=float(report.base_population_count),
            unit="patients",
            description="Adult Type 2 Diabetes cohort from CDC NHANES.",
        ),
        Metric(
            metric_id="m-coh-eligible",
            label="Eligible",
            value=(
                f"{report.target_eligible_count:,} "
                f"({report.target_eligible_pct:.1f}%)"
            ),
            tone=MetricTone.GOOD if is_good_eligible else MetricTone.WARN,
            numeric_value=report.target_eligible_pct,
            unit="%",
            description=f"Feasibility: {report.feasibility_status.value}.",
            benchmarks=[peer_benchmark],
        ),
        Metric(
            metric_id="m-coh-steepest",
            label="Steepest drop",
            value=steepest_label,
            tone=MetricTone.RISK,
            numeric_value=steepest_pct,
            unit="%",
            description=steepest_desc,
        ),
        Metric(
            metric_id="m-coh-unsimulable",
            label="Cannot simulate",
            value=str(unsimulatable_count),
            tone=(
                MetricTone.WARN if unsimulatable_count > 0 else MetricTone.GOOD
            ),
            numeric_value=float(unsimulatable_count),
            unit="criteria",
            description=(
                f"Requires doctor review: {unsimulatable_ids}."
                if unsimulatable_ids
                else "All clinical criteria simulated on NHANES."
            ),
        ),
    ]

    return StepData(
        id=StepId.COHORT,
        title=STEP_TITLE,
        summary=(
            f"'{document.title}' simulated on "
            f"{report.base_population_count:,} diabetic patients (NHANES): "
            f"retains {report.target_eligible_pct:.1f}% "
            f"({report.target_eligible_count:,}) vs "
            f"{report.peer_mean_eligible_pct:.1f}% peer average."
        ),
        headline=headline,
        metrics=metrics,
        decisions=decisions,
        status=(
            StepStatus.PARTIAL
            if unsimulatable_count > 0
            else StepStatus.COMPLETED
        ),
        agent=AGENT_NAME,
        warnings=_warnings(report, decisions),
        data_sources=[
            DataSource(
                source=EvidenceSource.NHANES,
                name=NHANES_DOCUMENT_NAME,
                description=(
                    "Real US adult Type 2 Diabetes clinical and laboratory "
                    "records (HbA1c, eGFR, BMI, SBP, comorbidities)."
                ),
                url=NHANES_URL,
                version=NHANES_VERSION,
                record_count=report.base_population_count,
            ),
            DataSource(
                source=EvidenceSource.AACT,
                name="ClinicalTrials.gov & Peer T2D Protocols",
                description=(
                    "Comparator adult Type 2 Diabetes trials simulated on "
                    "the same NHANES patient cohort."
                ),
                url=REGISTRY_URL,
                record_count=len(report.peer_trial_runs),
            ),
        ],
        tables=[
            _funnel_table(report),
            _peer_table(report),
            _subgroup_table(report),
        ],
        charts=[
            _waterfall_chart(report),
            _peer_comparison_chart(report),
        ],
        details={
            "feasibility_status": report.feasibility_status.value,
            "peer_mean_eligible_pct": report.peer_mean_eligible_pct,
            "unsimulatable_criteria_count": unsimulatable_count,
            "female_eligible_pct": report.target_cohort_profile.female_pct,
            "age_65_plus_eligible_pct": (
                report.target_cohort_profile.age_65_plus_pct
            ),
        },
    )
