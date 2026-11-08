"""Family XS deterministic checks: cross-section consistency (14 rules)."""

import re

from backend.agents.completeness.checks.common import (
    absence_fired_outcome,
    cannot_assess_outcome,
    compare_category_sets,
    extract_all_timepoints_weeks,
    find_other_items,
    find_pattern_citation,
    fired_outcome,
    format_offenders,
    not_applicable_outcome,
    parse_duration_to_weeks,
    passed_outcome,
    weeks_match,
)
from backend.agents.completeness.logic import CheckOutcome, DeterministicCheck
from backend.shared.messages import (
    Citation,
    CommitteeType,
    CriterionKind,
    EndpointKind,
    EpochType,
    EstimandStrategy,
    IntercurrentEvent,
    IntercurrentEventType,
    ProtocolDocument,
    RuleStatus,
    TrialProfile,
)

DAYS_PER_WEEK = 7.0
VISIT_TOLERANCE_WEEKS = 1.0
DURATION_TOLERANCE_WEEKS = 0.5

DRUG_TOKEN_PATTERN = re.compile(
    r"\b("
    r"metformin|sulfonylurea|sulfonylureas|glimepiride|glipizide|glyburide|"
    r"glibenclamide|insulin|sglt2|glp[\s\-]?1|dpp[\s\-]?4|thiazolidinedione|"
    r"pioglitazone|rosiglitazone|acarbose|meglitinide|repaglinide|nateglinide|"
    r"corticosteroid|corticosteroids"
    r")\b",
    re.IGNORECASE,
)

AGE_RANGE_PATTERN = re.compile(
    r"(?:aged?|between)\s*(\d+(?:\.\d+)?)\s*(?:to|and|[-–])\s*"
    r"(\d+(?:\.\d+)?)\s*years",
    re.IGNORECASE,
)
MIN_AGE_PATTERN = re.compile(
    r"(?:>=\s*|≥\s*|at\s+least\s+|minimum\s+age\s+(?:of\s+)?)(\d+(?:\.\d+)?)"
    r"\s*years",
    re.IGNORECASE,
)
MAX_AGE_PATTERN = re.compile(
    r"(?:<=\s*|≤\s*|at\s+most\s+|up\s+to\s+|maximum\s+age\s+(?:of\s+)?)"
    r"(\d+(?:\.\d+)?)\s*years",
    re.IGNORECASE,
)

ABBREVIATION_DEF_PATTERN = re.compile(r"\(([A-Z]{2,8})\)")
GLOSSARY_HEADER_PATTERN = re.compile(
    r"\b(?:abbreviations?|glossary)\b", re.IGNORECASE
)
GLOSSARY_ENTRY_PATTERN = re.compile(
    r"^\s*(?:[\-•*]\s*)?([A-Z]{2,8})\b"
    r"(?:\s*[:\-–—]\s*|\s{2,}|\t+|\s+)"
    r"[A-Za-z][^\n]{2,}$",
    re.MULTILINE,
)
COMMON_ROMAN_OR_UNITS: frozenset[str] = frozenset(
    {
        "II",
        "III",
        "IV",
        "VI",
        "VII",
        "VIII",
        "IX",
        "AM",
        "PM",
        "US",
        "UK",
        "EU",
        "ICH",
        "FDA",
        "EMA",
        "IRB",
        "IEC",
        "GCP",
        "ICF",
        "SAE",
        "AE",
        "SD",
        "SE",
        "CI",
        "OR",
        "HR",
        "MM",
        "MG",
        "KG",
        "DL",
        "ML",
        "UL",
        "IN",
        "EX",
    }
)
SECTION_XREF_PATTERN = re.compile(
    r"\bSection\s+(\d+(?:\.\d+)+)\b", re.IGNORECASE
)


def _normalize_drug_token(token: str) -> str:
    lowered = token.lower().replace("-", "").replace(" ", "")
    if lowered in {
        "sulfonylurea",
        "sulfonylureas",
        "glimepiride",
        "glipizide",
        "glyburide",
        "glibenclamide",
    }:
        return "sulfonylurea"
    if lowered in {"corticosteroid", "corticosteroids"}:
        return "corticosteroid"
    if lowered in {"thiazolidinedione", "pioglitazone", "rosiglitazone"}:
        return "thiazolidinedione"
    if lowered in {"meglitinide", "repaglinide", "nateglinide"}:
        return "meglitinide"
    return lowered


def _all_intercurrent_events(
    document: ProtocolDocument,
) -> list[IntercurrentEvent]:
    events: list[IntercurrentEvent] = []
    if document.estimands is not None:
        for estimand in document.estimands.estimands:
            events.extend(estimand.intercurrent_events)
    if document.synopsis_check is not None:
        events.extend(document.synopsis_check.synopsis_ice_strategies)
    return events


def check_xs_03(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-03: Rescue ICE in Section 3 requires rescue criteria in Section 6."""
    if document.estimands is None or document.interventions is None:
        return cannot_assess_outcome(
            "ESTIMANDS or INTERVENTIONS facet did not run."
        )
    events = _all_intercurrent_events(document)
    rescue_events = [
        ev
        for ev in events
        if ev.event_type == IntercurrentEventType.RESCUE_MEDICATION
    ]
    if not rescue_events:
        other_events = [
            ev for ev in events if ev.event_type == IntercurrentEventType.OTHER
        ]
        if other_events:
            return cannot_assess_outcome(
                "Intercurrent event has category OTHER; cannot verify "
                "whether rescue medication is listed."
            )
        return not_applicable_outcome(
            "Rescue medication is not listed as an intercurrent event."
        )

    interventions = document.interventions
    if (
        interventions.rescue_therapy_criteria is None
        or interventions.rescue_medication_regimen is None
    ):
        missing: list[str] = []
        if interventions.rescue_therapy_criteria is None:
            missing.append("glycaemic rescue thresholds")
        if interventions.rescue_medication_regimen is None:
            missing.append("permitted rescue medication regimen")
        return absence_fired_outcome(
            "Rescue medication is listed as an intercurrent event in "
            f"Section 3, but Section 6 omits {', '.join(missing)}."
        )
    return passed_outcome(
        "Rescue intercurrent event is paired with Section 6 rescue criteria "
        "and regimen.",
        evidence=[
            rescue_events[0].citation,
            interventions.rescue_therapy_criteria.citation,
            interventions.rescue_medication_regimen.citation,
        ],
    )


def check_xs_04(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-04: Treatment-policy estimand requires follow-up after stopping."""
    if document.estimands is None or document.interventions is None:
        return cannot_assess_outcome(
            "ESTIMANDS or INTERVENTIONS facet did not run."
        )
    events = _all_intercurrent_events(document)
    tp_events = [
        ev for ev in events if ev.strategy == EstimandStrategy.TREATMENT_POLICY
    ]
    if not tp_events:
        other_events = [
            ev for ev in events if ev.strategy == EstimandStrategy.OTHER
        ]
        if other_events:
            return cannot_assess_outcome(
                "Intercurrent event strategy is OTHER; cannot verify "
                "whether treatment-policy strategy applies."
            )
        return not_applicable_outcome(
            "No intercurrent event uses a treatment-policy strategy."
        )

    continues = (
        document.interventions.continues_follow_up_after_discontinuation
    )
    if continues is None:
        return absence_fired_outcome(
            "Section 3 specifies a treatment-policy strategy, but Section 7 "
            "does not state that participants who stop study drug remain in "
            "trial follow-up."
        )
    if not continues.value:
        return fired_outcome(
            "Section 3 specifies a treatment-policy strategy, but Section 7 "
            "withdraws participants who discontinue study medication from "
            "follow-up.",
            evidence=[tp_events[0].citation, continues.citation],
        )
    return passed_outcome(
        "Treatment-policy strategy is supported by continued follow-up after "
        "treatment discontinuation.",
        evidence=[tp_events[0].citation, continues.citation],
    )


def check_xs_05(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-05: Primary endpoint assessment timepoint must match an SoA visit."""
    if document.endpoints is None or document.schedule is None:
        return cannot_assess_outcome(
            "ENDPOINTS or SCHEDULE facet did not run."
        )
    primaries = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    if not primaries:
        return cannot_assess_outcome("No primary endpoint extracted.")
    primary = primaries[0]
    target_weeks = [
        w
        for w in extract_all_timepoints_weeks(primary.time_frame or "")
        if w > 0.0
    ]
    if not target_weeks:
        target_weeks = [
            w
            for w in extract_all_timepoints_weeks(primary.description)
            if w > 0.0
        ]
    if not target_weeks:
        return cannot_assess_outcome(
            "Primary endpoint does not state a numeric post-baseline "
            "timepoint in weeks."
        )
    if not document.schedule:
        return cannot_assess_outcome("Schedule of Activities is empty.")

    primary_week = target_weeks[-1]
    visit_weeks: list[tuple[float, Citation | None]] = []
    for visit in document.schedule:
        parsed_visit = parse_duration_to_weeks(visit.visit_name)
        if parsed_visit is not None:
            visit_weeks.append((parsed_visit, visit.citation))
        elif visit.study_day is not None and visit.study_day > 0:
            visit_weeks.append(
                (visit.study_day / DAYS_PER_WEEK, visit.citation)
            )

    if not visit_weeks:
        return cannot_assess_outcome(
            "No scheduled visits have parseable week or day timings."
        )

    for v_week, v_cit in visit_weeks:
        if weeks_match(
            primary_week, v_week, tolerance_weeks=VISIT_TOLERANCE_WEEKS
        ):
            ev = [primary.citation]
            if v_cit is not None:
                ev.append(v_cit)
            return passed_outcome(
                f"Primary endpoint timepoint (Week {primary_week:g}) matches "
                "a scheduled visit in the Schedule of Activities.",
                evidence=ev,
            )

    evidence = [primary.citation]
    for _, v_cit in visit_weeks[:2]:
        if v_cit is not None:
            evidence.append(v_cit)
    listed = ", ".join(f"Week {w:g}" for w, _ in visit_weeks)
    return fired_outcome(
        f"Primary endpoint assessment timepoint (Week {primary_week:g}) has "
        f"no matching visit in the Schedule of Activities (found: {listed}).",
        evidence=evidence,
    )


def check_xs_07(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-07: Synopsis enrollment, arm count, and duration must match body."""
    if document.synopsis_check is None:
        return cannot_assess_outcome("SYNOPSIS_CHECK facet did not run.")
    syn = document.synopsis_check
    discrepancies: list[str] = []
    evidence: list[Citation] = []
    compared_any = False

    body_n = (
        document.design.target_enrollment
        if document.design is not None
        and document.design.target_enrollment is not None
        else (
            document.statistics.sample_size
            if document.statistics is not None
            else None
        )
    )
    if syn.synopsis_enrollment is not None and body_n is not None:
        compared_any = True
        if syn.synopsis_enrollment.value != body_n.value:
            discrepancies.append(
                f"sample size (synopsis N={syn.synopsis_enrollment.value} "
                f"vs body N={body_n.value})"
            )
            evidence.extend(
                [syn.synopsis_enrollment.citation, body_n.citation]
            )

    body_arms = (
        document.design.arm_count
        if document.design is not None
        and document.design.arm_count is not None
        else None
    )
    if syn.synopsis_arm_count is not None and body_arms is not None:
        compared_any = True
        if syn.synopsis_arm_count.value != body_arms.value:
            discrepancies.append(
                f"arm count (synopsis={syn.synopsis_arm_count.value} "
                f"vs body={body_arms.value})"
            )
            evidence.extend(
                [syn.synopsis_arm_count.citation, body_arms.citation]
            )

    if (
        syn.synopsis_treatment_duration_weeks is not None
        and syn.body_treatment_duration_weeks is not None
    ):
        compared_any = True
        if not weeks_match(
            syn.synopsis_treatment_duration_weeks.value,
            syn.body_treatment_duration_weeks.value,
            tolerance_weeks=DURATION_TOLERANCE_WEEKS,
        ):
            discrepancies.append(
                "treatment duration "
                f"(synopsis={syn.synopsis_treatment_duration_weeks.value:g}w "
                f"vs body={syn.body_treatment_duration_weeks.value:g}w)"
            )
            evidence.extend(
                [
                    syn.synopsis_treatment_duration_weeks.citation,
                    syn.body_treatment_duration_weeks.citation,
                ]
            )

    if not compared_any:
        return cannot_assess_outcome(
            "Insufficient synopsis and body fields to compare enrollment, "
            "arm count, or treatment duration."
        )
    if discrepancies:
        return fired_outcome(
            "Synopsis disagrees with protocol body on: "
            f"{'; '.join(discrepancies)}.",
            evidence=evidence,
        )
    return passed_outcome(
        "Synopsis enrollment, arm count, and treatment duration match the "
        "protocol body."
    )


def check_xs_08(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-08: Trial schema epochs must match Schedule of Activities epochs."""
    if document.synopsis_check is None or document.schedule is None:
        return cannot_assess_outcome(
            "SYNOPSIS_CHECK or SCHEDULE facet did not run."
        )
    schema_epochs = document.synopsis_check.schema_epochs
    if not schema_epochs or not document.schedule:
        return cannot_assess_outcome(
            "Trial schema epochs or Schedule of Activities visits are empty."
        )
    if any(ep.epoch_type == EpochType.OTHER for ep in schema_epochs) or any(
        v.epoch == EpochType.OTHER for v in document.schedule
    ):
        return cannot_assess_outcome(
            "Epoch category OTHER present in schema or schedule; cannot "
            "compare deterministically."
        )
    schema_types = {ep.epoch_type.value for ep in schema_epochs}
    schedule_types = {
        v.epoch.value for v in document.schedule if v.epoch is not None
    }
    if not schedule_types:
        return cannot_assess_outcome(
            "Schedule of Activities visits do not specify epoch types."
        )
    evidence: list[Citation] = [ep.citation for ep in schema_epochs]
    evidence.extend(
        v.citation for v in document.schedule if v.citation is not None
    )
    if schema_types != schedule_types:
        only_schema = sorted(schema_types - schedule_types)
        only_schedule = sorted(schedule_types - schema_types)
        parts: list[str] = []
        if only_schema:
            parts.append(f"only in trial schema: {', '.join(only_schema)}")
        if only_schedule:
            parts.append(
                f"only in Schedule of Activities: {', '.join(only_schedule)}"
            )
        return fired_outcome(
            "Trial schema epochs disagree with Schedule of Activities "
            f"({'; '.join(parts)}).",
            evidence=evidence,
        )
    return passed_outcome(
        "Trial schema epochs match Schedule of Activities visit epochs.",
        evidence=evidence,
    )


def check_xs_09(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-09: Stratification factors must match across synopsis, §6, §10."""
    if (
        document.synopsis_check is None
        or document.interventions is None
        or document.analysis is None
    ):
        return cannot_assess_outcome(
            "SYNOPSIS_CHECK, INTERVENTIONS, or ANALYSIS facet did not run."
        )
    syn_items = document.synopsis_check.synopsis_stratification_factors
    int_items = document.interventions.stratification_factors
    ana_items = document.analysis.primary_analysis_covariates

    all_items = [*syn_items, *int_items, *ana_items]
    if not all_items:
        return not_applicable_outcome(
            "Randomisation is not stratified in synopsis, Section 6, or "
            "Section 10."
        )
    other_items = find_other_items(all_items)
    if other_items:
        return cannot_assess_outcome(
            "Stratification factor has category OTHER; cannot compare across "
            "sections deterministically."
        )

    named_lists = [
        ("Section 1.1.2 synopsis", syn_items),
        ("Section 6.7.2 randomisation", int_items),
        ("Section 10 analysis", ana_items),
    ]
    present = [(label, items) for label, items in named_lists if items]
    if len(present) < 2:
        return cannot_assess_outcome(
            "Stratification factors extracted from only one section; cannot "
            "compare across sections."
        )
    base_label, base_items = present[0]
    mismatches: list[str] = []
    citations: list[Citation] = []
    for other_label, other_items_list in present[1:]:
        outcome = compare_category_sets(
            base_label,
            base_items,
            other_label,
            other_items_list,
            document=document,
        )
        if outcome.status != RuleStatus.PASSED:
            mismatches.append(outcome.finding.rstrip("."))
            citations.extend(outcome.evidence)
    if mismatches:
        return fired_outcome(
            f"{format_offenders(mismatches)}.",
            evidence=citations,
        )

    return passed_outcome(
        "Stratification factors match across synopsis, Section 6, and "
        "Section 10.",
        evidence=[item.citation for item in all_items],
    )


def check_xs_10(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-10: Prohibited medications must not overlap background or rescue."""
    if document.interventions is None:
        return cannot_assess_outcome("INTERVENTIONS facet did not run.")
    prohibited = document.interventions.prohibited_medications
    if not prohibited:
        return not_applicable_outcome(
            "No prohibited concomitant medications extracted."
        )

    permitted_sources: list[tuple[str, Citation, set[str]]] = []
    if document.interventions.background_therapy is not None:
        bg = document.interventions.background_therapy
        tokens = {
            _normalize_drug_token(m.group(1))
            for m in DRUG_TOKEN_PATTERN.finditer(bg.value)
        }
        permitted_sources.append(("background therapy", bg.citation, tokens))
    if document.interventions.rescue_medication_regimen is not None:
        rescue = document.interventions.rescue_medication_regimen
        tokens = {
            _normalize_drug_token(m.group(1))
            for m in DRUG_TOKEN_PATTERN.finditer(rescue.value)
        }
        permitted_sources.append(
            ("rescue medication", rescue.citation, tokens)
        )

    offenders: list[str] = []
    citations: list[Citation] = []
    for item in prohibited:
        prohibited_tokens = {
            _normalize_drug_token(m.group(1))
            for m in DRUG_TOKEN_PATTERN.finditer(item.value)
        }
        for label, perm_citation, perm_tokens in permitted_sources:
            overlap = sorted(prohibited_tokens & perm_tokens)
            if overlap:
                offenders.append(
                    f"'{item.value}' overlaps with permitted {label} "
                    f"({', '.join(overlap)})"
                )
                citations.extend([item.citation, perm_citation])
    if offenders:
        return fired_outcome(
            f"Prohibited medication overlap: {format_offenders(offenders)}.",
            evidence=citations,
        )
    return passed_outcome(
        "No prohibited medications overlap with permitted background or "
        "rescue therapies.",
        evidence=[item.citation for item in prohibited],
    )


def check_xs_12(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-12: Oversight committees in synopsis must match governance."""
    if document.synopsis_check is None:
        return cannot_assess_outcome("SYNOPSIS_CHECK facet did not run.")
    syn_comm = document.synopsis_check.synopsis_committees
    gov_comm = document.synopsis_check.governance_committees
    if not syn_comm and not gov_comm:
        return not_applicable_outcome(
            "No oversight committees listed in synopsis or governance section."
        )
    return compare_category_sets(
        "Section 1.1.2 synopsis",
        syn_comm,
        "Section 11.4 governance",
        gov_comm,
        document=document,
    )


def check_xs_13(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-13: Interim analysis in §10 requires stopping boundaries and DMC."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    has_interim = document.analysis.has_interim_analysis
    if has_interim is None:
        return cannot_assess_outcome(
            "Whether an interim analysis is planned could not be determined."
        )
    if not has_interim.value:
        return not_applicable_outcome("No interim analysis is planned.")

    has_dmc = (
        document.design is not None
        and document.design.has_data_monitoring_committee is not None
        and document.design.has_data_monitoring_committee.value
    ) or (
        document.synopsis_check is not None
        and any(
            c.category == CommitteeType.DATA_MONITORING
            for c in document.synopsis_check.governance_committees
        )
    )
    missing: list[str] = []
    if document.analysis.stopping_boundaries is None:
        missing.append("trial stopping boundaries")
    if not has_dmc:
        missing.append("Data Monitoring Committee (DMC) oversight")

    if missing:
        return absence_fired_outcome(
            "An interim analysis is planned in Section 10, but "
            f"{' and '.join(missing)} are missing."
        )
    assert document.analysis.stopping_boundaries is not None
    return passed_outcome(
        "Interim analysis is paired with stopping boundaries and DMC "
        "oversight.",
        evidence=[
            has_interim.citation,
            document.analysis.stopping_boundaries.citation,
        ],
    )


def check_xs_15(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-15: Biospecimen retention years in §8 must match consent in §11.3."""
    if document.synopsis_check is None:
        return cannot_assess_outcome("SYNOPSIS_CHECK facet did not run.")
    sec8 = document.synopsis_check.assessments_retention_years
    sec11 = document.synopsis_check.icf_retention_years
    if sec8 is None and sec11 is None:
        return not_applicable_outcome(
            "No biological sample retention period stated in Section 8 or "
            "Section 11.3."
        )
    if sec8 is None or sec11 is None:
        return absence_fired_outcome(
            "Biological sample retention duration is stated in only one of "
            "Section 8 and Section 11.3."
        )
    if abs(sec8.value - sec11.value) > 1e-6:
        return fired_outcome(
            f"Sample retention period in Section 8 ({sec8.value:g} years) "
            f"disagrees with Section 11.3 ({sec11.value:g} years).",
            evidence=[sec8.citation, sec11.citation],
        )
    return passed_outcome(
        f"Biospecimen retention period ({sec8.value:g} years) matches across "
        "Section 8 and Section 11.3.",
        evidence=[sec8.citation, sec11.citation],
    )


def _extract_criteria_age_bounds(
    document: ProtocolDocument,
) -> tuple[float | None, float | None, Citation | None]:
    if not document.eligibility_criteria:
        return None, None, None
    for crit in document.eligibility_criteria:
        if crit.kind != CriterionKind.INCLUSION:
            continue
        range_match = AGE_RANGE_PATTERN.search(crit.text)
        if range_match is not None:
            return (
                float(range_match.group(1)),
                float(range_match.group(2)),
                crit.citation,
            )
        min_match = MIN_AGE_PATTERN.search(crit.text)
        max_match = MAX_AGE_PATTERN.search(crit.text)
        if min_match is not None or max_match is not None:
            low = float(min_match.group(1)) if min_match is not None else None
            high = float(max_match.group(1)) if max_match is not None else None
            return low, high, crit.citation
    return None, None, None


def check_xs_18(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-18: Participant age bounds must match across design and criteria."""
    if document.design is None or document.eligibility_criteria is None:
        return cannot_assess_outcome(
            "DESIGN or ELIGIBILITY facet did not run."
        )
    crit_min, crit_max, crit_cit = _extract_criteria_age_bounds(document)
    if crit_min is None and crit_max is None:
        return cannot_assess_outcome(
            "Could not parse numeric age bounds from inclusion criteria."
        )
    design_min = document.design.min_age_years
    design_max = document.design.max_age_years
    if design_min is None and design_max is None:
        return cannot_assess_outcome(
            "No age bounds extracted in trial design facts."
        )

    mismatches: list[str] = []
    evidence: list[Citation] = []
    if (
        crit_min is not None
        and design_min is not None
        and abs(crit_min - design_min.value) > 1e-6
    ):
        mismatches.append(
            f"minimum age (design={design_min.value:g} vs "
            f"criteria={crit_min:g})"
        )
        evidence.append(design_min.citation)
    if (
        crit_max is not None
        and design_max is not None
        and abs(crit_max - design_max.value) > 1e-6
    ):
        mismatches.append(
            f"maximum age (design={design_max.value:g} vs "
            f"criteria={crit_max:g})"
        )
        evidence.append(design_max.citation)
    if crit_cit is not None:
        evidence.append(crit_cit)

    if mismatches:
        return fired_outcome(
            "Participant age limits differ between synopsis/design and "
            f"inclusion criteria: {'; '.join(mismatches)}.",
            evidence=evidence,
        )
    if design_min is not None:
        evidence.insert(0, design_min.citation)
    return passed_outcome(
        "Participant age bounds match across design and inclusion criteria.",
        evidence=evidence,
    )


def check_xs_20(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-20: Synopsis total participant duration must match sum of epochs."""
    if document.synopsis_check is None:
        return cannot_assess_outcome("SYNOPSIS_CHECK facet did not run.")
    syn_dur = document.synopsis_check.synopsis_treatment_duration_weeks
    epochs = document.synopsis_check.schema_epochs
    if syn_dur is None or not epochs:
        return cannot_assess_outcome(
            "Synopsis duration or trial schema epochs are absent."
        )
    if any(ep.duration_weeks is None for ep in epochs):
        return cannot_assess_outcome(
            "One or more trial schema epochs lack a numeric duration in weeks."
        )
    total_weeks = sum(ep.duration_weeks or 0.0 for ep in epochs)
    treatment_weeks = sum(
        ep.duration_weeks or 0.0
        for ep in epochs
        if ep.epoch_type == EpochType.TREATMENT
    )
    evidence = [syn_dur.citation, *(ep.citation for ep in epochs)]
    if weeks_match(
        syn_dur.value, total_weeks, tolerance_weeks=DURATION_TOLERANCE_WEEKS
    ) or (
        treatment_weeks > 0.0
        and weeks_match(
            syn_dur.value,
            treatment_weeks,
            tolerance_weeks=DURATION_TOLERANCE_WEEKS,
        )
    ):
        return passed_outcome(
            f"Synopsis duration ({syn_dur.value:g} weeks) matches the trial "
            "schema epoch durations.",
            evidence=evidence,
        )
    return fired_outcome(
        f"Synopsis duration ({syn_dur.value:g} weeks) does not equal the sum "
        f"of trial schema epochs ({total_weeks:g} weeks).",
        evidence=evidence,
    )


def _glossary_defined_acronyms(document: ProtocolDocument) -> set[str]:
    """Return acronyms defined in an abbreviations or glossary list."""
    glossary_pages: set[int] = set()
    for sec in document.sections or []:
        if GLOSSARY_HEADER_PATTERN.search(sec.title) is not None:
            glossary_pages.update(range(sec.start_page, sec.end_page + 1))
    for sub in document.subsections or []:
        if GLOSSARY_HEADER_PATTERN.search(sub.title) is not None:
            glossary_pages.add(sub.page_number)

    defined: set[str] = set()
    for page in document.pages:
        is_glossary_page = (
            page.page_number in glossary_pages
            or GLOSSARY_HEADER_PATTERN.search(page.text) is not None
        )
        if not is_glossary_page:
            continue
        for match in GLOSSARY_ENTRY_PATTERN.finditer(page.text):
            acronym = match.group(1)
            if acronym not in COMMON_ROMAN_OR_UNITS:
                defined.add(acronym)
    return defined


def check_xs_21(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-21: Acronyms must not be used on an earlier page before expansion."""
    if document.sections is None:
        return cannot_assess_outcome("SECTIONS facet did not run.")
    if not document.pages:
        return cannot_assess_outcome("Protocol has no pages to scan.")

    glossary_acronyms = _glossary_defined_acronyms(document)
    first_def_page: dict[str, int] = {
        acronym: 1 for acronym in glossary_acronyms
    }
    for page in document.pages:
        for match in ABBREVIATION_DEF_PATTERN.finditer(page.text):
            acronym = match.group(1)
            if acronym in COMMON_ROMAN_OR_UNITS:
                continue
            if acronym not in first_def_page:
                first_def_page[acronym] = page.page_number

    offenders: list[str] = []
    citations: list[Citation] = []
    for acronym, def_page in sorted(first_def_page.items()):
        token_pattern = re.compile(rf"\b{re.escape(acronym)}\b")
        for page in document.pages:
            if page.page_number >= def_page:
                break
            if token_pattern.search(page.text) is not None:
                offenders.append(
                    f"'{acronym}' (page {page.page_number} before definition "
                    f"on page {def_page})"
                )
                early_cit = find_pattern_citation(document, token_pattern)
                if early_cit is not None:
                    citations.append(early_cit)
                break

    if offenders:
        return fired_outcome(
            f"Abbreviation(s) used before expansion and absent from "
            f"glossary: {format_offenders(offenders)}.",
            evidence=citations,
        )

    return passed_outcome(
        "No abbreviations were found used on an earlier page before their "
        "expansion or glossary entry."
    )


def _heading_exists_in_pages(document: ProtocolDocument, target: str) -> bool:
    """Return True if a heading line starting with target appears in pages."""
    heading_pattern = re.compile(
        rf"^\s*{re.escape(target)}\.?\s+\S", re.MULTILINE
    )
    return any(
        heading_pattern.search(page.text) is not None
        for page in document.pages
    )


def check_xs_22(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """XS-22: Internal 'Section X.Y' cross-references must exist."""
    if document.subsections is None or not document.subsections:
        return cannot_assess_outcome(
            "Protocol subsection map is unavailable or empty."
        )
    known_numbers: set[str] = set()
    for sub in document.subsections:
        cleaned = sub.number.strip().rstrip(".")
        known_numbers.add(cleaned)
        parts = cleaned.split(".")
        for idx in range(1, len(parts)):
            known_numbers.add(".".join(parts[: idx + 1]))

    offenders: list[str] = []
    citations: list[Citation] = []
    seen_targets: set[tuple[str, int]] = set()
    for page in document.pages:
        for match in SECTION_XREF_PATTERN.finditer(page.text):
            target = match.group(1).rstrip(".")
            if target in known_numbers:
                continue
            if _heading_exists_in_pages(document, target):
                known_numbers.add(target)
                continue
            key = (target, page.page_number)
            if key in seen_targets:
                continue
            seen_targets.add(key)
            offenders.append(f"'Section {target}' (page {page.page_number})")
            cit = find_pattern_citation(
                document,
                re.compile(
                    rf"\bSection\s+{re.escape(target)}\b", re.IGNORECASE
                ),
            )
            if cit is not None:
                citations.append(cit)

    if offenders:
        return fired_outcome(
            f"In-text cross-reference(s) do not match any numbered heading "
            f"in the protocol: {format_offenders(offenders)}.",
            evidence=citations,
        )

    return passed_outcome(
        "All internal 'Section X.Y' cross-references match extracted "
        "subsection headings."
    )


CONSISTENCY_CHECKS: dict[str, DeterministicCheck] = {
    "XS-03": check_xs_03,
    "XS-04": check_xs_04,
    "XS-05": check_xs_05,
    "XS-07": check_xs_07,
    "XS-08": check_xs_08,
    "XS-09": check_xs_09,
    "XS-10": check_xs_10,
    "XS-12": check_xs_12,
    "XS-13": check_xs_13,
    "XS-15": check_xs_15,
    "XS-18": check_xs_18,
    "XS-20": check_xs_20,
    "XS-21": check_xs_21,
    "XS-22": check_xs_22,
}
