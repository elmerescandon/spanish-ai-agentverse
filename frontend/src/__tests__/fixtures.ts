import type { ProtocolSummary, Recommendation } from "@/lib/api";
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
