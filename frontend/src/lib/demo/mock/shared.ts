import type {
  DataSource,
  GuidelineReference,
  StepId,
  TraceEntry,
} from "../types";

// Shared building blocks for the sample-protocol mock. Everything here is
// illustrative: the protocol, consent form, peer trials and cohort are
// synthetic, and registry IDs are NCT0000000x placeholders. Guideline
// names and URLs are real; quotes are only given where they are short,
// well-known passages, otherwise `quote` is left null.

export const PROTOCOL_DOCUMENT = "SGLT2_T2D_Phase3_Protocol_v0.3.pdf";
export const CONSENT_DOCUMENT = "SGLT2_T2D_Informed_Consent_v0.2.pdf";
export const PEER_SET_DOCUMENT = "ClinicalTrials.gov peer set (illustrative)";
export const COHORT_DOCUMENT = "MIMIC-IV simulated cohort (illustrative)";

export const MOCK_PROTOCOL_PAGE_COUNT = 86;
export const CONSENT_PAGE_COUNT = 9;

// Cohort funnel endpoints, reused by headline, metrics, tables and claims.
export const COHORT_START_COUNT = 18_402;
export const COHORT_ELIGIBLE_COUNT = 2_115;

// When the sample run started; every step and trace timestamp is an
// offset from here so started_at + duration_ms always equals completed_at.
const RUN_STARTED_AT_MS = Date.UTC(2026, 10, 6, 10, 42, 0);

interface StepTiming {
  offset_ms: number;
  duration_ms: number;
}

// Ingest runs first; the three recommendation agents then run in
// parallel from the same start, at different speeds.
const RECOMMENDATIONS_START_OFFSET_MS = 18_900;
export const STEP_TIMING: Record<StepId, StepTiming> = {
  ingest: { offset_ms: 0, duration_ms: 18_640 },
  check: { offset_ms: RECOMMENDATIONS_START_OFFSET_MS, duration_ms: 41_200 },
  peers: { offset_ms: RECOMMENDATIONS_START_OFFSET_MS, duration_ms: 63_450 },
  cohort: { offset_ms: RECOMMENDATIONS_START_OFFSET_MS, duration_ms: 87_900 },
};

function isoAt(offsetMs: number): string {
  return new Date(RUN_STARTED_AT_MS + offsetMs).toISOString();
}

/** started_at / completed_at / duration_ms for a step, always consistent. */
export function stepTiming(stepId: StepId): {
  started_at: string;
  completed_at: string;
  duration_ms: number;
} {
  const { offset_ms, duration_ms } = STEP_TIMING[stepId];
  return {
    started_at: isoAt(offset_ms),
    completed_at: isoAt(offset_ms + duration_ms),
    duration_ms,
  };
}

type TraceDraft = Omit<
  TraceEntry,
  "trace_id" | "timestamp" | "duration_ms"
> & { duration_ms: number };

/**
 * Number and time-stamp a decision's reasoning steps. Each entry starts
 * when the previous one ends, beginning `startInStepMs` into the step.
 */
export function timedTrace(
  stepId: StepId,
  decisionId: string,
  startInStepMs: number,
  drafts: TraceDraft[]
): TraceEntry[] {
  let cursorMs = STEP_TIMING[stepId].offset_ms + startInStepMs;
  return drafts.map((draft, index) => {
    const entry: TraceEntry = {
      ...draft,
      trace_id: `${decisionId.replace(/^d-/, "t-")}-${index + 1}`,
      timestamp: isoAt(cursorMs),
    };
    cursorMs += draft.duration_ms;
    return entry;
  });
}

// General public pages for each guideline; we link to the index rather
// than a specific PDF so links stay valid when versions are updated.
const ICH_EFFICACY_URL = "https://www.ich.org/page/efficacy-guidelines";
const ICH_MULTIDISCIPLINARY_URL =
  "https://www.ich.org/page/multidisciplinary-guidelines";
const SPIRIT_URL = "https://www.spirit-statement.org/";
const ADA_STANDARDS_URL = "https://professional.diabetes.org/standards-of-care";
const FDA_GUIDANCE_URL =
  "https://www.fda.gov/regulatory-information/search-fda-guidance-documents";

export const REFERENCES = {
  ichE6R3: {
    label: "ICH E6(R3) Good Clinical Practice",
    url: ICH_EFFICACY_URL,
    quote: null,
  },
  ichE6R2Idmc: {
    label: "ICH E6(R2) Good Clinical Practice, 5.5.2",
    url: ICH_EFFICACY_URL,
    quote:
      "The sponsor may consider establishing an independent " +
      "data-monitoring committee (IDMC) to assess the progress of a " +
      "clinical trial, including the safety data and the critical " +
      "efficacy endpoints at intervals, and to recommend to the sponsor " +
      "whether to continue, modify, or stop a trial.",
  },
  ichE9SampleSize: {
    label: "ICH E9 Statistical Principles for Clinical Trials, 3.5",
    url: ICH_EFFICACY_URL,
    quote:
      "The number of subjects in a clinical trial should always be " +
      "large enough to provide a reliable answer to the questions " +
      "addressed.",
  },
  ichE9R1Estimand: {
    label: "ICH E9(R1) Addendum on Estimands, Glossary",
    url: ICH_EFFICACY_URL,
    quote:
      "A precise description of the treatment effect reflecting the " +
      "clinical question posed by the trial objective.",
  },
  ichE7: {
    label: "ICH E7 Studies in Support of Special Populations: Geriatrics",
    url: ICH_EFFICACY_URL,
    quote:
      "Patients entering clinical trials should be reasonably " +
      "representative of the population that will be later treated by " +
      "the drug.",
  },
  ichM11: {
    label: "ICH M11 Clinical electronic Structured Harmonised Protocol",
    url: ICH_MULTIDISCIPLINARY_URL,
    quote: null,
  },
  spiritOutcomes: {
    label: "SPIRIT 2013, item 12 (Outcomes)",
    url: SPIRIT_URL,
    quote:
      "Primary, secondary, and other outcomes, including the specific " +
      "measurement variable",
  },
  spiritSchedule: {
    label: "SPIRIT 2013, item 13 (Participant timeline)",
    url: SPIRIT_URL,
    quote:
      "Time schedule of enrolment, interventions (including any run-ins " +
      "and washouts), assessments, and visits for participants.",
  },
  spiritConcomitant: {
    label: "SPIRIT 2013, item 11d (Concomitant care)",
    url: SPIRIT_URL,
    quote:
      "Relevant concomitant care and interventions that are permitted " +
      "or prohibited during the trial.",
  },
  spiritSampleSize: {
    label: "SPIRIT 2013, item 14 (Sample size)",
    url: SPIRIT_URL,
    quote:
      "Estimated number of participants needed to achieve study " +
      "objectives and how it was determined, including clinical and " +
      "statistical assumptions supporting any sample size calculations.",
  },
  spiritStopping: {
    label: "SPIRIT 2013, item 21b (Interim analyses)",
    url: SPIRIT_URL,
    quote:
      "Description of any interim analyses and stopping guidelines, " +
      "including who will have access to these interim results and make " +
      "the final decision to terminate the trial.",
  },
  adaHypoglycaemia: {
    label: "ADA Standards of Care in Diabetes, Section 6 (Glycemic Goals)",
    url: ADA_STANDARDS_URL,
    quote:
      "Level 1 hypoglycemia is defined as a measurable glucose " +
      "concentration <70 mg/dL (3.9 mmol/L) but ≥54 mg/dL (3.0 mmol/L).",
  },
  adaStandards: {
    label: "ADA Standards of Care in Diabetes",
    url: ADA_STANDARDS_URL,
    quote: null,
  },
  fdaDiabetes: {
    label:
      "FDA draft guidance: Diabetes Mellitus: Developing Drugs and " +
      "Therapeutic Biologics for Treatment and Prevention",
    url: FDA_GUIDANCE_URL,
    quote: null,
  },
  fdaDiversity: {
    label: "FDA guidance: Enhancing the Diversity of Clinical Trial Populations",
    url: FDA_GUIDANCE_URL,
    quote: null,
  },
} satisfies Record<string, GuidelineReference>;

export const DATA_SOURCES = {
  protocol: {
    source: "protocol",
    name: PROTOCOL_DOCUMENT,
    description:
      "Uploaded draft protocol SGLT2-T2D-301 (synthetic sample), " +
      `${MOCK_PROTOCOL_PAGE_COUNT} pages.`,
    version: "v0.3 (draft)",
    record_count: MOCK_PROTOCOL_PAGE_COUNT,
  },
  consent: {
    source: "consent",
    name: CONSENT_DOCUMENT,
    description:
      "Participant information and consent form (synthetic sample), " +
      `${CONSENT_PAGE_COUNT} pages; written against protocol v0.2.`,
    version: "v0.2",
    record_count: CONSENT_PAGE_COUNT,
  },
  ichM11: {
    source: "guideline",
    name: "ICH M11 protocol template",
    description: "Section structure used to map the protocol (11 sections).",
    url: ICH_MULTIDISCIPLINARY_URL,
    version: "Step 4",
  },
  rubric: {
    source: "other",
    name: "Completeness rubric (illustrative)",
    description:
      "14 items drawn from ICH E6, ICH E9/E9(R1), ICH M11 and SPIRIT 2013.",
    version: "v1",
    record_count: 14,
  },
  ichEfficacy: {
    source: "guideline",
    name: "ICH E6(R3), E7, E9 and E9(R1)",
    description: "GCP, geriatric, statistical and estimand guidance.",
    url: ICH_EFFICACY_URL,
  },
  spirit: {
    source: "guideline",
    name: "SPIRIT 2013 checklist",
    description: "Recommended items for a clinical trial protocol.",
    url: SPIRIT_URL,
    version: "2013",
  },
  ada: {
    source: "guideline",
    name: "ADA Standards of Care in Diabetes",
    description: "Hypoglycaemia levels and glycaemic targets.",
    url: ADA_STANDARDS_URL,
  },
  aact: {
    source: "aact",
    name: "AACT snapshot of ClinicalTrials.gov (illustrative)",
    description:
      "Phase 3 T2D add-on-to-metformin trials with an HbA1c primary " +
      "endpoint, started 2016-2025. Trial IDs shown are placeholders.",
    url: "https://aact.ctti-clinicaltrials.org/",
    version: "2026-10-01 snapshot",
    record_count: 42,
  },
  clinicalTrialsGov: {
    source: "aact",
    name: "ClinicalTrials.gov",
    description: "Registry the AACT snapshot is built from.",
    url: "https://clinicaltrials.gov/",
  },
  mimic: {
    source: "mimic",
    name: COHORT_DOCUMENT,
    description:
      "Synthetic adult T2D cohort shaped on MIMIC-IV distributions. Not " +
      "real patients and not a recruitment feasibility estimate.",
    url: "https://physionet.org/content/mimiciv/",
    version: "MIMIC-IV v3.1 distributions",
    record_count: COHORT_START_COUNT,
  },
  nhanes: {
    source: "nhanes",
    name: "NHANES 2017-March 2020 (illustrative subset)",
    description:
      "US adults with diagnosed diabetes, used as a population reference " +
      "for subgroup shares.",
    url: "https://www.cdc.gov/nchs/nhanes/",
    version: "2017-March 2020 pre-pandemic",
    record_count: 1_012,
  },
} satisfies Record<string, DataSource>;
