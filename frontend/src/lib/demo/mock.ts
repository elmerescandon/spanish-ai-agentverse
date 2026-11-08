import type { StepData } from "./types";

// All demo content is illustrative mock data for the Phase III SGLT2 T2D
// protocol. IDs and evidence cross-reference across steps so the
// traceability chain can be walked end to end.

const PROTOCOL_DOCUMENT = "SGLT2_T2D_Phase3_Protocol_v0.3.pdf";
const CONSENT_DOCUMENT = "SGLT2_T2D_Informed_Consent_v0.2.pdf";

export const MOCK_PROTOCOL_PAGE_COUNT = 86;

export const MOCK_STEPS: StepData[] = [
  {
    id: "ingest",
    title: "Data Ingestion",
    summary: "Protocol PDF parsed into a structured, cited document.",
    headline: { label: "criteria extracted", value: "34" },
    metrics: [
      { label: "Pages", value: "86" },
      { label: "ICH M11 sections", value: "11/11", tone: "good" },
      { label: "Criteria extracted", value: "34" },
      { label: "Parser warnings", value: "2", tone: "warn" },
    ],
    decisions: [
      {
        decision_id: "d-ing-01",
        step_id: "ingest",
        severity: "info",
        title: "Eligibility criteria extracted",
        claim:
          "34 discrete criteria were extracted: 14 inclusion, 20 exclusion.",
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
          },
        ],
        trace: [
          {
            agent: "Ingestion",
            kind: "retrieve",
            text: "Located Section 5 (Study Population) on pages 24-26.",
            evidence_ids: ["e-ing-01"],
          },
          {
            agent: "Ingestion",
            kind: "rule",
            text: "Split numbered criteria into discrete items.",
            evidence_ids: ["e-ing-01", "e-ing-02"],
          },
          {
            agent: "Ingestion",
            kind: "conclude",
            text: "34 criteria extracted, each with a verbatim quote.",
            evidence_ids: ["e-ing-02"],
          },
        ],
      },
      {
        decision_id: "d-ing-02",
        step_id: "ingest",
        severity: "warning",
        title: "Schedule of Activities partly unreadable",
        claim:
          "The final row of the Schedule of Activities table could not " +
          "be parsed reliably, so the last visit week is uncertain.",
        evidence: [
          {
            evidence_id: "e-ing-03",
            source: "protocol",
            document: PROTOCOL_DOCUMENT,
            page: 31,
            quote: "End of Treatment visit: Week 26 (+/- 3 days)",
            is_verified: false,
          },
        ],
        trace: [
          {
            agent: "Ingestion",
            kind: "retrieve",
            text: "Found the Schedule of Activities table on page 31.",
            evidence_ids: ["e-ing-03"],
          },
          {
            agent: "Ingestion",
            kind: "conclude",
            text: "Merged cells in the last row lowered parse confidence.",
            evidence_ids: ["e-ing-03"],
          },
        ],
      },
    ],
  },
  {
    id: "check",
    title: "Completeness & Consistency",
    summary: "Protocol checked against the guideline rubric.",
    headline: { label: "items missing", value: "2", tone: "risk" },
    metrics: [
      { label: "Present", value: "9", tone: "good" },
      { label: "Weak", value: "3", tone: "warn" },
      { label: "Missing", value: "2", tone: "risk" },
      { label: "Contradictions", value: "1", tone: "warn" },
    ],
    decisions: [
      {
        decision_id: "d-chk-01",
        step_id: "check",
        severity: "critical",
        title: "Rescue medication criteria missing",
        claim:
          "No rescue medication rule is defined, although the protocol " +
          "allows glycaemic rescue after Week 12.",
        evidence: [
          {
            evidence_id: "e-chk-01",
            source: "protocol",
            document: PROTOCOL_DOCUMENT,
            page: 38,
            quote:
              "Rescue therapy may be initiated at the investigator's " +
              "discretion after Week 12.",
            is_verified: true,
          },
        ],
        trace: [
          {
            agent: "Completeness",
            kind: "rule",
            text: "Rubric item R-07 requires explicit rescue thresholds.",
            evidence_ids: ["e-chk-01"],
          },
          {
            agent: "Completeness",
            kind: "conclude",
            text: "No threshold found anywhere in the document: missing.",
            evidence_ids: ["e-chk-01"],
          },
        ],
        proposed_change: {
          path: "6.4 Rescue therapy",
          before: "at the investigator's discretion",
          after: "when fasting plasma glucose exceeds 13.3 mmol/L",
        },
      },
      {
        decision_id: "d-chk-02",
        step_id: "check",
        severity: "warning",
        title: "Endpoint week conflicts with schedule",
        claim:
          "The primary endpoint is measured at Week 24, but the last " +
          "scheduled visit is Week 26.",
        evidence: [
          {
            evidence_id: "e-chk-02",
            source: "protocol",
            document: PROTOCOL_DOCUMENT,
            page: 12,
            quote:
              "Primary endpoint: mean change in HbA1c from baseline " +
              "at Week 24.",
            is_verified: true,
          },
          {
            evidence_id: "e-chk-03",
            source: "consent",
            document: CONSENT_DOCUMENT,
            page: 3,
            quote: "You will attend study visits for about 26 weeks.",
            is_verified: true,
          },
        ],
        trace: [
          {
            agent: "Consistency",
            kind: "compare",
            text: "Compared endpoint timing with the visit schedule.",
            evidence_ids: ["e-chk-02", "e-chk-03"],
          },
          {
            agent: "Consistency",
            kind: "conclude",
            text: "Week 24 endpoint is not tied to a scheduled visit.",
            evidence_ids: ["e-chk-02"],
          },
        ],
        proposed_change: {
          path: "3.1 Primary endpoint",
          before: "at Week 24",
          after: "at Week 24 (Visit 9, window +/- 3 days)",
        },
        derived_from: ["d-ing-02"],
      },
      {
        decision_id: "d-chk-03",
        step_id: "check",
        severity: "warning",
        title: "Sample size assumption is weak",
        claim:
          "The sample size cites a 0.5% HbA1c effect without a source " +
          "or variance estimate.",
        evidence: [
          {
            evidence_id: "e-chk-04",
            source: "protocol",
            document: PROTOCOL_DOCUMENT,
            page: 52,
            quote:
              "Assuming a treatment difference of 0.5%, 1,200 " +
              "participants provide 90% power.",
            is_verified: true,
          },
        ],
        trace: [
          {
            agent: "Completeness",
            kind: "rule",
            text: "Rubric item R-11 requires a sourced effect size.",
            evidence_ids: ["e-chk-04"],
          },
          {
            agent: "Completeness",
            kind: "conclude",
            text: "Effect size stated, but no citation or SD: weak.",
            evidence_ids: ["e-chk-04"],
          },
        ],
      },
    ],
  },
  {
    id: "peers",
    title: "Protocol Comparison",
    summary: "Draft compared with similar Phase 3 diabetes trials.",
    headline: { label: "peer trials", value: "42" },
    metrics: [
      { label: "Peer trials", value: "42" },
      { label: "Outliers", value: "2", tone: "warn" },
      { label: "Biggest outlier", value: "HbA1c ≥ 9.0", tone: "risk" },
      { label: "Peer median duration", value: "36 wk" },
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
          },
          {
            evidence_id: "e-prs-02",
            source: "aact",
            document: "ClinicalTrials.gov NCT00000001 (illustrative)",
            page: null,
            quote: "Exclusion: HbA1c > 10.5% at screening.",
            is_verified: true,
          },
        ],
        trace: [
          {
            agent: "Comparison",
            kind: "retrieve",
            text: "Fetched 42 Phase 3 T2D trials from the last 10 years.",
            evidence_ids: ["e-prs-02"],
          },
          {
            agent: "Comparison",
            kind: "compare",
            text: "Draft cut-off 9.0 is below the peer 10th percentile.",
            evidence_ids: ["e-prs-01", "e-prs-02"],
          },
          {
            agent: "Comparison",
            kind: "conclude",
            text: "Flagged as an outlier that may slow recruitment.",
            evidence_ids: ["e-prs-01"],
          },
        ],
        proposed_change: {
          path: "5.2 Exclusion criteria",
          before: "HbA1c above 9.0%",
          after: "HbA1c above 10.0%",
        },
        derived_from: ["d-ing-01"],
      },
      {
        decision_id: "d-prs-02",
        step_id: "peers",
        severity: "info",
        title: "Treatment duration shorter than peers",
        claim:
          "26 weeks is below the peer median of 36 weeks, which is " +
          "acceptable for an HbA1c endpoint.",
        evidence: [
          {
            evidence_id: "e-prs-03",
            source: "aact",
            document: "ClinicalTrials.gov peer set (illustrative)",
            page: null,
            quote: "Median treatment duration across peers: 36 weeks.",
            is_verified: true,
          },
        ],
        trace: [
          {
            agent: "Comparison",
            kind: "compare",
            text: "Compared planned duration with the peer distribution.",
            evidence_ids: ["e-prs-03"],
          },
          {
            agent: "Comparison",
            kind: "conclude",
            text: "Within the P10-P90 range, so informational only.",
            evidence_ids: ["e-prs-03"],
          },
        ],
        derived_from: ["d-chk-02"],
      },
    ],
  },
  {
    id: "cohort",
    title: "Cohort Comparison",
    summary: "Eligibility rules applied to a simulated patient cohort.",
    headline: { label: "eGFR < 45", value: "-31%", tone: "risk" },
    metrics: [
      { label: "Cohort", value: "18,402" },
      { label: "Eligible", value: "2,115", tone: "good" },
      { label: "Steepest drop", value: "eGFR < 45: -31%", tone: "risk" },
      { label: "Cannot simulate", value: "3", tone: "warn" },
    ],
    decisions: [
      {
        decision_id: "d-coh-01",
        step_id: "cohort",
        severity: "critical",
        title: "eGFR exclusion removes the most patients",
        claim:
          "The eGFR below 45 exclusion removes 31% of otherwise " +
          "eligible patients, far more than in peer trials.",
        evidence: [
          {
            evidence_id: "e-coh-01",
            source: "protocol",
            document: PROTOCOL_DOCUMENT,
            page: 25,
            quote: "eGFR below 45 mL/min/1.73 m2 at screening.",
            is_verified: true,
          },
          {
            evidence_id: "e-coh-02",
            source: "mimic",
            document: "MIMIC-IV simulated cohort (illustrative)",
            page: null,
            quote: "3,066 of 9,891 remaining patients have eGFR < 45.",
            is_verified: true,
          },
        ],
        trace: [
          {
            agent: "Cohort",
            kind: "rule",
            text: "Converted the criterion to a computable eGFR filter.",
            evidence_ids: ["e-coh-01"],
          },
          {
            agent: "Cohort",
            kind: "compare",
            text: "Applied the filter to the cohort; 31% were removed.",
            evidence_ids: ["e-coh-02"],
          },
          {
            agent: "Cohort",
            kind: "conclude",
            text: "Largest single drop in the attrition waterfall.",
            evidence_ids: ["e-coh-02"],
          },
        ],
        proposed_change: {
          path: "5.2 Exclusion criteria",
          before: "eGFR below 45",
          after: "eGFR below 30",
        },
        derived_from: ["d-prs-01"],
      },
      {
        decision_id: "d-coh-02",
        step_id: "cohort",
        severity: "warning",
        title: "Women under-represented after filtering",
        claim:
          "Women are 38% of the eligible cohort versus 46% in peer " +
          "trials.",
        evidence: [
          {
            evidence_id: "e-coh-03",
            source: "mimic",
            document: "MIMIC-IV simulated cohort (illustrative)",
            page: null,
            quote: "Eligible cohort: 38% female (803 of 2,115).",
            is_verified: true,
          },
        ],
        trace: [
          {
            agent: "Cohort",
            kind: "compare",
            text: "Compared subgroup shares with peer baseline tables.",
            evidence_ids: ["e-coh-03"],
          },
          {
            agent: "Cohort",
            kind: "conclude",
            text: "8-point gap, driven by the eGFR and HbA1c exclusions.",
            evidence_ids: ["e-coh-03"],
          },
        ],
        derived_from: ["d-coh-01"],
      },
    ],
  },
];
