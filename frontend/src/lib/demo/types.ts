import type { Severity } from "@/lib/api";

// Frontend-only shapes for the mocked demo. They are shaped like the
// Pydantic models the backend will need (Decision, TraceStep, ...), but
// nothing here touches backend/shared/messages.py.

export const STEP_IDS = ["ingest", "check", "peers", "cohort"] as const;
export type StepId = (typeof STEP_IDS)[number];
// Steps after ingest, each backed by its own recommendation endpoint.
export type RecommendationStepId = Exclude<StepId, "ingest">;

export const EVIDENCE_SOURCES = [
  "protocol",
  "consent",
  "aact",
  "mimic",
  "nhanes",
  "guideline",
  "literature",
  "other",
] as const;
export type EvidenceSource = (typeof EVIDENCE_SOURCES)[number];

export const STEP_STATUSES = ["completed", "partial", "failed"] as const;
export type StepStatus = (typeof STEP_STATUSES)[number];

export const CHANGE_TYPES = ["add", "modify", "remove"] as const;
export type ChangeType = (typeof CHANGE_TYPES)[number];

export const CHART_KINDS = [
  "bar",
  "stacked_bar",
  "waterfall",
  "line",
  "histogram",
  "comparison",
] as const;
export type ChartKind = (typeof CHART_KINDS)[number];

export const REVIEW_STATUSES = ["pending", "accepted", "rejected"] as const;
export type ReviewStatus = (typeof REVIEW_STATUSES)[number];

// Agent-specific data with no typed field yet (backend `details`).
export type DetailMap = Record<string, unknown>;

// The backend always sends every field below (empty when unknown). The
// wide optional fields are marked optional here so hand-written mocks
// can omit them; components should treat a missing one as empty.

export interface Evidence {
  evidence_id: string;
  source: EvidenceSource;
  document: string;
  page: number | null;
  quote: string;
  is_verified: boolean;
  section_title?: string | null;
  // Surrounding text so a reviewer can read the quote in context.
  context?: string | null;
  url?: string | null;
  confidence?: number | null;
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
  trace_id?: string | null;
  timestamp?: string | null;
  duration_ms?: number | null;
  details?: DetailMap;
}

export interface ProposedChange {
  path: string;
  before: string;
  after: string;
  change_type?: ChangeType;
  section_title?: string | null;
  page?: number | null;
  rationale?: string | null;
}

export const METRIC_TONES = ["neutral", "good", "warn", "risk"] as const;
export type MetricTone = (typeof METRIC_TONES)[number];

export interface MetricBenchmark {
  label: string;
  value: string;
  numeric_value?: number | null;
}

export interface Metric {
  label: string;
  value: string;
  tone?: MetricTone;
  metric_id?: string | null;
  numeric_value?: number | null;
  unit?: string | null;
  description?: string | null;
  benchmarks?: MetricBenchmark[];
}

export interface ChartPoint {
  label: string;
  value: number;
  lower?: number | null;
  upper?: number | null;
  annotation?: string | null;
}

export interface ChartSeries {
  name: string;
  points: ChartPoint[];
}

export interface Chart {
  chart_id: string;
  kind: ChartKind;
  title: string;
  description?: string | null;
  x_label?: string | null;
  y_label?: string | null;
  unit?: string | null;
  series: ChartSeries[];
}

export interface TableColumn {
  key: string;
  label: string;
  unit?: string | null;
}

export interface DataTable {
  table_id: string;
  title: string;
  description?: string | null;
  columns: TableColumn[];
  rows: DetailMap[];
}

export interface DataSource {
  source: EvidenceSource;
  name: string;
  description?: string | null;
  url?: string | null;
  version?: string | null;
  record_count?: number | null;
}

export interface StepWarning {
  code: string;
  message: string;
  severity: Severity;
}

export interface ProtocolLocation {
  section_heading?: string | null;
  section_title?: string | null;
  start_page?: number | null;
  end_page?: number | null;
  criterion_id?: string | null;
}

export interface GuidelineReference {
  label: string;
  url?: string | null;
  quote?: string | null;
}

export interface DecisionOption {
  option_id: string;
  title: string;
  rationale: string;
  is_recommended?: boolean;
  proposed_change?: ProposedChange | null;
  // Projected effect of picking this option (e.g. eligible % after).
  impact?: Metric[];
  risks?: string[];
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
  category?: string | null;
  confidence?: number | null;
  location?: ProtocolLocation | null;
  impact?: Metric[];
  options?: DecisionOption[];
  references?: GuidelineReference[];
  decision_owner?: string | null;
  review_status?: ReviewStatus;
  reviewer_comment?: string | null;
  tags?: string[];
  tables?: DataTable[];
  charts?: Chart[];
  details?: DetailMap;
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
  status?: StepStatus;
  agent?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  warnings?: StepWarning[];
  data_sources?: DataSource[];
  tables?: DataTable[];
  charts?: Chart[];
  details?: DetailMap;
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
  "section_title",
  "context",
  "url",
  "confidence",
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
  "category",
  "confidence",
  "location",
  "impact",
  "options",
  "references",
  "decision_owner",
  "review_status",
  "reviewer_comment",
  "tags",
  "tables",
  "charts",
  "details",
] as const;

export const STEP_DATA_KEYS = [
  "id",
  "title",
  "summary",
  "headline",
  "metrics",
  "decisions",
  "status",
  "agent",
  "started_at",
  "completed_at",
  "duration_ms",
  "warnings",
  "data_sources",
  "tables",
  "charts",
  "details",
] as const;

export const UPLOAD_FILE_RESPONSE_KEYS = [
  "protocol_id",
  "title",
  "page_count",
  "step",
  "filename",
  "file_size_bytes",
] as const;

export interface UploadFileResponse {
  protocol_id: string;
  title: string;
  page_count: number;
  step: StepData;
  filename?: string | null;
  file_size_bytes?: number | null;
}
