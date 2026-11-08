"""Prompt text for the completeness checker's Gemini calls."""

from enum import StrEnum

from backend.shared.messages import (
    ControlType,
    DiabetesType,
    DrugClass,
    InterventionType,
)

INSTRUCTIONS_SEPARATOR = "\n---\n"


# [TO REFACTOR:(alex)]: same helper as the parser's prompts.quoted_values;
# move to backend/shared once the parser's step-3 work has merged.
def quoted_values(enum_class: type[StrEnum]) -> str:
    """List an enum's values as the JSON strings Gemini must return."""
    return ", ".join(f'"{member.value}"' for member in enum_class)


TRIAL_PROFILE_INSTRUCTIONS = (
    "Classify this clinical trial protocol into JSON matching the "
    "TrialProfile schema. Wrap each value as "
    '{"value": ..., "citation": {"page_number": ..., "quote": ...}}.\n'
    "- intervention_type: the investigational intervention, one of "
    f"{quoted_values(InterventionType)}.\n"
    "- diabetes_type: the population's diabetes type, one of "
    f"{quoted_values(DiabetesType)}.\n"
    "- drug_class: the investigational drug's pharmacological class, one "
    f"of {quoted_values(DrugClass)}; null for a non-drug intervention.\n"
    "- control_type: the comparator arm, one of "
    f"{quoted_values(ControlType)} (USUAL_CARE = standard care or a "
    "non-drug support such as a subsidy; NONE = single-arm).\n"
    "- is_non_inferiority: true if the primary hypothesis is "
    "non-inferiority, false if the protocol states superiority.\n"
    "- is_add_on: true if the investigational treatment is added on top of "
    "background glucose-lowering therapy, false if the protocol states "
    "monotherapy or no background therapy.\n"
    "- phase: leave null.\n\n"
    "Rules:\n"
    "- Every quote is copied verbatim from the cited page (at least 15 "
    "characters) and uses the === PAGE n === marker's page number.\n"
    "- If the protocol does not state a fact, return null for it. Never "
    "guess, and never default a missing true/false fact to false."
)
