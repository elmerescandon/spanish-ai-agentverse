import type {
  ProtocolFieldsResponse,
  ProtocolSummary,
  Recommendation,
} from "@/lib/api";
import type { StepData } from "@/lib/demo/types";

export const MOCK_PROTOCOL: ProtocolSummary = {
  protocol_id: "prot-001",
  title: "Test Protocol",
  status: "ready",
  data: { phase: "Phase 2" },
};

export const MOCK_RECOMMENDATIONS: Recommendation[] = [
  {
    recommendation_id: "rec-001",
    protocol_id: "prot-001",
    source_step: "completeness",
    severity: "warning",
    title: "Add HbA1c schedule",
    description: "Specify baseline schedule.",
    status: "pending",
    comment: null,
    details: {},
  },
];

export function makeStep(
  id: StepData["id"],
  title: string
): StepData {
  return {
    id,
    title,
    summary: `${title} summary`,
    headline: { label: "items", value: "1", tone: "neutral" },
    metrics: [],
    decisions: [],
  };
}

export const MOCK_STEP: StepData = makeStep("check", "Completeness");

export const MOCK_SAVED_REVIEW: import("@/lib/api").SavedDecisionReview = {
  decision_id: "review-1",
  option_id: "target",
  status: "accepted",
  proposed_change: {
    path: "5.4 Recruitment",
    before: "No target",
    after: "Review enrolment against a 45% target.",
  },
};

export const MOCK_SAMPLE_REQUEST: import("@/lib/api").SampleProtocolRequest = {
  title: "SGLT2_T2D_Phase3_Protocol_v0.3",
  page_count: 86,
};

export const MOCK_STORED_PROTOCOL: import("@/lib/api").StoredProtocolResponse =
  { protocol_id: "proto-stored1", ...MOCK_SAMPLE_REQUEST };

export const MOCK_PROTOCOL_FIELDS: ProtocolFieldsResponse = {
  protocol_id: "proto-001",
  title: "Test Protocol",
  page_count: 98,
  uploaded_at: "2026-11-08T09:00:00Z",
  fields: [
    {
      field: "comparison.hba1c_upper_bound",
      value: "10.5",
      unit: "%",
      page: null,
    },
  ],
  changes: [
    {
      change_id: 1,
      field: "comparison.hba1c_upper_bound",
      old_value: "11",
      new_value: "10.5",
      decision_id: "comparison-hba1c_upper_bound",
      option_id: "comparison-hba1c_upper_bound-all",
      rationale: "10.5% is in line with 2 all peer trials.",
      changed_at: "2026-11-08T10:00:00Z",
    },
  ],
};
