"""Family DM deterministic checks: diabetes S1 blockers (7 rules)."""

import re

from backend.agents.completeness.checks.common import (
    absence_fired_outcome,
    cannot_assess_outcome,
    fired_outcome,
    format_offenders,
    passed_outcome,
)
from backend.agents.completeness.logic import CheckOutcome, DeterministicCheck
from backend.shared.messages import (
    Citation,
    EndpointKind,
    Estimand,
    IntercurrentEventType,
    ProtocolDocument,
    TrialProfile,
)

CGM_TIR_PATTERN = re.compile(
    r"\b(?:time[\s\-]+in[\s\-]+range|tir|"
    r"continuous\s+glucose\s+monitoring|cgm)\b",
    re.IGNORECASE,
)

MIN_STABLE_BACKGROUND_WEEKS = 8.0
ADA_LEVEL_1_MG_DL = 70.0
ADA_LEVEL_2_MG_DL = 54.0
GLUCOSE_TOLERANCE_MG_DL = 0.5

REQUIRED_DIABETES_ICES: tuple[IntercurrentEventType, ...] = (
    IntercurrentEventType.RESCUE_MEDICATION,
    IntercurrentEventType.TREATMENT_DISCONTINUATION,
    IntercurrentEventType.BACKGROUND_THERAPY_CHANGE,
)


def _primary_estimand(document: ProtocolDocument) -> Estimand | None:
    if document.estimands is None:
        return None
    for estimand in document.estimands.estimands:
        if estimand.endpoint_kind == EndpointKind.PRIMARY:
            return estimand
    return (
        document.estimands.estimands[0]
        if document.estimands.estimands
        else None
    )


def check_dm_06(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-06: CGM time-in-range must not be the primary glycaemic endpoint."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    primaries = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    if not primaries:
        return cannot_assess_outcome("No primary endpoint extracted.")

    offenders: list[str] = []
    citations: list[Citation] = []
    for ep in primaries:
        if CGM_TIR_PATTERN.search(ep.description) is not None:
            offenders.append(f"'{ep.description}'")
            citations.append(ep.citation)
    if offenders:
        return fired_outcome(
            f"Primary endpoint(s) use continuous glucose monitoring (CGM) "
            f"time-in-range rather than HbA1c: {format_offenders(offenders)}.",
            evidence=citations,
        )
    return passed_outcome(
        "Primary efficacy endpoint does not use CGM time-in-range.",
        evidence=[primaries[0].citation],
    )


def check_dm_13(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-13: Section 6 must define a pre-specified glycaemic rescue plan."""
    if document.interventions is None:
        return cannot_assess_outcome("INTERVENTIONS facet did not run.")
    criteria = document.interventions.rescue_therapy_criteria
    regimen = document.interventions.rescue_medication_regimen
    missing: list[str] = []
    if criteria is None or not criteria.value.strip():
        missing.append("glycaemic rescue thresholds")
    if regimen is None or not regimen.value.strip():
        missing.append("rescue medication regimen")
    if missing:
        return absence_fired_outcome(
            "Section 6 omits pre-specified glycaemic rescue elements: "
            f"{', '.join(missing)}."
        )
    assert criteria is not None and regimen is not None
    return passed_outcome(
        "Section 6 defines both glycaemic rescue criteria and rescue "
        "medication regimen.",
        evidence=[criteria.citation, regimen.citation],
    )


def check_dm_17(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-17: Add-on trials require >= 8w stable background therapy."""
    if document.interventions is None:
        return cannot_assess_outcome("INTERVENTIONS facet did not run.")
    stable_weeks = document.interventions.background_therapy_stable_weeks
    if stable_weeks is None:
        return absence_fired_outcome(
            "Protocol does not specify a required duration of stable "
            "background antidiabetic therapy before randomisation."
        )
    if stable_weeks.value < MIN_STABLE_BACKGROUND_WEEKS:
        return fired_outcome(
            f"Required stable background therapy duration "
            f"({stable_weeks.value:g} weeks) is shorter than the minimum "
            f"{MIN_STABLE_BACKGROUND_WEEKS:g} weeks.",
            evidence=[stable_weeks.citation],
        )
    return passed_outcome(
        f"Stable background therapy is required for {stable_weeks.value:g} "
        f"weeks (>= {MIN_STABLE_BACKGROUND_WEEKS:g} weeks).",
        evidence=[stable_weeks.citation],
    )


def check_dm_21(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-21: Primary estimand must cover rescue, discontinuation, add-on."""
    if document.estimands is None:
        return cannot_assess_outcome("ESTIMANDS facet did not run.")
    primary = _primary_estimand(document)
    if primary is None:
        return absence_fired_outcome(
            "No primary estimand extracted; all three core diabetes "
            "intercurrent events are missing."
        )
    present_types = {ev.event_type for ev in primary.intercurrent_events}
    missing = [
        ice.value for ice in REQUIRED_DIABETES_ICES if ice not in present_types
    ]
    if not missing:
        return passed_outcome(
            "Primary estimand lists all three core diabetes intercurrent "
            "events (rescue, discontinuation, and background therapy change).",
            evidence=[ev.citation for ev in primary.intercurrent_events],
        )
    if IntercurrentEventType.OTHER in present_types:
        return cannot_assess_outcome(
            "Primary estimand includes an intercurrent event classified as "
            "OTHER; cannot determine whether missing diabetes categories "
            f"({', '.join(missing)}) are covered."
        )
    return absence_fired_outcome(
        "Primary estimand omits required diabetes intercurrent events: "
        f"{', '.join(missing)}."
    )


def check_dm_23(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-23: HbA1c assessments must continue after treatment stopping."""
    if document.interventions is None:
        return cannot_assess_outcome("INTERVENTIONS facet did not run.")
    collects = document.interventions.collects_hba1c_after_discontinuation
    if collects is None:
        return absence_fired_outcome(
            "Protocol does not state that scheduled HbA1c assessments "
            "continue after premature treatment discontinuation."
        )
    if not collects.value:
        return fired_outcome(
            "Participants who discontinue study medication early do not "
            "continue scheduled HbA1c assessments through the primary visit.",
            evidence=[collects.citation],
        )
    return passed_outcome(
        "Scheduled HbA1c assessments continue after premature treatment "
        "discontinuation.",
        evidence=[collects.citation],
    )


def check_dm_28(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-28: Hypoglycaemia must use ADA/IHSG Level 1 (70), 2 (54), and 3."""
    if document.safety_monitoring is None:
        return cannot_assess_outcome("SAFETY_MONITORING facet did not run.")
    safety = document.safety_monitoring
    defines = safety.defines_hypoglycemia_levels
    lvl1 = safety.level_1_glucose_mg_dl
    lvl2 = safety.level_2_glucose_mg_dl
    lvl3 = safety.level_3_requires_assistance

    if defines is not None and not defines.value:
        return fired_outcome(
            "Hypoglycaemia assessments explicitly omit the three-tier "
            "ADA/IHSG classification.",
            evidence=[defines.citation],
        )

    wrong_values: list[str] = []
    evidence: list[Citation] = []
    if (
        lvl1 is not None
        and abs(lvl1.value - ADA_LEVEL_1_MG_DL) > GLUCOSE_TOLERANCE_MG_DL
    ):
        wrong_values.append(
            f"Level 1 threshold={lvl1.value:g} mg/dL "
            f"(expected {ADA_LEVEL_1_MG_DL:g} mg/dL)"
        )
        evidence.append(lvl1.citation)
    if (
        lvl2 is not None
        and abs(lvl2.value - ADA_LEVEL_2_MG_DL) > GLUCOSE_TOLERANCE_MG_DL
    ):
        wrong_values.append(
            f"Level 2 threshold={lvl2.value:g} mg/dL "
            f"(expected {ADA_LEVEL_2_MG_DL:g} mg/dL)"
        )
        evidence.append(lvl2.citation)
    if lvl3 is not None and not lvl3.value:
        wrong_values.append(
            "Level 3 severe hypoglycaemia does not require external assistance"
        )
        evidence.append(lvl3.citation)

    if wrong_values:
        return fired_outcome(
            "Hypoglycaemia classification deviates from ADA/IHSG cut-offs: "
            f"{'; '.join(wrong_values)}.",
            evidence=evidence,
        )

    missing: list[str] = []
    if defines is None:
        missing.append("three-tier hypoglycaemia classification")
    if lvl1 is None:
        missing.append("Level 1 (< 70 mg/dL) threshold")
    if lvl2 is None:
        missing.append("Level 2 (< 54 mg/dL) threshold")
    if lvl3 is None:
        missing.append("Level 3 external-assistance criterion")
    if missing:
        return absence_fired_outcome(
            "Hypoglycaemia assessments omit ADA/IHSG classification "
            f"elements: {', '.join(missing)}."
        )

    assert lvl1 is not None and lvl2 is not None and lvl3 is not None
    return passed_outcome(
        "Hypoglycaemia is classified by ADA/IHSG Level 1 (< 70 mg/dL), "
        "Level 2 (< 54 mg/dL), and Level 3 (external assistance).",
        evidence=[lvl1.citation, lvl2.citation, lvl3.citation],
    )


def check_dm_45(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-45: Type 1 diabetes protocols must define DKA ketone monitoring."""
    if document.safety_monitoring is None:
        return cannot_assess_outcome("SAFETY_MONITORING facet did not run.")
    dka = document.safety_monitoring.defines_dka_criteria
    if dka is None:
        return absence_fired_outcome(
            "Type 1 diabetes protocol omits diabetic ketoacidosis (DKA) "
            "ketone monitoring and sick-day mitigation rules."
        )
    if not dka.value:
        return fired_outcome(
            "Type 1 diabetes protocol states no DKA ketone monitoring or "
            "mitigation rules are included.",
            evidence=[dka.citation],
        )
    return passed_outcome(
        "Type 1 diabetes protocol defines DKA ketone monitoring and "
        "mitigation procedures.",
        evidence=[dka.citation],
    )


DIABETES_CHECKS: dict[str, DeterministicCheck] = {
    "DM-06": check_dm_06,
    "DM-13": check_dm_13,
    "DM-17": check_dm_17,
    "DM-21": check_dm_21,
    "DM-23": check_dm_23,
    "DM-28": check_dm_28,
    "DM-45": check_dm_45,
}
