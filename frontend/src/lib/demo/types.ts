import type { Severity } from "@/lib/api";

// Frontend-only shapes for the mocked demo. They are shaped like the
// Pydantic models the backend will need (Decision, TraceStep, ...), but
// nothing here touches backend/shared/messages.py.

export const STEP_IDS = ["ingest", "check", "peers", "cohort"] as const;
export type StepId = (typeof STEP_IDS)[number];

export type EvidenceSource = "protocol" | "consent" | "aact" | "mimic";

export interface Evidence {
  evidence_id: string;
  source: EvidenceSource;
  document: string;
  page: number | null;
  quote: string;
  is_verified: boolean;
}

export type TraceKind = "retrieve" | "rule" | "compare" | "conclude";

export interface TraceEntry {
  agent: string;
  kind: TraceKind;
  text: string;
  evidence_ids: string[];
}

export interface ProposedChange {
  path: string;
  before: string;
  after: string;
}

export interface Decision {
  decision_id: string;
  step_id: StepId;
  severity: Severity;
  title: string;
  claim: string;
  evidence: Evidence[];
  trace: TraceEntry[];
  proposed_change?: ProposedChange;
  // Decisions from earlier steps this one builds on (traceability chain).
  derived_from?: string[];
}

export type MetricTone = "neutral" | "good" | "warn" | "risk";

export interface Metric {
  label: string;
  value: string;
  tone?: MetricTone;
}

export interface StepData {
  id: StepId;
  title: string;
  summary: string;
  // The single number shown on the zoomed-out pipeline node.
  headline: Metric;
  // Overview figures; kept to MAX_STEP_METRICS so a step stays scannable.
  metrics: Metric[];
  decisions: Decision[];
}

export type ReviewResolution = "open" | "accepted" | "rejected";

export interface ReviewComment {
  comment_id: string;
  author: string;
  body: string;
  created_at: string;
}

export interface ReviewThread {
  decision_id: string;
  resolution: ReviewResolution;
  comments: ReviewComment[];
}
