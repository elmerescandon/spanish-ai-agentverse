"""Measurable code pre-checks for judgement rules (no LLM call)."""

import re
from collections.abc import Callable, Mapping

from backend.agents.completeness.checks.common import (
    CGM_TIR_PATTERN,
    CONTINUOUS_CHANGE_PATTERN,
    HBA1C_PATTERN,
    HYPOGLYCEMIA_ENDPOINT_PATTERN,
    RESPONDER_TERM_PATTERN,
    absence_fired_outcome,
    extract_all_timepoints_weeks,
    find_pattern_citation,
    fired_outcome,
    not_applicable_outcome,
    passed_outcome,
)
from backend.agents.completeness.logic import CheckOutcome
from backend.shared.messages import (
    Citation,
    ControlType,
    DrugClass,
    EndpointKind,
    EpochType,
    EstimandStrategy,
    InterventionType,
    M11Heading,
    ProtocolDocument,
    TrialPhase,
    TrialProfile,
)

type JudgementPrecheck = Callable[
    [ProtocolDocument, TrialProfile], CheckOutcome | None
]

# REG-39: first-person wording. Case-sensitive so "US" (the country) does
# not match the pronoun "us".
BMI_PATTERN = re.compile(r"\bbmi\b|body\s+mass\s+index", re.IGNORECASE)
FIRST_PERSON_PATTERN = re.compile(r"\b(?:[Ww]e|[Oo]ur|us)\b")

HYS_LAW_PATTERN = re.compile(r"\bhy['’]?s\s+law\b", re.IGNORECASE)
# DM-42: validated diabetes-specific PROs. Acronyms are case-sensitive so
# "PAID" does not match "participants will be paid".
DIABETES_PRO_PATTERN = re.compile(
    r"\b(?:DTSQ[sc]?|DQOL|ADDQoL|PAID|HFS(?:-II)?|DDS)\b"
    r"|(?i:diabetes\s+treatment\s+satisfaction|diabetes\s+distress"
    r"|hypoglyc(?:a)?emia\s+fear)"
)
PHONE_CONTACT_PATTERN = re.compile(
    r"\b(?:tele)?phone\b|\bcall\b|\bremote\b|\bvirtual\b", re.IGNORECASE
)
SHORT_TRIAL_WEEKS = 8.0  # below this, HbA1c cannot show the full effect
CONFIRMATORY_PHASES = frozenset({TrialPhase.PHASE3, TrialPhase.PHASE4})
SMALL_MOLECULE_CLASSES = frozenset(
    {
        DrugClass.METFORMIN,
        DrugClass.SULFONYLUREA,
        DrugClass.DPP4_INHIBITOR,
        DrugClass.SGLT2_INHIBITOR,
        DrugClass.TZD,
    }
)

MIN_SIX_MONTH_WEEKS = 25.0
MAX_THREE_MONTH_WEEKS = 13.0
MAX_SIX_MONTH_WEEKS = 26.5
MAX_HBA1C_NI_MARGIN_PERCENT = 0.3
MAX_HBA1C_NI_MARGIN_MMOL_MOL = 3.0
MMOL_MOL_CUTOFF = 1.5


def precheck_est_07(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """EST-07: N/A when no secondary endpoints are defined; else Gemini."""
    if document.endpoints is None or not document.endpoints:
        return None
    has_secondary = any(
        ep.kind == EndpointKind.SECONDARY for ep in document.endpoints
    )
    if not has_secondary:
        return not_applicable_outcome(
            "No secondary endpoints are defined in Section 3."
        )
    return None


def precheck_est_08(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """EST-08: Passes when primary endpoint is continuous change from base."""
    if document.endpoints is None:
        return None
    primaries = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    if not primaries:
        return None
    if all(
        CONTINUOUS_CHANGE_PATTERN.search(ep.description) is not None
        and RESPONDER_TERM_PATTERN.search(ep.description) is None
        for ep in primaries
    ):
        return passed_outcome(
            "Primary endpoint is a continuous change-from-baseline measure.",
            evidence=[primaries[0].citation],
        )
    return None


def precheck_est_13(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """EST-13: Fires (second opinion) when missing_data_method is None."""
    if document.analysis is None:
        return None
    method = document.analysis.missing_data_method
    if method is None or not method.value.strip():
        return absence_fired_outcome(
            "Section 10 omits a missing-data handling or imputation method."
        )
    return None


def precheck_est_23(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """EST-23: Passes with cited source; fires when source is absent."""
    if document.statistics is None:
        return None
    stats = document.statistics
    if (
        stats.assumptions_source_citation is not None
        and stats.assumptions_source_citation.value.strip()
    ):
        return passed_outcome(
            "Sample-size assumptions cite an empirical source: "
            f"'{stats.assumptions_source_citation.value}'.",
            evidence=[stats.assumptions_source_citation.citation],
        )
    has_effect_or_sd = (
        stats.effect_size is not None
        or stats.effect_size_value is not None
        or stats.standard_deviation is not None
    )
    if stats.assumptions_source_citation is None and has_effect_or_sd:
        return absence_fired_outcome(
            "Sample-size calculation states an effect size or standard "
            "deviation without citing an empirical source."
        )
    return None


def precheck_est_24(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """EST-24: Fires when non_inferiority_margin is absent; else Gemini."""
    if document.statistics is None:
        return None
    if document.statistics.non_inferiority_margin is None:
        return absence_fired_outcome(
            "Non-inferiority protocol does not specify a non-inferiority "
            "margin."
        )
    return None


def precheck_est_25(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """EST-25: N/A when primary estimand does not use treatment policy."""
    if document.estimands is None or not document.estimands.estimands:
        return None
    ices = [
        ice
        for est in document.estimands.estimands
        if est.endpoint_kind == EndpointKind.PRIMARY
        for ice in est.intercurrent_events
    ]
    if not ices:
        return None
    if any(ice.strategy == EstimandStrategy.OTHER for ice in ices):
        return None
    if not any(
        ice.strategy == EstimandStrategy.TREATMENT_POLICY for ice in ices
    ):
        return not_applicable_outcome(
            "Primary estimand does not use a treatment-policy strategy."
        )
    return None


def precheck_dm_01(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-01: Passes when primary endpoint is change from baseline in HbA1c."""
    if document.endpoints is None:
        return None
    primaries = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    for ep in primaries:
        if (
            CONTINUOUS_CHANGE_PATTERN.search(ep.description) is not None
            and HBA1C_PATTERN.search(ep.description) is not None
        ):
            return passed_outcome(
                "Primary efficacy endpoint is change from baseline in HbA1c.",
                evidence=[ep.citation],
            )
    return None


def precheck_dm_02(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-02: Passes when primary assessment is at >= 26 weeks."""
    if document.endpoints is None:
        return None
    primaries = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    for ep in primaries:
        combined = f"{ep.description} {ep.time_frame or ''}"
        weeks = [w for w in extract_all_timepoints_weeks(combined) if w > 0.0]
        if weeks and max(weeks) >= MIN_SIX_MONTH_WEEKS:
            return passed_outcome(
                f"Primary efficacy assessment occurs at Week {max(weeks):g} "
                "(>= 26 weeks).",
                evidence=[ep.citation],
            )
    return None


def _treatment_duration_weeks(
    document: ProtocolDocument,
) -> tuple[float, Citation] | None:
    syn = document.synopsis_check
    if syn is None:
        return None
    if syn.body_treatment_duration_weeks is not None:
        return (
            syn.body_treatment_duration_weeks.value,
            syn.body_treatment_duration_weeks.citation,
        )
    if syn.synopsis_treatment_duration_weeks is not None:
        return (
            syn.synopsis_treatment_duration_weeks.value,
            syn.synopsis_treatment_duration_weeks.citation,
        )
    for ep in syn.schema_epochs:
        if (
            ep.epoch_type == EpochType.TREATMENT
            and ep.duration_weeks is not None
        ):
            return (ep.duration_weeks, ep.citation)
    return None


def precheck_dm_11(
    document: ProtocolDocument, profile: TrialProfile
) -> CheckOutcome | None:
    """DM-11: N/A when trial is add-on or placebo duration <= 3 months."""
    if profile.is_add_on is not None and profile.is_add_on.value is True:
        return not_applicable_outcome(
            "Trial is an add-on study, not placebo monotherapy.",
            evidence=[profile.is_add_on.citation],
        )
    dur = _treatment_duration_weeks(document)
    if dur is not None and dur[0] <= MAX_THREE_MONTH_WEEKS:
        return not_applicable_outcome(
            f"Placebo exposure is {dur[0]:g} weeks (<= 3 months).",
            evidence=[dur[1]],
        )
    return None


def precheck_dm_12(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-12: Passes when placebo duration does not exceed 6 months (26w)."""
    dur = _treatment_duration_weeks(document)
    if dur is not None and dur[0] <= MAX_SIX_MONTH_WEEKS:
        return passed_outcome(
            f"Placebo-controlled treatment duration is {dur[0]:g} weeks "
            "(<= 26 weeks).",
            evidence=[dur[1]],
        )
    return None


def precheck_dm_15(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-15: Fires when HbA1c NI margin > 0.3% (3 mmol/mol) or is absent."""
    if document.statistics is None:
        return None
    margin = document.statistics.non_inferiority_margin
    if margin is None:
        return absence_fired_outcome(
            "Non-inferiority trial omits the HbA1c non-inferiority margin."
        )
    val = margin.value
    exceeds_percent = (
        val <= MMOL_MOL_CUTOFF and val > MAX_HBA1C_NI_MARGIN_PERCENT
    )
    exceeds_mmol = val > MMOL_MOL_CUTOFF and val > MAX_HBA1C_NI_MARGIN_MMOL_MOL
    if exceeds_percent or exceeds_mmol:
        return fired_outcome(
            f"HbA1c non-inferiority margin ({val:g}) exceeds the 0.3% "
            "(3 mmol/mol) threshold.",
            evidence=[margin.citation],
        )
    return None


def precheck_dm_20(
    document: ProtocolDocument, profile: TrialProfile
) -> CheckOutcome | None:
    """DM-20: Passes when comparator arm is not placebo."""
    if (
        profile.control_type is not None
        and profile.control_type.value != ControlType.PLACEBO
    ):
        return passed_outcome(
            f"Comparator arm is {profile.control_type.value}, not placebo.",
            evidence=[profile.control_type.citation],
        )
    if document.interventions is not None and document.interventions.arms:
        controls = [
            arm for arm in document.interventions.arms if arm.is_control
        ]
        if controls and all(
            arm.control_type is not None
            and arm.control_type != ControlType.PLACEBO
            for arm in controls
        ):
            return passed_outcome(
                "No placebo comparator arm is used in the trial.",
                evidence=[controls[0].citation],
            )
    return None


def precheck_dm_32(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-32: N/A when no endpoint targets hypoglycaemia."""
    if document.endpoints is None or not document.endpoints:
        return None
    has_hypo = any(
        HYPOGLYCEMIA_ENDPOINT_PATTERN.search(ep.description) is not None
        for ep in document.endpoints
    )
    if not has_hypo:
        return not_applicable_outcome(
            "No primary or secondary endpoint targets hypoglycaemia reduction."
        )
    return None


def precheck_dm_43(
    _document: ProtocolDocument, profile: TrialProfile
) -> CheckOutcome | None:
    """DM-43: N/A when the investigational drug is an insulin."""
    if (
        profile.drug_class is not None
        and profile.drug_class.value == DrugClass.INSULIN
    ):
        return not_applicable_outcome(
            "Investigational drug is an insulin, not a non-insulin adjunct.",
            evidence=[profile.drug_class.citation],
        )
    return None


def precheck_reg_17(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """REG-17: Fires when a design pick-list field is missing.

    When all five are stated, Gemini judges study type and primary purpose,
    which the parser does not extract.
    """
    design = document.design
    if design is None:
        return None
    fields = {
        "phase": design.phase,
        "allocation": design.allocation,
        "intervention model": design.intervention_model,
        "masking": design.masking,
        "number of arms": design.arm_count,
    }
    missing = [name for name, value in fields.items() if value is None]
    if not missing:
        return None
    return absence_fired_outcome(
        f"Design fields not stated: {', '.join(missing)}."
    )


def precheck_reg_21(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """REG-21: Fires when an arm has no dose or regimen; else Gemini."""
    if document.interventions is None:
        return None
    undosed = [
        arm
        for arm in document.interventions.arms
        if arm.dose_and_regimen is None or not arm.dose_and_regimen.strip()
    ]
    if not undosed:
        return None
    names = ", ".join(arm.name for arm in undosed)
    return fired_outcome(
        f"No dose, route, frequency or duration found for: {names}.",
        evidence=[arm.citation for arm in undosed],
        needs_second_opinion=True,
    )


def precheck_reg_39(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """REG-39: Fires on first-person summary wording; else Gemini decides.

    Gemini still checks the sponsor fields for personal names.
    """
    citation = find_pattern_citation(
        document, FIRST_PERSON_PATTERN, (M11Heading.PROTOCOL_SUMMARY,)
    )
    if citation is None:
        return None
    return fired_outcome(
        "The protocol summary is written in the first person.",
        evidence=[citation],
    )


def precheck_elq_12(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """ELQ-12: Passes with no upper age limit; else Gemini judges it."""
    if document.design is None or document.design.max_age_years is not None:
        return None
    return passed_outcome("No upper age limit is set.")


def precheck_elq_19(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """ELQ-19: Passes when no criterion mentions BMI; else Gemini judges."""
    if document.eligibility_criteria is None:
        return None
    if any(
        BMI_PATTERN.search(c.text) is not None
        for c in document.eligibility_criteria
    ):
        return None
    return passed_outcome("No eligibility criterion limits BMI.")


def precheck_dm_09(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-09: Not applicable when the primary timepoint is 8 weeks or more."""
    if document.endpoints is None:
        return None
    weeks = [
        week
        for ep in document.endpoints
        if ep.kind == EndpointKind.PRIMARY and ep.time_frame
        for week in extract_all_timepoints_weeks(ep.time_frame)
    ]
    if not weeks or max(weeks) < SHORT_TRIAL_WEEKS:
        return None
    return not_applicable_outcome(
        f"the primary assessment is at week {max(weeks):g}, not a short trial"
    )


def precheck_dm_10(
    _document: ProtocolDocument, profile: TrialProfile
) -> CheckOutcome | None:
    """DM-10: Not applicable in phase 3 or 4; else Gemini decides."""
    if profile.phase is None or profile.phase.value not in CONFIRMATORY_PHASES:
        return None
    return not_applicable_outcome(
        "a confirmatory phase trial is not a dose-ranging study",
        evidence=[profile.phase.citation],
    )


def _no_endpoint_matches(
    document: ProtocolDocument, pattern: re.Pattern[str], reason: str
) -> CheckOutcome | None:
    """Not applicable when no endpoint matches pattern; else Gemini."""
    if document.endpoints is None:
        return None
    if any(pattern.search(ep.description) for ep in document.endpoints):
        return None
    return not_applicable_outcome(reason)


def precheck_dm_30(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-30: Not applicable without a hypoglycaemia endpoint."""
    return _no_endpoint_matches(
        document,
        HYPOGLYCEMIA_ENDPOINT_PATTERN,
        "no endpoint measures hypoglycaemia",
    )


def precheck_dm_33(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-33: Not applicable without a CGM endpoint."""
    return _no_endpoint_matches(
        document, CGM_TIR_PATTERN, "no endpoint uses CGM"
    )


def precheck_dm_35(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-35: Passes when CV events are adjudicated; else Gemini judges."""
    monitoring = document.safety_monitoring
    if monitoring is None or monitoring.has_cv_adjudication is None:
        return None
    if not monitoring.has_cv_adjudication.value:
        return None
    return passed_outcome(
        "Cardiovascular events are adjudicated.",
        evidence=[monitoring.has_cv_adjudication.citation],
    )


def precheck_dm_36(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-36: Passes on Hy's law liver rules; else Gemini judges."""
    citation = find_pattern_citation(document, HYS_LAW_PATTERN)
    if citation is None:
        return None
    return passed_outcome(
        "Liver monitoring follows Hy's law rules.", evidence=[citation]
    )


def precheck_dm_38(
    _document: ProtocolDocument, profile: TrialProfile
) -> CheckOutcome | None:
    """DM-38: Not applicable for small-molecule classes; else Gemini."""
    if (
        profile.intervention_type is not None
        and profile.intervention_type.value == InterventionType.BIOLOGIC
    ):
        return None
    if (
        profile.drug_class is None
        or profile.drug_class.value not in SMALL_MOLECULE_CLASSES
    ):
        return None
    return not_applicable_outcome(
        "the drug is a small molecule, not a protein or peptide",
        evidence=[profile.drug_class.citation],
    )


def precheck_dm_42(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """DM-42: Passes on a named diabetes PRO; else Gemini judges."""
    citation = find_pattern_citation(document, DIABETES_PRO_PATTERN)
    if citation is None:
        return None
    return passed_outcome(
        "A validated diabetes-specific PRO is used.", evidence=[citation]
    )


def precheck_m11_01(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """M11-01: Fires when a main section is missing; else Gemini decides.

    Gemini still checks heading names and order.
    """
    if document.sections is None:
        return None
    present = {section.heading for section in document.sections}
    missing = [
        heading.value
        for heading in M11Heading
        if heading != M11Heading.OTHER and heading not in present
    ]
    if not missing:
        return None
    return absence_fired_outcome(
        f"No section found for: {', '.join(missing)}."
    )


def precheck_m11_07(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """M11-07: Fires without a full title or phase; else Gemini decides.

    Gemini still checks the protocol ID and version.
    """
    design = document.design
    if design is None:
        return None
    missing = [
        name
        for name, value in (
            ("full title", design.official_title),
            ("phase", design.phase),
        )
        if value is None
    ]
    if not missing:
        return None
    return absence_fired_outcome(
        f"The title page does not state: {', '.join(missing)}."
    )


def precheck_m11_18(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """M11-18: Passes when the summary lists committees; else Gemini."""
    if document.synopsis_check is None:
        return None
    committees = document.synopsis_check.synopsis_committees
    if not committees:
        return None
    return passed_outcome(
        "The protocol summary lists the trial committees.",
        evidence=[item.citation for item in committees],
    )


def precheck_m11_19(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """M11-19: Passes when a schema with epochs was found; else Gemini."""
    if document.synopsis_check is None:
        return None
    epochs = document.synopsis_check.schema_epochs
    if not epochs:
        return None
    return passed_outcome(
        "The trial schema shows the trial epochs.",
        evidence=[epoch.citation for epoch in epochs],
    )


def precheck_m11_20(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome | None:
    """M11-20: Fires with no schedule; passes with phone contacts.

    Otherwise Gemini decides whether phone contacts are needed.
    """
    if document.schedule is None:
        return None
    if not document.schedule:
        return absence_fired_outcome("No schedule of activities was found.")
    phone_visits = [
        visit
        for visit in document.schedule
        if PHONE_CONTACT_PATTERN.search(
            " ".join([visit.visit_name, *visit.procedures])
        )
    ]
    if not phone_visits:
        return None
    return passed_outcome(
        "The schedule of activities includes telephone contacts.",
        evidence=[v.citation for v in phone_visits if v.citation],
    )


def precheck_m11_27(
    _document: ProtocolDocument, profile: TrialProfile
) -> CheckOutcome | None:
    """M11-27: Passes when superiority or non-inferiority is stated."""
    if profile.is_non_inferiority is None:
        return None
    kind = (
        "non-inferiority"
        if profile.is_non_inferiority.value
        else "superiority"
    )
    return passed_outcome(
        f"The design is stated as a {kind} trial.",
        evidence=[profile.is_non_inferiority.citation],
    )


JUDGEMENT_PRECHECKS: Mapping[str, JudgementPrecheck] = {
    "EST-07": precheck_est_07,
    "EST-08": precheck_est_08,
    "EST-13": precheck_est_13,
    "EST-23": precheck_est_23,
    "EST-24": precheck_est_24,
    "EST-25": precheck_est_25,
    "DM-01": precheck_dm_01,
    "DM-02": precheck_dm_02,
    "DM-11": precheck_dm_11,
    "DM-12": precheck_dm_12,
    "DM-15": precheck_dm_15,
    "DM-20": precheck_dm_20,
    "DM-32": precheck_dm_32,
    "DM-43": precheck_dm_43,
    "REG-17": precheck_reg_17,
    "REG-21": precheck_reg_21,
    "REG-39": precheck_reg_39,
    "ELQ-12": precheck_elq_12,
    "ELQ-19": precheck_elq_19,
    "DM-09": precheck_dm_09,
    "DM-10": precheck_dm_10,
    "DM-30": precheck_dm_30,
    "DM-33": precheck_dm_33,
    "DM-35": precheck_dm_35,
    "DM-36": precheck_dm_36,
    "DM-38": precheck_dm_38,
    "DM-42": precheck_dm_42,
    "M11-01": precheck_m11_01,
    "M11-07": precheck_m11_07,
    "M11-18": precheck_m11_18,
    "M11-19": precheck_m11_19,
    "M11-20": precheck_m11_20,
    "M11-27": precheck_m11_27,
}
