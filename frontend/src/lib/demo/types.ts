import type { Severity } from "@/lib/api";

// Frontend-only shapes for the mocked demo. They are shaped like the
// Pydantic models the backend will need (Decision, TraceStep, ...), but
// nothing here touches backend/shared/messages.py.

export const STEP_IDS = ["ingest", "check", "peers", "cohort"] as const;
export type StepId = (typeof STEP_IDS)[number];

export const EVIDENCE_SOURCES = [
  "protocol",
  "consent",
  "aact",
  "mimic",
  "nhanes",
] as const;
export type EvidenceSource = (typeof EVIDENCE_SOURCES)[number];

export interface Evidence {
  evidence_id: string;
  source: EvidenceSource;
  document: string;
  page: number | null;
  quote: string;
  is_verified: boolean;
}

export const TRACE_KINDS = [
  "retrieve",
  "rule",
  "compare",
  "conclude",
] as const;
export type TraceKind = (typeof TRACE_KINDS)[number];

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
  proposed_change?: ProposedChange | null;
  // Decisions from earlier steps this one builds on (traceability chain).
  derived_from?: string[];
}

export const METRIC_TONES = ["neutral", "good", "warn", "risk"] as const;
export type MetricTone = (typeof METRIC_TONES)[number];

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

// Property keys of the backend models, compared against OpenAPI in
// contract.test.ts so a renamed field fails a test instead of the demo.
export const EVIDENCE_KEYS = [
  "evidence_id",
  "source",
  "document",
  "page",
  "quote",
  "is_verified",
] as const;

export const DECISION_KEYS = [
  "decision_id",
  "step_id",
  "severity",
  "title",
  "claim",
  "evidence",
  "trace",
  "proposed_change",
  "derived_from",
] as const;

export const STEP_DATA_KEYS = [
  "id",
  "title",
  "summary",
  "headline",
  "metrics",
  "decisions",
] as const;

export const UPLOAD_FILE_RESPONSE_KEYS = [
  "protocol_id",
  "title",
  "page_count",
  "step",
] as const;

export interface UploadFileResponse {
  protocol_id: string;
  title: string;
  page_count: number;
  step: StepData;
}
