export type ProtocolStatus = "uploaded" | "analyzing" | "ready";

export type PipelineStep = "completeness" | "comparison" | "cohort";

export type Severity = "info" | "warning" | "critical";

export type RecommendationStatus = "pending" | "accepted" | "rejected";

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
