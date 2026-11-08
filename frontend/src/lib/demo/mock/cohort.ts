import type { ChartPoint, DetailMap, StepData } from "../types";
import { CRITERIA, criterionById } from "./criteria";
import {
  COHORT_DOCUMENT,
  COHORT_ELIGIBLE_COUNT,
  COHORT_START_COUNT,
  DATA_SOURCES,
  PEER_SET_DOCUMENT,
  PROTOCOL_DOCUMENT,
  REFERENCES,
  stepTiming,
  timedTrace,
} from "./shared";

const AGENT = "Cohort";

interface FilterRule {
  criterion_id: string;
  rule: string;
  data_field: string;
  removed: number;
  note?: string;
}

interface FilterGroup {
  label: string;
  rules: FilterRule[];
}

// Criteria baked into the starting cohort definition (remove nobody here).
const COHORT_DEFINITION_RULES: FilterRule[] = [
  {
    criterion_id: "I-02",
    rule: "remove if t2d_diagnosis_days < 180",
    data_field: "diagnoses_icd: first E11.* date",
    removed: 0,
    note: "Applied when building the starting cohort.",
  },
  {
    criterion_id: "E-01",
    rule: "remove if any E10.* or LADA diagnosis",
    data_field: "diagnoses_icd",
    removed: 0,
    note: "Applied when building the starting cohort.",
  },
];

// Applied in protocol order. Each `removed` is sequential: patients
// removed by this rule among those still in the funnel.
export const FILTER_GROUPS: FilterGroup[] = [
  {
    label: "Age 18-75",
    rules: [
      {
        criterion_id: "I-01",
        rule: "remove if age < 18 or age > 75",
        data_field: "patients: age at index date",
        removed: 2_987,
        note: "All removed patients are over 75 (cohort is adults only).",
      },
    ],
  },
  {
    label: "HbA1c below 7.0%",
    rules: [
      {
        criterion_id: "I-03",
        rule: "remove if hba1c < 7.0",
        data_field: "labs: HbA1c, latest in 12 months",
        removed: 2_911,
        note: "Lower bound of I-03; the upper bound is applied via E-03.",
      },
    ],
  },
  {
    label: "HbA1c above 9.0%",
    rules: [
      {
        criterion_id: "E-03",
        rule: "remove if hba1c > 9.0",
        data_field: "labs: HbA1c, latest in 12 months",
        removed: 1_499,
        note: "E-03 is stricter than I-03's 10.5%, so 9.0% is used.",
      },
    ],
  },
  {
    label: "Metformin background",
    rules: [
      {
        criterion_id: "I-05",
        rule: "remove if metformin < 1500 mg/day or < 56 days",
        data_field: "prescriptions: metformin dose and dates",
        removed: 1_031,
      },
      {
        criterion_id: "I-06",
        rule: "remove if metformin dose changed in last 56 days",
        data_field: "prescriptions: metformin dose and dates",
        removed: 83,
      },
    ],
  },
  {
    label: "eGFR below 45",
    rules: [
      {
        criterion_id: "E-05",
        rule: "remove if egfr < 45",
        data_field: "labs: creatinine → eGFR (CKD-EPI 2021)",
        removed: 3_066,
        note: "3,066 of 9,891 (31.0%): the largest drop in the funnel.",
      },
      {
        criterion_id: "E-06",
        rule: "remove if dialysis or kidney transplant",
        data_field: "procedures_icd, diagnoses_icd: Z99.2, Z94.0",
        removed: 0,
        note: "Every matching patient already had eGFR < 45.",
      },
    ],
  },
  {
    label: "Insulin in prior 12 months",
    rules: [
      {
        criterion_id: "E-07",
        rule: "remove if any insulin order in last 365 days",
        data_field: "prescriptions: insulin",
        removed: 1_972,
        note: "641 of these had 14 days or less of insulin.",
      },
    ],
  },
  {
    label: "Cardiovascular history",
    rules: [
      {
        criterion_id: "E-12",
        rule: "remove if MI, stroke or TIA in last 90 days",
        data_field: "diagnoses_icd: I21, I63, G45",
        removed: 512,
      },
      {
        criterion_id: "E-13",
        rule: "remove if heart failure with NYHA IV proxy",
        data_field: "diagnoses_icd: I50 + inotrope or LVAD",
        removed: 141,
        note: "NYHA class is not coded; proxy rule used.",
      },
      {
        criterion_id: "E-14",
        rule: "remove if latest BP >= 180/110",
        data_field: "vitals: systolic and diastolic BP",
        removed: 463,
      },
      {
        criterion_id: "E-15",
        rule: "remove if PCI, CABG or carotid procedure in 90 days",
        data_field: "procedures_icd",
        removed: 290,
      },
    ],
  },
  {
    label: "BMI, labs and other history",
    rules: [
      {
        criterion_id: "I-04",
        rule: "remove if bmi < 22 or bmi > 45",
        data_field: "omr: BMI",
        removed: 211,
      },
      {
        criterion_id: "I-07",
        rule: "remove if c_peptide < 0.8",
        data_field: "labs: fasting C-peptide",
        removed: 64,
        note: "Measured in 18% of patients; missing values treated as met.",
      },
      {
        criterion_id: "E-02",
        rule: "remove if any DKA diagnosis",
        data_field: "diagnoses_icd: E11.1, E10.1",
        removed: 22,
      },
      {
        criterion_id: "E-04",
        rule: "remove if severe hypoglycaemia in last 182 days",
        data_field: "diagnoses_icd: E16.0, E11.64 with ED visit",
        removed: 58,
      },
      {
        criterion_id: "E-16",
        rule: "remove if alt or ast > 3 x ULN",
        data_field: "labs: ALT, AST",
        removed: 97,
      },
      {
        criterion_id: "E-17",
        rule: "remove if cirrhosis or chronic liver disease",
        data_field: "diagnoses_icd: K70, K74",
        removed: 83,
      },
      {
        criterion_id: "E-18",
        rule: "remove if malignancy in last 5 years (not C44)",
        data_field: "diagnoses_icd: C00-C97",
        removed: 161,
      },
      {
        criterion_id: "E-19",
        rule: "remove if 2+ genital mycotic infections in 365 days",
        data_field: "diagnoses_icd: N77.1, B37.3",
        removed: 48,
      },
    ],
  },
  {
    label: "Other recent medication",
    rules: [
      {
        criterion_id: "E-08",
        rule: "remove if SGLT2 inhibitor in last 84 days",
        data_field: "prescriptions: SGLT2 inhibitors",
        removed: 214,
      },
      {
        criterion_id: "E-09",
        rule: "remove if GLP-1 RA in last 84 days",
        data_field: "prescriptions: GLP-1 receptor agonists",
        removed: 187,
      },
      {
        criterion_id: "E-10",
        rule: "remove if systemic steroid > 14 days in last 56 days",
        data_field: "prescriptions: systemic corticosteroids",
        removed: 121,
      },
      {
        criterion_id: "E-11",
        rule: "remove if weight-loss drug in last 84 days",
        data_field: "prescriptions: weight-loss medication",
        removed: 66,
      },
    ],
  },
];

const NOT_SIMULATED_REASONS: Record<string, string> = {
  "I-08": "Assumed met: measured at the screening visit.",
  "I-09": "Cannot simulate: future contraception intent is not recorded.",
  "I-10": "Assumed met: consent happens at screening.",
  "I-11": "Assumed met: willingness to attend is not recorded.",
  "I-12": "Cannot simulate: willingness to self-monitor is not recorded.",
  "I-13": "Assumed met: device use is assessed at screening.",
  "I-14": "Assumed met: counselling agreement happens at screening.",
  "E-20": "Cannot simulate: depends on investigator judgement.",
};

const formatCount = (count: number): string => count.toLocaleString("en-US");
const percentOf = (part: number, whole: number): number =>
  Math.round((part / whole) * 1000) / 10;

// One row per criterion, running the funnel from the starting cohort.
function buildFilterRows(): DetailMap[] {
  let remaining = COHORT_START_COUNT;
  const appliedRules = [
    ...COHORT_DEFINITION_RULES,
    ...FILTER_GROUPS.flatMap((group) => group.rules),
  ];
  const appliedRows = appliedRules.map((rule) => {
    const before = remaining;
    remaining -= rule.removed;
    return {
      criterion_id: rule.criterion_id,
      criterion: criterionById(rule.criterion_id).text,
      status: "simulated",
      rule: rule.rule,
      data_field: rule.data_field,
      before,
      removed: rule.removed,
      remaining,
      percent_removed: percentOf(rule.removed, before),
      note: rule.note ?? "",
    };
  });
  const skippedRows = CRITERIA.filter(
    (criterion) => criterion.computable !== "yes"
  ).map((criterion) => ({
    criterion_id: criterion.id,
    criterion: criterion.text,
    status:
      criterion.computable === "no" ? "cannot simulate" : "assumed met",
    rule: "none",
    data_field: "none",
    before: "-",
    removed: "-",
    remaining: "-",
    percent_removed: "-",
    note: NOT_SIMULATED_REASONS[criterion.id] ?? "",
  }));
  return [...appliedRows, ...skippedRows];
}

// First point is the starting total; each later point is a signed change.
function buildWaterfallPoints(): ChartPoint[] {
  let remaining = COHORT_START_COUNT;
  const changes = FILTER_GROUPS.map((group) => {
    const removed = group.rules.reduce((sum, rule) => sum + rule.removed, 0);
    const before = remaining;
    remaining -= removed;
    return {
      label: group.label,
      value: -removed,
      annotation:
        `-${percentOf(removed, before)}% of ${formatCount(before)}; ` +
        `${formatCount(remaining)} left`,
    };
  });
  return [
    {
      label: "Starting cohort",
      value: COHORT_START_COUNT,
      annotation: "Adults with T2D for 180+ days, no type 1 diabetes",
    },
    ...changes,
  ];
}

const attritionChart = {
  chart_id: "ch-coh-waterfall",
  kind: "waterfall" as const,
  title: "Attrition from 18,402 to 2,115 eligible",
  description:
    "First bar is the starting cohort; each later bar is the number " +
    "removed by that group of criteria, applied in protocol order.",
  x_label: "Criterion group",
  y_label: "Patients",
  unit: "patients",
  series: [{ name: "Patients", points: buildWaterfallPoints() }],
};

const filterTable = {
  table_id: "tbl-coh-filters",
  title: "Every criterion applied to the cohort",
  description:
    "26 criteria simulated as rules, 5 assumed met, 3 cannot be " +
    "simulated.",
  columns: [
    { key: "criterion_id", label: "ID" },
    { key: "criterion", label: "Criterion" },
    { key: "status", label: "Status" },
    { key: "rule", label: "Computable rule" },
    { key: "data_field", label: "Data field" },
    { key: "before", label: "Before", unit: "patients" },
    { key: "removed", label: "Removed", unit: "patients" },
    { key: "remaining", label: "Remaining", unit: "patients" },
    { key: "percent_removed", label: "Removed", unit: "%" },
    { key: "note", label: "Note or reason" },
  ],
  rows: buildFilterRows(),
};

// Women's share (%) after each filter group, ending at 803 of 2,115.
const FEMALE_SHARE_BY_STAGE: ChartPoint[] = [
  { label: "Starting cohort", value: 44.0 },
  { label: "Age 18-75", value: 43.2 },
  { label: "HbA1c below 7.0%", value: 43.0 },
  { label: "HbA1c above 9.0%", value: 42.8 },
  { label: "Metformin background", value: 42.5 },
  { label: "eGFR below 45", value: 39.4, annotation: "-3.1 points" },
  { label: "Insulin in prior 12 months", value: 38.9 },
  { label: "Cardiovascular history", value: 38.6 },
  { label: "BMI, labs and other history", value: 38.3 },
  { label: "Other recent medication", value: 38.0 },
];

const femaleShareChart = {
  chart_id: "ch-coh-female-share",
  kind: "line" as const,
  title: "Share of women through the funnel",
  description: "The steepest fall comes at the eGFR exclusion.",
  x_label: "After filter",
  y_label: "Women",
  unit: "%",
  series: [{ name: "Women", points: FEMALE_SHARE_BY_STAGE }],
};

const subgroupTable = {
  table_id: "tbl-coh-subgroups",
  title: "Eligible cohort vs peer baseline",
  description: "Eligible cohort of 2,115 against pooled peer baseline tables.",
  columns: [
    { key: "subgroup", label: "Subgroup" },
    { key: "category", label: "Category" },
    { key: "eligible_n", label: "Eligible", unit: "patients" },
    { key: "eligible_pct", label: "Eligible", unit: "%" },
    { key: "peer_pct", label: "Peer baseline", unit: "%" },
    { key: "difference_pts", label: "Difference", unit: "points" },
  ],
  rows: [
    { subgroup: "Sex", category: "Female", eligible_n: 803, eligible_pct: 38.0, peer_pct: 46, difference_pts: -8.0 },
    { subgroup: "Sex", category: "Male", eligible_n: 1_312, eligible_pct: 62.0, peer_pct: 54, difference_pts: 8.0 },
    { subgroup: "Age", category: "18-44", eligible_n: 254, eligible_pct: 12.0, peer_pct: 14, difference_pts: -2.0 },
    { subgroup: "Age", category: "45-64", eligible_n: 1_164, eligible_pct: 55.0, peer_pct: 56, difference_pts: -1.0 },
    { subgroup: "Age", category: "65 and over", eligible_n: 697, eligible_pct: 33.0, peer_pct: 30, difference_pts: 3.0 },
    { subgroup: "Ethnicity", category: "White", eligible_n: 1_396, eligible_pct: 66.0, peer_pct: 62, difference_pts: 4.0 },
    { subgroup: "Ethnicity", category: "Black", eligible_n: 359, eligible_pct: 17.0, peer_pct: 7, difference_pts: 10.0 },
    { subgroup: "Ethnicity", category: "Hispanic or Latino", eligible_n: 169, eligible_pct: 8.0, peer_pct: 14, difference_pts: -6.0 },
    { subgroup: "Ethnicity", category: "Asian", eligible_n: 106, eligible_pct: 5.0, peer_pct: 13, difference_pts: -8.0 },
    { subgroup: "Ethnicity", category: "Other or unknown", eligible_n: 85, eligible_pct: 4.0, peer_pct: 4, difference_pts: 0.0 },
  ],
};

// eGFR among the 9,891 patients reaching the eGFR filter.
const EGFR_BINS: ChartPoint[] = [
  { label: "Below 30", value: 1_212 },
  { label: "30-44", value: 1_854, annotation: "Recovered if cut-off is 30" },
  { label: "45-59", value: 2_410 },
  { label: "60-89", value: 3_326 },
  { label: "90 and above", value: 1_089 },
];

export const COHORT_STEP: StepData = {
  id: "cohort",
  title: "Cohort Comparison",
  summary:
    "Eligibility rules applied, criterion by criterion, to a simulated " +
    "patient cohort to show who each rule removes.",
  headline: {
    label: "eGFR < 45",
    value: "-31%",
    tone: "risk",
    numeric_value: -31.0,
    unit: "%",
  },
  metrics: [
    {
      metric_id: "m-coh-start",
      label: "Cohort",
      value: "18,402",
      numeric_value: COHORT_START_COUNT,
      unit: "patients",
      description: "Synthetic adults with T2D for at least 180 days.",
    },
    {
      metric_id: "m-coh-eligible",
      label: "Eligible",
      value: "2,115",
      tone: "good",
      numeric_value: COHORT_ELIGIBLE_COUNT,
      unit: "patients",
      description:
        "11.5% of the cohort pass every simulated criterion; an upper " +
        "bound, since 8 criteria were not simulated.",
      benchmarks: [{ label: "Target enrolment", value: "1,200", numeric_value: 1_200 }],
    },
    {
      metric_id: "m-coh-steepest",
      label: "Steepest drop",
      value: "eGFR < 45: -31%",
      tone: "risk",
      numeric_value: -31.0,
      unit: "%",
      description: "3,066 of the 9,891 patients reaching this filter.",
    },
    {
      metric_id: "m-coh-unsimulable",
      label: "Cannot simulate",
      value: "3",
      tone: "warn",
      numeric_value: 3,
      unit: "criteria",
      description: "I-09, I-12 and E-20 need information EHRs do not hold.",
    },
  ],
  status: "completed",
  agent: AGENT,
  ...stepTiming("cohort"),
  warnings: [
    {
      code: "CRITERIA_NOT_SIMULABLE",
      message:
        "3 criteria (I-09, I-12, E-20) cannot be simulated and 5 " +
        "administrative ones are assumed met.",
      severity: "warning",
    },
    {
      code: "PROXY_RULES",
      message:
        "E-13 uses a proxy for NYHA class IV, and I-07 treats a missing " +
        "C-peptide (82% of patients) as met.",
      severity: "info",
    },
    {
      code: "SYNTHETIC_COHORT",
      message:
        "The cohort is synthetic; counts show relative impact, not a " +
        "recruitment forecast.",
      severity: "info",
    },
  ],
  data_sources: [
    DATA_SOURCES.mimic,
    DATA_SOURCES.nhanes,
    DATA_SOURCES.aact,
    DATA_SOURCES.protocol,
  ],
  tables: [filterTable, subgroupTable],
  charts: [attritionChart, femaleShareChart],
  decisions: [
    {
      decision_id: "d-coh-01",
      step_id: "cohort",
      severity: "critical",
      title: "eGFR exclusion removes the most patients",
      claim:
        "The eGFR below 45 exclusion removes 31% of the patients still " +
        "in the funnel at that point (3,066 of 9,891), the largest drop " +
        "both in share and in number, although the cut-off itself is the " +
        "peer median.",
      category: "Cohort impact",
      confidence: 0.81,
      location: {
        section_heading: "5.2",
        section_title: "Exclusion Criteria",
        start_page: 25,
        end_page: 25,
        criterion_id: "E-05",
      },
      evidence: [
        {
          evidence_id: "e-coh-01",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 25,
          quote: "eGFR below 45 mL/min/1.73 m2 at screening.",
          is_verified: true,
          section_title: "5.2 Exclusion Criteria",
          context:
            "E-04. Severe hypoglycaemia within 6 months before screening. " +
            "E-05. eGFR below 45 mL/min/1.73 m2 at screening. E-06. " +
            "Dialysis or kidney transplant.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-coh-02",
          source: "mimic",
          document: COHORT_DOCUMENT,
          page: null,
          quote: "3,066 of 9,891 remaining patients have eGFR < 45.",
          is_verified: true,
          context:
            "9,891 patients pass the age, HbA1c and metformin filters. " +
            "3,066 of 9,891 remaining patients have eGFR < 45. Of these, " +
            "1,854 are between 30 and 44.",
          url: DATA_SOURCES.mimic.url,
          confidence: 0.9,
        },
        {
          evidence_id: "e-coh-04",
          source: "aact",
          document: PEER_SET_DOCUMENT,
          page: null,
          quote:
            "eGFR exclusion cut-off across 39 peers: median 45, P10 30, " +
            "P90 60.",
          is_verified: true,
          context:
            "3 peers set no eGFR limit. eGFR exclusion cut-off across 39 " +
            "peers: median 45, P10 30, P90 60.",
          confidence: 0.86,
        },
      ],
      trace: timedTrace("cohort", "d-coh-01", 14_600, [
        {
          agent: AGENT,
          kind: "rule",
          text: "Converted the criterion to a computable eGFR filter.",
          evidence_ids: ["e-coh-01"],
          duration_ms: 410,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Applied the filter to the cohort; 31% were removed.",
          evidence_ids: ["e-coh-02"],
          duration_ms: 4_870,
        },
        {
          agent: AGENT,
          kind: "compare",
          text:
            "The cut-off equals the peer median, so the drop reflects the " +
            "population rather than an unusual rule.",
          evidence_ids: ["e-coh-04"],
          duration_ms: 520,
        },
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Re-ran the funnel with a cut-off of 30: +498 eligible.",
          evidence_ids: ["e-coh-02"],
          duration_ms: 6_240,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "Largest single drop in the attrition waterfall.",
          evidence_ids: ["e-coh-02"],
          duration_ms: 130,
        },
      ]),
      proposed_change: {
        path: "5.2 Exclusion criteria, E-05",
        before: "eGFR below 45",
        after: "eGFR below 30 (randomisation stratified by eGFR 30-44 vs 45+)",
        change_type: "modify",
        section_title: "5.2 Exclusion Criteria",
        page: 25,
        rationale:
          "Recovers 498 eligible patients while stratification keeps the " +
          "weaker glucose-lowering effect at low eGFR visible.",
      },
      derived_from: ["d-ing-01"],
      impact: [
        {
          label: "Removed here",
          value: "3,066",
          tone: "risk",
          numeric_value: 3_066,
          unit: "patients",
        },
        {
          label: "Eligible if cut-off is 30",
          value: "2,613 (+23.5%)",
          tone: "good",
          numeric_value: 2_613,
          unit: "patients",
          benchmarks: [{ label: "Current", value: "2,115", numeric_value: COHORT_ELIGIBLE_COUNT }],
        },
      ],
      options: [
        {
          option_id: "o-coh-01-a",
          title: "Relax to clinical standard: lower cut-off to 30 and stratify",
          rationale:
            "Aligns with KDIGO Stage 3b clinical standard; adds the 30-44 " +
            "band without hiding its smaller HbA1c effect.",
          is_recommended: true,
          proposed_change: {
            path: "5.2 Exclusion criteria, E-05",
            before: "eGFR below 45",
            after:
              "eGFR below 30 (randomisation stratified by eGFR 30-44 vs 45+)",
            change_type: "modify",
            section_title: "5.2 Exclusion Criteria",
            page: 25,
          },
          impact: [
            { label: "Currently eligible", value: "2,115 patients" },
            { label: "Projected eligible", value: "2,613 patients" },
            { label: "Additional eligible patients", value: "+498" },
            { label: "Relative increase", value: "+23.5%", tone: "good",
              description: "Illustrative simulation, not an enrollment guarantee." },
          ],
          risks: [
            "SGLT2 glucose lowering is weaker at low eGFR.",
            "Needs renal safety monitoring in the 30-44 band.",
          ],
        },
        {
          option_id: "o-coh-01-b",
          title: "Align with peer trials lower decile: lower cut-off to 30 without stratifying",
          rationale: "Matches peer P10 threshold with the simplest protocol edit.",
          proposed_change: {
            path: "5.2 Exclusion criteria, E-05",
            before: "eGFR below 45",
            after: "eGFR below 30",
            change_type: "modify",
            section_title: "5.2 Exclusion Criteria",
            page: 25,
          },
          impact: [
            { label: "Currently eligible", value: "2,115 patients" },
            { label: "Projected eligible", value: "2,613 patients" },
            { label: "Additional eligible patients", value: "+498" },
            { label: "Relative increase", value: "+23.5%", tone: "good",
              description: "Illustrative simulation, not an enrollment guarantee." },
          ],
          risks: ["Uneven eGFR mix across arms could dilute the effect."],
        },
      ],
      references: [REFERENCES.adaStandards, REFERENCES.fdaDiabetes],
      decision_owner: "Medical Monitor",
      review_status: "pending",
      tags: ["eligibility", "renal", "recruitment"],
      charts: [
        attritionChart,
        {
          chart_id: "ch-coh-egfr",
          kind: "histogram",
          title: "eGFR of patients reaching the eGFR filter",
          description: "9,891 patients; the two left bars (3,066) are removed.",
          x_label: "eGFR (mL/min/1.73 m2)",
          y_label: "Patients",
          unit: "patients",
          series: [{ name: "Patients", points: EGFR_BINS }],
        },
      ],
    },
    {
      decision_id: "d-coh-02",
      step_id: "cohort",
      severity: "warning",
      title: "Women under-represented after filtering",
      claim:
        "Women are 38% of the eligible cohort versus 46% in peer " +
        "trials.",
      category: "Representativeness",
      confidence: 0.77,
      location: {
        section_heading: "5",
        section_title: "Trial Population",
        start_page: 24,
        end_page: 26,
      },
      evidence: [
        {
          evidence_id: "e-coh-03",
          source: "mimic",
          document: COHORT_DOCUMENT,
          page: null,
          quote: "Eligible cohort: 38% female (803 of 2,115).",
          is_verified: true,
          context:
            "The starting cohort is 44% female. Eligible cohort: 38% " +
            "female (803 of 2,115). The largest fall, 3.1 points, comes " +
            "at the eGFR filter.",
          url: DATA_SOURCES.mimic.url,
          confidence: 0.9,
        },
        {
          evidence_id: "e-coh-05",
          source: "aact",
          document: PEER_SET_DOCUMENT,
          page: null,
          quote: "Peer trials enrolled 46% women (median of 42 baseline tables).",
          is_verified: true,
          context:
            "Baseline characteristics were available for all 42 peers. " +
            "Peer trials enrolled 46% women (median of 42 baseline tables).",
          confidence: 0.85,
        },
        {
          evidence_id: "e-coh-06",
          source: "nhanes",
          document: DATA_SOURCES.nhanes.name,
          page: null,
          quote: "Women are 47% of adults with diagnosed diabetes in this subset.",
          is_verified: true,
          context:
            "Weighted to the US adult population. Women are 47% of adults " +
            "with diagnosed diabetes in this subset.",
          url: DATA_SOURCES.nhanes.url,
          confidence: 0.8,
        },
      ],
      trace: timedTrace("cohort", "d-coh-02", 32_400, [
        {
          agent: AGENT,
          kind: "compare",
          text: "Compared subgroup shares with peer baseline tables.",
          evidence_ids: ["e-coh-03", "e-coh-05"],
          duration_ms: 1_640,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Checked against the US population reference (NHANES): 47%.",
          evidence_ids: ["e-coh-06"],
          duration_ms: 720,
        },
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Tracked women's share after each filter group.",
          evidence_ids: ["e-coh-03"],
          duration_ms: 2_310,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "8-point gap, driven mostly by the eGFR exclusion.",
          evidence_ids: ["e-coh-03"],
          duration_ms: 140,
        },
      ]),
      proposed_change: {
        path: "5.4 Recruitment and retention",
        before: "",
        after:
          "Enrolment of women is reviewed monthly against a target of at " +
          "least 45%, with site-level outreach if it falls below 40%.",
        change_type: "add",
        section_title: "5.4 Recruitment and Retention",
        page: 27,
        rationale: "Makes the gap visible during recruitment, not after.",
      },
      derived_from: ["d-coh-01"],
      impact: [
        {
          label: "Women, eligible",
          value: "38.0%",
          tone: "warn",
          numeric_value: 38.0,
          unit: "%",
          benchmarks: [
            { label: "Peer trials", value: "46%", numeric_value: 46 },
            { label: "NHANES", value: "47%", numeric_value: 47 },
          ],
        },
      ],
      options: [
        {
          option_id: "o-coh-02-a",
          title: "Set a 45% female enrolment target",
          rationale:
            "Moves toward the 46% peer median without changing eligibility " +
            "rules. This is a recruitment target, not a simulated gain. " +
            "Actual improvement has not been estimated.",
          is_recommended: true,
          proposed_change: {
            path: "5.4 Recruitment and retention",
            before: "",
            after:
              "Enrolment of women is reviewed monthly against a target of " +
              "at least 45%.",
            change_type: "add",
            section_title: "5.4 Recruitment and Retention",
            page: 27,
          },
          impact: [
            { label: "Current eligible female share", value: "38%" },
            { label: "Recruitment target", value: "45%" },
            { label: "Target above current share",
              value: "+7 percentage points", tone: "neutral" },
            { label: "Peer benchmark", value: "46%" },
          ],
          risks: ["Targets alone may not change who sites approach."],
        },
        {
          option_id: "o-coh-02-b",
          title: "Relax to clinical standard: lower eGFR cut-off to recover female share",
          rationale: "Removes the eGFR < 45 filter that disproportionately excludes women.",
          proposed_change: {
            path: "5.2 Exclusion criteria, E-05",
            before: "eGFR below 45",
            after: "eGFR below 30",
            change_type: "modify",
            section_title: "5.2 Exclusion Criteria",
            page: 25,
          },
          impact: [{ label: "Women, eligible (projected)", value: "40.6%", tone: "good" }],
          risks: ["Still 5 points below peers without site outreach."],
        },
      ],
      references: [REFERENCES.fdaDiversity, REFERENCES.ichE7],
      decision_owner: "Clinical Operations Lead",
      review_status: "pending",
      tags: ["diversity", "sex", "recruitment"],
      tables: [subgroupTable],
      charts: [femaleShareChart],
    },
    {
      decision_id: "d-coh-03",
      step_id: "cohort",
      severity: "warning",
      title: "Age cap removes 16% of the cohort",
      claim:
        "The 75-year upper limit removes 2,987 of 18,402 patients " +
        "(16.2%). Raising it to 80 would add an estimated 231 eligible " +
        "patients after all later filters.",
      category: "Cohort impact",
      confidence: 0.79,
      location: {
        section_heading: "5.1",
        section_title: "Inclusion Criteria",
        start_page: 24,
        end_page: 24,
        criterion_id: "I-01",
      },
      evidence: [
        {
          evidence_id: "e-coh-07",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 24,
          quote: "Aged 18 to 75 years at screening.",
          is_verified: true,
          section_title: "5.1 Inclusion Criteria",
          context:
            "Participants must meet all of the following criteria. I-01. " +
            "Aged 18 to 75 years at screening.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-coh-08",
          source: "mimic",
          document: COHORT_DOCUMENT,
          page: null,
          quote: "2,987 of 18,402 patients are older than 75.",
          is_verified: true,
          context:
            "2,987 of 18,402 patients are older than 75. 1,248 of them " +
            "are aged 76-80.",
          url: DATA_SOURCES.mimic.url,
          confidence: 0.9,
        },
      ],
      trace: timedTrace("cohort", "d-coh-03", 45_100, [
        {
          agent: AGENT,
          kind: "rule",
          text: "Converted I-01 to an age filter (18-75 at index date).",
          evidence_ids: ["e-coh-07"],
          duration_ms: 230,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Applied it first in the funnel: 2,987 removed (16.2%).",
          evidence_ids: ["e-coh-08"],
          duration_ms: 1_940,
        },
        {
          agent: AGENT,
          kind: "retrieve",
          text:
            "Re-ran the funnel with limits of 80 (+231 eligible) and none " +
            "(+396); older patients fail the eGFR filter more often.",
          evidence_ids: ["e-coh-08"],
          duration_ms: 8_150,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "Second-largest absolute drop; links to the peer age outlier.",
          evidence_ids: ["e-coh-07", "e-coh-08"],
          duration_ms: 120,
        },
      ]),
      proposed_change: {
        path: "5.1 Inclusion criteria, I-01",
        before: "Aged 18 to 75 years",
        after: "Aged 18 to 80 years",
        change_type: "modify",
        section_title: "5.1 Inclusion Criteria",
        page: 24,
        rationale: "Peer median limit; +231 eligible in the simulation.",
      },
      derived_from: ["d-prs-03"],
      impact: [
        {
          label: "Removed here",
          value: "2,987 (16.2%)",
          tone: "warn",
          numeric_value: 2_987,
          unit: "patients",
        },
        {
          label: "Eligible if limit is 80",
          value: "2,346 (+10.9%)",
          tone: "good",
          numeric_value: 2_346,
          unit: "patients",
        },
      ],
      options: [
        {
          option_id: "o-coh-03-a",
          title: "Align with peer trials median: raise upper age limit to 80",
          rationale: "Peer median threshold; modest gain with limited extra risk.",
          is_recommended: true,
          proposed_change: {
            path: "5.1 Inclusion criteria, I-01",
            before: "Aged 18 to 75 years",
            after: "Aged 18 to 80 years",
            change_type: "modify",
            section_title: "5.1 Inclusion Criteria",
            page: 24,
          },
          impact: [
            { label: "Eligible", value: "2,346 (+10.9%)", tone: "good", numeric_value: 2_346 },
          ],
          risks: ["More volume depletion events to monitor."],
        },
        {
          option_id: "o-coh-03-b",
          title: "Relax to clinical standard: remove upper age cap (18 years and older)",
          rationale: "Matches ICH E7 geriatric guidance and 17 of 42 peer trials.",
          proposed_change: {
            path: "5.1 Inclusion criteria, I-01",
            before: "Aged 18 to 75 years",
            after: "Aged 18 years and older",
            change_type: "modify",
            section_title: "5.1 Inclusion Criteria",
            page: 24,
          },
          impact: [
            { label: "Eligible", value: "2,511 (+18.7%)", tone: "good", numeric_value: 2_511 },
          ],
          risks: ["Frailty and polypharmacy need extra safety rules."],
        },
      ],
      references: [REFERENCES.ichE7],
      decision_owner: "Medical Monitor",
      review_status: "pending",
      tags: ["eligibility", "age", "recruitment"],
    },
    {
      decision_id: "d-coh-04",
      step_id: "cohort",
      severity: "warning",
      title: "Prior insulin exclusion is broad",
      claim:
        "Excluding any insulin in the prior 12 months removes 1,972 of " +
        "6,825 remaining patients (28.9%); 641 of them had only a short " +
        "course of 14 days or less, often during a hospital stay.",
      category: "Cohort impact",
      confidence: 0.76,
      location: {
        section_heading: "5.2",
        section_title: "Exclusion Criteria",
        start_page: 25,
        end_page: 25,
        criterion_id: "E-07",
      },
      evidence: [
        {
          evidence_id: "e-coh-09",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 25,
          quote: "Insulin use within 12 months before screening.",
          is_verified: true,
          section_title: "5.2 Exclusion Criteria",
          context:
            "E-06. Dialysis or kidney transplant. E-07. Insulin use " +
            "within 12 months before screening. E-08. SGLT2 inhibitor use " +
            "within 12 weeks before screening.",
          confidence: 0.97,
        },
        {
          evidence_id: "e-coh-10",
          source: "mimic",
          document: COHORT_DOCUMENT,
          page: null,
          quote:
            "1,972 of 6,825 remaining patients had insulin in the prior " +
            "12 months; 641 for 14 days or less.",
          is_verified: true,
          context:
            "1,972 of 6,825 remaining patients had insulin in the prior " +
            "12 months; 641 for 14 days or less. Most short courses were " +
            "inpatient sliding-scale orders.",
          url: DATA_SOURCES.mimic.url,
          confidence: 0.84,
        },
      ],
      trace: timedTrace("cohort", "d-coh-04", 58_300, [
        {
          agent: AGENT,
          kind: "rule",
          text: "Converted E-07 to: any insulin order in the last 365 days.",
          evidence_ids: ["e-coh-09"],
          duration_ms: 260,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Applied after the eGFR filter: 1,972 of 6,825 removed.",
          evidence_ids: ["e-coh-10"],
          duration_ms: 2_080,
        },
        {
          agent: AGENT,
          kind: "retrieve",
          text:
            "Split by duration: 641 had 14 days or less. Allowing them " +
            "adds 279 eligible after later filters.",
          evidence_ids: ["e-coh-10"],
          duration_ms: 5_460,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "Third-largest relative drop; partly avoidable.",
          evidence_ids: ["e-coh-09", "e-coh-10"],
          duration_ms: 110,
        },
      ]),
      proposed_change: {
        path: "5.2 Exclusion criteria, E-07",
        before: "Insulin use within 12 months before screening.",
        after:
          "Insulin use for more than 14 days within 12 months before " +
          "screening.",
        change_type: "modify",
        section_title: "5.2 Exclusion Criteria",
        page: 25,
        rationale:
          "Keeps out chronic insulin users while allowing short " +
          "inpatient courses.",
      },
      derived_from: ["d-ing-01"],
      impact: [
        {
          label: "Removed here",
          value: "1,972 (28.9%)",
          tone: "warn",
          numeric_value: 1_972,
          unit: "patients",
        },
        {
          label: "Eligible if short courses allowed",
          value: "2,394 (+13.2%)",
          tone: "good",
          numeric_value: 2_394,
          unit: "patients",
        },
      ],
      options: [
        {
          option_id: "o-coh-04-a",
          title: "Relax to clinical standard: allow short insulin courses of 14 days or less",
          rationale: "Targets the avoidable inpatient sliding-scale drop while keeping chronic users out.",
          is_recommended: true,
          proposed_change: {
            path: "5.2 Exclusion criteria, E-07",
            before: "Insulin use within 12 months before screening.",
            after:
              "Insulin use for more than 14 days within 12 months before " +
              "screening.",
            change_type: "modify",
            section_title: "5.2 Exclusion Criteria",
            page: 25,
          },
          impact: [
            { label: "Eligible", value: "2,394 (+13.2%)", tone: "good", numeric_value: 2_394 },
          ],
          risks: ["Needs medication history detailed enough to check."],
        },
        {
          option_id: "o-coh-04-b",
          title: "Align with peer trials median: shorten lookback to 3 months",
          rationale: "Matches peer trials median washout window; bigger recruitment gain.",
          proposed_change: {
            path: "5.2 Exclusion criteria, E-07",
            before: "within 12 months",
            after: "within 3 months",
            change_type: "modify",
            section_title: "5.2 Exclusion Criteria",
            page: 25,
          },
          impact: [
            { label: "Eligible", value: "2,602 (+23.0%)", tone: "good", numeric_value: 2_602 },
          ],
          risks: ["Admits more advanced disease, raising HbA1c variance."],
        },
      ],
      references: [REFERENCES.adaStandards],
      decision_owner: "Medical Monitor",
      review_status: "pending",
      tags: ["eligibility", "medication-history", "recruitment"],
    },
    {
      decision_id: "d-coh-05",
      step_id: "cohort",
      severity: "info",
      title: "Three criteria cannot be simulated",
      claim:
        "I-09, I-12 and E-20 need information patient records do not " +
        "hold, and 5 administrative criteria are assumed met, so 2,115 " +
        "is an upper bound before screen failures on these items.",
      category: "Simulation coverage",
      confidence: 0.92,
      location: {
        section_heading: "5",
        section_title: "Trial Population",
        start_page: 24,
        end_page: 26,
      },
      evidence: [
        {
          evidence_id: "e-coh-11",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 24,
          quote: criterionById("I-09").text,
          is_verified: true,
          section_title: "5.1 Inclusion Criteria",
          context:
            "I-08. Negative pregnancy test at screening for women of " +
            "childbearing potential. I-09. " +
            criterionById("I-09").text,
          confidence: 0.98,
        },
        {
          evidence_id: "e-coh-12",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 24,
          quote: criterionById("I-12").text,
          is_verified: true,
          section_title: "5.1 Inclusion Criteria",
          context:
            "I-11. Able and willing to attend all scheduled visits. I-12. " +
            criterionById("I-12").text,
          confidence: 0.98,
        },
        {
          evidence_id: "e-coh-13",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 26,
          quote: criterionById("E-20").text,
          is_verified: true,
          section_title: "5.2 Exclusion Criteria",
          context:
            "E-19. Two or more genital mycotic infections in the past " +
            "year. E-20. " +
            criterionById("E-20").text,
          confidence: 0.96,
        },
      ],
      trace: timedTrace("cohort", "d-coh-05", 2_100, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Loaded the 34 extracted criteria.",
          evidence_ids: ["e-coh-11"],
          duration_ms: 380,
        },
        {
          agent: AGENT,
          kind: "rule",
          text:
            "Mapped each criterion to data fields: 26 computable, 5 " +
            "administrative, 3 with no matching field.",
          evidence_ids: ["e-coh-11", "e-coh-12", "e-coh-13"],
          duration_ms: 6_920,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "3 criteria flagged as not simulable.",
          evidence_ids: ["e-coh-12", "e-coh-13"],
          duration_ms: 140,
        },
      ]),
      derived_from: ["d-ing-01"],
      impact: [
        { label: "Simulated", value: "26/34", numeric_value: 26, unit: "criteria" },
        { label: "Assumed met", value: "5", numeric_value: 5, unit: "criteria" },
        { label: "Cannot simulate", value: "3", tone: "warn", numeric_value: 3, unit: "criteria" },
      ],
      references: [REFERENCES.ichM11],
      decision_owner: "Clinical Operations Lead",
      review_status: "pending",
      tags: ["simulation", "coverage"],
      tables: [
        {
          table_id: "tbl-coh-unsimulated",
          title: "Criteria not simulated",
          columns: [
            { key: "criterion_id", label: "ID" },
            { key: "criterion", label: "Criterion" },
            { key: "status", label: "Status" },
            { key: "reason", label: "Reason" },
          ],
          rows: CRITERIA.filter((criterion) => criterion.computable !== "yes").map(
            (criterion) => ({
              criterion_id: criterion.id,
              criterion: criterion.text,
              status:
                criterion.computable === "no" ? "cannot simulate" : "assumed met",
              reason: NOT_SIMULATED_REASONS[criterion.id] ?? "",
            })
          ),
        },
      ],
    },
  ],
};
