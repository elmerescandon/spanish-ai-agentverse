import type {
  StepData,
  StepId,
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
  Exclude<StepId, "ingest">,
  RecommendationFetcher
> = {
  check: fetchChecklistRecommendation,
  peers: fetchProtocolRecommendation,
  cohort: fetchCohortRecommendation,
};
