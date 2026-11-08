// The 34 eligibility criteria of the sample protocol (synthetic), shared
// by the ingestion table and the cohort filter table so both list exactly
// the same items with the same ids, text and pages.

export type CriterionType = "inclusion" | "exclusion";
// "yes": a structured-data rule; "assumed met": administrative, treated
// as satisfied; "no": cannot be evaluated from records at all.
export type Computability = "yes" | "assumed met" | "no";

export interface Criterion {
  id: string;
  type: CriterionType;
  category: string;
  text: string;
  section: string;
  page: number;
  confidence: number;
  computable: Computability;
  notes: string;
}

const INCLUSION_SECTION = "5.1 Inclusion Criteria";
const EXCLUSION_SECTION = "5.2 Exclusion Criteria";

function inclusion(
  id: string,
  category: string,
  text: string,
  computable: Computability,
  notes = "",
  confidence = 0.98
): Criterion {
  return {
    id,
    type: "inclusion",
    category,
    text,
    section: INCLUSION_SECTION,
    page: 24,
    confidence,
    computable,
    notes,
  };
}

function exclusion(
  id: string,
  category: string,
  text: string,
  page: number,
  notes = "",
  computable: Computability = "yes",
  confidence = 0.97
): Criterion {
  return {
    id,
    type: "exclusion",
    category,
    text,
    section: EXCLUSION_SECTION,
    page,
    confidence,
    computable,
    notes,
  };
}

export const CRITERIA: Criterion[] = [
  inclusion("I-01", "Demographics", "Aged 18 to 75 years at screening.", "yes",
    "Upper age bound is below the peer range."),
  inclusion("I-02", "Diagnosis and glycaemic",
    "Diagnosis of type 2 diabetes for at least 180 days before screening.",
    "yes"),
  inclusion("I-03", "Diagnosis and glycaemic",
    "Participants must have an HbA1c between 7.0% and 10.5% at screening.",
    "yes", "Upper bound conflicts with E-03 (9.0%)."),
  inclusion("I-04", "Diagnosis and glycaemic",
    "Body mass index between 22 and 45 kg/m2.", "yes"),
  inclusion("I-05", "Background therapy",
    "On metformin at a stable dose of at least 1,500 mg/day for at least " +
      "8 weeks.", "yes"),
  inclusion("I-06", "Background therapy",
    "No change in metformin dose in the 8 weeks before screening.", "yes"),
  inclusion("I-07", "Laboratory",
    "Fasting C-peptide of at least 0.8 ng/mL at screening.", "yes"),
  inclusion("I-08", "Reproductive",
    "Negative pregnancy test at screening for women of childbearing " +
      "potential.", "assumed met", "Measured at the screening visit."),
  inclusion("I-09", "Reproductive",
    "Women of childbearing potential agree to use highly effective " +
      "contraception.", "no", "Future intent is not recorded in EHR data."),
  inclusion("I-10", "Administrative and other",
    "Signed informed consent before any study procedure.", "assumed met"),
  inclusion("I-11", "Administrative and other",
    "Able and willing to attend all scheduled visits.", "assumed met"),
  inclusion("I-12", "Administrative and other",
    "Willing to perform self-monitoring of blood glucose.", "no",
    "Willingness is not recorded in EHR data."),
  inclusion("I-13", "Administrative and other",
    "Able to use the electronic diary.", "assumed met"),
  inclusion("I-14", "Administrative and other",
    "Agrees to follow diet and exercise counselling throughout the trial.",
    "assumed met"),
  exclusion("E-01", "Diagnosis and glycaemic",
    "Type 1 diabetes or latent autoimmune diabetes in adults.", 25),
  exclusion("E-02", "Diagnosis and glycaemic",
    "History of diabetic ketoacidosis.", 25),
  exclusion("E-03", "Diagnosis and glycaemic",
    "Participants with an HbA1c above 9.0% are excluded from enrolment.",
    25, "Stricter than I-03; this is the bound applied in practice."),
  exclusion("E-04", "Diagnosis and glycaemic",
    "Severe hypoglycaemia within 6 months before screening.", 25),
  exclusion("E-05", "Renal", "eGFR below 45 mL/min/1.73 m2 at screening.",
    25, "Removes the most patients in the cohort simulation."),
  exclusion("E-06", "Renal", "Dialysis or kidney transplant.", 25),
  exclusion("E-07", "Prior medication",
    "Insulin use within 12 months before screening.", 25,
    "Also excludes short courses, e.g. during a hospital stay."),
  exclusion("E-08", "Prior medication",
    "SGLT2 inhibitor use within 12 weeks before screening.", 25),
  exclusion("E-09", "Prior medication",
    "GLP-1 receptor agonist use within 12 weeks before screening.", 25),
  exclusion("E-10", "Prior medication",
    "Systemic corticosteroids for more than 14 days within 8 weeks " +
      "before screening.", 26),
  exclusion("E-11", "Prior medication",
    "Weight-loss medication within 12 weeks before screening.", 26),
  exclusion("E-12", "Cardiovascular",
    "Myocardial infarction, stroke or TIA within 3 months before " +
      "screening.", 26),
  exclusion("E-13", "Cardiovascular", "Heart failure, NYHA class IV.", 26),
  exclusion("E-14", "Cardiovascular",
    "Uncontrolled hypertension (180/110 mmHg or higher).", 26),
  exclusion("E-15", "Cardiovascular",
    "Coronary or carotid revascularisation within 3 months before " +
      "screening.", 26),
  exclusion("E-16", "Hepatic",
    "ALT or AST above 3 times the upper limit of normal.", 26),
  exclusion("E-17", "Hepatic", "Cirrhosis or other chronic liver disease.",
    26),
  exclusion("E-18", "Administrative and other",
    "Malignancy within 5 years, except treated basal cell carcinoma.", 26),
  exclusion("E-19", "Administrative and other",
    "Two or more genital mycotic infections in the past year.", 26),
  exclusion("E-20", "Administrative and other",
    "Any condition that, in the investigator's judgement, makes adherence " +
      "unlikely.", 26, "Depends on investigator judgement.", "no", 0.96),
];

export function criterionById(id: string): Criterion {
  const criterion = CRITERIA.find((candidate) => candidate.id === id);
  if (!criterion) {
    throw new Error(`expected a criterion '${id}', found none`);
  }
  return criterion;
}
