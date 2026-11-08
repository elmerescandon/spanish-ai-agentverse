"""Family DM deterministic checks: diabetes-specific design rules."""

import re
from collections.abc import Mapping

from backend.agents.completeness.checks.common import (
    CENTRAL_LAB_PATTERN,
    CGM_TIR_PATTERN,
    HBA1C_PATTERN,
    RESPONDER_TERM_PATTERN,
    absence_fired_outcome,
    cannot_assess_outcome,
    cap_citations,
    find_pattern_citation,
    fired_outcome,
    format_offenders,
    not_applicable_outcome,
    passed_outcome,
)
from backend.agents.completeness.logic import CheckOutcome, DeterministicCheck
from backend.shared.messages import (
    Citation,
    EndpointKind,
    Estimand,
    IntercurrentEventType,
    ProtocolDocument,
    RuleStatus,
    StratificationFactorType,
    SubgroupDimension,
    TrialProfile,
)

MIN_STABLE_BACKGROUND_WEEKS = 8.0
ADA_LEVEL_1_MG_DL = 70.0
ADA_LEVEL_2_MG_DL = 54.0
GLUCOSE_TOLERANCE_MG_DL = 0.5

# DM-04 / DM-08: assay certification and US glucose units.
CERTIFIED_ASSAY_PATTERN = re.compile(r"\bNGSP\b|\bIFCC\b", re.IGNORECASE)
FPG_PATTERN = re.compile(
    r"\bFPG\b|\bfasting\s+(?:plasma\s+)?glucose\b", re.IGNORECASE
)
MG_PER_DL_PATTERN = re.compile(r"\bmg\s*/\s*dl\b", re.IGNORECASE)
# DM-29: a named device for confirming glucose values.
GLUCOSE_DEVICE_PATTERN = re.compile(
    r"\b(?:blood\s+)?glucose\s+met(?:er|re)s?\b|\bglucometers?\b|\bSMBG\b"
    r"|\bCGM\b|continuous\s+glucose\s+monitor",
    re.IGNORECASE,
)
STRATA_FOR_DIABETES = frozenset(
    {
        StratificationFactorType.BASELINE_HBA1C,
        StratificationFactorType.PRIOR_THERAPY,
    }
)
ELDERLY_BAND_BOUNDS = ("65", "75", "85")  # 65-74, 75-84, >=85 years
REQUIRED_SUBGROUPS = (
    SubgroupDimension.SEX,
    SubgroupDimension.RACE,
    SubgroupDimension.ETHNICITY,
    SubgroupDimension.DIABETES_DURATION,
    SubgroupDimension.BASELINE_HBA1C,
)
# DM-39: cardiovascular risk factors; vital signs cover BP and heart rate.
CV_RISK_FACTOR_PATTERNS: Mapping[str, re.Pattern[str]] = {
    "lipids": re.compile(
        r"lipid|cholesterol|triglycerid|\bLDL\b|\bHDL\b", re.IGNORECASE
    ),
    "body weight": re.compile(r"\bweight\b", re.IGNORECASE),
    "waist circumference": re.compile(r"\bwaist\b", re.IGNORECASE),
    "blood pressure": re.compile(
        r"blood\s+pressure|\bBP\b|vital\s+signs", re.IGNORECASE
    ),
    "heart rate": re.compile(
        r"heart\s+rate|\bpulse\b|vital\s+signs", re.IGNORECASE
    ),
}
# DM-40: microvascular safety assessments.
MICROVASCULAR_PATTERNS: Mapping[str, re.Pattern[str]] = {
    "eye examination": re.compile(
        r"fundus|fundoscop|retin|ophthalm|\beye\s+exam", re.IGNORECASE
    ),
    "urine albumin-to-creatinine ratio (UACR)": re.compile(
        r"\bUACR\b|albumin[\s-]*(?:to[\s-]*)?creatinine"
        r"|urin(?:e|ary)\s+albumin|microalbumin",
        re.IGNORECASE,
    ),
}

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


def _required_mentions_outcome(
    document: ProtocolDocument,
    required: Mapping[str, re.Pattern[str]],
    passed_text: str,
) -> CheckOutcome:
    """Pass when every named pattern appears in the protocol pages."""
    found: dict[str, Citation] = {}
    for name, pattern in required.items():
        citation = find_pattern_citation(document, pattern)
        if citation is not None:
            found[name] = citation
    missing = [name for name in required if name not in found]
    if missing:
        return absence_fired_outcome(
            f"The protocol does not state: {', '.join(missing)}."
        )
    return passed_outcome(passed_text, evidence=found.values())


def check_dm_04(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-04: HbA1c by a central lab with an NGSP- or IFCC-certified assay."""
    return _required_mentions_outcome(
        document,
        {
            "a central laboratory": CENTRAL_LAB_PATTERN,
            "an NGSP- or IFCC-certified HbA1c assay": CERTIFIED_ASSAY_PATTERN,
        },
        "HbA1c is analysed centrally with a certified assay.",
    )


def check_dm_07(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-07: The primary endpoint must not be an HbA1c responder rate."""
    if document.endpoints is None:
        return cannot_assess_outcome("ENDPOINTS facet did not run.")
    primaries = [
        ep for ep in document.endpoints if ep.kind == EndpointKind.PRIMARY
    ]
    if not primaries:
        return cannot_assess_outcome("No primary endpoint was extracted.")
    responders = [
        ep
        for ep in primaries
        if HBA1C_PATTERN.search(ep.description) is not None
        and RESPONDER_TERM_PATTERN.search(ep.description) is not None
    ]
    if responders:
        return fired_outcome(
            "The primary endpoint is an HbA1c responder rate: "
            f"{format_offenders([ep.description for ep in responders])}.",
            evidence=[ep.citation for ep in responders],
        )
    return passed_outcome(
        "No primary endpoint is an HbA1c responder rate.",
        evidence=[ep.citation for ep in primaries],
    )


def check_dm_08(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-08: FPG is measured centrally and reported in mg/dL."""
    fpg = find_pattern_citation(document, FPG_PATTERN)
    if fpg is None:
        return not_applicable_outcome("the protocol does not measure FPG")
    outcome = _required_mentions_outcome(
        document,
        {
            "a central laboratory for FPG": CENTRAL_LAB_PATTERN,
            "FPG in mg/dL": MG_PER_DL_PATTERN,
        },
        "FPG is measured centrally and reported in mg/dL.",
    )
    if outcome.status == RuleStatus.PASSED:
        return passed_outcome(
            outcome.finding, evidence=[fpg, *outcome.evidence]
        )
    return outcome


def check_dm_24(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-24: Randomisation is stratified by baseline HbA1c or therapy."""
    if document.interventions is None:
        return cannot_assess_outcome("INTERVENTIONS facet did not run.")
    strata = document.interventions.stratification_factors
    if not strata:
        return absence_fired_outcome("No stratification factors were found.")
    relevant = [
        item for item in strata if item.category in STRATA_FOR_DIABETES
    ]
    if relevant:
        return passed_outcome(
            "Randomisation is stratified by baseline HbA1c or prior therapy.",
            evidence=[item.citation for item in relevant],
        )
    labels = format_offenders([item.label for item in strata])
    return fired_outcome(
        f"Strata ({labels}) include neither baseline HbA1c nor prior therapy.",
        evidence=[item.citation for item in strata],
    )


def check_dm_25(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-25: Age subgroups 65-74, 75-84 and 85 or over are pre-specified."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    age_groups = [
        item
        for item in document.analysis.prespecified_subgroups
        if item.category == SubgroupDimension.AGE
    ]
    if not age_groups:
        return absence_fired_outcome("No age subgroups are pre-specified.")
    labels = " ".join(item.label for item in age_groups)
    missing = [bound for bound in ELDERLY_BAND_BOUNDS if bound not in labels]
    evidence = [item.citation for item in age_groups]
    if missing:
        return fired_outcome(
            f"Age subgroups ({labels}) do not split the elderly into "
            "65-74, 75-84 and 85 or over.",
            evidence=evidence,
        )
    return passed_outcome(
        "Elderly age bands 65-74, 75-84 and 85 or over are pre-specified.",
        evidence=evidence,
    )


def check_dm_26(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-26: Subgroups cover sex, race, ethnicity, duration and HbA1c."""
    if document.analysis is None:
        return cannot_assess_outcome("ANALYSIS facet did not run.")
    subgroups = document.analysis.prespecified_subgroups
    present = {item.category for item in subgroups}
    missing = [dim.value for dim in REQUIRED_SUBGROUPS if dim not in present]
    if not missing:
        return passed_outcome(
            "All required subgroup dimensions are pre-specified.",
            evidence=cap_citations(item.citation for item in subgroups),
        )
    finding = f"Missing pre-specified subgroups: {', '.join(missing)}."
    if not subgroups:
        return absence_fired_outcome(finding)
    return fired_outcome(
        finding, evidence=[item.citation for item in subgroups]
    )


def check_dm_29(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-29: A glucose meter or CGM is named for confirming events."""
    return _required_mentions_outcome(
        document,
        {"a glucose meter or CGM device": GLUCOSE_DEVICE_PATTERN},
        "A glucose meter or CGM is specified.",
    )


def _schedule_coverage_outcome(
    document: ProtocolDocument,
    required: Mapping[str, re.Pattern[str]],
    passed_text: str,
) -> CheckOutcome:
    """Pass when every named assessment appears in some scheduled visit."""
    if document.schedule is None:
        return cannot_assess_outcome("SCHEDULE facet did not run.")
    found: dict[str, Citation | None] = {}
    for name, pattern in required.items():
        for visit in document.schedule:
            if any(pattern.search(proc) for proc in visit.procedures):
                found[name] = visit.citation
                break
    evidence = [c for c in found.values() if c is not None]
    missing = [name for name in required if name not in found]
    if missing:
        return fired_outcome(
            f"Not in the schedule of activities: {', '.join(missing)}.",
            evidence=evidence,
            needs_second_opinion=True,
        )
    return passed_outcome(passed_text, evidence=evidence)


def check_dm_39(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-39: Lipids, weight, waist, BP and heart rate are scheduled."""
    return _schedule_coverage_outcome(
        document,
        CV_RISK_FACTOR_PATTERNS,
        "All cardiovascular risk factors are in the schedule of activities.",
    )


def check_dm_40(
    document: ProtocolDocument, _profile: TrialProfile
) -> CheckOutcome:
    """DM-40: An eye examination and urine albumin are scheduled."""
    return _schedule_coverage_outcome(
        document,
        MICROVASCULAR_PATTERNS,
        "Eye examinations and UACR are in the schedule of activities.",
    )


DIABETES_CHECKS: dict[str, DeterministicCheck] = {
    "DM-06": check_dm_06,
    "DM-13": check_dm_13,
    "DM-17": check_dm_17,
    "DM-21": check_dm_21,
    "DM-23": check_dm_23,
    "DM-28": check_dm_28,
    "DM-45": check_dm_45,
    "DM-04": check_dm_04,
    "DM-07": check_dm_07,
    "DM-08": check_dm_08,
    "DM-24": check_dm_24,
    "DM-25": check_dm_25,
    "DM-26": check_dm_26,
    "DM-29": check_dm_29,
    "DM-39": check_dm_39,
    "DM-40": check_dm_40,
}
