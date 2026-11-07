"""Pure functions for Step 3 Cohort Comparison (Part 1 & Part 2)."""

import math
import re
from datetime import UTC, datetime
from uuid import uuid4

from backend.agents.cohort.models import (
    DEFAULT_DECISION_OWNER,
    AtomicPredicate,
    CohortComparisonReport,
    CohortProfile,
    CohortRecommendationCard,
    CohortVariable,
    ComparisonOperator,
    ContinuousVariableStats,
    CriterionAttritionStep,
    CriterionClassification,
    CriterionType,
    DecisionStatus,
    DecisionTraceEntry,
    DoctorOption,
    DoctorOptionKind,
    EligibilityRule,
    FeasibilityStatus,
    PatientRecord,
    PeerTrialBenchmarkRun,
    PeerTrialProtocol,
    ProtocolCriterionInput,
    RuleSimulability,
    SeverityLevel,
    SubgroupDropImpact,
    WhatIfRelaxationResult,
)

# Clinical reference constants
LIVER_ULN_U_PER_L = 40.0  # Standard Upper Limit of Normal for ALT and AST
SENIOR_AGE_THRESHOLD = 65
PEDIATRIC_AGE_THRESHOLD = 18

# Benchmark classification thresholds
NORMAL_HIGH_DROP_THRESHOLD_PCT = 15.0
BOTTLENECK_EXCESS_DROP_PCT = 8.0
BOTTLENECK_ABSOLUTE_DROP_PCT = 18.0
SUBGROUP_DISPROPORTIONATE_LOSS_PCT = 15.0
FEASIBILITY_HIGH_RISK_RATIO = 0.55
FEASIBILITY_MODERATE_RISK_RATIO = 0.80

ADMINISTRATIVE_KEYWORDS: tuple[str, ...] = (
    "informed consent",
    "written consent",
    "willing and able",
    "comply with study",
    "contraception",
    "speak english",
    "able to read",
    "investigator opinion",
)

PEER_STANDARD_PREDICATES: dict[CohortVariable, list[AtomicPredicate]] = {
    CohortVariable.EGFR: [
        AtomicPredicate(
            variable=CohortVariable.EGFR,
            operator=ComparisonOperator.GTE,
            value=45.0,
            unit="mL/min/1.73m2",
        )
    ],
    CohortVariable.HBA1C: [
        AtomicPredicate(
            variable=CohortVariable.HBA1C,
            operator=ComparisonOperator.BETWEEN,
            value=7.0,
            upper_value=10.5,
            unit="%",
        )
    ],
    CohortVariable.BMI: [
        AtomicPredicate(
            variable=CohortVariable.BMI,
            operator=ComparisonOperator.BETWEEN,
            value=22.0,
            upper_value=45.0,
            unit="kg/m2",
        )
    ],
    CohortVariable.AGE: [
        AtomicPredicate(
            variable=CohortVariable.AGE,
            operator=ComparisonOperator.BETWEEN,
            value=18.0,
            upper_value=80.0,
            unit="years",
        )
    ],
    CohortVariable.ALT: [
        AtomicPredicate(
            variable=CohortVariable.ALT,
            operator=ComparisonOperator.LTE,
            value=120.0,
            unit="U/L",
        )
    ],
    CohortVariable.AST: [
        AtomicPredicate(
            variable=CohortVariable.AST,
            operator=ComparisonOperator.LTE,
            value=120.0,
            unit="U/L",
        )
    ],
    CohortVariable.SBP: [
        AtomicPredicate(
            variable=CohortVariable.SBP,
            operator=ComparisonOperator.LT,
            value=180.0,
            unit="mmHg",
        )
    ],
    CohortVariable.GLUCOSE: [
        AtomicPredicate(
            variable=CohortVariable.GLUCOSE,
            operator=ComparisonOperator.LTE,
            value=240.0,
            unit="mg/dL",
        )
    ],
}

PEER_STANDARD_LABELS: dict[CohortVariable, str] = {
    CohortVariable.EGFR: "eGFR >= 45.0 mL/min/1.73m2 (CKD Stage 3a allowed)",
    CohortVariable.HBA1C: "HbA1c between 7.0% and 10.5%",
    CohortVariable.BMI: "BMI between 22.0 and 45.0 kg/m2",
    CohortVariable.AGE: "Adults aged 18 to 80 years (inclusive of 65+)",
    CohortVariable.ALT: "ALT <= 3.0x ULN (120 U/L)",
    CohortVariable.AST: "AST <= 3.0x ULN (120 U/L)",
    CohortVariable.SBP: "Systolic BP < 180 mmHg",
    CohortVariable.GLUCOSE: "Fasting glucose <= 240 mg/dL",
}

CLINICAL_SAFETY_NOTES: dict[CohortVariable, str] = {
    CohortVariable.EGFR: (
        "Doctor Review: Relaxing eGFR to >= 45 mL/min/1.73m2 includes "
        "CKD Stage 3a patients (common in older adults with T2D). Verify "
        "whether renal dose adjustment or Week-2 creatinine monitoring is "
        "required per FDA Renal Impairment Guidance."
    ),
    CohortVariable.BMI: (
        "Doctor Review: Expanding the BMI cap up to 45 kg/m2 reflects real "
        "world Type 2 Diabetes obesity prevalence and improves female, "
        "Black, and Hispanic representation without adding safety risk."
    ),
    CohortVariable.AGE: (
        "Doctor Review: ICH E7 geriatric guidelines recommend including "
        "patients aged >= 65 unless contraindicated. Consider removing "
        "arbitrary upper age caps while keeping organ-function safety rules."
    ),
    CohortVariable.HBA1C: (
        "Doctor Review: Widening the HbA1c window to 7.0%-10.5% aligns with "
        "peer Phase 2/3 diabetes trials; ensure rescue medication criteria "
        "are specified for persistent hyperglycemia > 240 mg/dL."
    ),
    CohortVariable.SBP: (
        "Doctor Review: Allowing controlled/moderately elevated SBP up to "
        "160-180 mmHg prevents disproportionate exclusion of older and Black "
        "patients; require stable antihypertensive therapy for >= 4 weeks."
    ),
}


def format_predicate_summary(predicates: list[AtomicPredicate]) -> str:
    """Format a list of atomic predicates into a human-readable rule string."""
    if not predicates:
        return "No clinical filter predicates (pass-through)"
    parts: list[str] = []
    for pred in predicates:
        unit_suffix = f" {pred.unit}" if pred.unit else ""
        if pred.operator == ComparisonOperator.BETWEEN:
            parts.append(
                f"{pred.variable.value} between {pred.value} and "
                f"{pred.upper_value}{unit_suffix}"
            )
        else:
            var_name = pred.variable.value
            op_val = pred.operator.value
            parts.append(f"{var_name} {op_val} {pred.value}{unit_suffix}")
    return " AND ".join(parts)


def _extract_numbers(text: str) -> list[float]:
    """Extract all floating-point or integer numbers from a string."""
    return [float(m) for m in re.findall(r"\d+(?:\.\d+)?", text)]


def _parse_numeric_bound(
    text: str,
    variable: CohortVariable,
    kind: CriterionType,
    unit: str,
) -> list[AtomicPredicate]:
    """Parse range or single threshold from criterion text into pass rules."""
    lower = text.lower()
    nums = _extract_numbers(lower)
    if not nums:
        return []

    is_exclusion = kind == CriterionType.EXCLUSION

    # Check for explicit range ("between X and Y", "X to Y", ">= X and <= Y")
    range_match = re.search(
        r"(?:between|from|of)?\s*(?:>=|≥|>)?\s*(\d+(?:\.\d+)?)\s*%?\s*"
        r"(?:to|and|-|–)\s*(?:<=|≤|<)?\s*(\d+(?:\.\d+)?)",
        lower,
    )
    if range_match and not is_exclusion:
        low_val = float(range_match.group(1))
        high_val = float(range_match.group(2))
        if low_val < high_val:
            return [
                AtomicPredicate(
                    variable=variable,
                    operator=ComparisonOperator.BETWEEN,
                    value=low_val,
                    upper_value=high_val,
                    unit=unit,
                )
            ]

    val = nums[0]
    has_less = any(
        tok in lower for tok in ("<", "≤", "less than", "below", "under")
    )
    has_greater = any(
        tok in lower
        for tok in (
            ">",
            "≥",
            "greater than",
            "above",
            "over",
            "at least",
            "exceed",
        )
    )

    if is_exclusion:
        # Exclusion: "eGFR < 60" -> pass condition is eGFR >= 60
        if has_less and not has_greater:
            return [
                AtomicPredicate(
                    variable=variable,
                    operator=ComparisonOperator.GTE,
                    value=val,
                    unit=unit,
                )
            ]
        # Exclusion: "Glucose > 240" -> pass condition is glucose <= 240
        if has_greater and not has_less:
            return [
                AtomicPredicate(
                    variable=variable,
                    operator=ComparisonOperator.LTE,
                    value=val,
                    unit=unit,
                )
            ]
    else:
        # Inclusion: "BMI >= 25" -> pass condition is BMI >= 25
        if has_greater and not has_less:
            return [
                AtomicPredicate(
                    variable=variable,
                    operator=ComparisonOperator.GTE,
                    value=val,
                    unit=unit,
                )
            ]
        # Inclusion: "BMI <= 45" -> pass condition is BMI <= 45
        if has_less and not has_greater:
            return [
                AtomicPredicate(
                    variable=variable,
                    operator=ComparisonOperator.LTE,
                    value=val,
                    unit=unit,
                )
            ]

    return []


def compile_criterion_to_rule(
    criterion: ProtocolCriterionInput,
) -> EligibilityRule:
    """Deterministic clinical rule compiler for diabetes trial criteria."""
    text = criterion.text.strip()
    lower = text.lower()
    kind = criterion.kind
    is_exclusion = kind == CriterionType.EXCLUSION
    predicates: list[AtomicPredicate] = []

    # 1. Diabetes type (T1D vs T2D)
    if "type 1 diabetes" in lower or "t1dm" in lower or "t1d" in lower:
        target_type = "T2D" if is_exclusion else "T1D"
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.DIABETES_TYPE,
                operator=ComparisonOperator.EQ,
                value=target_type,
            )
        )
    elif (
        "type 2 diabetes" in lower or "t2dm" in lower or "t2d" in lower
    ) and not is_exclusion:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.DIABETES_TYPE,
                operator=ComparisonOperator.EQ,
                value="T2D",
            )
        )

    # 2. Age criteria inside text
    if any(k in lower for k in ("aged", "age ", "years of age", "years old")):
        age_preds = _parse_numeric_bound(
            lower, CohortVariable.AGE, kind, "years"
        )
        predicates.extend(age_preds)

    # 3. HbA1c / A1c
    if "hba1c" in lower or "a1c" in lower or "glycohemoglobin" in lower:
        predicates.extend(
            _parse_numeric_bound(lower, CohortVariable.HBA1C, kind, "%")
        )

    # 4. Renal function: eGFR / Creatinine clearance
    if (
        "egfr" in lower
        or "glomerular filtration" in lower
        or "creatinine clearance" in lower
        or "crcl" in lower
    ):
        predicates.extend(
            _parse_numeric_bound(
                lower, CohortVariable.EGFR, kind, "mL/min/1.73m2"
            )
        )
    elif "creatinine" in lower and "clearance" not in lower:
        predicates.extend(
            _parse_numeric_bound(
                lower, CohortVariable.CREATININE, kind, "mg/dL"
            )
        )

    # 5. BMI
    if "bmi" in lower or "body mass index" in lower:
        predicates.extend(
            _parse_numeric_bound(lower, CohortVariable.BMI, kind, "kg/m2")
        )

    # 6. Liver enzymes: ALT / AST (handling multiples of ULN like "3x ULN")
    if "alt" in lower or "ast" in lower or "transaminase" in lower:
        uln_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|times)\s*uln", lower)
        explicit_u_l = re.search(
            r"(?:>|>=|≤|<=|<)\s*(\d+(?:\.\d+)?)\s*u/l", lower
        )
        cutoff = 120.0
        if explicit_u_l:
            cutoff = float(explicit_u_l.group(1))
        elif uln_match:
            cutoff = round(float(uln_match.group(1)) * LIVER_ULN_U_PER_L, 1)
        if "alt" in lower or "transaminase" in lower:
            predicates.append(
                AtomicPredicate(
                    variable=CohortVariable.ALT,
                    operator=ComparisonOperator.LTE,
                    value=cutoff,
                    unit="U/L",
                )
            )
        if "ast" in lower or "transaminase" in lower:
            predicates.append(
                AtomicPredicate(
                    variable=CohortVariable.AST,
                    operator=ComparisonOperator.LTE,
                    value=cutoff,
                    unit="U/L",
                )
            )

    # 7. Blood pressure: SBP / DBP
    if "sbp" in lower or "systolic" in lower or "blood pressure" in lower:
        sbp_match = re.search(r"(?:sbp|systolic)[^\d]*(\d+(?:\.\d+)?)", lower)
        dbp_match = re.search(r"(?:dbp|diastolic)[^\d]*(\d+(?:\.\d+)?)", lower)
        if sbp_match and is_exclusion:
            predicates.append(
                AtomicPredicate(
                    variable=CohortVariable.SBP,
                    operator=ComparisonOperator.LT,
                    value=float(sbp_match.group(1)),
                    unit="mmHg",
                )
            )
        if dbp_match and is_exclusion:
            predicates.append(
                AtomicPredicate(
                    variable=CohortVariable.DBP,
                    operator=ComparisonOperator.LT,
                    value=float(dbp_match.group(1)),
                    unit="mmHg",
                )
            )

    # 8. Fasting / plasma glucose
    if "glucose" in lower or "hyperglycemia" in lower:
        predicates.extend(
            _parse_numeric_bound(lower, CohortVariable.GLUCOSE, kind, "mg/dL")
        )

    # 9. UACR / Albuminuria
    if "uacr" in lower or "albumin-to-creatinine" in lower:
        predicates.extend(
            _parse_numeric_bound(lower, CohortVariable.UACR, kind, "mg/g")
        )

    # 10. Triglycerides
    if "triglyceride" in lower:
        predicates.extend(
            _parse_numeric_bound(
                lower, CohortVariable.TRIGLYCERIDES, kind, "mg/dL"
            )
        )

    # 11. Boolean comorbidities, pregnancy, bariatric, DKA, food insecurity
    if "pregnan" in lower or "breast-feeding" in lower or "nursing" in lower:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.IS_PREGNANT,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if "bariatric" in lower:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.PRIOR_BARIATRIC_SURGERY,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if "ketoacidosis" in lower or " dka" in lower or "(dka)" in lower:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.HISTORY_OF_DKA,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if "hunger vital sign" in lower or "food insecur" in lower:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.FOOD_INSECURE,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if "heart failure" in lower or "nyha" in lower:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.HAS_HEART_FAILURE,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if (
        "myocardial infarction" in lower
        or "coronary" in lower
        or "stroke" in lower
    ):
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.HAS_CHD_OR_MI,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if "retinopathy" in lower or "maculopathy" in lower:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.HAS_RETINOPATHY,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if "malignan" in lower or "cancer" in lower or "neoplasm" in lower:
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.HAS_CANCER,
                operator=ComparisonOperator.EQ,
                value=not is_exclusion,
            )
        )
    if "insulin" in lower and ("treatment-naive" in lower or is_exclusion):
        predicates.append(
            AtomicPredicate(
                variable=CohortVariable.ON_INSULIN,
                operator=ComparisonOperator.EQ,
                value=False,
            )
        )

    if predicates:
        return EligibilityRule(
            criterion_id=criterion.criterion_id,
            kind=kind,
            original_text=text,
            page_number=criterion.page_number,
            quote=criterion.quote,
            simulability=RuleSimulability.SIMULATABLE,
            predicates=predicates,
        )

    # Check if purely administrative / procedural
    if any(kw in lower for kw in ADMINISTRATIVE_KEYWORDS):
        return EligibilityRule(
            criterion_id=criterion.criterion_id,
            kind=kind,
            original_text=text,
            page_number=criterion.page_number,
            quote=criterion.quote,
            simulability=RuleSimulability.ADMINISTRATIVE_NON_CLINICAL,
            unsimulatable_reason=(
                "Administrative/procedural requirement; does not filter "
                "patients by clinical laboratory or vital-sign profile."
            ),
            doctor_review_note=(
                "Administrative criterion bypassed in clinical cohort "
                "simulation. Physician may verify operational feasibility."
            ),
            predicates=[],
        )

    # Fallback: clinical criterion not present in standardized NHANES columns
    return EligibilityRule(
        criterion_id=criterion.criterion_id,
        kind=kind,
        original_text=text,
        page_number=criterion.page_number,
        quote=criterion.quote,
        simulability=RuleSimulability.REQUIRES_DOCTOR_REVIEW,
        unsimulatable_reason=(
            "Criterion references a specialized clinical variable not "
            "measured in the standard NHANES cohort."
        ),
        estimated_literature_drop_pct=5.0,
        doctor_review_note=(
            "HUMAN-IN-THE-LOOP REQUIRED: This criterion could not be "
            "automatically simulated on the NHANES dataset. Please review "
            "manually to confirm clinical necessity and accrual impact."
        ),
        predicates=[],
    )


def compile_protocol_criteria(
    criteria: list[ProtocolCriterionInput],
    min_age_years: float | None = None,
    max_age_years: float | None = None,
) -> list[EligibilityRule]:
    """Compile all protocol criteria plus design age bounds into rules."""
    rules = [compile_criterion_to_rule(item) for item in criteria]

    has_explicit_age_rule = any(
        any(p.variable == CohortVariable.AGE for p in rule.predicates)
        for rule in rules
    )
    if not has_explicit_age_rule and (
        min_age_years is not None or max_age_years is not None
    ):
        age_preds: list[AtomicPredicate] = []
        if min_age_years is not None and max_age_years is not None:
            age_preds.append(
                AtomicPredicate(
                    variable=CohortVariable.AGE,
                    operator=ComparisonOperator.BETWEEN,
                    value=float(min_age_years),
                    upper_value=float(max_age_years),
                    unit="years",
                )
            )
        elif min_age_years is not None:
            age_preds.append(
                AtomicPredicate(
                    variable=CohortVariable.AGE,
                    operator=ComparisonOperator.GTE,
                    value=float(min_age_years),
                    unit="years",
                )
            )
        elif max_age_years is not None:
            age_preds.append(
                AtomicPredicate(
                    variable=CohortVariable.AGE,
                    operator=ComparisonOperator.LTE,
                    value=float(max_age_years),
                    unit="years",
                )
            )
        rules.insert(
            0,
            EligibilityRule(
                criterion_id="DESIGN-AGE",
                kind=CriterionType.INCLUSION,
                original_text=(
                    f"Study design age eligibility: "
                    f"min={min_age_years}, max={max_age_years} years"
                ),
                simulability=RuleSimulability.SIMULATABLE,
                predicates=age_preds,
            ),
        )
    return rules


def evaluate_predicate(
    patient: PatientRecord, predicate: AtomicPredicate
) -> bool:
    """Evaluate a single AtomicPredicate against a validated PatientRecord."""
    raw_val = getattr(patient, predicate.variable.value)
    op = predicate.operator

    if isinstance(raw_val, bool) or isinstance(predicate.value, bool):
        if op == ComparisonOperator.EQ:
            return bool(raw_val) == bool(predicate.value)
        if op == ComparisonOperator.NEQ:
            return bool(raw_val) != bool(predicate.value)
        raise ValueError(
            f"Unsupported boolean operator {op} for {predicate.variable}"
        )

    if isinstance(raw_val, str) or isinstance(predicate.value, str):
        if op == ComparisonOperator.EQ:
            return str(raw_val).upper() == str(predicate.value).upper()
        if op == ComparisonOperator.NEQ:
            return str(raw_val).upper() != str(predicate.value).upper()
        raise ValueError(
            f"Unsupported string operator {op} for {predicate.variable}"
        )

    num_val = float(raw_val)
    target = float(predicate.value)
    if op == ComparisonOperator.GTE:
        return num_val >= target
    if op == ComparisonOperator.LTE:
        return num_val <= target
    if op == ComparisonOperator.GT:
        return num_val > target
    if op == ComparisonOperator.LT:
        return num_val < target
    if op == ComparisonOperator.EQ:
        return math.isclose(num_val, target, rel_tol=1e-6)
    if op == ComparisonOperator.NEQ:
        return not math.isclose(num_val, target, rel_tol=1e-6)
    if op == ComparisonOperator.BETWEEN:
        if predicate.upper_value is None:
            raise ValueError(
                f"BETWEEN operator requires upper_value, got None for "
                f"{predicate.variable}"
            )
        return target <= num_val <= float(predicate.upper_value)

    raise ValueError(f"Unhandled operator: {op}")


def evaluate_rule(patient: PatientRecord, rule: EligibilityRule) -> bool:
    """Return True if the patient passes all predicates in the rule."""
    if rule.simulability != RuleSimulability.SIMULATABLE:
        return True
    return all(evaluate_predicate(patient, pred) for pred in rule.predicates)


def _compute_continuous_stats(values: list[float]) -> ContinuousVariableStats:
    """Compute mean, SD, median, min, and max for a numeric list."""
    if not values:
        return ContinuousVariableStats(
            mean=0.0, sd=0.0, median=0.0, min_val=0.0, max_val=0.0
        )
    sorted_vals = sorted(values)
    count = len(sorted_vals)
    mean = sum(sorted_vals) / count
    variance = sum((v - mean) ** 2 for v in sorted_vals) / count
    mid = count // 2
    median = (
        sorted_vals[mid]
        if count % 2 == 1
        else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0
    )
    return ContinuousVariableStats(
        mean=round(mean, 2),
        sd=round(math.sqrt(variance), 2),
        median=round(median, 2),
        min_val=round(sorted_vals[0], 2),
        max_val=round(sorted_vals[-1], 2),
    )


def compute_cohort_profile(
    patients: list[PatientRecord], base_total_count: int
) -> CohortProfile:
    """Compute demographic, vital sign, lab, and comorbidity statistics."""
    count = len(patients)
    if count == 0:
        return CohortProfile(
            patient_count=0,
            share_of_base_pct=0.0,
            age_mean=0.0,
            age_sd=0.0,
            age_65_plus_pct=0.0,
            pediatric_under_18_pct=0.0,
            female_pct=0.0,
            race_distribution_pct={},
            vitals={},
            labs={},
            comorbidity_rates_pct={},
        )

    age_stats = _compute_continuous_stats([float(p.age) for p in patients])
    seniors = sum(1 for p in patients if p.age >= SENIOR_AGE_THRESHOLD)
    peds = sum(1 for p in patients if p.age < PEDIATRIC_AGE_THRESHOLD)
    females = sum(1 for p in patients if p.sex == "Female")

    race_counts: dict[str, int] = {}
    for p in patients:
        race_counts[p.race] = race_counts.get(p.race, 0) + 1
    race_pct = {
        race: round(cnt / count * 100.0, 2)
        for race, cnt in sorted(race_counts.items())
    }

    vitals = {
        col: _compute_continuous_stats(
            [float(getattr(p, col)) for p in patients]
        )
        for col in ("bmi", "sbp", "dbp", "hr")
    }
    labs = {
        col: _compute_continuous_stats(
            [float(getattr(p, col)) for p in patients]
        )
        for col in (
            "hba1c",
            "egfr",
            "glucose",
            "creatinine",
            "alt",
            "ast",
            "uacr",
            "cholesterol",
            "triglycerides",
        )
    }
    comorbidities = {
        col: round(
            sum(1 for p in patients if bool(getattr(p, col))) / count * 100.0,
            2,
        )
        for col in (
            "on_insulin",
            "on_oral_meds",
            "has_retinopathy",
            "has_heart_failure",
            "has_chd_or_mi",
            "has_cancer",
        )
    }

    return CohortProfile(
        patient_count=count,
        share_of_base_pct=round(count / max(base_total_count, 1) * 100.0, 2),
        age_mean=age_stats.mean,
        age_sd=age_stats.sd,
        age_65_plus_pct=round(seniors / count * 100.0, 2),
        pediatric_under_18_pct=round(peds / count * 100.0, 2),
        female_pct=round(females / count * 100.0, 2),
        race_distribution_pct=race_pct,
        vitals=vitals,
        labs=labs,
        comorbidity_rates_pct=comorbidities,
    )


def _compute_subgroup_impacts(
    base_patients: list[PatientRecord],
    retained_patients: list[PatientRecord],
) -> list[SubgroupDropImpact]:
    """Compare demographic subgroup representation before vs after a rule."""
    if not base_patients or not retained_patients:
        return []
    base_n = len(base_patients)
    ret_n = len(retained_patients)

    definitions: list[tuple[str, list[PatientRecord], list[PatientRecord]]] = [
        (
            "Older Adults (Age >= 65)",
            [p for p in base_patients if p.age >= SENIOR_AGE_THRESHOLD],
            [p for p in retained_patients if p.age >= SENIOR_AGE_THRESHOLD],
        ),
        (
            "Female Patients",
            [p for p in base_patients if p.sex == "Female"],
            [p for p in retained_patients if p.sex == "Female"],
        ),
        (
            "Black Patients",
            [p for p in base_patients if p.race == "Black"],
            [p for p in retained_patients if p.race == "Black"],
        ),
        (
            "Hispanic Patients",
            [p for p in base_patients if p.race == "Hispanic"],
            [p for p in retained_patients if p.race == "Hispanic"],
        ),
        (
            "Asian Patients",
            [p for p in base_patients if p.race == "Asian"],
            [p for p in retained_patients if p.race == "Asian"],
        ),
    ]

    impacts: list[SubgroupDropImpact] = []
    for name, base_sub, ret_sub in definitions:
        if not base_sub:
            continue
        base_share = len(base_sub) / base_n * 100.0
        ret_share = len(ret_sub) / ret_n * 100.0
        rel_change = (
            (ret_share - base_share) / base_share * 100.0
            if base_share > 0
            else 0.0
        )
        if rel_change <= -SUBGROUP_DISPROPORTIONATE_LOSS_PCT:
            impacts.append(
                SubgroupDropImpact(
                    subgroup_name=name,
                    base_share_pct=round(base_share, 2),
                    retained_share_pct=round(ret_share, 2),
                    relative_drop_pct=round(abs(rel_change), 2),
                )
            )
    impacts.sort(key=lambda item: -item.relative_drop_pct)
    return impacts


def filter_cohort(
    patients: list[PatientRecord],
    rules: list[EligibilityRule],
    peer_variable_drops: dict[CohortVariable, float] | None = None,
) -> tuple[list[PatientRecord], list[CriterionAttritionStep]]:
    """Run sequential and marginal cohort filtering across all rules."""
    if not patients:
        raise ValueError("Expected non-empty patient list for filter_cohort")

    total_n = len(patients)
    surviving = list(patients)
    funnel: list[CriterionAttritionStep] = []

    for rule in rules:
        before_n = len(surviving)
        surviving = [p for p in surviving if evaluate_rule(p, rule)]
        after_n = len(surviving)
        seq_drop = before_n - after_n
        seq_drop_pct = round(seq_drop / total_n * 100.0, 2)

        marginal_survivors = [p for p in patients if evaluate_rule(p, rule)]
        marginal_drop = total_n - len(marginal_survivors)
        marginal_drop_pct = round(marginal_drop / total_n * 100.0, 2)

        primary_var = rule.predicates[0].variable if rule.predicates else None
        peer_drop = (
            peer_variable_drops.get(primary_var)
            if (peer_variable_drops and primary_var is not None)
            else None
        )
        excess_drop = (
            round(marginal_drop_pct - peer_drop, 2)
            if peer_drop is not None
            else None
        )
        peer_std = (
            PEER_STANDARD_LABELS.get(primary_var)
            if primary_var is not None
            else None
        )
        subgroup_impacts = _compute_subgroup_impacts(
            patients, marginal_survivors
        )

        peer_std_preds = (
            PEER_STANDARD_PREDICATES.get(primary_var)
            if primary_var is not None
            else None
        )
        stricter_than_peer_std = True
        if peer_std_preds is not None:
            peer_std_rule = rule.model_copy(
                update={"predicates": peer_std_preds}
            )
            peer_std_survivors = sum(
                1 for p in patients if evaluate_rule(p, peer_std_rule)
            )
            stricter_than_peer_std = peer_std_survivors > len(
                marginal_survivors
            )

        if rule.simulability == RuleSimulability.REQUIRES_DOCTOR_REVIEW:
            classification = CriterionClassification.UNSIMULATABLE_NEEDS_REVIEW
        elif stricter_than_peer_std and (
            (
                excess_drop is not None
                and excess_drop >= BOTTLENECK_EXCESS_DROP_PCT
            )
            or (
                peer_drop is None
                and marginal_drop_pct >= BOTTLENECK_ABSOLUTE_DROP_PCT
            )
            or (
                bool(subgroup_impacts)
                and marginal_drop_pct >= NORMAL_HIGH_DROP_THRESHOLD_PCT
                and (excess_drop is None or excess_drop >= 4.0)
            )
        ):
            classification = CriterionClassification.PROTOCOL_BOTTLENECK
        elif marginal_drop_pct >= NORMAL_HIGH_DROP_THRESHOLD_PCT:
            classification = CriterionClassification.NORMAL_FIELD_STANDARD
        else:
            classification = CriterionClassification.ACCEPTABLE

        funnel.append(
            CriterionAttritionStep(
                criterion_id=rule.criterion_id,
                kind=rule.kind,
                original_text=rule.original_text,
                page_number=rule.page_number,
                rule_summary=format_predicate_summary(rule.predicates),
                simulability=rule.simulability,
                patients_before=before_n,
                patients_after=after_n,
                sequential_drop_count=seq_drop,
                sequential_drop_pct=seq_drop_pct,
                marginal_drop_count=marginal_drop,
                marginal_drop_pct=marginal_drop_pct,
                peer_mean_drop_pct=peer_drop,
                excess_drop_vs_peers_pct=excess_drop,
                peer_standard_threshold=peer_std,
                classification=classification,
                subgroup_impacts=subgroup_impacts,
                doctor_review_note=rule.doctor_review_note,
            )
        )

    return surviving, funnel


def run_peer_benchmarks(
    patients: list[PatientRecord],
    peer_protocols: list[PeerTrialProtocol],
) -> tuple[
    list[PeerTrialBenchmarkRun],
    CohortProfile,
    dict[CohortVariable, float],
]:
    """Run peer protocols on the same NHANES cohort for benchmarking."""
    total_n = len(patients)
    runs: list[PeerTrialBenchmarkRun] = []
    pooled_Ids: set[int] = set()
    variable_drops: dict[CohortVariable, list[float]] = {}

    for peer in peer_protocols:
        peer_rules = compile_protocol_criteria(
            peer.criteria,
            min_age_years=peer.min_age_years,
            max_age_years=peer.max_age_years,
        )
        eligible, peer_funnel = filter_cohort(patients, peer_rules)
        for p in eligible:
            pooled_Ids.add(p.patient_id)
        for rule, step in zip(peer_rules, peer_funnel, strict=True):
            for pred in rule.predicates:
                variable_drops.setdefault(pred.variable, []).append(
                    step.marginal_drop_pct
                )

        runs.append(
            PeerTrialBenchmarkRun(
                nct_id=peer.nct_id,
                title=peer.title,
                phase=peer.phase,
                eligible_count=len(eligible),
                eligible_pct=round(len(eligible) / total_n * 100.0, 2),
                profile=compute_cohort_profile(eligible, total_n),
                published_baseline=peer.published_baseline,
            )
        )

    pooled_patients = [p for p in patients if p.patient_id in pooled_Ids]
    benchmark_profile = compute_cohort_profile(pooled_patients, total_n)
    mean_var_drops = {
        var: round(sum(drops) / len(drops), 2)
        for var, drops in variable_drops.items()
        if drops
    }
    return runs, benchmark_profile, mean_var_drops


def simulate_what_if_relaxation(
    patients: list[PatientRecord],
    rules: list[EligibilityRule],
    target_criterion_id: str,
    replacement_predicates: list[AtomicPredicate],
    proposed_wording: str,
    clinical_safety_note: str,
) -> WhatIfRelaxationResult:
    """Simulate cohort gain when relaxing one criterion to peer standard."""
    total_n = len(patients)
    before_patients, _ = filter_cohort(patients, rules)
    before_n = len(before_patients)

    original_rule: EligibilityRule | None = None
    updated_rules: list[EligibilityRule] = []
    for rule in rules:
        if rule.criterion_id == target_criterion_id:
            original_rule = rule
            updated_rules.append(
                rule.model_copy(
                    update={
                        "predicates": replacement_predicates,
                        "simulability": RuleSimulability.SIMULATABLE,
                    }
                )
            )
        else:
            updated_rules.append(rule)

    if original_rule is None:
        raise ValueError(
            f"Criterion '{target_criterion_id}' not found in rules"
        )

    after_patients, _ = filter_cohort(patients, updated_rules)
    after_n = len(after_patients)
    after_profile = compute_cohort_profile(after_patients, total_n)

    gain = max(0, after_n - before_n)
    rel_gain = round(gain / max(before_n, 1) * 100.0, 2)
    recovered_subgroups = {
        "Older Adults (Age >= 65)": after_profile.age_65_plus_pct,
        "Female Patients": after_profile.female_pct,
        **{
            f"{race} Patients": pct
            for race, pct in after_profile.race_distribution_pct.items()
        },
    }

    return WhatIfRelaxationResult(
        criterion_id=target_criterion_id,
        original_rule_summary=format_predicate_summary(
            original_rule.predicates
        ),
        proposed_rule_summary=format_predicate_summary(replacement_predicates),
        proposed_protocol_wording=proposed_wording,
        eligible_before=before_n,
        eligible_after=after_n,
        eligible_pct_before=round(before_n / total_n * 100.0, 2),
        eligible_pct_after=round(after_n / total_n * 100.0, 2),
        patients_gained=gain,
        relative_gain_pct=rel_gain,
        recovered_subgroup_shares_pct=recovered_subgroups,
        clinical_safety_note=clinical_safety_note,
    )


def _build_recommendations(
    protocol_id: str,
    patients: list[PatientRecord],
    rules: list[EligibilityRule],
    funnel: list[CriterionAttritionStep],
) -> list[CohortRecommendationCard]:
    """Generate doctor-in-the-loop Decision Cards for bottlenecks & reviews."""
    cards: list[CohortRecommendationCard] = []

    for rule, step in zip(rules, funnel, strict=True):
        if step.classification == CriterionClassification.PROTOCOL_BOTTLENECK:
            primary_var = (
                rule.predicates[0].variable
                if rule.predicates
                else CohortVariable.EGFR
            )
            replacement_preds = PEER_STANDARD_PREDICATES.get(primary_var, [])
            peer_label = PEER_STANDARD_LABELS.get(
                primary_var, "Relax threshold to peer clinical standard"
            )
            safety_note = CLINICAL_SAFETY_NOTES.get(
                primary_var,
                "Doctor Review: Verify clinical safety of relaxing threshold "
                "to match completed peer Diabetes trials.",
            )
            what_if = simulate_what_if_relaxation(
                patients=patients,
                rules=rules,
                target_criterion_id=rule.criterion_id,
                replacement_predicates=replacement_preds,
                proposed_wording=peer_label,
                clinical_safety_note=safety_note,
            )

            subgroup_text = (
                ", ".join(
                    f"{imp.subgroup_name} (-{imp.relative_drop_pct:.1f}%)"
                    for imp in step.subgroup_impacts
                )
                if step.subgroup_impacts
                else "broad diabetic population"
            )
            peer_cmp = (
                f" (peer trials average drop: {step.peer_mean_drop_pct:.1f}%)"
                if step.peer_mean_drop_pct is not None
                else ""
            )

            options = [
                DoctorOption(
                    option_id=f"{rule.criterion_id}-OPT-RELAX",
                    kind=DoctorOptionKind.RELAX_TO_PEER_STANDARD,
                    title=f"Relax to peer standard: {peer_label}",
                    clinical_rationale=(
                        f"Recovers +{what_if.patients_gained} eligible "
                        f"patients (+{what_if.relative_gain_pct:.1f}%) on "
                        f"the NHANES cohort and improves representation of "
                        f"{subgroup_text}. {safety_note}"
                    ),
                    proposed_protocol_text=peer_label,
                    replacement_predicates=replacement_preds,
                    what_if_simulation=what_if,
                    safety_monitoring_requirement=safety_note,
                ),
                DoctorOption(
                    option_id=f"{rule.criterion_id}-OPT-SUBCOHORT",
                    kind=DoctorOptionKind.ADD_STRATIFIED_SUBCOHORT,
                    title=(
                        "Keep main threshold & add safety-monitored sub-cohort"
                    ),
                    clinical_rationale=(
                        "Preserves the primary analysis cohort while "
                        "enrolling excluded patients in a stratified "
                        "exploratory safety arm with additional lab checks."
                    ),
                    proposed_protocol_text=(
                        f"{rule.original_text} (Main Cohort); patients "
                        f"meeting {peer_label} eligible for Stratified "
                        f"Safety Sub-cohort."
                    ),
                    replacement_predicates=replacement_preds,
                    what_if_simulation=what_if,
                    safety_monitoring_requirement=(
                        "Add dedicated DSMB safety review at Week 4."
                    ),
                ),
                DoctorOption(
                    option_id=f"{rule.criterion_id}-OPT-KEEP",
                    kind=DoctorOptionKind.KEEP_STRICT_WITH_JUSTIFICATION,
                    title="Keep strict criterion (Requires Doctor Rationale)",
                    clinical_rationale=(
                        "Retain original threshold if justified by drug "
                        "mechanism, clearance pathway, or specific organ "
                        "toxicity risk. Requires logged physician rationale."
                    ),
                    proposed_protocol_text=rule.original_text,
                ),
            ]

            severity = (
                SeverityLevel.CRITICAL
                if step.marginal_drop_pct >= 25.0
                else SeverityLevel.WARNING
            )
            rec_id = f"rec-cohort-{rule.criterion_id.lower()}"
            cards.append(
                CohortRecommendationCard(
                    recommendation_id=rec_id,
                    protocol_id=protocol_id,
                    criterion_id=rule.criterion_id,
                    severity=severity,
                    classification=step.classification,
                    title=(
                        f"Restrictive criterion {rule.criterion_id} drops "
                        f"{step.marginal_drop_pct:.1f}% of diabetic cohort"
                    ),
                    description=(
                        f"Criterion '{rule.original_text}' "
                        f"({step.rule_summary}) excludes "
                        f"{step.marginal_drop_pct:.1f}% of real NHANES "
                        f"diabetic patients{peer_cmp}, disproportionately "
                        f"affecting {subgroup_text}. Relaxing to peer "
                        f"standard ({peer_label}) increases eligible cohort "
                        f"from {what_if.eligible_pct_before:.1f}% to "
                        f"{what_if.eligible_pct_after:.1f}%."
                    ),
                    original_criterion_text=rule.original_text,
                    page_number=rule.page_number,
                    quote=rule.quote,
                    compiled_rule_summary=step.rule_summary,
                    target_drop_pct=step.marginal_drop_pct,
                    peer_benchmark_drop_pct=step.peer_mean_drop_pct,
                    subgroup_impacts=step.subgroup_impacts,
                    doctor_options=options,
                )
            )

        elif (
            step.classification
            == CriterionClassification.UNSIMULATABLE_NEEDS_REVIEW
        ):
            options = [
                DoctorOption(
                    option_id=f"{rule.criterion_id}-OPT-REVIEW",
                    kind=DoctorOptionKind.MANUAL_CLINICAL_REVIEW,
                    title="Physician Manual Review: Confirm or Clarify Rule",
                    clinical_rationale=(
                        rule.doctor_review_note
                        or "Variable not present in standard NHANES cohort; "
                        "requires physician verification."
                    ),
                    proposed_protocol_text=rule.original_text,
                ),
                DoctorOption(
                    option_id=f"{rule.criterion_id}-OPT-KEEP",
                    kind=DoctorOptionKind.KEEP_STRICT_WITH_JUSTIFICATION,
                    title="Approve Criterion After Clinical Review",
                    clinical_rationale=(
                        "Confirm that this specialized criterion is "
                        "clinically necessary and feasible at trial sites."
                    ),
                    proposed_protocol_text=rule.original_text,
                ),
            ]
            review_rec_id = f"rec-review-{rule.criterion_id.lower()}"
            cards.append(
                CohortRecommendationCard(
                    recommendation_id=review_rec_id,
                    protocol_id=protocol_id,
                    criterion_id=rule.criterion_id,
                    severity=SeverityLevel.INFO,
                    classification=step.classification,
                    title=(
                        f"Doctor Review Required: {rule.criterion_id} "
                        f"not in standard NHANES variables"
                    ),
                    description=(
                        f"Criterion '{rule.original_text}' references a "
                        f"variable outside the 28 standardized NHANES "
                        f"columns ({rule.unsimulatable_reason}). It was "
                        f"not applied as an automatic filter; physician "
                        f"review is requested to confirm accrual impact."
                    ),
                    original_criterion_text=rule.original_text,
                    page_number=rule.page_number,
                    quote=rule.quote,
                    compiled_rule_summary=(
                        "Not simulatable in NHANES (Doctor Review)"
                    ),
                    target_drop_pct=0.0,
                    peer_benchmark_drop_pct=None,
                    subgroup_impacts=[],
                    doctor_options=options,
                )
            )

    return cards


def build_cohort_comparison_report(
    protocol_id: str,
    protocol_title: str,
    criteria: list[ProtocolCriterionInput],
    patients: list[PatientRecord],
    peer_protocols: list[PeerTrialProtocol],
    min_age_years: float | None = None,
    max_age_years: float | None = None,
    precompiled_rules: list[EligibilityRule] | None = None,
) -> CohortComparisonReport:
    """Execute full Step 3 (Part 1 + Part 2) pipeline and build report."""
    if not patients:
        raise ValueError("patients list cannot be empty")

    total_n = len(patients)
    disease_profile = compute_cohort_profile(patients, total_n)

    peer_runs, peer_profile, peer_var_drops = run_peer_benchmarks(
        patients, peer_protocols
    )
    peer_mean_pct = (
        round(
            sum(r.eligible_pct for r in peer_runs) / len(peer_runs),
            2,
        )
        if peer_runs
        else 0.0
    )

    rules = (
        precompiled_rules
        if precompiled_rules is not None
        else compile_protocol_criteria(
            criteria,
            min_age_years=min_age_years,
            max_age_years=max_age_years,
        )
    )
    eligible_patients, funnel = filter_cohort(
        patients, rules, peer_variable_drops=peer_var_drops
    )
    target_profile = compute_cohort_profile(eligible_patients, total_n)
    target_pct = target_profile.share_of_base_pct

    ratio = target_pct / max(peer_mean_pct, 1.0)
    if ratio < FEASIBILITY_HIGH_RISK_RATIO:
        feasibility = FeasibilityStatus.HIGH_ACCRUAL_RISK
    elif ratio < FEASIBILITY_MODERATE_RISK_RATIO:
        feasibility = FeasibilityStatus.MODERATE_RISK
    else:
        feasibility = FeasibilityStatus.HIGH_FEASIBILITY

    unsimulatable = [
        r
        for r in rules
        if r.simulability == RuleSimulability.REQUIRES_DOCTOR_REVIEW
    ]
    recommendations = _build_recommendations(
        protocol_id=protocol_id,
        patients=patients,
        rules=rules,
        funnel=funnel,
    )

    return CohortComparisonReport(
        protocol_id=protocol_id,
        protocol_title=protocol_title,
        base_population_count=total_n,
        target_eligible_count=len(eligible_patients),
        target_eligible_pct=target_pct,
        peer_mean_eligible_pct=peer_mean_pct,
        feasibility_status=feasibility,
        disease_population_profile=disease_profile,
        target_cohort_profile=target_profile,
        peer_benchmark_profile=peer_profile,
        peer_trial_runs=peer_runs,
        compiled_rules=rules,
        attrition_funnel=funnel,
        unsimulatable_criteria_for_doctor=unsimulatable,
        recommendations=recommendations,
        decision_audit_log=[],
    )


def apply_doctor_decision(
    report: CohortComparisonReport,
    patients: list[PatientRecord],
    recommendation_id: str,
    decision_status: DecisionStatus,
    doctor_comment: str,
    selected_option_id: str | None = None,
    decided_by_role: str = DEFAULT_DECISION_OWNER,
) -> CohortComparisonReport:
    """Apply a human-in-the-loop doctor decision with full traceability."""
    cleaned_comment = doctor_comment.strip()
    if not cleaned_comment:
        raise ValueError(
            "doctor_comment is required for traceability when recording a "
            f"clinical decision, got empty string for {recommendation_id}"
        )

    target_card: CohortRecommendationCard | None = None
    for card in report.recommendations:
        if card.recommendation_id == recommendation_id:
            target_card = card
            break

    if target_card is None:
        raise ValueError(
            f"Recommendation '{recommendation_id}' not found in report"
        )

    chosen_option: DoctorOption | None = None
    if selected_option_id is not None:
        for opt in target_card.doctor_options:
            if opt.option_id == selected_option_id:
                chosen_option = opt
                break
        if chosen_option is None:
            raise ValueError(
                f"Option '{selected_option_id}' not found in "
                f"recommendation '{recommendation_id}'"
            )
    elif (
        decision_status == DecisionStatus.ACCEPTED
        and target_card.doctor_options
    ):
        chosen_option = target_card.doctor_options[0]
        selected_option_id = chosen_option.option_id

    updated_rules = list(report.compiled_rules)
    if (
        decision_status == DecisionStatus.ACCEPTED
        and chosen_option is not None
        and chosen_option.replacement_predicates is not None
    ):
        updated_rules = [
            rule.model_copy(
                update={
                    "predicates": chosen_option.replacement_predicates,
                    "simulability": RuleSimulability.SIMULATABLE,
                }
            )
            if rule.criterion_id == target_card.criterion_id
            else rule
            for rule in report.compiled_rules
        ]

    total_n = len(patients)
    eligible_after, updated_funnel = filter_cohort(patients, updated_rules)
    profile_after = compute_cohort_profile(eligible_after, total_n)
    pct_before = report.target_eligible_pct
    pct_after = profile_after.share_of_base_pct

    trace_entry = DecisionTraceEntry(
        trace_id=f"trace-{uuid4().hex[:8]}",
        recommendation_id=recommendation_id,
        criterion_id=target_card.criterion_id,
        decision_status=decision_status,
        selected_option_id=selected_option_id,
        decided_by_role=decided_by_role,
        doctor_comment=cleaned_comment,
        timestamp_iso=datetime.now(UTC).isoformat(),
        eligible_pct_before=pct_before,
        eligible_pct_after=pct_after,
    )

    updated_cards = [
        card.model_copy(
            update={
                "status": decision_status,
                "selected_option_id": selected_option_id,
                "doctor_comment": cleaned_comment,
            }
        )
        if card.recommendation_id == recommendation_id
        else card
        for card in report.recommendations
    ]

    ratio = pct_after / max(report.peer_mean_eligible_pct, 1.0)
    if ratio < FEASIBILITY_HIGH_RISK_RATIO:
        new_feasibility = FeasibilityStatus.HIGH_ACCRUAL_RISK
    elif ratio < FEASIBILITY_MODERATE_RISK_RATIO:
        new_feasibility = FeasibilityStatus.MODERATE_RISK
    else:
        new_feasibility = FeasibilityStatus.HIGH_FEASIBILITY

    return report.model_copy(
        update={
            "target_eligible_count": len(eligible_after),
            "target_eligible_pct": pct_after,
            "feasibility_status": new_feasibility,
            "target_cohort_profile": profile_after,
            "compiled_rules": updated_rules,
            "attrition_funnel": updated_funnel,
            "recommendations": updated_cards,
            "decision_audit_log": [*report.decision_audit_log, trace_entry],
        }
    )
