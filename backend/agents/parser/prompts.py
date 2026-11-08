"""Prompt text shared by every parser facet.

Facet-specific instructions live next to each facet definition; the rules
here apply to all of them, so citations can be checked against the PDF.
"""

from backend.shared.messages import (
    AllocationType,
    CriterionKind,
    EndpointKind,
    InterventionModelType,
    M11Heading,
    MaskingType,
    TrialPhase,
)

INSTRUCTIONS_SEPARATOR = "\n---\n"

ALLOWED_CRITERION_KINDS = ", ".join(
    f'"{member.value}"' for member in CriterionKind
)
ALLOWED_PHASES = ", ".join(f'"{member.value}"' for member in TrialPhase)
ALLOWED_ALLOCATIONS = ", ".join(
    f'"{member.value}"' for member in AllocationType
)
ALLOWED_INTERVENTION_MODELS = ", ".join(
    f'"{member.value}"' for member in InterventionModelType
)
ALLOWED_MASKING = ", ".join(f'"{member.value}"' for member in MaskingType)
ALLOWED_M11_HEADINGS = ", ".join(f'"{member.value}"' for member in M11Heading)
ALLOWED_ENDPOINT_KINDS = ", ".join(
    f'"{member.value}"' for member in EndpointKind
)

COMMON_EXTRACTION_RULES = (
    "Rules:\n"
    "- Every citation quote must be copied verbatim from the cited page: "
    "at least 15 characters, no paraphrasing, no ellipsis.\n"
    "- Use the page number from the === PAGE n === marker that precedes "
    "the quoted text.\n"
    "- If a fact is not stated in the document, return null for it "
    "(or an empty list). Never invent a value."
)

REPAIR_INSTRUCTIONS = (
    "Your previous answer cited quotes that do not appear on the cited "
    "page. Return the full answer again, replacing each quote below with "
    "text copied exactly from the document and the correct page number. "
    "Drop a fact only if the document does not state it.\n"
    "Quotes that failed verification:"
)

ELIGIBILITY_INSTRUCTIONS = (
    "Extract all participant eligibility criteria from the protocol into "
    "JSON matching the EligibilityExtraction schema.\n"
    "- Create one criterion per numbered or bulleted item in the "
    "Inclusion Criteria and Exclusion Criteria sections.\n"
    "- Merge any sub-bullets, lettered sub-items (a, b, c), or attached "
    "notes into their parent criterion's text.\n"
    f"- Set kind to one of: {ALLOWED_CRITERION_KINDS}, according to "
    "whether the item sits under inclusion or exclusion criteria.\n"
    '- Set criterion_id to a placeholder such as "IN-01" or "EX-01".\n'
    "- Quote rule for short criteria: every citation.quote must have at "
    "least 15 non-space, non-hyphen characters copied verbatim from the "
    "cited page. For short criteria (for example, '- Aged ≥18 years' or "
    "'- Male or female'), copy the whole criterion line as printed and "
    "extend the verbatim quote into the immediately preceding or "
    "following line on the same page so it reaches at least 15 "
    "non-space characters."
)

DESIGN_INSTRUCTIONS = (
    "Extract the study's trial design facts from the protocol into JSON "
    "matching the TrialDesignFacts schema. Wrap each present value in "
    '{"value": ..., "citation": {"page_number": ..., "quote": ...}} and '
    "return null for any field not stated in the document.\n"
    f"- phase: one of {ALLOWED_PHASES}. Report the phase stated in the "
    'document (for example, "Phase II" -> "PHASE2", "Phase 3" -> '
    '"PHASE3"). For a behavioral or non-drug trial with no phase stated, '
    'use "NA".\n'
    f"- allocation: one of {ALLOWED_ALLOCATIONS}.\n"
    f"- intervention_model: one of {ALLOWED_INTERVENTION_MODELS}.\n"
    f"- masking: one of {ALLOWED_MASKING}.\n"
    "- target_enrollment: total planned number of enrolled or randomized "
    "participants (integer).\n"
    "- arm_count: number of treatment arms or study groups (integer).\n"
    "- min_age_years and max_age_years: age limits in years. '18 years "
    "and older' or 'Aged ≥18 years' means min_age_years=18 and "
    "max_age_years=null.\n"
    "- is_min_age_inclusive and is_max_age_inclusive: plain booleans (no "
    "citation) saying whether each age limit includes its endpoint. true "
    "for '\u226518', '18 and older' or 'up to and including 65'; false "
    "for '>18', '<18' or 'under 18'. null when that age limit is absent.\n"
    "- accepts_healthy_volunteers: boolean if explicitly stated.\n"
    "- site_count: number of study sites (integer; 'single-site' means 1).\n"
    "- country_count: number of participating countries (integer).\n"
    "- has_data_monitoring_committee: true if a DSMB/DMC is used.\n"
    "- nct_id: ClinicalTrials.gov NCT identifier if stated."
)

SECTIONS_INSTRUCTIONS = (
    "Extract the top-level sections of the protocol body into JSON matching "
    "the SectionMap schema.\n"
    "- Produce one entry per top-level section of the protocol body "
    "(1, 2, 3, ..., plus a standalone SYNOPSIS if unnumbered), not every "
    "subsection (do not list 1.1, 1.2, 4.1, etc. as separate entries).\n"
    "- Skip front and back matter: title page, statement of compliance, "
    "signature pages, table of contents, list of attachments/tables/figures, "
    "abbreviation lists, definitions of terms, and references.\n"
    f"- Classify heading by the section's CONTENT (not by its heading text, "
    "since sponsors name sections differently) into one of: "
    f"{ALLOWED_M11_HEADINGS}. For example, a section titled "
    "'5 TARGET POPULATION AND STUDY SAMPLE' or '4. SUBJECT POPULATION' "
    "containing inclusion/exclusion criteria must be classified as "
    '"TRIAL_POPULATION". Use "OTHER" when nothing fits.\n'
    "- CRITICAL page numbering rule: start_page and end_page MUST be the "
    "1-based PDF page positions from the === PAGE n === markers, NOT the "
    "page numbers printed inside the document headers, footers, or Table of "
    "Contents (for example, if a section starts under === PAGE 22 === even "
    "though the page header prints '17', start_page is 22).\n"
    "- Set citation.page_number to start_page and quote the section's "
    "heading line plus the immediately following words on start_page so the "
    "verbatim quote is at least 15 non-space, non-hyphen characters.\n"
    "- Write summary as a single concise sentence."
)

ENDPOINTS_INSTRUCTIONS = (
    "Extract every primary, secondary, and exploratory endpoint or outcome "
    "measure from the protocol, in document order, into JSON matching the "
    "EndpointList schema.\n"
    f"- Set kind to one of: {ALLOWED_ENDPOINT_KINDS}.\n"
    "- Set time_frame to the assessment timepoint if stated (for example, "
    "'6 months' or '26 weeks'), or null if not stated.\n"
    "- Quote the endpoint's own wording verbatim from the cited page (at "
    "least 15 non-space, non-hyphen characters). A protocol may state its "
    "endpoints inside its Objectives, Aims, or Hypotheses (for example, "
    "where the Endpoints row says 'As outlined above under aims'): extract "
    "and quote those endpoint statements directly."
)
