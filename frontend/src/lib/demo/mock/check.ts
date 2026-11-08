import type { ChartSeries, StepData } from "../types";
import {
  CONSENT_DOCUMENT,
  DATA_SOURCES,
  PROTOCOL_DOCUMENT,
  REFERENCES,
  stepTiming,
  timedTrace,
} from "./shared";

const COMPLETENESS = "Completeness";
const CONSISTENCY = "Consistency";

type RubricStatus = "present" | "weak" | "missing";

interface RubricItem {
  item: string;
  requirement: string;
  reference: string;
  status: RubricStatus;
  // "contradiction" when the item is present but disagrees with another
  // statement; counted separately from status.
  flag: string;
  section: string;
  page: number;
  snippet: string;
  explanation: string;
}

const NOT_FOUND = "not found";

// The 14-item rubric. Counts per status drive the step metrics, headline
// and stacked bar, so every figure on this step comes from this list.
export const RUBRIC: RubricItem[] = [
  {
    item: "R-01",
    requirement: "Title, phase, sponsor and protocol version",
    reference: "ICH M11, Section 1; SPIRIT 2013 items 1-3",
    status: "present",
    flag: "",
    section: "1",
    page: 1,
    snippet: "Protocol SGLT2-T2D-301, Version 0.3 (draft)",
    explanation: "Title page names the study, phase and version.",
  },
  {
    item: "R-02",
    requirement: "Objectives linked to endpoints",
    reference: "ICH M11, Section 3; SPIRIT 2013 item 7",
    status: "present",
    flag: "",
    section: "3",
    page: 12,
    snippet:
      "Primary endpoint: mean change in HbA1c from baseline at Week 24.",
    explanation: "Each objective maps to exactly one named endpoint.",
  },
  {
    item: "R-03",
    requirement: "Primary estimand with ICH E9(R1) attributes",
    reference: "ICH E9(R1)",
    status: "weak",
    flag: "",
    section: "3",
    page: 13,
    snippet:
      "The primary efficacy analysis will compare mean change in HbA1c " +
      "from baseline to Week 24 between each dose and placebo.",
    explanation:
      "Four of five attributes are given, but intercurrent events and " +
      "their strategies are not.",
  },
  {
    item: "R-04",
    requirement: "Eligibility criteria numbered and measurable",
    reference: "ICH M11, Section 5; SPIRIT 2013 item 10",
    status: "present",
    flag: "contradiction",
    section: "5",
    page: 24,
    snippet:
      "Participants must have an HbA1c between 7.0% and 10.5% at " +
      "screening.",
    explanation:
      "All 34 criteria are numbered with thresholds, but the HbA1c upper " +
      "bound is 10.5% here and 9.0% in E-03 (p. 25).",
  },
  {
    item: "R-05",
    requirement: "Schedule of Activities aligned with endpoints",
    reference: "SPIRIT 2013 item 13",
    status: "weak",
    flag: "",
    section: "6",
    page: 31,
    snippet: "V7: Week 20 (+/- 3 days): HbA1c, FPG, vital signs",
    explanation:
      "The schedule exists, but no visit falls at Week 24, when the " +
      "primary endpoint is measured.",
  },
  {
    item: "R-06",
    requirement: "Randomisation and blinding",
    reference: "ICH M11, Section 4; SPIRIT 2013 items 16-17",
    status: "present",
    flag: "",
    section: "4",
    page: 18,
    snippet:
      "Participants will be randomised 1:1:1 to SGLT2 inhibitor 10 mg, " +
      "25 mg or placebo.",
    explanation: "Ratio, stratification and double-blinding are described.",
  },
  {
    item: "R-07",
    requirement: "Rescue medication criteria",
    reference: "SPIRIT 2013 item 11d; FDA diabetes draft guidance",
    status: "missing",
    flag: "",
    section: "6",
    page: 38,
    snippet: NOT_FOUND,
    explanation:
      "Rescue is allowed after Week 12 (p. 38), but no glucose or HbA1c " +
      "threshold triggers it anywhere in the 86 pages.",
  },
  {
    item: "R-08",
    requirement: "Permitted and prohibited concomitant medication",
    reference: "SPIRIT 2013 item 11d",
    status: "present",
    flag: "",
    section: "6",
    page: 36,
    snippet:
      "Glucose-lowering medications other than study drug and metformin " +
      "are prohibited except as rescue therapy.",
    explanation: "Section 6.3 lists what is allowed and what is prohibited.",
  },
  {
    item: "R-09",
    requirement: "Safety event definitions, incl. hypoglycaemia",
    reference: "ADA Standards of Care, Section 6; ICH E6(R3)",
    status: "present",
    flag: "contradiction",
    section: "8",
    page: 46,
    snippet:
      "Hypoglycaemia is defined as plasma glucose below 3.9 mmol/L " +
      "(70 mg/dL), graded as Level 1, 2 or 3.",
    explanation:
      "Defined in line with ADA levels, but the consent form (p. 5) uses " +
      "4.0 mmol/L.",
  },
  {
    item: "R-10",
    requirement: "Data monitoring committee and stopping rules",
    reference: "ICH E6(R2) 5.5.2; SPIRIT 2013 items 21a-21b",
    status: "missing",
    flag: "",
    section: "10",
    page: 60,
    snippet: NOT_FOUND,
    explanation:
      "Only ongoing review by the sponsor's medical monitor; no DMC, " +
      "interim review or stopping rule.",
  },
  {
    item: "R-11",
    requirement: "Sample size justification",
    reference: "ICH E9, 3.5; SPIRIT 2013 item 14",
    status: "weak",
    flag: "",
    section: "9",
    page: 52,
    snippet:
      "Assuming a treatment difference of 0.5%, 1,200 participants " +
      "provide 90% power.",
    explanation:
      "Effect size and power are given, but no SD and no source for the " +
      "0.5% difference.",
  },
  {
    item: "R-12",
    requirement: "Statistical analysis of the primary endpoint",
    reference: "ICH E9; SPIRIT 2013 item 20a",
    status: "present",
    flag: "",
    section: "9",
    page: 54,
    snippet:
      "The primary endpoint is analysed by ANCOVA with baseline HbA1c " +
      "as a covariate.",
    explanation: "Model and covariates are specified.",
  },
  {
    item: "R-13",
    requirement: "Informed consent process",
    reference: "ICH E6(R3); SPIRIT 2013 item 26a",
    status: "present",
    flag: "",
    section: "10",
    page: 61,
    snippet:
      "Written informed consent is obtained before any study-specific " +
      "procedure.",
    explanation: "Process described and a consent form is provided.",
  },
  {
    item: "R-14",
    requirement: "Data management and record retention",
    reference: "ICH E6(R3); SPIRIT 2013 item 19",
    status: "present",
    flag: "",
    section: "10",
    page: 63,
    snippet:
      "Essential documents are retained for at least 25 years after the " +
      "end of the trial.",
    explanation: "Retention period and data capture system are named.",
  },
];

const SECTION_LABELS: Record<string, string> = {
  "1": "§1 Summary",
  "3": "§3 Objectives",
  "4": "§4 Design",
  "5": "§5 Population",
  "6": "§6 Intervention",
  "8": "§8 Assessments",
  "9": "§9 Statistics",
  "10": "§10 Oversight",
};

const STATUS_SERIES: { status: RubricStatus; name: string }[] = [
  { status: "present", name: "Present" },
  { status: "weak", name: "Weak" },
  { status: "missing", name: "Missing" },
];

function rubricSeriesBySection(): ChartSeries[] {
  return STATUS_SERIES.map(({ status, name }) => ({
    name,
    points: Object.entries(SECTION_LABELS).map(([section, label]) => ({
      label,
      value: RUBRIC.filter(
        (row) => row.section === section && row.status === status
      ).length,
    })),
  }));
}

const RESCUE_AFTER =
  "when fasting plasma glucose exceeds 13.3 mmol/L (240 mg/dL) on two " +
  "consecutive measurements after Week 12";

const ENDPOINT_AT_WEEK_26 = "at Week 26 (Visit 8, End of Treatment, +/- 3 days)";

const SAMPLE_SIZE_BEFORE =
  "Assuming a treatment difference of 0.5%, 1,200 participants provide " +
  "90% power.";

export const CHECK_STEP: StepData = {
  id: "check",
  title: "Completeness & Consistency",
  summary:
    "Protocol checked against a 14-item rubric built from ICH and SPIRIT " +
    "guidance, and against the consent form for contradictions.",
  headline: {
    label: "items missing",
    value: "2",
    tone: "risk",
    numeric_value: 2,
    unit: "items",
  },
  metrics: [
    {
      metric_id: "m-chk-present",
      label: "Present",
      value: "9",
      tone: "good",
      numeric_value: 9,
      unit: "items",
      description: "Rubric items fully addressed.",
    },
    {
      metric_id: "m-chk-weak",
      label: "Weak",
      value: "3",
      tone: "warn",
      numeric_value: 3,
      unit: "items",
      description: "Mentioned, but not specific enough to act on.",
    },
    {
      metric_id: "m-chk-missing",
      label: "Missing",
      value: "2",
      tone: "risk",
      numeric_value: 2,
      unit: "items",
      description: "Not found anywhere in the 86 pages.",
    },
    {
      metric_id: "m-chk-contradictions",
      label: "Contradictions",
      value: "2",
      tone: "warn",
      numeric_value: 2,
      unit: "pairs",
      description:
        "Statements that disagree within the protocol or with the " +
        "consent form.",
    },
  ],
  status: "completed",
  agent: `${COMPLETENESS} + ${CONSISTENCY}`,
  ...stepTiming("check"),
  warnings: [
    {
      code: "CONSENT_VERSION_MISMATCH",
      message:
        "The consent form was written for protocol v0.2; its statements " +
        "were compared with v0.3 anyway.",
      severity: "warning",
    },
    {
      code: "SCANNED_PAGES_SKIPPED",
      message:
        "Pages 71-72 (scanned appendix) were not checked against the " +
        "rubric; no rubric item points there.",
      severity: "info",
    },
  ],
  data_sources: [
    DATA_SOURCES.protocol,
    DATA_SOURCES.consent,
    DATA_SOURCES.rubric,
    DATA_SOURCES.ichEfficacy,
    DATA_SOURCES.spirit,
    DATA_SOURCES.ada,
  ],
  tables: [
    {
      table_id: "tbl-chk-rubric",
      title: "Completeness rubric",
      description:
        "9 present, 3 weak, 2 missing; 2 present items are flagged as " +
        "contradictions.",
      columns: [
        { key: "item", label: "Item" },
        { key: "requirement", label: "Requirement" },
        { key: "reference", label: "Guideline" },
        { key: "status", label: "Status" },
        { key: "flag", label: "Flag" },
        { key: "section", label: "Section" },
        { key: "page", label: "Page" },
        { key: "snippet", label: "Protocol text" },
        { key: "explanation", label: "Why this status" },
      ],
      rows: RUBRIC.map((row) => ({ ...row })),
    },
    {
      table_id: "tbl-chk-contradictions",
      title: "Contradictions found",
      columns: [
        { key: "topic", label: "Topic" },
        { key: "first_source", label: "Says" },
        { key: "first_value", label: "Value" },
        { key: "second_source", label: "But" },
        { key: "second_value", label: "Value" },
      ],
      rows: [
        {
          topic: "HbA1c upper bound",
          first_source: "Protocol p. 24 (I-03)",
          first_value: "10.5%",
          second_source: "Protocol p. 25 (E-03)",
          second_value: "9.0%",
        },
        {
          topic: "Hypoglycaemia threshold",
          first_source: "Protocol p. 46 (8.4)",
          first_value: "3.9 mmol/L (70 mg/dL)",
          second_source: "Consent p. 5",
          second_value: "4.0 mmol/L (72 mg/dL)",
        },
      ],
    },
  ],
  charts: [
    {
      chart_id: "ch-chk-rubric",
      kind: "stacked_bar",
      title: "Rubric status by protocol section",
      description:
        "Both missing items sit in Sections 6 (rescue) and 10 " +
        "(oversight).",
      x_label: "ICH M11 section",
      y_label: "Rubric items",
      unit: "items",
      series: rubricSeriesBySection(),
    },
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
      category: "Completeness",
      confidence: 0.91,
      location: {
        section_heading: "6.4",
        section_title: "Rescue Therapy",
        start_page: 38,
        end_page: 38,
        criterion_id: "R-07",
      },
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
          section_title: "6.4 Rescue Therapy",
          context:
            "Rescue therapy may be initiated at the investigator's " +
            "discretion after Week 12. Participants who receive rescue " +
            "therapy will remain in the trial and continue study drug.",
          confidence: 0.97,
        },
        {
          evidence_id: "e-chk-05",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 36,
          quote:
            "Glucose-lowering medications other than study drug and " +
            "metformin are prohibited except as rescue therapy.",
          is_verified: true,
          section_title: "6.3 Concomitant Therapy",
          context:
            "Participants must keep their metformin dose unchanged. " +
            "Glucose-lowering medications other than study drug and " +
            "metformin are prohibited except as rescue therapy.",
          confidence: 0.96,
        },
        {
          evidence_id: "e-chk-06",
          source: "guideline",
          document: REFERENCES.spiritConcomitant.label,
          page: null,
          quote: REFERENCES.spiritConcomitant.quote,
          is_verified: true,
          url: REFERENCES.spiritConcomitant.url,
          confidence: 0.9,
        },
      ],
      trace: timedTrace("check", "d-chk-01", 2_300, [
        {
          agent: COMPLETENESS,
          kind: "rule",
          text: "Rubric item R-07 requires explicit rescue thresholds.",
          evidence_ids: ["e-chk-06"],
          duration_ms: 420,
        },
        {
          agent: COMPLETENESS,
          kind: "retrieve",
          text: "Found rescue mentioned in 6.3 (p. 36) and 6.4 (p. 38).",
          evidence_ids: ["e-chk-01", "e-chk-05"],
          duration_ms: 1_960,
        },
        {
          agent: COMPLETENESS,
          kind: "compare",
          text:
            "Searched all 86 pages for a glucose or HbA1c value tied to " +
            "rescue: 0 matches.",
          evidence_ids: ["e-chk-01"],
          duration_ms: 3_870,
        },
        {
          agent: COMPLETENESS,
          kind: "conclude",
          text: "No threshold found anywhere in the document: missing.",
          evidence_ids: ["e-chk-01"],
          duration_ms: 160,
        },
      ]),
      proposed_change: {
        path: "6.4 Rescue therapy",
        before: "at the investigator's discretion",
        after: RESCUE_AFTER,
        change_type: "modify",
        section_title: "6.4 Rescue Therapy",
        page: 38,
        rationale:
          "An objective, repeat-confirmed trigger makes rescue consistent " +
          "across sites and auditable.",
      },
      impact: [
        {
          label: "Rubric R-07",
          value: "Missing → Present",
          tone: "good",
          description: "If the recommended option is adopted.",
        },
        {
          label: "Missing items",
          value: "2 → 1",
          tone: "good",
          numeric_value: 1,
          unit: "items",
        },
      ],
      options: [
        {
          option_id: "o-chk-01-a",
          title: "Fasting glucose threshold, confirmed on repeat",
          rationale:
            "Fasting glucose responds within days, so a confirmed FPG " +
            "trigger catches loss of control between HbA1c draws.",
          is_recommended: true,
          proposed_change: {
            path: "6.4 Rescue therapy",
            before: "at the investigator's discretion",
            after: RESCUE_AFTER,
            change_type: "modify",
            section_title: "6.4 Rescue Therapy",
            page: 38,
          },
          impact: [{ label: "Rubric R-07", value: "Present", tone: "good" }],
          risks: [
            "The same threshold must appear in the SAP and estimand.",
            "Adds central-lab FPG checks at Weeks 16 and 20.",
          ],
        },
        {
          option_id: "o-chk-01-b",
          title: "HbA1c threshold at scheduled visits",
          rationale:
            "Uses the primary endpoint's own measure, with no extra " +
            "sampling.",
          proposed_change: {
            path: "6.4 Rescue therapy",
            before: "at the investigator's discretion",
            after: "when HbA1c is 8.5% or higher at or after Week 12",
            change_type: "modify",
            section_title: "6.4 Rescue Therapy",
            page: 38,
          },
          impact: [{ label: "Rubric R-07", value: "Present", tone: "good" }],
          risks: [
            "HbA1c lags 8-12 weeks, so rescue starts later.",
            "Only checked at Weeks 12 and 20.",
          ],
        },
        {
          option_id: "o-chk-01-c",
          title: "Keep investigator discretion, record the reason",
          rationale: "Smallest edit; keeps clinical flexibility.",
          impact: [{ label: "Rubric R-07", value: "Weak", tone: "warn" }],
          risks: [
            "Rescue rates may differ by site and by perceived arm.",
            "Reviewers usually expect an objective trigger.",
          ],
        },
      ],
      references: [
        REFERENCES.spiritConcomitant,
        REFERENCES.fdaDiabetes,
        REFERENCES.ichE9R1Estimand,
      ],
      decision_owner: "Medical Monitor",
      review_status: "pending",
      tags: ["rescue", "glycaemic-control", "rubric-missing"],
    },
    {
      decision_id: "d-chk-02",
      step_id: "check",
      severity: "warning",
      title: "Endpoint week conflicts with schedule",
      claim:
        "The primary endpoint is measured at Week 24, but the Schedule " +
        "of Activities has no Week 24 visit: HbA1c is drawn at Week 20 " +
        "and at the Week 26 End of Treatment visit.",
      category: "Consistency",
      confidence: 0.84,
      location: {
        section_heading: "3.1",
        section_title: "Primary Objective and Endpoint",
        start_page: 12,
        end_page: 12,
        criterion_id: "R-05",
      },
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
          section_title: "3.1 Primary Objective and Endpoint",
          context:
            "The primary objective is to show that each dose lowers " +
            "HbA1c more than placebo when added to metformin. Primary " +
            "endpoint: mean change in HbA1c from baseline at Week 24.",
          confidence: 0.99,
        },
        {
          evidence_id: "e-chk-07",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 31,
          quote:
            "V7: Week 20 (+/- 3 days): HbA1c, FPG, vital signs, adverse " +
            "event review.",
          is_verified: true,
          section_title: "6.1 Schedule of Activities",
          context:
            "V7: Week 20 (+/- 3 days): HbA1c, FPG, vital signs, adverse " +
            "event review. End of Treatment visit: Week 26 (+/- 3 days)",
          confidence: 0.93,
        },
        {
          evidence_id: "e-chk-03",
          source: "consent",
          document: CONSENT_DOCUMENT,
          page: 3,
          quote: "You will attend study visits for about 26 weeks.",
          is_verified: true,
          section_title: "What will happen during the study",
          context:
            "You will attend study visits for about 26 weeks. Most " +
            "visits are every 4 weeks and last about one hour.",
          confidence: 0.95,
        },
      ],
      trace: timedTrace("check", "d-chk-02", 6_800, [
        {
          agent: CONSISTENCY,
          kind: "retrieve",
          text: "Read the primary endpoint time point (Week 24, p. 12).",
          evidence_ids: ["e-chk-02"],
          duration_ms: 380,
        },
        {
          agent: CONSISTENCY,
          kind: "compare",
          text:
            "Compared endpoint timing with the visit schedule: HbA1c " +
            "is drawn at Weeks 0, 12, 20 and 26, none within 3 days of " +
            "Week 24.",
          evidence_ids: ["e-chk-02", "e-chk-07"],
          duration_ms: 1_240,
        },
        {
          agent: CONSISTENCY,
          kind: "compare",
          text: "The consent form also describes about 26 weeks of visits.",
          evidence_ids: ["e-chk-03"],
          duration_ms: 610,
        },
        {
          agent: CONSISTENCY,
          kind: "conclude",
          text:
            "Week 24 endpoint is not tied to a scheduled visit: rubric " +
            "item R-05 is weak.",
          evidence_ids: ["e-chk-02"],
          duration_ms: 140,
        },
      ]),
      proposed_change: {
        path: "3.1 Primary endpoint",
        before: "at Week 24",
        after: ENDPOINT_AT_WEEK_26,
        change_type: "modify",
        section_title: "3.1 Primary Objective and Endpoint",
        page: 12,
        rationale:
          "Measuring at the existing End of Treatment visit needs no " +
          "extra visit and matches the consent form.",
      },
      derived_from: ["d-ing-02", "d-ing-03"],
      impact: [
        { label: "Extra visits", value: "0", tone: "good", numeric_value: 0 },
        { label: "Rubric R-05", value: "Weak → Present", tone: "good" },
      ],
      options: [
        {
          option_id: "o-chk-02-a",
          title: "Move the endpoint to Week 26",
          rationale:
            "Uses the End of Treatment visit (V8) that already draws " +
            "HbA1c.",
          is_recommended: true,
          proposed_change: {
            path: "3.1 Primary endpoint",
            before: "at Week 24",
            after: ENDPOINT_AT_WEEK_26,
            change_type: "modify",
            section_title: "3.1 Primary Objective and Endpoint",
            page: 12,
          },
          impact: [{ label: "Extra visits", value: "0", tone: "good" }],
          risks: [
            "Relies on the Week 26 reading flagged during ingestion.",
            "Key secondary endpoints should move to Week 26 too.",
          ],
        },
        {
          option_id: "o-chk-02-b",
          title: "Add a Week 24 visit",
          rationale: "Keeps the endpoint as written.",
          proposed_change: {
            path: "6.1 Schedule of Activities",
            before: "V7: Week 20 (+/- 3 days)",
            after:
              "V7: Week 20 (+/- 3 days); V8: Week 24 (+/- 3 days): HbA1c, " +
              "FPG",
            change_type: "add",
            section_title: "6.1 Schedule of Activities",
            page: 31,
          },
          impact: [
            {
              label: "Extra visits",
              value: "+1,200",
              tone: "warn",
              numeric_value: 1_200,
              description: "One per participant.",
            },
          ],
          risks: [
            "More cost and participant burden.",
            "Consent form must be updated.",
          ],
        },
      ],
      references: [REFERENCES.spiritOutcomes, REFERENCES.spiritSchedule],
      decision_owner: "Lead Biostatistician",
      review_status: "pending",
      tags: ["endpoints", "schedule-of-activities", "rubric-weak"],
    },
    {
      decision_id: "d-chk-03",
      step_id: "check",
      severity: "warning",
      title: "Sample size assumption is weak",
      claim:
        "The sample size cites a 0.5% HbA1c effect without a source " +
        "or variance estimate. With a typical SD of 1.1%, two doses " +
        "against placebo need about 143 per arm (429 in total) after " +
        "15% dropout, so 1,200 implies unstated assumptions.",
      category: "Completeness",
      confidence: 0.8,
      location: {
        section_heading: "9.2",
        section_title: "Sample Size Determination",
        start_page: 52,
        end_page: 53,
        criterion_id: "R-11",
      },
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
          section_title: "9.2 Sample Size Determination",
          context:
            "The sample size is based on the primary endpoint. Assuming " +
            "a treatment difference of 0.5%, 1,200 participants provide " +
            "90% power. A two-sided significance level of 5% is used.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-chk-08",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 53,
          quote: "An overall dropout rate of 15% is assumed.",
          is_verified: true,
          section_title: "9.2 Sample Size Determination",
          context:
            "An overall dropout rate of 15% is assumed. No interim " +
            "analysis for sample size re-estimation is planned.",
          confidence: 0.97,
        },
        {
          evidence_id: "e-chk-09",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 18,
          quote:
            "Participants will be randomised 1:1:1 to SGLT2 inhibitor " +
            "10 mg, 25 mg or placebo.",
          is_verified: true,
          section_title: "4.3 Randomisation and Blinding",
          context:
            "Participants will be randomised 1:1:1 to SGLT2 inhibitor " +
            "10 mg, 25 mg or placebo. Randomisation is stratified by " +
            "screening HbA1c (below or at least 8.0%).",
          confidence: 0.98,
        },
      ],
      trace: timedTrace("check", "d-chk-03", 12_500, [
        {
          agent: COMPLETENESS,
          kind: "rule",
          text:
            "Rubric item R-11 requires a sourced effect size and a " +
            "variance estimate.",
          evidence_ids: ["e-chk-04"],
          duration_ms: 350,
        },
        {
          agent: COMPLETENESS,
          kind: "retrieve",
          text: "Read the design (3 arms, 1:1:1) and the 15% dropout.",
          evidence_ids: ["e-chk-08", "e-chk-09"],
          duration_ms: 1_120,
        },
        {
          agent: COMPLETENESS,
          kind: "compare",
          text:
            "Recomputed with SD 1.1%, alpha 0.025 per dose comparison " +
            "and 90% power: 121 per arm, 143 after dropout, 429 total.",
          evidence_ids: ["e-chk-04", "e-chk-08", "e-chk-09"],
          duration_ms: 2_480,
          details: {
            sd_percent: 1.1,
            alpha_per_comparison: 0.025,
            power: 0.9,
            participants_per_arm: 121,
            participants_per_arm_after_dropout: 143,
            participants_total: 429,
          },
        },
        {
          agent: COMPLETENESS,
          kind: "conclude",
          text:
            "Effect size stated, but no citation or SD, and 1,200 is " +
            "about 2.8 times the recomputed need: weak.",
          evidence_ids: ["e-chk-04"],
          duration_ms: 210,
        },
      ]),
      proposed_change: {
        path: "9.2 Sample size determination",
        before: SAMPLE_SIZE_BEFORE,
        after:
          "Assuming a treatment difference of 0.5% and an SD of 1.1% " +
          "(source to be cited), alpha 0.025 per dose comparison and 15% " +
          "dropout, 429 participants provide 90% power; enrolment is set " +
          "at 1,200 to meet [state the driver, e.g. safety exposure].",
        change_type: "modify",
        section_title: "9.2 Sample Size Determination",
        page: 52,
        rationale:
          "Makes every assumption checkable and explains the gap between " +
          "429 and 1,200.",
      },
      impact: [
        {
          label: "Recomputed need",
          value: "429",
          numeric_value: 429,
          unit: "participants",
          benchmarks: [{ label: "Protocol", value: "1,200", numeric_value: 1_200 }],
        },
        { label: "Rubric R-11", value: "Weak → Present", tone: "good" },
      ],
      options: [
        {
          option_id: "o-chk-03-a",
          title: "State the SD, its source and the reason for 1,200",
          rationale:
            "Keeps the planned size if it is needed for something else, " +
            "such as safety exposure, but says so.",
          is_recommended: true,
          proposed_change: {
            path: "9.2 Sample size determination",
            before: SAMPLE_SIZE_BEFORE,
            after:
              "Assuming a treatment difference of 0.5% and an SD of 1.1% " +
              "(source to be cited), 429 participants provide 90% power; " +
              "enrolment is set at 1,200 to meet [stated driver].",
            change_type: "modify",
            section_title: "9.2 Sample Size Determination",
            page: 52,
          },
          impact: [{ label: "Participants", value: "1,200 (unchanged)" }],
          risks: ["The stated driver must hold up to review."],
        },
        {
          option_id: "o-chk-03-b",
          title: "Reduce enrolment to 429",
          rationale: "Matches the stated efficacy assumptions.",
          proposed_change: {
            path: "9.2 Sample size determination",
            before: SAMPLE_SIZE_BEFORE,
            after:
              "Assuming a treatment difference of 0.5% and an SD of 1.1%, " +
              "429 participants (143 per arm) provide 90% power.",
            change_type: "modify",
            section_title: "9.2 Sample Size Determination",
            page: 52,
          },
          impact: [
            {
              label: "Participants",
              value: "1,200 → 429 (-64%)",
              tone: "good",
              numeric_value: 429,
            },
          ],
          risks: [
            "Less safety exposure than regulators may expect.",
            "No margin if the true SD is larger than 1.1%.",
          ],
        },
      ],
      references: [REFERENCES.ichE9SampleSize, REFERENCES.spiritSampleSize],
      decision_owner: "Lead Biostatistician",
      review_status: "pending",
      tags: ["statistics", "sample-size", "rubric-weak"],
      tables: [
        {
          table_id: "tbl-chk-sample-size",
          title: "Sample size recomputation",
          description: "Two-sided test per dose, Bonferroni-split alpha.",
          columns: [
            { key: "assumption", label: "Assumption" },
            { key: "value", label: "Value" },
            { key: "source", label: "Source" },
          ],
          rows: [
            { assumption: "Treatment difference", value: "0.5%", source: "Protocol p. 52" },
            { assumption: "Standard deviation", value: "1.1%", source: "Assumed (not in protocol)" },
            { assumption: "Alpha per comparison", value: "0.025", source: "0.05 split over 2 doses" },
            { assumption: "Power", value: "90%", source: "Protocol p. 52" },
            { assumption: "Dropout", value: "15%", source: "Protocol p. 53" },
            { assumption: "Per arm, after dropout", value: "143", source: "Computed" },
            { assumption: "Total (3 arms)", value: "429", source: "Computed" },
          ],
        },
      ],
    },
    {
      decision_id: "d-chk-04",
      step_id: "check",
      severity: "critical",
      title: "No DSMB or stopping rules defined",
      claim:
        "The protocol relies on ongoing review by the sponsor's medical " +
        "monitor and defines no independent data monitoring committee, " +
        "interim safety review or stopping rule.",
      category: "Completeness",
      confidence: 0.88,
      location: {
        section_heading: "10.3",
        section_title: "Trial Oversight",
        start_page: 58,
        end_page: 64,
        criterion_id: "R-10",
      },
      evidence: [
        {
          evidence_id: "e-chk-11",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 60,
          quote:
            "Safety data will be reviewed by the sponsor's medical " +
            "monitor on an ongoing basis.",
          is_verified: true,
          section_title: "10.3 Trial Oversight",
          context:
            "The sponsor is responsible for overall trial oversight. " +
            "Safety data will be reviewed by the sponsor's medical " +
            "monitor on an ongoing basis. Serious adverse events are " +
            "reported as described in Section 8.6.",
          confidence: 0.97,
        },
        {
          evidence_id: "e-chk-12",
          source: "guideline",
          document: REFERENCES.spiritStopping.label,
          page: null,
          quote: REFERENCES.spiritStopping.quote,
          is_verified: true,
          url: REFERENCES.spiritStopping.url,
          confidence: 0.9,
        },
      ],
      trace: timedTrace("check", "d-chk-04", 19_400, [
        {
          agent: COMPLETENESS,
          kind: "rule",
          text:
            "Rubric item R-10 requires a monitoring committee (or a reason " +
            "for none) and stopping guidance.",
          evidence_ids: ["e-chk-12"],
          duration_ms: 330,
        },
        {
          agent: COMPLETENESS,
          kind: "retrieve",
          text: "Read Section 10.3 Trial Oversight (pp. 58-64).",
          evidence_ids: ["e-chk-11"],
          duration_ms: 1_450,
        },
        {
          agent: COMPLETENESS,
          kind: "compare",
          text:
            "Searched 86 pages for 'data monitoring committee', 'DSMB', " +
            "'DMC', 'interim' and 'stopping': 0 matches.",
          evidence_ids: ["e-chk-11"],
          duration_ms: 2_960,
        },
        {
          agent: COMPLETENESS,
          kind: "conclude",
          text: "No committee and no stopping rule: missing.",
          evidence_ids: ["e-chk-11", "e-chk-12"],
          duration_ms: 150,
        },
      ]),
      proposed_change: {
        path: "10.3 Trial oversight",
        before: "",
        after:
          "An independent Data Monitoring Committee (two clinicians and " +
          "one statistician, none employed by the sponsor) will review " +
          "unblinded safety data every 6 months under a written charter " +
          "and may recommend stopping or modifying a dose arm.",
        change_type: "add",
        section_title: "10.3 Trial Oversight",
        page: 60,
        rationale:
          "Two active doses, 1,200 participants and no interim review " +
          "leave no independent check on emerging harm.",
      },
      impact: [
        { label: "Rubric R-10", value: "Missing → Present", tone: "good" },
        {
          label: "Missing items",
          value: "2 → 1",
          tone: "good",
          numeric_value: 1,
          unit: "items",
        },
      ],
      options: [
        {
          option_id: "o-chk-04-a",
          title: "Add an independent DMC with a charter",
          rationale:
            "Standard for a blinded multi-dose Phase 3 trial of this size.",
          is_recommended: true,
          proposed_change: {
            path: "10.3 Trial oversight",
            before: "",
            after:
              "An independent Data Monitoring Committee will review " +
              "unblinded safety data every 6 months under a written " +
              "charter and may recommend stopping or modifying a dose arm.",
            change_type: "add",
            section_title: "10.3 Trial Oversight",
            page: 60,
          },
          impact: [{ label: "Rubric R-10", value: "Present", tone: "good" }],
          risks: ["Charter and committee set-up add 4-6 weeks before FPI."],
        },
        {
          option_id: "o-chk-04-b",
          title: "Explain why no DMC is needed",
          rationale:
            "SPIRIT accepts a stated reason instead of a committee, for " +
            "example for a low-risk, short trial.",
          proposed_change: {
            path: "10.3 Trial oversight",
            before: "",
            after:
              "No DMC is planned because [reason]; the medical monitor " +
              "reviews blinded safety data every 4 weeks against the " +
              "stopping criteria in Section 7.1.",
            change_type: "add",
            section_title: "10.3 Trial Oversight",
            page: 60,
          },
          impact: [{ label: "Rubric R-10", value: "Weak", tone: "warn" }],
          risks: [
            "Hard to justify with two active doses and 1,200 participants.",
            "Still needs stopping criteria to be written.",
          ],
        },
      ],
      references: [
        REFERENCES.ichE6R2Idmc,
        REFERENCES.ichE6R3,
        REFERENCES.spiritStopping,
      ],
      decision_owner: "Medical Monitor",
      review_status: "pending",
      tags: ["safety", "oversight", "rubric-missing"],
    },
    {
      decision_id: "d-chk-05",
      step_id: "check",
      severity: "warning",
      title: "Hypoglycaemia defined differently in consent",
      claim:
        "The protocol uses 3.9 mmol/L (70 mg/dL) with three severity " +
        "levels; the consent form says 4.0 mmol/L (72 mg/dL) and names no " +
        "levels, so participants may report events the protocol does not " +
        "count.",
      category: "Consistency",
      confidence: 0.9,
      location: {
        section_heading: "8.4",
        section_title: "Hypoglycaemia",
        start_page: 46,
        end_page: 46,
        criterion_id: "R-09",
      },
      evidence: [
        {
          evidence_id: "e-chk-13",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 46,
          quote:
            "Hypoglycaemia is defined as plasma glucose below 3.9 mmol/L " +
            "(70 mg/dL), graded as Level 1, 2 or 3.",
          is_verified: true,
          section_title: "8.4 Hypoglycaemia",
          context:
            "Participants record all glucose readings in the e-diary. " +
            "Hypoglycaemia is defined as plasma glucose below 3.9 mmol/L " +
            "(70 mg/dL), graded as Level 1, 2 or 3. Level 3 events are " +
            "reported as serious adverse events.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-chk-14",
          source: "consent",
          document: CONSENT_DOCUMENT,
          page: 5,
          quote: "Low blood sugar means a reading below 4.0 mmol/L (72 mg/dL).",
          is_verified: true,
          section_title: "Possible risks: low blood sugar",
          context:
            "The study medicine can lower your blood sugar. Low blood " +
            "sugar means a reading below 4.0 mmol/L (72 mg/dL). Tell the " +
            "study team if this happens.",
          confidence: 0.96,
        },
        {
          evidence_id: "e-chk-15",
          source: "guideline",
          document: REFERENCES.adaHypoglycaemia.label,
          page: null,
          quote: REFERENCES.adaHypoglycaemia.quote,
          is_verified: true,
          url: REFERENCES.adaHypoglycaemia.url,
          confidence: 0.9,
        },
      ],
      trace: timedTrace("check", "d-chk-05", 25_100, [
        {
          agent: CONSISTENCY,
          kind: "retrieve",
          text: "Read the hypoglycaemia definition in 8.4 (p. 46).",
          evidence_ids: ["e-chk-13"],
          duration_ms: 410,
        },
        {
          agent: CONSISTENCY,
          kind: "retrieve",
          text: "Read the matching passage in the consent form (p. 5).",
          evidence_ids: ["e-chk-14"],
          duration_ms: 520,
        },
        {
          agent: CONSISTENCY,
          kind: "compare",
          text:
            "Thresholds differ (3.9 vs 4.0 mmol/L) and the consent form " +
            "omits severity levels.",
          evidence_ids: ["e-chk-13", "e-chk-14"],
          duration_ms: 890,
        },
        {
          agent: CONSISTENCY,
          kind: "rule",
          text: "The protocol's 3.9 mmol/L matches the ADA Level 1 cut-off.",
          evidence_ids: ["e-chk-15"],
          duration_ms: 300,
        },
        {
          agent: CONSISTENCY,
          kind: "conclude",
          text:
            "Contradiction: align the consent form with the protocol, " +
            "not the reverse.",
          evidence_ids: ["e-chk-13", "e-chk-14"],
          duration_ms: 120,
        },
      ]),
      proposed_change: {
        path: "Consent form, Possible risks: low blood sugar",
        before: "below 4.0 mmol/L (72 mg/dL)",
        after:
          "below 3.9 mmol/L (70 mg/dL). A reading below 3.0 mmol/L " +
          "(54 mg/dL), or any episode where you need someone's help, is " +
          "serious: tell the study team straight away",
        change_type: "modify",
        section_title: "Possible risks: low blood sugar",
        page: 5,
        rationale:
          "Participants then report the same events the protocol counts, " +
          "in plain language.",
      },
      derived_from: ["d-ing-04"],
      impact: [
        { label: "Contradictions", value: "2 → 1", tone: "good", numeric_value: 1 },
      ],
      options: [
        {
          option_id: "o-chk-05-a",
          title: "Update the consent form to the protocol definition",
          rationale: "The protocol already follows the ADA levels.",
          is_recommended: true,
          proposed_change: {
            path: "Consent form, Possible risks: low blood sugar",
            before: "below 4.0 mmol/L (72 mg/dL)",
            after: "below 3.9 mmol/L (70 mg/dL), with serious levels explained",
            change_type: "modify",
            section_title: "Possible risks: low blood sugar",
            page: 5,
          },
          impact: [{ label: "Contradictions", value: "2 → 1", tone: "good" }],
          risks: ["Consent form revision needs ethics committee approval."],
        },
        {
          option_id: "o-chk-05-b",
          title: "Change the protocol to 4.0 mmol/L",
          rationale: "Avoids a consent form revision.",
          impact: [{ label: "Contradictions", value: "2 → 1" }],
          risks: [
            "Departs from ADA levels, so results are harder to compare.",
            "Inflates hypoglycaemia rates against peer trials.",
          ],
        },
      ],
      references: [REFERENCES.adaHypoglycaemia, REFERENCES.adaStandards],
      decision_owner: "Regulatory Lead",
      review_status: "pending",
      tags: ["safety", "consent", "contradiction"],
    },
    {
      decision_id: "d-chk-06",
      step_id: "check",
      severity: "warning",
      title: "Estimand not fully defined",
      claim:
        "Section 3.3 names the endpoint and comparison but not the " +
        "intercurrent events (rescue therapy, stopping study drug) or how " +
        "each is handled; Section 9.4 imputes missing values with last " +
        "observation carried forward instead.",
      category: "Completeness",
      confidence: 0.86,
      location: {
        section_heading: "3.3",
        section_title: "Estimands",
        start_page: 13,
        end_page: 13,
        criterion_id: "R-03",
      },
      evidence: [
        {
          evidence_id: "e-chk-16",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 13,
          quote:
            "The primary efficacy analysis will compare mean change in " +
            "HbA1c from baseline to Week 24 between each dose and placebo.",
          is_verified: true,
          section_title: "3.3 Estimands",
          context:
            "3.3 Estimands. The primary efficacy analysis will compare " +
            "mean change in HbA1c from baseline to Week 24 between each " +
            "dose and placebo. Further details are given in Section 9.",
          confidence: 0.97,
        },
        {
          evidence_id: "e-chk-17",
          source: "protocol",
          document: PROTOCOL_DOCUMENT,
          page: 54,
          quote:
            "Missing Week 24 HbA1c values will be imputed using the last " +
            "observation carried forward.",
          is_verified: true,
          section_title: "9.4 Primary Analysis",
          context:
            "The primary endpoint is analysed by ANCOVA with baseline " +
            "HbA1c as a covariate. Missing Week 24 HbA1c values will be " +
            "imputed using the last observation carried forward.",
          confidence: 0.97,
        },
        {
          evidence_id: "e-chk-18",
          source: "guideline",
          document: REFERENCES.ichE9R1Estimand.label,
          page: null,
          quote: REFERENCES.ichE9R1Estimand.quote,
          is_verified: true,
          url: REFERENCES.ichE9R1Estimand.url,
          confidence: 0.9,
        },
      ],
      trace: timedTrace("check", "d-chk-06", 30_200, [
        {
          agent: COMPLETENESS,
          kind: "rule",
          text:
            "Rubric item R-03 requires all five estimand attributes, " +
            "including intercurrent events and strategies.",
          evidence_ids: ["e-chk-18"],
          duration_ms: 380,
        },
        {
          agent: COMPLETENESS,
          kind: "retrieve",
          text: "Read 3.3 Estimands (p. 13) and 9.4 Primary Analysis (p. 54).",
          evidence_ids: ["e-chk-16", "e-chk-17"],
          duration_ms: 1_380,
        },
        {
          agent: COMPLETENESS,
          kind: "compare",
          text:
            "Population, variable, treatment and summary are present; " +
            "intercurrent events are not, and rescue is allowed after " +
            "Week 12.",
          evidence_ids: ["e-chk-16"],
          duration_ms: 1_720,
        },
        {
          agent: COMPLETENESS,
          kind: "conclude",
          text:
            "Estimand incomplete and LOCF handles missing data implicitly: " +
            "weak.",
          evidence_ids: ["e-chk-16", "e-chk-17"],
          duration_ms: 160,
        },
      ]),
      proposed_change: {
        path: "3.3 Estimands",
        before:
          "The primary efficacy analysis will compare mean change in " +
          "HbA1c from baseline to Week 24 between each dose and placebo.",
        after:
          "Primary estimand: in adults with T2D on metformin, the " +
          "difference between each dose and placebo in mean change in " +
          "HbA1c from baseline to the primary time point, regardless of " +
          "rescue therapy or stopping study drug (treatment policy).",
        change_type: "modify",
        section_title: "3.3 Estimands",
        page: 13,
        rationale:
          "States which effect is estimated and how rescue and " +
          "discontinuation count, replacing implicit LOCF.",
      },
      derived_from: ["d-ing-03", "d-chk-01"],
      impact: [
        { label: "Estimand attributes", value: "4/5", tone: "warn", numeric_value: 4 },
        { label: "Rubric R-03", value: "Weak → Present", tone: "good" },
      ],
      options: [
        {
          option_id: "o-chk-06-a",
          title: "Treatment-policy estimand",
          rationale:
            "Counts outcomes regardless of rescue or stopping, which is " +
            "what a prescriber would see in practice.",
          is_recommended: true,
          impact: [{ label: "Estimand attributes", value: "5/5", tone: "good" }],
          risks: ["Needs follow-up after discontinuation to limit missing data."],
        },
        {
          option_id: "o-chk-06-b",
          title: "Hypothetical estimand without rescue",
          rationale: "Isolates the drug effect as if no rescue were given.",
          proposed_change: {
            path: "3.3 Estimands",
            before:
              "The primary efficacy analysis will compare mean change in " +
              "HbA1c from baseline to Week 24 between each dose and placebo.",
            after:
              "Primary estimand: the difference in mean change in HbA1c " +
              "from baseline to the primary time point as if no rescue " +
              "therapy had been available (hypothetical strategy).",
            change_type: "modify",
            section_title: "3.3 Estimands",
            page: 13,
          },
          impact: [{ label: "Estimand attributes", value: "5/5", tone: "good" }],
          risks: ["Relies on modelling assumptions about post-rescue values."],
        },
      ],
      references: [REFERENCES.ichE9R1Estimand],
      decision_owner: "Lead Biostatistician",
      review_status: "pending",
      tags: ["statistics", "estimand", "rubric-weak"],
    },
    {
      decision_id: "d-chk-07",
      step_id: "check",
      severity: "warning",
      title: "HbA1c upper bound stated twice",
      claim:
        "Inclusion I-03 allows HbA1c up to 10.5%, but exclusion E-03 " +
        "removes anyone above 9.0%, so the effective window is 7.0-9.0% " +
        "and the 9.0-10.5% part of I-03 can never apply.",
      category: "Consistency",
      confidence: 0.95,
      location: {
        section_heading: "5",
        section_title: "Trial Population",
        start_page: 24,
        end_page: 25,
        criterion_id: "E-03",
      },
      evidence: [
        {
          evidence_id: "e-chk-19",
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
            "between 7.0% and 10.5% at screening.",
          confidence: 0.98,
        },
        {
          evidence_id: "e-chk-20",
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
      ],
      trace: timedTrace("check", "d-chk-07", 35_000, [
        {
          agent: CONSISTENCY,
          kind: "retrieve",
          text: "Collected every HbA1c threshold in Section 5.",
          evidence_ids: ["e-chk-19", "e-chk-20"],
          duration_ms: 460,
        },
        {
          agent: CONSISTENCY,
          kind: "compare",
          text: "Upper bound is 10.5% in I-03 and 9.0% in E-03.",
          evidence_ids: ["e-chk-19", "e-chk-20"],
          duration_ms: 330,
        },
        {
          agent: CONSISTENCY,
          kind: "conclude",
          text:
            "Contradiction: the stricter 9.0% wins in practice, so later " +
            "agents use a 7.0-9.0% window.",
          evidence_ids: ["e-chk-20"],
          duration_ms: 140,
        },
      ]),
      proposed_change: {
        path: "5.2 Exclusion criteria, E-03",
        before:
          "Participants with an HbA1c above 9.0% are excluded from " +
          "enrolment.",
        after: "",
        change_type: "remove",
        section_title: "5.2 Exclusion Criteria",
        page: 25,
        rationale:
          "One place to state the window; the value itself is compared " +
          "with peer trials in the next step.",
      },
      derived_from: ["d-ing-01"],
      impact: [
        { label: "Contradictions", value: "2 → 1", tone: "good", numeric_value: 1 },
        { label: "Effective HbA1c window", value: "7.0-9.0%", tone: "warn" },
      ],
      options: [
        {
          option_id: "o-chk-07-a",
          title: "Keep one bound, in I-03 only",
          rationale:
            "Deleting E-03 leaves a single window to maintain; adjust the " +
            "I-03 value if the peer comparison suggests it.",
          is_recommended: true,
          proposed_change: {
            path: "5.2 Exclusion criteria, E-03",
            before:
              "Participants with an HbA1c above 9.0% are excluded from " +
              "enrolment.",
            after: "",
            change_type: "remove",
            section_title: "5.2 Exclusion Criteria",
            page: 25,
          },
          impact: [
            { label: "Effective upper bound", value: "9.0% → 10.5%", tone: "good" },
          ],
          risks: ["Widens eligibility; check the effect on HbA1c variance."],
        },
        {
          option_id: "o-chk-07-b",
          title: "Make I-03 match E-03",
          rationale: "Keeps today's effective window unchanged.",
          proposed_change: {
            path: "5.1 Inclusion criteria, I-03",
            before: "between 7.0% and 10.5%",
            after: "between 7.0% and 9.0%",
            change_type: "modify",
            section_title: "5.1 Inclusion Criteria",
            page: 24,
          },
          impact: [{ label: "Effective upper bound", value: "9.0% (unchanged)" }],
          risks: ["Keeps a cut-off stricter than most peer trials."],
        },
      ],
      references: [REFERENCES.ichM11],
      decision_owner: "Protocol Author",
      review_status: "pending",
      tags: ["eligibility", "hba1c", "contradiction"],
    },
  ],
};
