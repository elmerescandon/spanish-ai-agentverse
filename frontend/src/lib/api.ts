import type {
  RecommendationStepId,
  StepData,
  UploadFileResponse,
} from "@/lib/demo/types";

export const PROTOCOL_STATUSES = ["uploaded", "analyzing", "ready"] as const;
export type ProtocolStatus = (typeof PROTOCOL_STATUSES)[number];

export const PIPELINE_STEPS = ["completeness", "comparison", "cohort"] as const;
export type PipelineStep = (typeof PIPELINE_STEPS)[number];

export const SEVERITIES = ["info", "warning", "critical"] as const;
export type Severity = (typeof SEVERITIES)[number];

export const RECOMMENDATION_STATUSES = [
  "pending",
  "accepted",
  "rejected",
] as const;
export type RecommendationStatus = (typeof RECOMMENDATION_STATUSES)[number];

export const PROTOCOL_SUMMARY_KEYS = [
  "protocol_id",
  "title",
  "status",
  "data",
] as const;

export const RECOMMENDATION_KEYS = [
  "recommendation_id",
  "protocol_id",
  "source_step",
  "severity",
  "title",
  "description",
  "status",
  "comment",
  "details",
] as const;

export const UPDATE_RECOMMENDATION_KEYS = ["status", "comment"] as const;

// Protocol review: accept one of Theo's offered values, then pull the
// protocol's fields and the changes accepted so far.
export const FIELD_CHANGE_REQUEST_KEYS = ["field", "value"] as const;

export const PROTOCOL_FIELD_KEYS = ["field", "value", "unit", "page"] as const;

export const FIELD_CHANGE_KEYS = [
  "change_id",
  "field",
  "old_value",
  "new_value",
  "decision_id",
  "option_id",
  "rationale",
  "changed_at",
] as const;

export const FIELD_CHANGE_RESPONSE_KEYS = ["field", "change"] as const;

export const PROTOCOL_FIELDS_RESPONSE_KEYS = [
  "protocol_id",
  "title",
  "page_count",
  "uploaded_at",
  "fields",
  "changes",
] as const;

export interface ProtocolSummary {
  protocol_id: string;
  title: string;
  status: ProtocolStatus;
  data: Record<string, unknown>;
}

export interface Recommendation {
  recommendation_id: string;
  protocol_id: string;
  source_step: PipelineStep;
  severity: Severity;
  title: string;
  description: string;
  status: RecommendationStatus;
  comment: string | null;
  details: Record<string, unknown>;
}

export interface HealthCheckResponse {
  status: string;
  [key: string]: unknown;
}

export interface UpdateRecommendationPayload {
  status: RecommendationStatus;
  comment?: string | null;
}

export interface FieldChangeRequest {
  field: string;
  value: number;
}

export interface ProtocolField {
  field: string;
  value: string;
  unit: string | null;
  page: number | null;
}

export interface FieldChange {
  change_id: number;
  field: string;
  old_value: string | null;
  new_value: string;
  decision_id: string;
  option_id: string;
  rationale: string;
  changed_at: string;
}

export interface FieldChangeResponse {
  field: ProtocolField;
  // null when the field already held the value (a retried request).
  change: FieldChange | null;
}

export interface ProtocolFieldsResponse {
  protocol_id: string;
  title: string;
  page_count: number;
  uploaded_at: string;
  fields: ProtocolField[];
  changes: FieldChange[];
}

export interface CreateProtocolPayload {
  title: string;
  data?: Record<string, unknown>;
}

export const PRESELECTED_PROTOCOL: ProtocolSummary = {
  protocol_id: "prot-t2d-001",
  title: "Phase III Evaluation of SGLT2 Inhibitor in High-Risk T2D Cohort",
  status: "ready",
  data: {
    indication: "Type 2 Diabetes Mellitus",
    phase: "Phase 3",
    target_enrollment: 1200,
    primary_endpoint: "Mean HbA1c reduction from baseline at Week 24",
  },
};

export async function checkHealth(): Promise<HealthCheckResponse> {
  const res = await fetch("/api/health");
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.statusText}`);
  }
  return res.json();
}

export async function getProtocols(): Promise<ProtocolSummary[]> {
  const res = await fetch("/api/protocols");
  if (!res.ok) {
    throw new Error(`Failed to fetch protocols: ${res.statusText}`);
  }
  const data = await res.json();
  if (Array.isArray(data)) return data;
  if (data && Array.isArray((data as { protocols?: ProtocolSummary[] }).protocols)) {
    return (data as { protocols: ProtocolSummary[] }).protocols;
  }
  return [];
}

export async function getProtocol(id: string): Promise<ProtocolSummary> {
  const res = await fetch(`/api/protocols/${id}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch protocol ${id}: ${res.statusText}`);
  }
  return res.json();
}

export async function createProtocol(
  payload: CreateProtocolPayload
): Promise<ProtocolSummary> {
  const res = await fetch("/api/protocols", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title: payload.title,
      data: payload.data ?? {},
    }),
  });
  if (!res.ok) {
    throw new Error(`Failed to create protocol: ${res.statusText}`);
  }
  return res.json();
}

export async function getRecommendations(
  protocolId: string
): Promise<Recommendation[]> {
  const res = await fetch(`/api/protocols/${protocolId}/recommendations`);
  if (!res.ok) {
    throw new Error(`Failed to fetch recommendations: ${res.statusText}`);
  }
  const data = await res.json();
  if (Array.isArray(data)) return data;
  if (
    data &&
    Array.isArray((data as { recommendations?: Recommendation[] }).recommendations)
  ) {
    return (data as { recommendations: Recommendation[] }).recommendations;
  }
  return [];
}

export async function updateRecommendation(
  protocolId: string,
  recommendationId: string,
  update: UpdateRecommendationPayload
): Promise<Recommendation> {
  const res = await fetch(
    `/api/protocols/${protocolId}/recommendations/${recommendationId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(update),
    }
  );
  if (!res.ok) {
    throw new Error(`Failed to update recommendation: ${res.statusText}`);
  }
  return res.json();
}

// Backend errors are FastAPI `{detail}` bodies: a string, or a list of
// validation errors for 422s.
async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail !== undefined) return JSON.stringify(body.detail);
  } catch {
    // Body was not JSON; fall back to the status text.
  }
  return res.statusText || `HTTP ${res.status}`;
}

export async function uploadProtocolFile(
  file: File
): Promise<UploadFileResponse> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch("/api/upload-file", { method: "POST", body });
  if (!res.ok) {
    throw new Error(`Failed to upload protocol: ${await readErrorDetail(res)}`);
  }
  return res.json();
}

async function postRecommendation(
  path: string,
  protocolId: string
): Promise<StepData> {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ protocol_id: protocolId }),
  });
  if (!res.ok) {
    throw new Error(
      `Failed to fetch recommendation: ${await readErrorDetail(res)}`
    );
  }
  return res.json();
}

export function fetchChecklistRecommendation(
  protocolId: string
): Promise<StepData> {
  return postRecommendation("/api/checklist-recommendation", protocolId);
}

export function fetchProtocolRecommendation(
  protocolId: string
): Promise<StepData> {
  return postRecommendation("/api/protocol-recommendation", protocolId);
}

export function fetchCohortRecommendation(
  protocolId: string
): Promise<StepData> {
  return postRecommendation("/api/cohort-recommendation", protocolId);
}

export type RecommendationFetcher = (protocolId: string) => Promise<StepData>;

// The steps that follow ingest, each backed by its own agent endpoint.
export const RECOMMENDATION_ENDPOINTS: Record<
  RecommendationStepId,
  RecommendationFetcher
> = {
  check: fetchChecklistRecommendation,
  peers: fetchProtocolRecommendation,
  cohort: fetchCohortRecommendation,
};

// Only a value the PEERS step offered for the field is accepted; anything
// else comes back as a 422 whose detail says what is allowed.
export async function acceptFieldChange(
  protocolId: string,
  change: FieldChangeRequest
): Promise<FieldChangeResponse> {
  const res = await fetch(`/api/protocols/${protocolId}/changes`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(change),
  });
  if (!res.ok) {
    throw new Error(`Failed to accept change: ${await readErrorDetail(res)}`);
  }
  return res.json();
}

export async function getProtocolFields(
  protocolId: string
): Promise<ProtocolFieldsResponse> {
  const res = await fetch(`/api/protocols/${protocolId}/fields`);
  if (!res.ok) {
    throw new Error(
      `Failed to fetch protocol fields: ${await readErrorDetail(res)}`
    );
  }
  return res.json();
}
