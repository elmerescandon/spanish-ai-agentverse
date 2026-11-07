import { execFileSync } from "child_process";
import path from "path";
import { describe, expect, it } from "bun:test";
import { DEFAULT_PROTOCOL, DEFAULT_RECOMMENDATIONS } from "@/app/page";
import {
  PIPELINE_STEPS,
  PROTOCOL_STATUSES,
  PROTOCOL_SUMMARY_KEYS,
  RECOMMENDATION_KEYS,
  RECOMMENDATION_STATUSES,
  SEVERITIES,
  UPDATE_RECOMMENDATION_KEYS,
} from "@/lib/api";
import { MOCK_PROTOCOL, MOCK_RECOMMENDATIONS } from "./fixtures";

interface OpenApiSchemaProperty {
  type?: string;
  enum?: string[];
  const?: string;
}

interface OpenApiComponentSchema {
  enum?: string[];
  properties?: Record<string, OpenApiSchemaProperty>;
  required?: string[];
}

interface OpenApiDocument {
  paths: Record<string, Record<string, unknown>>;
  components: {
    schemas: Record<string, OpenApiComponentSchema>;
  };
}

function loadBackendOpenApiSchema(): OpenApiDocument {
  const repoRoot = path.resolve(import.meta.dirname, "../../..");
  const rawJson = execFileSync(
    "uv",
    [
      "run",
      "python",
      "-c",
      "import json; from backend.main import app; print(json.dumps(app.openapi()))",
    ],
    { cwd: repoRoot, encoding: "utf-8" }
  );
  return JSON.parse(rawJson) as OpenApiDocument;
}

describe("Frontend <-> Backend API Schema & Component Contract Alignment", () => {
  const openApi = loadBackendOpenApiSchema();
  const schemas = openApi.components.schemas;

  it("aligns all enum definitions between backend/api/schemas.py and frontend/src/lib/api.ts", () => {
    expect(schemas.ProtocolStatus?.enum).toEqual([...PROTOCOL_STATUSES]);
    expect(schemas.PipelineStep?.enum).toEqual([...PIPELINE_STEPS]);
    expect(schemas.Severity?.enum).toEqual([...SEVERITIES]);
    expect(schemas.RecommendationStatus?.enum).toEqual([
      ...RECOMMENDATION_STATUSES,
    ]);
  });

  it("aligns model property keys and routes between backend FastAPI and frontend API client", () => {
    expect(Object.keys(openApi.paths)).toEqual(
      expect.arrayContaining([
        "/api/health",
        "/api/protocols",
        "/api/protocols/{protocol_id}",
        "/api/protocols/{protocol_id}/recommendations",
        "/api/protocols/{protocol_id}/recommendations/{recommendation_id}",
      ])
    );

    const backendProtocolKeys = Object.keys(
      schemas.ProtocolSummary?.properties ?? {}
    ).sort();
    expect(backendProtocolKeys).toEqual([...PROTOCOL_SUMMARY_KEYS].sort());

    const backendRecommendationKeys = Object.keys(
      schemas.Recommendation?.properties ?? {}
    ).sort();
    expect(backendRecommendationKeys).toEqual([...RECOMMENDATION_KEYS].sort());

    const backendDecisionKeys = Object.keys(
      schemas.RecommendationDecisionRequest?.properties ?? {}
    ).sort();
    expect(backendDecisionKeys).toEqual([...UPDATE_RECOMMENDATION_KEYS].sort());
  });

  it("ensures UI component defaults and test fixtures conform strictly to backend schemas", () => {
    const backendProtocolKeys = Object.keys(
      schemas.ProtocolSummary?.properties ?? {}
    ).sort();
    const backendRecommendationKeys = Object.keys(
      schemas.Recommendation?.properties ?? {}
    ).sort();

    // Verify component default protocol and test mock protocol
    for (const proto of [DEFAULT_PROTOCOL, MOCK_PROTOCOL]) {
      expect(Object.keys(proto).sort()).toEqual(backendProtocolKeys);
      expect(schemas.ProtocolStatus?.enum).toContain(proto.status);
    }

    // Verify component default recommendations and test mock recommendations
    for (const rec of [...DEFAULT_RECOMMENDATIONS, ...MOCK_RECOMMENDATIONS]) {
      expect(Object.keys(rec).sort()).toEqual(backendRecommendationKeys);
      expect(schemas.PipelineStep?.enum).toContain(rec.source_step);
      expect(schemas.Severity?.enum).toContain(rec.severity);
      expect(schemas.RecommendationStatus?.enum).toContain(rec.status);
    }
  });
});
