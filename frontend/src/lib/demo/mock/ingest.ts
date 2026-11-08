import type { StepData } from "../types";
import { CRITERIA, type CriterionType } from "./criteria";
import {
  CONSENT_DOCUMENT,
  DATA_SOURCES,
  MOCK_PROTOCOL_PAGE_COUNT,
  PROTOCOL_DOCUMENT,
  REFERENCES,
  stepTiming,
  timedTrace,
} from "./shared";

const AGENT = "Ingestion";

// Parse confidence per ICH M11 section, as a percentage. Section 6 holds
// the Schedule of Activities (merged cells) and Section 11 two scanned
// pages, which is why those two score lowest.
const M11_SECTIONS = [
  { section: "1", title: "Protocol Summary", start: 1, end: 9, pct: 98 },
  { section: "2", title: "Introduction", start: 10, end: 11, pct: 99 },
  {
    section: "3",
    title: "Objectives, Endpoints and Estimands",
    start: 12,
    end: 15,
    pct: 97,
  },
  { section: "4", title: "Trial Design", start: 16, end: 21, pct: 95 },
  { section: "5", title: "Trial Population", start: 22, end: 27, pct: 96 },
  {
    section: "6",
    title: "Trial Intervention and Schedule of Activities",
    start: 28,
    end: 39,
    pct: 81,
  },
  {
    section: "7",
    title: "Participant Discontinuation",
    start: 40,
    end: 42,
    pct: 97,
  },
  {
    section: "8",
    title: "Trial Assessments and Procedures",
    start: 43,
    end: 49,
    pct: 93,
  },
  {
    section: "9",
    title: "Statistical Considerations",
    start: 50,
    end: 57,
    pct: 94,
  },
  {
    section: "10",
    title: "Regulatory, Ethical and Trial Oversight",
    start: 58,
    end: 64,
    pct: 96,
  },
  {
    section: "11",
    title: "Appendices and References",
    start: 65,
    end: MOCK_PROTOCOL_PAGE_COUNT,
    pct: 88,
  },
];

const CATEGORY_ORDER = [
  "Demographics",
  "Diagnosis and glycaemic",
  "Background therapy",
  "Laboratory",
  "Renal",
  "Prior medication",
  "Cardiovascular",
  "Hepatic",
  "Reproductive",
  "Administrative and other",
];

const countCriteria = (type: CriterionType, category?: string): number =>
  CRITERIA.filter(
    (criterion) =>
      criterion.type === type &&
      (category === undefined || criterion.category === category)
  ).length;

const CRITERIA_BY_CATEGORY = CATEGORY_ORDER.map((category) => ({
  category,
  inclusion: countCriteria("inclusion", category),
  exclusion: countCriteria("exclusion", category),
}));

const criteriaListTable = {
  table_id: "tbl-ing-criteria-list",
  title: "Every extracted eligibility criterion",
  description:
    "All 34 criteria with their verbatim text, page and whether the " +
    "cohort agent can evaluate them from patient records.",
  columns: [
    { key: "id", label: "ID" },
    { key: "type", label: "Type" },
    { key: "category", label: "Category" },
    { key: "text", label: "Criterion text" },
    { key: "section", label: "Section" },
    { key: "page", label: "Page" },
    { key: "confidence", label: "Parse confidence" },
    { key: "computable", label: "Computable" },
    { key: "notes", label: "Notes" },
  ],
  rows: CRITERIA.map((criterion) => ({ ...criterion })),
};

const FIELD_SNIPPET_TITLE =
  "A Phase 3, Randomised, Double-blind, Placebo-controlled Trial of an " +
  "SGLT2 Inhibitor Added to Metformin in Adults with Type 2 Diabetes";

const extractedFieldsTable = {
  table_id: "tbl-ing-fields",
  title: "Every extracted protocol field",
  description:
    "Key design fields with the verbatim text each value was read from.",
  columns: [
    { key: "field", label: "Field" },
    { key: "value", label: "Extracted value" },
    { key: "page", label: "Page" },
    { key: "snippet", label: "Source text" },
    { key: "confidence", label: "Confidence" },
  ],
  rows: [
    {
      field: "Title",
      value: "SGLT2 inhibitor added to metformin in adults with T2D",
      page: 1,
      snippet: FIELD_SNIPPET_TITLE,
      confidence: 0.99,
    },
    {
      field: "Protocol ID and version",
      value: "SGLT2-T2D-301, v0.3 (draft)",
      page: 1,
      snippet: "Protocol SGLT2-T2D-301, Version 0.3 (draft)",
      confidence: 0.99,
    },
    {
      field: "Phase",
      value: "3",
      page: 1,
      snippet: "A Phase 3, Randomised, Double-blind, Placebo-controlled Trial",
      confidence: 0.99,
    },
    {
      field: "Indication",
      value: "Type 2 diabetes, add-on to metformin",
      page: 1,
      snippet: "Added to Metformin in Adults with Type 2 Diabetes",
      confidence: 0.98,
    },
    {
      field: "Design",
      value: "Randomised, double-blind, placebo-controlled, parallel-group",
      page: 16,
      snippet:
        "This is a randomised, double-blind, placebo-controlled, " +
        "parallel-group trial.",
      confidence: 0.97,
    },
    {
      field: "Arms",
      value: "3 (10 mg, 25 mg, placebo), 1:1:1",
      page: 18,
      snippet:
        "Participants will be randomised 1:1:1 to SGLT2 inhibitor 10 mg, " +
        "25 mg or placebo.",
      confidence: 0.98,
    },
    {
      field: "Doses",
      value: "10 mg or 25 mg orally once daily",
      page: 28,
      snippet:
        "Study drug is taken orally once daily as a 10 mg or 25 mg " +
        "tablet, or matching placebo.",
      confidence: 0.97,
    },
    {
      field: "Treatment duration",
      value: "26 weeks",
      page: 16,
      snippet: "The treatment period is 26 weeks",
      confidence: 0.97,
    },
    {
      field: "Safety follow-up",
      value: "2 weeks",
      page: 16,
      snippet: "followed by a 2-week safety follow-up.",
      confidence: 0.97,
    },
    {
      field: "Washout of prior agents",
      value: "12 weeks (SGLT2 inhibitors, GLP-1 receptor agonists)",
      page: 25,
      snippet: "SGLT2 inhibitor use within 12 weeks before screening.",
      confidence: 0.97,
    },
    {
      field: "Sample size",
      value: "1,200 participants",
      page: 52,
      snippet:
        "Assuming a treatment difference of 0.5%, 1,200 participants " +
        "provide 90% power.",
      confidence: 0.98,
    },
    {
      field: "Assumed dropout",
      value: "15%",
      page: 53,
      snippet: "An overall dropout rate of 15% is assumed.",
      confidence: 0.97,
    },
    {
      field: "Primary endpoint",
      value: "Change in HbA1c from baseline at Week 24",
      page: 12,
      snippet:
        "Primary endpoint: mean change in HbA1c from baseline at Week 24.",
      confidence: 0.99,
    },
    {
      field: "Key secondary endpoints",
      value: "FPG, body weight, HbA1c < 7.0%, systolic BP (all Week 24)",
      page: 13,
      snippet:
        "Key secondary endpoints at Week 24: change in fasting plasma " +
        "glucose, change in body weight",
      confidence: 0.97,
    },
    {
      field: "Primary analysis",
      value: "ANCOVA adjusted for baseline HbA1c; LOCF for missing data",
      page: 54,
      snippet:
        "The primary endpoint is analysed by ANCOVA with baseline HbA1c " +
        "as a covariate.",
      confidence: 0.97,
    },
    {
      field: "Visits",
      value: "9 (V1 screening to V9 follow-up); End of Treatment Week 26",
      page: 31,
      snippet: "End of Treatment visit: Week 26 (+/- 3 days)",
      confidence: 0.62,
    },
  ],
};

const criteriaTable = {
  table_id: "tbl-ing-criteria",
  title: "Eligibility criteria by category",
  description:
    "Numbered items I-01 to I-14 (p. 24) and E-01 to E-20 (pp. 25-26).",
  columns: [
    { key: "category", label: "Category" },
    { key: "inclusion", label: "Inclusion" },
    { key: "exclusion", label: "Exclusion" },
    { key: "total", label: "Total" },
  ],
  rows: [
    ...CRITERIA_BY_CATEGORY.map((row) => ({
      ...row,
      total: row.inclusion + row.exclusion,
    })),
    {
      category: "Total",
      inclusion: countCriteria("inclusion"),
      exclusion: countCriteria("exclusion"),
      total: CRITERIA.length,
    },
  ],
};

export const INGEST_STEP: StepData = {
  id: "ingest",
  title: "Data Ingestion",
  summary:
    "Protocol PDF and consent form parsed into a structured, cited " +
    "document mapped to the 11 ICH M11 sections.",
  headline: {
    label: "criteria extracted",
    value: "34",
    numeric_value: 34,
    unit: "criteria",
  },
  metrics: [
    {
      metric_id: "m-ing-pages",
      label: "Pages",
      value: "86",
      numeric_value: MOCK_PROTOCOL_PAGE_COUNT,
      unit: "pages",
      description: "Pages read from the uploaded protocol PDF.",
    },
    {
      metric_id: "m-ing-sections",
      label: "ICH M11 sections",
      value: "11/11",
      tone: "good",
      numeric_value: 11,
      unit: "sections",
      description: "Protocol headings mapped onto the ICH M11 template.",
      benchmarks: [{ label: "ICH M11 template", value: "11", numeric_value: 11 }],
    },
    {
      metric_id: "m-ing-criteria",
      label: "Criteria extracted",
      value: "34",
      numeric_value: 34,
      unit: "criteria",
      description: "14 inclusion and 20 exclusion criteria, each quoted.",
    },
    {
      metric_id: "m-ing-warnings",
      label: "Parser warnings",
      value: "2",
      tone: "warn",
      numeric_value: 2,
      unit: "warnings",
      description: "Spots where the text could not be read with confidence.",
    },
  ],
  status: "completed",
  agent: AGENT,
  ...stepTiming("ingest"),
  warnings: [
    {
      code: "SOA_MERGED_CELLS",
      message:
        "Schedule of Activities (p. 31): merged cells in the final row; " +
        "the End of Treatment week was read with confidence 0.62.",
      severity: "warning",
    },
    {
      code: "OCR_LOW_CONFIDENCE",
      message:
        "Pages 71-72 (Appendix 11.4, lab reference ranges) are scanned " +
        "images; OCR mean character confidence 0.88.",
      severity: "info",
    },
  ],
  data_sources: [DATA_SOURCES.protocol, DATA_SOURCES.consent, DATA_SOURCES.ichM11],
  tables: [
    {
      table_id: "tbl-ing-sections",
      title: "ICH M11 sections extracted",
      description: "Page ranges and parse confidence for each section.",
      columns: [
        { key: "section", label: "Section" },
        { key: "title", label: "Title" },
        { key: "pages", label: "Pages" },
        { key: "page_count", label: "Page count", unit: "pages" },
        { key: "confidence", label: "Parse confidence" },
      ],
      rows: M11_SECTIONS.map((row) => ({
        section: row.section,
        title: row.title,
        pages: `${row.start}-${row.end}`,
        page_count: row.end - row.start + 1,
        confidence: row.pct / 100,
      })),
    },
    criteriaListTable,
    criteriaTable,
    extractedFieldsTable,
  ],
  charts: [
    {
      chart_id: "ch-ing-confidence",
      kind: "bar",
      title: "Parse confidence by ICH M11 section",
      description:
        "Sections 6 and 11 are lowest: a merged-cell table and two " +
        "scanned pages.",
      x_label: "ICH M11 section",
      y_label: "Parse confidence",
      unit: "%",
      series: [
        {
          name: "Parse confidence",
          points: M11_SECTIONS.map((row) => ({
            label: `§${row.section}`,
            value: row.pct,
            annotation: row.title,
          })),
        },
      ],
    },
  ],
  decisions: [
    {
      decision_id: "d-ing-01",
      step_id: "ingest",
      severity: "info",
      title: "Eligibility criteria extracted",
      claim:
        "34 discrete criteria were extracted: 14 inclusion, 20 exclusion.",
      category: "Eligibility",
      confidence: 0.96,
      location: {
        section_heading: "5",
        section_title: "Trial Population",
        start_page: 24,
        end_page: 26,
      },
      evidence: [
        {
          evidence_id: "e-ing-01",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 24,
          quote:
            "Participants must have an HbA1c between 7.0% and 10.5% " +
            "at screening.",
          is_verified: true,
          section_title: "5.1 Inclusion Criteria",
          context:
            "I-02. Diagnosis of type 2 diabetes for at least 180 days " +
            "before screening. I-03. Participants must have an HbA1c " +
            "between 7.0% and 10.5% at screening. I-04. Body mass index " +
            "between 22 and 45 kg/m2.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-ing-02",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 25,
          quote:
            "Participants with an HbA1c above 9.0% are excluded " +
            "from enrolment.",
          is_verified: true,
          section_title: "5.2 Exclusion Criteria",
          context:
            "E-02. History of diabetic ketoacidosis. E-03. Participants " +
            "with an HbA1c above 9.0% are excluded from enrolment. E-04. " +
            "Severe hypoglycaemia within 6 months before screening.",
          confidence: 0.98,
        },
      ],
      trace: timedTrace("ingest", "d-ing-01", 6_200, [
        {
          agent: AGENT,
          kind: "retrieve",
          text:
            "Located Section 5 (Trial Population) on pages 22-27, with " +
            "the numbered criteria lists on pages 24-26.",
          evidence_ids: ["e-ing-01"],
          duration_ms: 1_150,
        },
        {
          agent: AGENT,
          kind: "rule",
          text:
            "Split items I-01 to I-14 and E-01 to E-20 into discrete " +
            "criteria; multi-clause items were kept whole.",
          evidence_ids: ["e-ing-01", "e-ing-02"],
          duration_ms: 2_480,
        },
        {
          agent: AGENT,
          kind: "rule",
          text:
            "Normalised thresholds and units (%, mL/min/1.73 m2, years) " +
            "so later agents can compare and simulate them.",
          evidence_ids: ["e-ing-02"],
          duration_ms: 1_730,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text:
            "34 criteria extracted, each with a verbatim quote and page " +
            "that matched the PDF text exactly.",
          evidence_ids: ["e-ing-02"],
          duration_ms: 310,
        },
      ]),
      impact: [
        { label: "Inclusion", value: "14", numeric_value: 14, unit: "criteria" },
        { label: "Exclusion", value: "20", numeric_value: 20, unit: "criteria" },
        {
          label: "Quotes verified",
          value: "34/34",
          tone: "good",
          numeric_value: 34,
          unit: "criteria",
          description: "Each quote was matched character for character.",
        },
      ],
      references: [REFERENCES.ichM11],
      decision_owner: "Protocol Author",
      review_status: "pending",
      tags: ["eligibility", "extraction"],
      tables: [criteriaListTable, criteriaTable],
    },
    {
      decision_id: "d-ing-02",
      step_id: "ingest",
      severity: "warning",
      title: "Schedule of Activities partly unreadable",
      claim:
        "The final row of the Schedule of Activities table could not " +
        "be parsed reliably, so the last visit week is uncertain.",
      category: "Schedule of Activities",
      confidence: 0.62,
      location: {
        section_heading: "6.1",
        section_title: "Schedule of Activities",
        start_page: 31,
        end_page: 31,
      },
      evidence: [
        {
          evidence_id: "e-ing-03",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 31,
          quote: "End of Treatment visit: Week 26 (+/- 3 days)",
          is_verified: false,
          section_title: "6.1 Schedule of Activities",
          context:
            "V7: Week 20 (+/- 3 days): HbA1c, FPG, vital signs, adverse " +
            "event review. End of Treatment visit: Week 26 (+/- 3 days) " +
            "Follow-up: 2 weeks after the last dose of study drug.",
          confidence: 0.62,
        },
        {
          evidence_id: "e-ing-04",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 16,
          quote:
            "The treatment period is 26 weeks, followed by a 2-week " +
            "safety follow-up.",
          is_verified: true,
          section_title: "4.1 Overall Design",
          context:
            "This is a randomised, double-blind, placebo-controlled, " +
            "parallel-group trial. The treatment period is 26 weeks, " +
            "followed by a 2-week safety follow-up. Participants continue " +
            "their background metformin throughout.",
          confidence: 0.97,
        },
      ],
      trace: timedTrace("ingest", "d-ing-02", 11_400, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Found the Schedule of Activities table on page 31.",
          evidence_ids: ["e-ing-03"],
          duration_ms: 640,
        },
        {
          agent: AGENT,
          kind: "rule",
          text:
            "Parsed 9 visit columns by 21 assessment rows; the last row " +
            "spans merged cells.",
          evidence_ids: ["e-ing-03"],
          duration_ms: 2_210,
        },
        {
          agent: AGENT,
          kind: "compare",
          text:
            "Week 26 agrees with the 26-week treatment period stated in " +
            "Section 4.1 (p. 16), which supports the reading.",
          evidence_ids: ["e-ing-03", "e-ing-04"],
          duration_ms: 520,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text:
            "Merged cells in the last row lowered parse confidence to " +
            "0.62; kept Week 26 and flagged it for a human check.",
          evidence_ids: ["e-ing-03"],
          duration_ms: 180,
        },
      ]),
      impact: [
        {
          label: "Parse confidence",
          value: "0.62",
          tone: "warn",
          numeric_value: 0.62,
          description: "For the End of Treatment row only.",
          benchmarks: [
            { label: "Rest of table", value: "0.94", numeric_value: 0.94 },
          ],
        },
        { label: "Visits parsed", value: "9", numeric_value: 9, unit: "visits" },
      ],
      options: [
        {
          option_id: "o-ing-02-a",
          title: "Confirm the End of Treatment week by hand",
          rationale:
            "One cell is uncertain and Section 4.1 already corroborates " +
            "Week 26, so a 1-minute human check is enough.",
          is_recommended: true,
          impact: [{ label: "Effort", value: "~1 min" }],
          risks: ["None beyond the reviewer's time."],
        },
        {
          option_id: "o-ing-02-b",
          title: "Re-export the table without merged cells",
          rationale:
            "A native table makes every later upload parse cleanly, but " +
            "needs the protocol author to edit the source document.",
          impact: [{ label: "Effort", value: "~15 min" }],
          risks: ["Delays this review until a new PDF is uploaded."],
        },
      ],
      references: [REFERENCES.spiritSchedule],
      decision_owner: "Protocol Author",
      review_status: "pending",
      tags: ["schedule-of-activities", "parse-quality"],
      tables: [
        {
          table_id: "tbl-ing-soa",
          title: "Visits parsed from the Schedule of Activities",
          columns: [
            { key: "visit", label: "Visit" },
            { key: "name", label: "Name" },
            { key: "week", label: "Week" },
            { key: "window_days", label: "Window", unit: "days" },
            { key: "confidence", label: "Parse confidence" },
          ],
          rows: [
            { visit: "V1", name: "Screening", week: -2, window_days: 3, confidence: 0.96 },
            { visit: "V2", name: "Randomisation", week: 0, window_days: 0, confidence: 0.97 },
            { visit: "V3", name: "Treatment", week: 4, window_days: 3, confidence: 0.95 },
            { visit: "V4", name: "Treatment", week: 8, window_days: 3, confidence: 0.95 },
            { visit: "V5", name: "Treatment", week: 12, window_days: 3, confidence: 0.94 },
            { visit: "V6", name: "Treatment", week: 16, window_days: 3, confidence: 0.94 },
            { visit: "V7", name: "Treatment", week: 20, window_days: 3, confidence: 0.93 },
            { visit: "V8", name: "End of Treatment", week: 26, window_days: 3, confidence: 0.62 },
            { visit: "V9", name: "Safety follow-up", week: 28, window_days: 3, confidence: 0.92 },
          ],
        },
      ],
    },
    {
      decision_id: "d-ing-03",
      step_id: "ingest",
      severity: "info",
      title: "Primary and secondary endpoints extracted",
      claim:
        "1 primary, 4 key secondary and 2 exploratory endpoints were " +
        "extracted; the primary and key secondary ones are timed at " +
        "Week 24.",
      category: "Endpoints",
      confidence: 0.97,
      location: {
        section_heading: "3",
        section_title: "Objectives, Endpoints and Estimands",
        start_page: 12,
        end_page: 14,
      },
      evidence: [
        {
          evidence_id: "e-ing-05",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 12,
          quote:
            "Primary endpoint: mean change in HbA1c from baseline " +
            "at Week 24.",
          is_verified: true,
          section_title: "3.1 Primary Objective and Endpoint",
          context:
            "The primary objective is to show that each dose lowers " +
            "HbA1c more than placebo when added to metformin. Primary " +
            "endpoint: mean change in HbA1c from baseline at Week 24.",
          confidence: 0.99,
        },
        {
          evidence_id: "e-ing-06",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 13,
          quote:
            "Key secondary endpoints at Week 24: change in fasting " +
            "plasma glucose, change in body weight, proportion reaching " +
            "HbA1c below 7.0%, and change in systolic blood pressure.",
          is_verified: true,
          section_title: "3.2 Secondary Objectives and Endpoints",
          context:
            "Key secondary endpoints at Week 24: change in fasting " +
            "plasma glucose, change in body weight, proportion reaching " +
            "HbA1c below 7.0%, and change in systolic blood pressure. " +
            "These will be tested hierarchically in the order listed.",
          confidence: 0.97,
        },
      ],
      trace: timedTrace("ingest", "d-ing-03", 4_100, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Located Section 3 (Objectives and Endpoints), pages 12-15.",
          evidence_ids: ["e-ing-05"],
          duration_ms: 520,
        },
        {
          agent: AGENT,
          kind: "rule",
          text:
            "Classified each endpoint as primary, key secondary or " +
            "exploratory and captured its time point.",
          evidence_ids: ["e-ing-05", "e-ing-06"],
          duration_ms: 1_340,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "7 endpoints extracted; 5 are measured at Week 24.",
          evidence_ids: ["e-ing-06"],
          duration_ms: 150,
        },
      ]),
      impact: [
        { label: "Primary", value: "1", numeric_value: 1, unit: "endpoints" },
        { label: "Key secondary", value: "4", numeric_value: 4, unit: "endpoints" },
        { label: "Exploratory", value: "2", numeric_value: 2, unit: "endpoints" },
      ],
      references: [REFERENCES.spiritOutcomes],
      decision_owner: "Lead Biostatistician",
      review_status: "pending",
      tags: ["endpoints", "extraction"],
      tables: [
        {
          table_id: "tbl-ing-endpoints",
          title: "Endpoints extracted",
          columns: [
            { key: "type", label: "Type" },
            { key: "endpoint", label: "Endpoint" },
            { key: "timepoint", label: "Time point" },
            { key: "page", label: "Page" },
          ],
          rows: [
            { type: "Primary", endpoint: "Change in HbA1c from baseline", timepoint: "Week 24", page: 12 },
            { type: "Key secondary", endpoint: "Change in fasting plasma glucose", timepoint: "Week 24", page: 13 },
            { type: "Key secondary", endpoint: "Change in body weight", timepoint: "Week 24", page: 13 },
            { type: "Key secondary", endpoint: "Proportion with HbA1c < 7.0%", timepoint: "Week 24", page: 13 },
            { type: "Key secondary", endpoint: "Change in systolic blood pressure", timepoint: "Week 24", page: 13 },
            { type: "Exploratory", endpoint: "Change in eGFR", timepoint: "Week 26", page: 14 },
            { type: "Exploratory", endpoint: "Treatment satisfaction (DTSQ)", timepoint: "Week 26", page: 14 },
          ],
        },
      ],
    },
    {
      decision_id: "d-ing-04",
      step_id: "ingest",
      severity: "info",
      title: "Consent form linked to the protocol",
      claim:
        "The consent form names the same study, SGLT2-T2D-301, but was " +
        "written for protocol version 0.2, one version behind the " +
        "uploaded draft; its differences are checked in the next step.",
      category: "Source documents",
      confidence: 0.93,
      location: {
        section_heading: "1",
        section_title: "Protocol Summary",
        start_page: 1,
        end_page: 1,
      },
      evidence: [
        {
          evidence_id: "e-ing-07",
          source: "consent",
          document: CONSENT_DOCUMENT,
          page: 1,
          quote:
            "This form describes study SGLT2-T2D-301, protocol " +
            "version 0.2.",
          is_verified: true,
          section_title: "Participant Information",
          context:
            "You are being invited to take part in a research study. " +
            "This form describes study SGLT2-T2D-301, protocol version " +
            "0.2. Please read it carefully and ask any questions.",
          confidence: 0.95,
        },
        {
          evidence_id: "e-ing-08",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 1,
          quote: "Protocol SGLT2-T2D-301, Version 0.3 (draft)",
          is_verified: true,
          section_title: "Title Page",
          context:
            "A Phase 3, Randomised, Double-blind, Placebo-controlled " +
            "Trial of an SGLT2 Inhibitor Added to Metformin in Adults " +
            "with Type 2 Diabetes. Protocol SGLT2-T2D-301, Version 0.3 " +
            "(draft)",
          confidence: 0.99,
        },
      ],
      trace: timedTrace("ingest", "d-ing-04", 1_200, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Parsed the 9-page consent form uploaded with the protocol.",
          evidence_ids: ["e-ing-07"],
          duration_ms: 1_870,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Study identifier SGLT2-T2D-301 matches the protocol title page.",
          evidence_ids: ["e-ing-07", "e-ing-08"],
          duration_ms: 240,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Consent cites protocol v0.2; the uploaded protocol is v0.3.",
          evidence_ids: ["e-ing-07", "e-ing-08"],
          duration_ms: 190,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text:
            "Linked the two documents and passed the version gap to the " +
            "consistency check.",
          evidence_ids: ["e-ing-07"],
          duration_ms: 90,
        },
      ]),
      impact: [
        { label: "Consent pages", value: "9", numeric_value: 9, unit: "pages" },
        { label: "Version gap", value: "v0.2 vs v0.3", tone: "warn" },
      ],
      references: [REFERENCES.ichE6R3],
      decision_owner: "Regulatory Lead",
      review_status: "pending",
      tags: ["consent", "version-mismatch"],
    },
  ],
};
