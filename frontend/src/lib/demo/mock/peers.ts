import type { StepData } from "../types";
import {
  DATA_SOURCES,
  PEER_SET_DOCUMENT,
  PROTOCOL_DOCUMENT,
  REFERENCES,
  stepTiming,
  timedTrace,
} from "./shared";

const AGENT = "Comparison";
const PEER_TRIAL_COUNT = 42;

type Verdict = "in range" | "outlier";

interface PeerField {
  field: string;
  unit: string;
  draft: number;
  median: number;
  p10: number;
  p90: number;
  trials_reporting: number;
  verdict: Verdict;
  explanation: string;
}

// Draft vs peer distribution, one row per compared field. A field is an
// outlier when the draft value falls outside the peer P10-P90 range.
export const PEER_FIELDS: PeerField[] = [
  {
    field: "HbA1c lower bound",
    unit: "%",
    draft: 7.0,
    median: 7.0,
    p10: 7.0,
    p90: 7.5,
    trials_reporting: 42,
    verdict: "in range",
    explanation: "Same as the peer median.",
  },
  {
    field: "HbA1c upper bound (effective)",
    unit: "%",
    draft: 9.0,
    median: 10.0,
    p10: 9.5,
    p90: 10.5,
    trials_reporting: 42,
    verdict: "outlier",
    explanation:
      "E-03 makes 9.0% the bound in practice, below the peer P10 of 9.5%.",
  },
  {
    field: "Lower age bound",
    unit: "years",
    draft: 18,
    median: 18,
    p10: 18,
    p90: 20,
    trials_reporting: 42,
    verdict: "in range",
    explanation: "Same as the peer median.",
  },
  {
    field: "Upper age bound",
    unit: "years",
    draft: 75,
    median: 80,
    p10: 77,
    p90: 85,
    trials_reporting: 25,
    verdict: "outlier",
    explanation:
      "Below the P10 of the 25 peers that set a limit; 17 peers set none.",
  },
  {
    field: "eGFR exclusion cut-off",
    unit: "mL/min/1.73 m2",
    draft: 45,
    median: 45,
    p10: 30,
    p90: 60,
    trials_reporting: 39,
    verdict: "in range",
    explanation:
      "Typical for an HbA1c endpoint, though it removes the most " +
      "patients in the cohort step.",
  },
  {
    field: "Treatment duration",
    unit: "weeks",
    draft: 26,
    median: 36,
    p10: 24,
    p90: 52,
    trials_reporting: 42,
    verdict: "in range",
    explanation: "Shorter than the median but above P10.",
  },
  {
    field: "Washout of prior agents",
    unit: "weeks",
    draft: 12,
    median: 8,
    p10: 4,
    p90: 12,
    trials_reporting: 31,
    verdict: "in range",
    explanation: "At the peer P90: long, but not outside the range.",
  },
  {
    field: "Planned sample size",
    unit: "participants",
    draft: 1_200,
    median: 612,
    p10: 290,
    p90: 1_480,
    trials_reporting: 42,
    verdict: "in range",
    explanation: "About twice the median, within P90.",
  },
];

function peerField(name: string): PeerField {
  const row = PEER_FIELDS.find((candidate) => candidate.field === name);
  if (!row) throw new Error(`expected peer field '${name}', found none`);
  return row;
}

const HBA1C_LOWER = peerField("HbA1c lower bound");
const HBA1C_UPPER = peerField("HbA1c upper bound (effective)");
const DURATION = peerField("Treatment duration");
const WASHOUT = peerField("Washout of prior agents");

const peerComparisonTable = {
  table_id: "tbl-prs-comparison",
  title: "Draft vs peer trials, field by field",
  description:
    `Peer set of ${PEER_TRIAL_COUNT} trials; P10-P90 is the middle 80%.`,
  columns: [
    { key: "field", label: "Field" },
    { key: "unit", label: "Unit" },
    { key: "draft", label: "Draft" },
    { key: "median", label: "Peer median" },
    { key: "range", label: "Peer P10-P90" },
    { key: "trials_reporting", label: "Trials reporting" },
    { key: "verdict", label: "Verdict" },
    { key: "explanation", label: "Explanation" },
  ],
  rows: PEER_FIELDS.map((row) => ({
    field: row.field,
    unit: row.unit,
    draft: row.draft,
    median: row.median,
    range: `${row.p10}-${row.p90}`,
    trials_reporting: row.trials_reporting,
    verdict: row.verdict,
    explanation: row.explanation,
  })),
};

const hba1cChart = {
  chart_id: "ch-prs-hba1c",
  kind: "comparison" as const,
  title: "HbA1c eligibility window vs peers",
  description: "Peer median with P10-P90 range; the draft's upper bound is low.",
  x_label: "Bound",
  y_label: "HbA1c",
  unit: "%",
  series: [
    {
      name: "Peer median (P10-P90)",
      points: [HBA1C_LOWER, HBA1C_UPPER].map((row) => ({
        label: row.field,
        value: row.median,
        lower: row.p10,
        upper: row.p90,
      })),
    },
    {
      name: "Draft",
      points: [HBA1C_LOWER, HBA1C_UPPER].map((row) => ({
        label: row.field,
        value: row.draft,
        annotation: row.verdict,
      })),
    },
  ],
};

// Upper age limits among the 25 peers that set one (17 set none).
const AGE_LIMIT_BINS = [
  { label: "75 or below", value: 2 },
  { label: "76-79", value: 4 },
  { label: "80", value: 12 },
  { label: "81-85", value: 5 },
  { label: "Above 85", value: 2 },
];

export const PEERS_STEP: StepData = {
  id: "peers",
  title: "Protocol Comparison",
  summary:
    `Draft compared field by field with ${PEER_TRIAL_COUNT} similar ` +
    "Phase 3 add-on-to-metformin trials (illustrative peer set).",
  headline: {
    label: "peer trials",
    value: "42",
    numeric_value: PEER_TRIAL_COUNT,
    unit: "trials",
  },
  metrics: [
    {
      metric_id: "m-prs-trials",
      label: "Peer trials",
      value: "42",
      numeric_value: PEER_TRIAL_COUNT,
      unit: "trials",
      description: "Phase 3 T2D trials with an HbA1c primary endpoint.",
    },
    {
      metric_id: "m-prs-outliers",
      label: "Outliers",
      value: "2",
      tone: "warn",
      numeric_value: 2,
      unit: "fields",
      description:
        "Of 8 compared fields, 2 fall outside the peer P10-P90 range: " +
        "HbA1c upper bound and upper age bound.",
    },
    {
      metric_id: "m-prs-biggest",
      label: "Biggest outlier",
      value: "HbA1c ≥ 9.0",
      tone: "risk",
      numeric_value: HBA1C_UPPER.draft,
      unit: "%",
      description: "Effective HbA1c exclusion threshold in the draft.",
      benchmarks: [
        { label: "Peer median", value: "10.0%", numeric_value: HBA1C_UPPER.median },
        { label: "Peer P10", value: "9.5%", numeric_value: HBA1C_UPPER.p10 },
      ],
    },
    {
      metric_id: "m-prs-duration",
      label: "Peer median duration",
      value: "36 wk",
      numeric_value: DURATION.median,
      unit: "weeks",
      description: "Treatment period across the peer set.",
      benchmarks: [{ label: "Draft", value: "26 wk", numeric_value: DURATION.draft }],
    },
  ],
  status: "completed",
  agent: AGENT,
  ...stepTiming("peers"),
  warnings: [
    {
      code: "PEER_FIELDS_INCOMPLETE",
      message:
        "Washout is reported by 31 of 42 peers and an upper age limit by " +
        "25; those medians use only the trials that report them.",
      severity: "warning",
    },
    {
      code: "FREE_TEXT_THRESHOLDS",
      message:
        "Thresholds were parsed from free-text registry entries; 6 values " +
        "could not be parsed and were left out.",
      severity: "info",
    },
  ],
  data_sources: [
    DATA_SOURCES.aact,
    DATA_SOURCES.clinicalTrialsGov,
    DATA_SOURCES.protocol,
  ],
  tables: [
    peerComparisonTable,
    {
      table_id: "tbl-prs-selection",
      title: "How the peer set was selected",
      description: "Filters applied in order to the registry snapshot.",
      columns: [
        { key: "filter", label: "Filter" },
        { key: "trials", label: "Trials remaining" },
      ],
      rows: [
        { filter: "Interventional T2D trials started 2016-2025", trials: 3_912 },
        { filter: "Phase 3", trials: 1_318 },
        { filter: "Add-on to metformin", trials: 214 },
        { filter: "HbA1c primary endpoint", trials: 97 },
        {
          filter: "Oral investigational drug, at least 150 participants",
          trials: PEER_TRIAL_COUNT,
        },
      ],
    },
    {
      table_id: "tbl-prs-closest",
      title: "Closest peers (placeholder IDs)",
      description: "The 6 peers most similar in design to the draft.",
      columns: [
        { key: "trial", label: "Trial" },
        { key: "drug_class", label: "Drug class" },
        { key: "weeks", label: "Duration", unit: "weeks" },
        { key: "participants", label: "Participants" },
        { key: "hba1c_window", label: "HbA1c window", unit: "%" },
        { key: "age_range", label: "Age range", unit: "years" },
        { key: "egfr_cutoff", label: "eGFR cut-off" },
      ],
      rows: [
        { trial: "NCT00000001", drug_class: "SGLT2 inhibitor", weeks: 24, participants: 450, hba1c_window: "7.0-10.5", age_range: "18-80", egfr_cutoff: 45 },
        { trial: "NCT00000002", drug_class: "SGLT2 inhibitor", weeks: 52, participants: 1_310, hba1c_window: "7.0-10.0", age_range: "18 and over", egfr_cutoff: 60 },
        { trial: "NCT00000003", drug_class: "DPP-4 inhibitor", weeks: 24, participants: 612, hba1c_window: "7.0-10.0", age_range: "18-80", egfr_cutoff: 45 },
        { trial: "NCT00000004", drug_class: "SGLT2 inhibitor", weeks: 26, participants: 390, hba1c_window: "7.5-10.5", age_range: "18-78", egfr_cutoff: 30 },
        { trial: "NCT00000005", drug_class: "Oral GLP-1 RA", weeks: 26, participants: 820, hba1c_window: "7.0-9.5", age_range: "18 and over", egfr_cutoff: 30 },
        { trial: "NCT00000006", drug_class: "SGLT2 inhibitor", weeks: 36, participants: 540, hba1c_window: "7.0-10.0", age_range: "18-85", egfr_cutoff: 45 },
      ],
    },
  ],
  charts: [
    hba1cChart,
    {
      chart_id: "ch-prs-weeks",
      kind: "comparison",
      title: "Treatment duration and washout vs peers",
      description: "Both within the peer range; washout sits at P90.",
      x_label: "Field",
      y_label: "Weeks",
      unit: "weeks",
      series: [
        {
          name: "Peer median (P10-P90)",
          points: [DURATION, WASHOUT].map((row) => ({
            label: row.field,
            value: row.median,
            lower: row.p10,
            upper: row.p90,
          })),
        },
        {
          name: "Draft",
          points: [DURATION, WASHOUT].map((row) => ({
            label: row.field,
            value: row.draft,
            annotation: row.verdict,
          })),
        },
      ],
    },
  ],
  decisions: [
    {
      decision_id: "d-prs-01",
      step_id: "peers",
      severity: "warning",
      title: "HbA1c exclusion stricter than peers",
      claim:
        "Excluding HbA1c above 9.0% is outside the peer P10-P90 " +
        "range of 9.5-10.5%.",
      category: "Eligibility benchmark",
      confidence: 0.87,
      location: {
        section_heading: "5.2",
        section_title: "Exclusion Criteria",
        start_page: 25,
        end_page: 25,
        criterion_id: "E-03",
      },
      evidence: [
        {
          evidence_id: "e-prs-01",
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
            "with an HbA1c above 9.0% are excluded from enrolment.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-prs-02",
          source: "aact",
          document: "ClinicalTrials.gov NCT00000001 (illustrative)",
          page: null,
          quote: "Exclusion: HbA1c > 10.5% at screening.",
          is_verified: true,
          section_title: "Eligibility criteria",
          context:
            "Inclusion: HbA1c 7.0-10.5% on stable metformin. Exclusion: " +
            "HbA1c > 10.5% at screening. Exclusion: eGFR < 45.",
          confidence: 0.92,
        },
        {
          evidence_id: "e-prs-04",
          source: "aact",
          document: PEER_SET_DOCUMENT,
          page: null,
          quote:
            "HbA1c upper bound across 42 peers: median 10.0%, P10 9.5%, " +
            "P90 10.5%.",
          is_verified: true,
          context:
            "Upper HbA1c bounds were parsed from all 42 peer entries. " +
            "HbA1c upper bound across 42 peers: median 10.0%, P10 9.5%, " +
            "P90 10.5%.",
          confidence: 0.88,
        },
      ],
      trace: timedTrace("peers", "d-prs-01", 9_800, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Fetched 42 Phase 3 T2D trials from the last 10 years.",
          evidence_ids: ["e-prs-02", "e-prs-04"],
          duration_ms: 6_420,
        },
        {
          agent: AGENT,
          kind: "rule",
          text:
            "Used 9.0% as the draft's bound, since E-03 overrides the " +
            "10.5% in I-03.",
          evidence_ids: ["e-prs-01"],
          duration_ms: 310,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Draft cut-off 9.0 is below the peer 10th percentile (9.5).",
          evidence_ids: ["e-prs-01", "e-prs-04"],
          duration_ms: 880,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "Flagged as an outlier that may slow recruitment.",
          evidence_ids: ["e-prs-01"],
          duration_ms: 150,
        },
      ]),
      proposed_change: {
        path: "5.1 Inclusion criteria, I-03",
        before: "between 7.0% and 10.5%",
        after: "between 7.0% and 10.0%",
        change_type: "modify",
        section_title: "5.1 Inclusion Criteria",
        page: 24,
        rationale:
          "Together with removing E-03, sets a single window whose upper " +
          "bound is the peer median.",
      },
      derived_from: ["d-ing-01", "d-chk-07"],
      impact: [
        {
          label: "Upper bound vs peers",
          value: "Below P10 → median",
          tone: "good",
        },
      ],
      options: [
        {
          option_id: "o-prs-01-a",
          title: "Set the upper bound to 10.0%",
          rationale: "The peer median; keeps baseline HbA1c fairly narrow.",
          is_recommended: true,
          proposed_change: {
            path: "5.1 Inclusion criteria, I-03",
            before: "between 7.0% and 10.5%",
            after: "between 7.0% and 10.0%",
            change_type: "modify",
            section_title: "5.1 Inclusion Criteria",
            page: 24,
          },
          impact: [{ label: "Position vs peers", value: "Median", tone: "good" }],
          risks: ["Wider baseline spread may raise the SD used for sizing."],
        },
        {
          option_id: "o-prs-01-b",
          title: "Keep 10.5% from I-03",
          rationale: "Only E-03 needs deleting; matches the peer P90.",
          impact: [{ label: "Position vs peers", value: "P90", tone: "neutral" }],
          risks: [
            "More participants likely to need rescue early.",
            "Larger HbA1c variance.",
          ],
        },
        {
          option_id: "o-prs-01-c",
          title: "Keep 9.0% and fix I-03 to match",
          rationale: "Most homogeneous population.",
          impact: [{ label: "Position vs peers", value: "Below P10", tone: "risk" }],
          risks: ["Slowest recruitment of the three options."],
        },
      ],
      references: [REFERENCES.adaStandards, REFERENCES.fdaDiabetes],
      decision_owner: "Clinical Operations Lead",
      review_status: "pending",
      tags: ["eligibility", "hba1c", "outlier"],
      charts: [hba1cChart],
    },
    {
      decision_id: "d-prs-02",
      step_id: "peers",
      severity: "info",
      title: "Treatment duration shorter than peers",
      claim:
        "26 weeks is below the peer median of 36 weeks, which is " +
        "acceptable for an HbA1c endpoint.",
      category: "Design benchmark",
      confidence: 0.83,
      location: {
        section_heading: "4.1",
        section_title: "Overall Design",
        start_page: 16,
        end_page: 16,
      },
      evidence: [
        {
          evidence_id: "e-prs-03",
          source: "aact",
          document: PEER_SET_DOCUMENT,
          page: null,
          quote: "Median treatment duration across peers: 36 weeks.",
          is_verified: true,
          context:
            "Median treatment duration across peers: 36 weeks. P10 is " +
            "24 weeks and P90 is 52 weeks; 11 peers ran for 24-26 weeks.",
          confidence: 0.9,
        },
        {
          evidence_id: "e-prs-05",
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
            "followed by a 2-week safety follow-up.",
          confidence: 0.97,
        },
      ],
      trace: timedTrace("peers", "d-prs-02", 18_200, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Read the 26-week treatment period from Section 4.1.",
          evidence_ids: ["e-prs-05"],
          duration_ms: 240,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "Compared planned duration with the peer distribution.",
          evidence_ids: ["e-prs-03", "e-prs-05"],
          duration_ms: 610,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "Within the P10-P90 range, so informational only.",
          evidence_ids: ["e-prs-03"],
          duration_ms: 120,
        },
      ]),
      derived_from: ["d-chk-02"],
      impact: [
        {
          label: "Duration",
          value: "26 wk",
          numeric_value: DURATION.draft,
          unit: "weeks",
          benchmarks: [
            { label: "Peer median", value: "36 wk", numeric_value: DURATION.median },
            { label: "Peer P10", value: "24 wk", numeric_value: DURATION.p10 },
          ],
        },
      ],
      references: [REFERENCES.fdaDiabetes],
      decision_owner: "Lead Biostatistician",
      review_status: "pending",
      tags: ["duration", "in-range"],
    },
    {
      decision_id: "d-prs-03",
      step_id: "peers",
      severity: "warning",
      title: "Upper age limit below peer range",
      claim:
        "The draft caps age at 75. 17 of 42 peers set no upper limit, and " +
        "among the 25 that do, the median is 80 years (P10 77).",
      category: "Eligibility benchmark",
      confidence: 0.82,
      location: {
        section_heading: "5.1",
        section_title: "Inclusion Criteria",
        start_page: 24,
        end_page: 24,
        criterion_id: "I-01",
      },
      evidence: [
        {
          evidence_id: "e-prs-06",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 24,
          quote: "Aged 18 to 75 years at screening.",
          is_verified: true,
          section_title: "5.1 Inclusion Criteria",
          context:
            "Participants must meet all of the following criteria. I-01. " +
            "Aged 18 to 75 years at screening. I-02. Diagnosis of type 2 " +
            "diabetes for at least 180 days before screening.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-prs-07",
          source: "aact",
          document: PEER_SET_DOCUMENT,
          page: null,
          quote:
            "17 of 42 peers set no upper age limit; among the 25 that do, " +
            "the median is 80 years.",
          is_verified: true,
          context:
            "17 of 42 peers set no upper age limit; among the 25 that do, " +
            "the median is 80 years. Only 2 peers cap age at 75 or below.",
          confidence: 0.86,
        },
        {
          evidence_id: "e-prs-08",
          source: "guideline",
          document: REFERENCES.ichE7.label,
          page: null,
          quote: REFERENCES.ichE7.quote,
          is_verified: true,
          url: REFERENCES.ichE7.url,
          confidence: 0.85,
        },
      ],
      trace: timedTrace("peers", "d-prs-03", 24_500, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Collected upper age limits from all 42 peers.",
          evidence_ids: ["e-prs-07"],
          duration_ms: 1_830,
        },
        {
          agent: AGENT,
          kind: "compare",
          text:
            "Draft 75 is below the P10 (77) of peers that set a limit; " +
            "only 2 of 42 cap at 75 or below.",
          evidence_ids: ["e-prs-06", "e-prs-07"],
          duration_ms: 540,
        },
        {
          agent: AGENT,
          kind: "rule",
          text:
            "ICH E7 asks for participants representative of the treated " +
            "population, which includes many adults over 75 with T2D.",
          evidence_ids: ["e-prs-08"],
          duration_ms: 290,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "Flagged as the second outlier.",
          evidence_ids: ["e-prs-06"],
          duration_ms: 110,
        },
      ]),
      proposed_change: {
        path: "5.1 Inclusion criteria, I-01",
        before: "Aged 18 to 75 years",
        after: "Aged 18 to 80 years",
        change_type: "modify",
        section_title: "5.1 Inclusion Criteria",
        page: 24,
        rationale: "Brings the limit to the peer median.",
      },
      derived_from: ["d-ing-01"],
      impact: [
        {
          label: "Peers with a stricter cap",
          value: "2 of 42",
          tone: "warn",
          numeric_value: 2,
          unit: "trials",
        },
      ],
      options: [
        {
          option_id: "o-prs-03-a",
          title: "Raise the limit to 80",
          rationale: "Peer median among trials with a limit.",
          is_recommended: true,
          proposed_change: {
            path: "5.1 Inclusion criteria, I-01",
            before: "Aged 18 to 75 years",
            after: "Aged 18 to 80 years",
            change_type: "modify",
            section_title: "5.1 Inclusion Criteria",
            page: 24,
          },
          impact: [{ label: "Position vs peers", value: "Median", tone: "good" }],
          risks: ["More volume depletion and genital infection events."],
        },
        {
          option_id: "o-prs-03-b",
          title: "Remove the upper limit",
          rationale: "As 17 of 42 peers do; relies on the eGFR and CV rules.",
          proposed_change: {
            path: "5.1 Inclusion criteria, I-01",
            before: "Aged 18 to 75 years",
            after: "Aged 18 years or older",
            change_type: "modify",
            section_title: "5.1 Inclusion Criteria",
            page: 24,
          },
          impact: [{ label: "Position vs peers", value: "Most inclusive", tone: "good" }],
          risks: ["Needs extra safety monitoring for frail participants."],
        },
        {
          option_id: "o-prs-03-c",
          title: "Keep 75",
          rationale: "Simplest safety profile.",
          impact: [{ label: "Position vs peers", value: "Below P10", tone: "risk" }],
          risks: ["Results may not apply to older patients."],
        },
      ],
      references: [REFERENCES.ichE7, REFERENCES.fdaDiversity],
      decision_owner: "Medical Monitor",
      review_status: "pending",
      tags: ["eligibility", "age", "outlier"],
      charts: [
        {
          chart_id: "ch-prs-age",
          kind: "histogram",
          title: "Upper age limit in peers that set one",
          description: "25 peers; 17 more set no upper limit.",
          x_label: "Upper age limit (years)",
          y_label: "Trials",
          unit: "trials",
          series: [{ name: "Peers", points: AGE_LIMIT_BINS }],
        },
      ],
    },
    {
      decision_id: "d-prs-04",
      step_id: "peers",
      severity: "info",
      title: "Washout at the upper end of peers",
      claim:
        "A 12-week washout for prior SGLT2 inhibitors and GLP-1 receptor " +
        "agonists equals the peer P90; the median is 8 weeks.",
      category: "Design benchmark",
      confidence: 0.78,
      location: {
        section_heading: "5.2",
        section_title: "Exclusion Criteria",
        start_page: 25,
        end_page: 25,
        criterion_id: "E-08",
      },
      evidence: [
        {
          evidence_id: "e-prs-09",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 25,
          quote: "SGLT2 inhibitor use within 12 weeks before screening.",
          is_verified: true,
          section_title: "5.2 Exclusion Criteria",
          context:
            "E-07. Insulin use within 12 months before screening. E-08. " +
            "SGLT2 inhibitor use within 12 weeks before screening. E-09. " +
            "GLP-1 receptor agonist use within 12 weeks before screening.",
          confidence: 0.97,
        },
        {
          evidence_id: "e-prs-10",
          source: "aact",
          document: PEER_SET_DOCUMENT,
          page: null,
          quote:
            "Washout of prior glucose-lowering agents (31 peers): median " +
            "8 weeks, P10 4, P90 12.",
          is_verified: true,
          context:
            "11 peers do not state a washout. Washout of prior " +
            "glucose-lowering agents (31 peers): median 8 weeks, P10 4, " +
            "P90 12.",
          confidence: 0.8,
        },
      ],
      trace: timedTrace("peers", "d-prs-04", 31_000, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Read washout rules E-08 and E-09 (p. 25).",
          evidence_ids: ["e-prs-09"],
          duration_ms: 260,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "12 weeks equals the P90 of the 31 peers that report it.",
          evidence_ids: ["e-prs-09", "e-prs-10"],
          duration_ms: 720,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text: "In range; noted because it lengthens screening.",
          evidence_ids: ["e-prs-10"],
          duration_ms: 100,
        },
      ]),
      impact: [
        {
          label: "Washout",
          value: "12 wk",
          numeric_value: WASHOUT.draft,
          unit: "weeks",
          benchmarks: [
            { label: "Peer median", value: "8 wk", numeric_value: WASHOUT.median },
          ],
        },
      ],
      options: [
        {
          option_id: "o-prs-04-a",
          title: "Keep 12 weeks",
          rationale:
            "HbA1c reflects roughly the previous 2-3 months, so 12 weeks " +
            "gives a clean baseline.",
          is_recommended: true,
          impact: [{ label: "Screening length", value: "Unchanged" }],
          risks: ["Longer screening for switchers."],
        },
        {
          option_id: "o-prs-04-b",
          title: "Shorten to 8 weeks",
          rationale: "Peer median; shortens screening by 4 weeks.",
          proposed_change: {
            path: "5.2 Exclusion criteria, E-08 and E-09",
            before: "within 12 weeks before screening",
            after: "within 8 weeks before screening",
            change_type: "modify",
            section_title: "5.2 Exclusion Criteria",
            page: 25,
          },
          impact: [{ label: "Screening length", value: "-4 wk", tone: "good" }],
          risks: ["Baseline HbA1c may still reflect the prior drug."],
        },
      ],
      references: [REFERENCES.spiritSchedule],
      decision_owner: "Clinical Operations Lead",
      review_status: "pending",
      tags: ["washout", "in-range"],
    },
    {
      decision_id: "d-prs-05",
      step_id: "peers",
      severity: "info",
      title: "Sample size above peer median",
      claim:
        "1,200 participants is about twice the peer median of 612, but " +
        "within the P10-P90 range of 290-1,480.",
      category: "Design benchmark",
      confidence: 0.84,
      location: {
        section_heading: "9.2",
        section_title: "Sample Size Determination",
        start_page: 52,
        end_page: 52,
      },
      evidence: [
        {
          evidence_id: "e-prs-11",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 52,
          quote:
            "Assuming a treatment difference of 0.5%, 1,200 participants " +
            "provide 90% power.",
          is_verified: true,
          section_title: "9.2 Sample Size Determination",
          context:
            "The sample size is based on the primary endpoint. Assuming " +
            "a treatment difference of 0.5%, 1,200 participants provide " +
            "90% power.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-prs-12",
          source: "aact",
          document: PEER_SET_DOCUMENT,
          page: null,
          quote:
            "Planned enrolment across 42 peers: median 612, P10 290, " +
            "P90 1,480.",
          is_verified: true,
          context:
            "Planned enrolment across 42 peers: median 612, P10 290, " +
            "P90 1,480. Trials above 1,000 mostly ran for 52 weeks.",
          confidence: 0.9,
        },
      ],
      trace: timedTrace("peers", "d-prs-05", 38_600, [
        {
          agent: AGENT,
          kind: "retrieve",
          text: "Read planned enrolment for all 42 peers.",
          evidence_ids: ["e-prs-12"],
          duration_ms: 1_120,
        },
        {
          agent: AGENT,
          kind: "compare",
          text: "1,200 sits between the median (612) and P90 (1,480).",
          evidence_ids: ["e-prs-11", "e-prs-12"],
          duration_ms: 330,
        },
        {
          agent: AGENT,
          kind: "conclude",
          text:
            "In range; supports the completeness finding that 1,200 needs " +
            "a stated reason.",
          evidence_ids: ["e-prs-11"],
          duration_ms: 130,
        },
      ]),
      derived_from: ["d-chk-03"],
      impact: [
        {
          label: "Sample size",
          value: "1,200",
          numeric_value: 1_200,
          unit: "participants",
          benchmarks: [
            { label: "Peer median", value: "612", numeric_value: 612 },
            { label: "Peer P90", value: "1,480", numeric_value: 1_480 },
          ],
        },
      ],
      references: [REFERENCES.ichE9SampleSize],
      decision_owner: "Lead Biostatistician",
      review_status: "pending",
      tags: ["sample-size", "in-range"],
    },
  ],
};
