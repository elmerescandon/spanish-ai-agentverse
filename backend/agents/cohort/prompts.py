"""Prompt constants for compiling protocol eligibility criteria into rules."""

from backend.agents.cohort.models import (
    CohortVariable,
    ComparisonOperator,
    ProtocolCriterionInput,
    RuleSimulability,
)

ALLOWED_VARIABLES = ", ".join(f'"{v.value}"' for v in CohortVariable)
ALLOWED_OPERATORS = ", ".join(f'"{op.value}"' for op in ComparisonOperator)
ALLOWED_SIMULABILITY = ", ".join(f'"{s.value}"' for s in RuleSimulability)

RULE_COMPILATION_INSTRUCTIONS = (
    "Convert each clinical trial eligibility criterion into a structured "
    "EligibilityRule JSON object for our CDC NHANES Diabetes cohort.\n\n"
    f"Available patient variables: {ALLOWED_VARIABLES}.\n"
    f"Available operators: {ALLOWED_OPERATORS}.\n"
    f"Available simulability values: {ALLOWED_SIMULABILITY}.\n\n"
    "Rules for translation:\n"
    "1. Each predicate must express the condition required for a patient "
    "to PASS (be eligible under) that criterion.\n"
    "   - Example INCLUSION: 'HbA1c between 7.0% and 10.5%' -> "
    'variable="hba1c", operator="between", value=7.0, upper_value=10.5.\n'
    "   - Example EXCLUSION: 'eGFR < 45 mL/min/1.73m2' -> to PASS, the "
    'patient must have variable="egfr", operator=">=", value=45.0.\n'
    "   - Example EXCLUSION: 'History of diabetic ketoacidosis (DKA)' -> "
    'to PASS, variable="history_of_dka", operator="==", value=false.\n'
    "2. Standard ULN (Upper Limit of Normal) for liver enzymes: "
    "ALT ULN = 40.0 U/L, AST ULN = 40.0 U/L. Convert multiples like "
    "'ALT > 3x ULN' to value=120.0 U/L.\n"
    "3. If a criterion is purely administrative or procedural (e.g., "
    "'written informed consent', 'willing to comply with study visits'), "
    'set simulability="ADMINISTRATIVE_NON_CLINICAL", predicates=[], and '
    "provide a clear doctor_review_note.\n"
    "4. If a criterion is clinical/medical but relies on a variable not "
    "available in the list above (e.g., 'QTcF < 450 ms', 'C-peptide', "
    "'genetic mutation'), set simulability=\"REQUIRES_DOCTOR_REVIEW\", "
    "predicates=[], explain why in unsimulatable_reason, provide an "
    "estimated_literature_drop_pct (0 to 100), and write an explicit "
    "doctor_review_note so the reviewing physician is fully informed."
)


def build_rule_compilation_prompt(
    criteria: list[ProtocolCriterionInput],
) -> str:
    """Build the LLM prompt for translating a list of eligibility criteria."""
    formatted_items = "\n".join(
        f"- [{item.criterion_id}] ({item.kind.value}, "
        f"page={item.page_number}): {item.text}"
        for item in criteria
    )
    header = RULE_COMPILATION_INSTRUCTIONS
    return f"{header}\n\nCriteria to compile:\n{formatted_items}"
