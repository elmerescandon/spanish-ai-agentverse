"""Prompt text shared by every parser facet.

Facet-specific instructions live next to each facet definition; the rules
here apply to all of them, so citations can be checked against the PDF.
"""

from backend.shared.messages import (
    AllocationType,
    AnalysisSetType,
    CommitteeType,
    ControlType,
    CriterionKind,
    DrugClass,
    EndpointKind,
    EpochType,
    EstimandStrategy,
    IntercurrentEventType,
    InterventionModelType,
    InterventionType,
    M11Heading,
    MaskingType,
    ScaleDirection,
    StratificationFactorType,
    SubgroupDimension,
    TrialPhase,
)
from backend.shared.prompting import quoted_values

ALLOWED_CRITERION_KINDS = quoted_values(CriterionKind)
ALLOWED_PHASES = quoted_values(TrialPhase)
ALLOWED_ALLOCATIONS = quoted_values(AllocationType)
ALLOWED_INTERVENTION_MODELS = quoted_values(InterventionModelType)
ALLOWED_MASKING = quoted_values(MaskingType)
ALLOWED_M11_HEADINGS = quoted_values(M11Heading)
ALLOWED_ENDPOINT_KINDS = quoted_values(EndpointKind)
ALLOWED_SCALE_DIRECTIONS = quoted_values(ScaleDirection)
ALLOWED_EPOCH_TYPES = quoted_values(EpochType)
ALLOWED_ESTIMAND_STRATEGIES = quoted_values(EstimandStrategy)
ALLOWED_ICE_TYPES = quoted_values(IntercurrentEventType)
ALLOWED_INTERVENTION_TYPES = quoted_values(InterventionType)
ALLOWED_DRUG_CLASSES = quoted_values(DrugClass)
ALLOWED_CONTROL_TYPES = quoted_values(ControlType)
ALLOWED_ANALYSIS_SETS = quoted_values(AnalysisSetType)
ALLOWED_SUBGROUP_DIMENSIONS = quoted_values(SubgroupDimension)
ALLOWED_STRATIFICATION_FACTORS = quoted_values(StratificationFactorType)
ALLOWED_COMMITTEES = quoted_values(CommitteeType)

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
    "- official_title: the full official or scientific study title as "
    "printed, quoted from the page where it appears.\n"
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
    "Extract the top-level sections and numbered subsections of the protocol "
    "body into JSON matching the SectionMap schema.\n"
    "- In sections, produce one entry per top-level section of the protocol "
    "body (1, 2, 3, ..., plus a standalone SYNOPSIS if unnumbered), not "
    "subsections.\n"
    "- In subsections, produce one entry per numbered subsection in the "
    "protocol body (for example, '1.1', '1.2', '4.1', '4.2', '9.2', '11.3') "
    "with its number, title, 1-based PDF page_number, and verbatim "
    "citation.\n"
    "- Skip front and back matter: title page, statement of compliance, "
    "signature pages, table of contents, list of attachments/tables/figures, "
    "abbreviation lists, definitions of terms, and references.\n"
    f"- Classify heading by the section's CONTENT (not by its heading text, "
    "since sponsors name sections differently) into one of: "
    f"{ALLOWED_M11_HEADINGS}. For example, a section titled "
    "'5 TARGET POPULATION AND STUDY SAMPLE' or '4. SUBJECT POPULATION' "
    "containing inclusion/exclusion criteria must be classified as "
    '"TRIAL_POPULATION". Use "OTHER" when nothing fits.\n'
    "- CRITICAL page numbering rule: start_page, end_page, and subsection "
    "page_number MUST be the 1-based PDF page positions from the "
    "=== PAGE n === markers, NOT the page numbers printed inside the "
    "document headers, footers, or Table of Contents (for example, if a "
    "section starts under === PAGE 22 === even though the page header prints "
    "'17', start_page is 22).\n"
    "- Set citation.page_number to start_page (or subsection page_number) "
    "and quote the heading line plus the immediately following words on that "
    "page so the verbatim quote is at least 15 non-space, non-hyphen "
    "characters.\n"
    "- Write summary as a single concise sentence."
)

ENDPOINTS_INSTRUCTIONS = (
    "Extract every primary, secondary, and exploratory measured endpoint "
    "or outcome measure from the protocol, in document order, into JSON "
    "matching the EndpointList schema.\n"
    f"- Set kind to one of: {ALLOWED_ENDPOINT_KINDS}.\n"
    "- Set time_frame to the assessment timepoint if stated (for example, "
    "'6 months' or '26 weeks'), or null if not stated.\n"
    "- When an endpoint uses a rating or score scale (for example, DTSQ, "
    "SF-36, DDS), extract scale_name, numeric scale_min, numeric scale_max, "
    f"and scale_better_direction (one of {ALLOWED_SCALE_DIRECTIONS}) if "
    "stated in the protocol; return null for any scale field not stated.\n"
    "- Extract measured endpoints/outcome measures (for example, 'Change "
    "in HbA1c from baseline to Week 26'), not study objectives or "
    "hypotheses. When an objective or hypothesis restates an endpoint "
    "that is defined elsewhere in the protocol, list only the endpoint "
    "definition and do not duplicate it.\n"
    "- When a protocol states its endpoints only inside its Objectives, "
    "Aims, or Hypotheses (for example, where the Endpoints row says 'As "
    "outlined above under aims'), extract and quote those endpoint "
    "statements directly.\n"
    "- Quote the endpoint's own wording verbatim from the cited page (at "
    "least 15 non-space, non-hyphen characters)."
)

SCHEDULE_INSTRUCTIONS = (
    "Extract the study's Schedule of Activities (or Time and Events "
    "Schedule) into JSON matching the ScheduleOfActivities schema.\n"
    "- Prefer a Schedule of Activities / Time and Events table when its "
    "text is present in the extracted pages. When the table grid has no "
    "extractable text (or the protocol has no grid table), extract the "
    "scheduled visits from prose schedule sections, table footnotes, and "
    "study-evaluations sections.\n"
    "- Produce one entry per scheduled visit or assessment timepoint with:\n"
    "  - visit_name: name of the visit or timepoint as stated (for example, "
    "'Screening', 'Baseline / Day 1', 'Week 26', '6-month assessment').\n"
    "  - study_day: integer study day when stated in the text, or null when "
    "not stated.\n"
    f"  - epoch: canonical study period from {ALLOWED_EPOCH_TYPES} when the "
    'visit period is stated (use "OTHER" if a stated period does not fit '
    "the standard categories), or null when not stated.\n"
    "  - procedures: non-empty list of procedures, assessments, or "
    "activities performed at that visit as stated in the text.\n"
    "  - citation: quote the visit's row, column, footnote, or bullet text "
    "verbatim from the page where it appears (at least 15 non-space, "
    "non-hyphen characters; extend into neighbouring words on the same page "
    "if needed).\n"
    "- Never infer a visit or procedure that is not stated in the text; "
    "every visit must carry a verbatim citation quote that verifies."
)

STATISTICS_INSTRUCTIONS = (
    "Extract the study's statistical and sample-size assumptions from the "
    "sample size and statistical analysis sections into JSON matching the "
    "StatisticalAssumptions schema. Wrap each present value in "
    '{"value": ..., "citation": {"page_number": ..., "quote": ...}} and '
    "return null for any field not stated in the document.\n"
    "- sample_size: total planned number of enrolled or randomized "
    "participants used in the sample size calculation (integer, for example "
    "'target sample size is N = 200 enrolled participants' -> 200).\n"
    "- power: statistical power for the primary analysis expressed as a "
    "fraction in (0, 1) (for example, '80%' -> 0.8, '85% power' -> 0.85, "
    "or the power at the anticipated attrition rate when a power table is "
    "given).\n"
    "- alpha: Type I error rate or significance level (alpha) expressed as "
    "a fraction in (0, 1) (for example, 'Type 1 error rate of 0.05' or "
    "'2-sided alpha level of 0.05' or '5% significance level' -> 0.05).\n"
    "- dropout_rate: anticipated drop-out, attrition, or sample-size "
    "inflation rate expressed as a fraction in [0, 1) (for example, "
    "'drop-out rate < 10%' -> 0.10, '10% sample size inflation factor' -> "
    "0.10).\n"
    "- effect_size: assumed primary treatment effect or difference as "
    "stated in the text (string, for example '0.5%' or '0.4% to 0.5%').\n"
    "- effect_size_value: numeric absolute primary treatment difference in "
    "endpoint units when stated as a number (for example, 0.5 for '0.5% "
    "HbA1c'), or null when not stated as a single number.\n"
    "- standard_deviation: assumed standard deviation for the primary "
    "endpoint in the sample size calculation (positive float), or null.\n"
    "- allocation_ratio: ratio of treatment to control sample size (float, "
    "for example 1.0 for 1:1 randomization, 2.0 for 2:1), or null.\n"
    "- is_two_sided: tri-state boolean: true with quote if alpha is "
    "explicitly two-sided, false with quote if explicitly one-sided, or null "
    "if not stated (never default to false).\n"
    "- has_sample_size_calculation: tri-state boolean: true with quote if a "
    "formal sample-size or power calculation is given, false with quote if "
    "the protocol explicitly states sample size is not based on a power "
    "calculation, or null if not stated (never default to false).\n"
    "- assumptions_source_citation: cited prior trial, publication, or "
    "pilot study justifying the assumed effect size or SD, or null.\n"
    "- non_inferiority_margin: numeric non-inferiority margin when stated "
    "(positive float, for example 0.3 for '0.3%'), or null."
)

ESTIMANDS_INSTRUCTIONS = (
    "Extract structured ICH E9(R1) estimands from the objectives, estimands, "
    "and statistical sections into JSON matching the EstimandExtraction "
    "schema.\n"
    f"- For each defined estimand, set endpoint_kind to one of "
    f"{ALLOWED_ENDPOINT_KINDS}, endpoint_description, and any stated "
    "attributes (population, variable, intercurrent_events, "
    "population_level_summary, treatment_condition).\n"
    "- For each IntercurrentEvent in intercurrent_events, set:\n"
    f"  - event_type: canonical category from {ALLOWED_ICE_TYPES} "
    '(use "OTHER" rather than forcing a match when an event does not fit).\n'
    "  - event: description of the intercurrent event as stated.\n"
    f"  - strategy: canonical ICH E9(R1) strategy from "
    f"{ALLOWED_ESTIMAND_STRATEGIES}, or null if no handling strategy is "
    'stated (use "OTHER" rather than forcing a match).\n'
    "  - citation: verbatim quote from the cited page.\n"
    "- lists_all_five_attributes: tri-state boolean: true with quote if all "
    "5 ICH E9(R1) estimand attributes are explicitly stated for the primary "
    "estimand, false with quote if the protocol explicitly states estimands "
    "are not used, or null if not stated (never default to false)."
)

INTERVENTIONS_INSTRUCTIONS = (
    "Extract the study's intervention arms, background therapy, rescue "
    "therapy, prohibited medications, washout, stratification factors, and "
    "post-discontinuation follow-up into JSON matching the "
    "InterventionExtraction schema.\n"
    "- For each arm in arms, set name, intervention_type from "
    f"{ALLOWED_INTERVENTION_TYPES}, drug_class from {ALLOWED_DRUG_CLASSES} "
    "(or null for non-drug arms), dose_and_regimen, is_control, control_type "
    f"from {ALLOWED_CONTROL_TYPES} (or null for non-control arms), and "
    "verbatim citation.\n"
    "- background_therapy and background_therapy_stable_weeks: required "
    "background diabetes therapy and stable run-in/pre-trial duration in "
    "weeks (positive float), or null.\n"
    "- rescue_therapy_criteria and rescue_medication_regimen: glycemic "
    "thresholds and allowed drugs for rescue therapy, or null.\n"
    "- prohibited_medications and prior_washout_weeks: excluded therapies "
    "and required washout duration in weeks (positive float), or null.\n"
    "- stratification_factors: randomization stratification factors stated "
    "in the design or intervention sections; set category to one of "
    f'{ALLOWED_STRATIFICATION_FACTORS} (use "OTHER" rather than forcing a '
    "match), label, and citation.\n"
    "- continues_follow_up_after_discontinuation and "
    "collects_hba1c_after_discontinuation: tri-state booleans: true with "
    "quote if participants who discontinue treatment continue scheduled "
    "follow-up / HbA1c assessments, false with quote if the protocol states "
    "assessments stop at treatment discontinuation, or null if not stated "
    "(never default to false)."
)

ANALYSIS_INSTRUCTIONS = (
    "Extract the statistical analysis plan from the statistical section into "
    "JSON matching the AnalysisPlanExtraction schema.\n"
    "- analysis_sets and primary_analysis_set: defined analysis populations; "
    f'set category to one of {ALLOWED_ANALYSIS_SETS} (use "OTHER" rather '
    "than forcing a match), label, and verbatim citation.\n"
    "- primary_analysis_method: statistical model or test for the primary "
    "endpoint (for example, 'MMRM', 'ANCOVA', 'linear mixed model'), or "
    "null.\n"
    "- primary_analysis_covariates: covariates or factors included in the "
    "primary analysis model; set category to one of "
    f'{ALLOWED_STRATIFICATION_FACTORS} (use "OTHER" rather than forcing a '
    "match), label, and citation.\n"
    "- missing_data_method, sensitivity_analyses, confirmatory_hierarchy, "
    "stopping_boundaries, and alpha_spending_function: wrap each stated "
    "fact in a CitedValue or return null/empty list.\n"
    "- prespecified_subgroups: subgroup variables planned for subgroup "
    f"analyses; set category to one of {ALLOWED_SUBGROUP_DIMENSIONS} "
    '(use "OTHER" rather than forcing a match), label, and citation.\n'
    "- adjusts_for_baseline, controls_type_i_error, and "
    "has_interim_analysis: tri-state booleans: true with quote if explicitly "
    "stated, false with quote if the protocol explicitly states the "
    "opposite (for example, 'No interim analysis is planned' -> false), or "
    "null if not stated (never default to false)."
)

SYNOPSIS_CHECK_INSTRUCTIONS = (
    "Extract synopsis-vs-body consistency facts, oversight committees, study "
    "schema epochs, biospecimen retention periods, lay summary, and amendment "
    "history into JSON matching the SynopsisConsistencyExtraction schema.\n"
    "- Quote synopsis_enrollment, synopsis_arm_count, "
    "synopsis_treatment_duration_weeks, synopsis_primary_timepoint_weeks, "
    "synopsis_stratification_factors, synopsis_committees, and "
    "synopsis_ice_strategies ONLY from the Synopsis / Protocol Summary "
    "section; return null or empty list if not stated in the Synopsis.\n"
    "- Quote body_treatment_duration_weeks and body_primary_timepoint_weeks "
    "ONLY from the main protocol body sections (outside the Synopsis).\n"
    "- For synopsis_stratification_factors, set category to one of "
    f'{ALLOWED_STRATIFICATION_FACTORS} (use "OTHER" rather than forcing a '
    "match).\n"
    "- For synopsis_committees and governance_committees (from oversight or "
    "governance sections in the body), set category to one of "
    f'{ALLOWED_COMMITTEES} (use "OTHER" rather than forcing a match).\n'
    "- For schema_epochs, extract each study period/epoch from the study "
    f"schema or design overview with epoch_type from {ALLOWED_EPOCH_TYPES} "
    '(use "OTHER" rather than forcing a match), name, duration_weeks, and '
    "citation.\n"
    "- For synopsis_ice_strategies, use event_type from "
    f"{ALLOWED_ICE_TYPES} and strategy from {ALLOWED_ESTIMAND_STRATEGIES}.\n"
    "- assessments_retention_years and icf_retention_years: biospecimen or "
    "record retention duration in years stated in the Assessments section vs "
    "the Regulatory/Informed Consent section, or null.\n"
    "- has_lay_summary and states_no_amendments: tri-state booleans: true "
    "with quote if present/stated, false with quote if the opposite is "
    "stated, or null if not found (never default to false).\n"
    "- amendment_numbers: integer amendment numbers listed in the amendment "
    "history."
)

SAFETY_MONITORING_INSTRUCTIONS = (
    "Extract diabetes and general safety monitoring definitions from the "
    "safety and adverse-event sections into JSON matching the "
    "SafetyMonitoringExtraction schema.\n"
    "- level_1_glucose_mg_dl and level_2_glucose_mg_dl: numeric blood "
    "glucose thresholds in mg/dL for Level 1 (for example, 70.0) and Level 2 "
    "(for example, 54.0) hypoglycemia when stated, or null.\n"
    "- defines_hypoglycemia_levels, level_3_requires_assistance, "
    "captures_hypoglycemia_diary, defines_dka_criteria, "
    "defines_sae_escalation, monitors_renal_function, and "
    "has_cv_adjudication: tri-state booleans: true with quote if explicitly "
    "defined or performed in the protocol, false with quote if the protocol "
    "explicitly states the opposite, or null if not stated (never default to "
    "false)."
)
