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
    "- is_amended: true if this version amends an earlier protocol version "
    "(an amendment number or a summary of changes), false if it states it "
    "is the original version.\n"
    "- phase: leave null.\n\n"
    "Rules:\n"
    "- Every quote is copied verbatim from the cited page (at least 15 "
    "characters) and uses the === PAGE n === marker's page number.\n"
    "- If the protocol does not state a fact, return null for it. Never "
    "guess, and never default a missing true/false fact to false."
)

JUDGEMENT_BATCH_INSTRUCTIONS = (
    "Evaluate each clinical trial protocol rule listed above against the "
    "provided protocol pages and extracted JSON context. Return JSON "
    "matching the JudgementVerdicts schema with one entry per rule_id.\n\n"
    "Rules:\n"
    "- Every quote in evidence must be copied verbatim from the cited page "
    "(at least 15 characters) and use the === PAGE n === marker's page "
    "number.\n"
    '- Status "fired" requires a verbatim quote of the defect in evidence, '
    "or for an absence the nearest section heading quote plus the word "
    '"absent" in the finding text.\n'
    '- Status "not_applicable" is allowed ONLY when the rule\'s trigger is '
    "absent in the protocol text; state a one-line status_reason.\n"
    '- Status "cannot_assess" requires a one-line status_reason.\n'
    "- Never invent facts not present in the protocol pages.\n"
    "- When a finding concerns specific eligibility criteria, list their "
    "criterion_id values (from eligibility_criteria) in criterion_ids.\n"
    '- Always cite any FDA draft guidance as "FDA draft guidance '
    '(non-binding)".\n'
    "- Set confidence between 0.0 and 1.0 reflecting your certainty."
)

LIBRARY_MATCH_INSTRUCTIONS = (
    "For each library item above, decide whether the protocol's "
    "eligibility criteria cover it. Return JSON matching the LibraryMatches "
    "schema with one entry per rule_id.\n\n"
    "Rules:\n"
    "- is_present: true when an exclusion criterion (or a mirror-image "
    "inclusion criterion) covers the item, even with different wording or "
    "a different threshold.\n"
    "- criterion_ids: the criterion_id values that cover it, exactly as "
    "listed; empty when is_present is false.\n"
    "- is_operable: true when those criteria are answerable yes/no, with a "
    "threshold, unit, test and look-back window where one is needed.\n"
    "- has_rationale: true only when the protocol pages state a safety or "
    "scientific reason for the exclusion.\n"
    "- Never invent criteria. Set confidence between 0.0 and 1.0."
)

SECOND_OPINION_INSTRUCTIONS = (
    "Review each flagged protocol finding above against the provided "
    "protocol pages and evidence. Return JSON matching the "
    "SecondOpinionVerdicts schema with one entry per rule_id.\n\n"
    "Rules:\n"
    "- Set confirmed = true only when the cited verbatim quote or the "
    "searched section pages clearly support the rule's flag_if trigger.\n"
    "- Set confirmed = false when the quote is taken out of context, the "
    "searched pages actually contain the required information, or the "
    "rule's trigger does not apply.\n"
    "- Provide a concise reason and your confidence between 0.0 and 1.0."
)
