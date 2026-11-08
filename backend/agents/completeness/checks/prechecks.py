"""Measurable code pre-checks for judgement rules (no LLM call)."""

import re
from collections.abc import Callable, Mapping

from backend.agents.completeness.checks.common import (
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
    M11Heading,
    ProtocolDocument,
    TrialProfile,
)

type JudgementPrecheck = Callable[
    [ProtocolDocument, TrialProfile], CheckOutcome | None
]

CONTINUOUS_CHANGE_PATTERN = re.compile(
    r"\bchange\s+from\s+baseline\b", re.IGNORECASE
)
RESPONDER_TERM_PATTERN = re.compile(
    r"(?:\b(?:proportion|percentage|rate|responder|achieving)\b|[<≤])",
    re.IGNORECASE,
)
HBA1C_PATTERN = re.compile(
    r"\b(?:hba1c|a1c|glycated\s+ha?emoglobin)\b", re.IGNORECASE
)
HYPOGLYCEMIA_ENDPOINT_PATTERN = re.compile(
    r"\bhypoglyc(?:a?emia|emic)\b", re.IGNORECASE
)

# REG-39: first-person wording. Case-sensitive so "US" (the country) does
# not match the pronoun "us".
FIRST_PERSON_PATTERN = re.compile(r"\b(?:[Ww]e|[Oo]ur|us)\b")

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
}
