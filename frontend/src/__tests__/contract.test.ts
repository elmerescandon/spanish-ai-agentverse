import { execFileSync } from "child_process";
import path from "path";
import { describe, expect, it } from "bun:test";
import { DEFAULT_PROTOCOL, DEFAULT_RECOMMENDATIONS } from "@/app/page";
import {
  FIELD_CHANGE_KEYS,
  FIELD_CHANGE_REQUEST_KEYS,
  FIELD_CHANGE_RESPONSE_KEYS,
  PIPELINE_STEPS,
  PROTOCOL_FIELD_KEYS,
  PROTOCOL_FIELDS_RESPONSE_KEYS,
  PROTOCOL_STATUSES,
  PROTOCOL_SUMMARY_KEYS,
  RECOMMENDATION_KEYS,
  RECOMMENDATION_STATUSES,
  SEVERITIES,
  UPDATE_RECOMMENDATION_KEYS,
} from "@/lib/api";
import {
  CHANGE_TYPES,
  CHART_KINDS,
  DECISION_KEYS,
  EVIDENCE_KEYS,
  EVIDENCE_SOURCES,
  METRIC_TONES,
  REVIEW_STATUSES,
  STEP_DATA_KEYS,
  STEP_IDS,
  STEP_STATUSES,
  TRACE_KINDS,
  UPLOAD_FILE_RESPONSE_KEYS,
} from "@/lib/demo/types";
import { MOCK_STEPS, MOCK_UPLOAD_RESPONSE } from "@/lib/demo/mock";
import {
  MOCK_PROTOCOL,
  MOCK_PROTOCOL_FIELDS,
  MOCK_RECOMMENDATIONS,
} from "./fixtures";

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

  it("aligns the /demo step enums with the frontend arrays", () => {
    expect(schemas.StepId?.enum).toEqual([...STEP_IDS]);
    expect(schemas.EvidenceSource?.enum).toEqual([...EVIDENCE_SOURCES]);
    expect(schemas.TraceKind?.enum).toEqual([...TRACE_KINDS]);
    expect(schemas.MetricTone?.enum).toEqual([...METRIC_TONES]);
    expect(schemas.StepStatus?.enum).toEqual([...STEP_STATUSES]);
    expect(schemas.ChangeType?.enum).toEqual([...CHANGE_TYPES]);
    expect(schemas.ChartKind?.enum).toEqual([...CHART_KINDS]);
    expect(schemas.RecommendationStatus?.enum).toEqual([...REVIEW_STATUSES]);
  });

  it("exposes the four /demo endpoints as POST routes", () => {
    for (const route of [
      "/api/upload-file",
      "/api/checklist-recommendation",
      "/api/protocol-recommendation",
      "/api/cohort-recommendation",
    ]) {
      expect(Object.keys(openApi.paths[route] ?? {})).toContain("post");
    }
  });

  it("aligns /demo model property keys with the frontend types", () => {
    const keysOf = (name: string) =>
      Object.keys(schemas[name]?.properties ?? {}).sort();

    expect(keysOf("StepData")).toEqual([...STEP_DATA_KEYS].sort());
    expect(keysOf("Decision")).toEqual([...DECISION_KEYS].sort());
    expect(keysOf("Evidence")).toEqual([...EVIDENCE_KEYS].sort());
    expect(keysOf("UploadFileResponse")).toEqual(
      [...UPLOAD_FILE_RESPONSE_KEYS].sort()
    );
  });

  it("keeps the sample upload response within the backend keys", () => {
    for (const key of Object.keys(MOCK_UPLOAD_RESPONSE)) {
      expect(UPLOAD_FILE_RESPONSE_KEYS as readonly string[]).toContain(key);
    }
    const required = schemas["UploadFileResponse"]?.required ?? [];
    for (const key of required) {
      expect(Object.keys(MOCK_UPLOAD_RESPONSE)).toContain(key);
    }
    expect(MOCK_UPLOAD_RESPONSE.step.id).toBe("ingest");
  });

  it("keeps the mock steps within the backend enums and keys", () => {
    for (const step of MOCK_STEPS) {
      // Mocks may omit optional fields but must not invent new ones.
      for (const key of Object.keys(step)) {
        expect(STEP_DATA_KEYS as readonly string[]).toContain(key);
      }
      expect(STEP_IDS).toContain(step.id);
      for (const decision of step.decisions) {
        expect(STEP_IDS).toContain(decision.step_id);
        for (const evidence of decision.evidence) {
          expect(EVIDENCE_SOURCES).toContain(evidence.source);
        }
        for (const entry of decision.trace) {
          expect(TRACE_KINDS).toContain(entry.kind);
        }
      }
    }
  });

  it("aligns the protocol review routes and models with the frontend", () => {
    const keysOf = (name: string) =>
      Object.keys(schemas[name]?.properties ?? {}).sort();

    expect(
      Object.keys(openApi.paths["/api/protocols/{protocol_id}/changes"] ?? {})
    ).toContain("post");
    expect(
      Object.keys(openApi.paths["/api/protocols/{protocol_id}/fields"] ?? {})
    ).toContain("get");
    expect(keysOf("FieldChangeRequest")).toEqual(
      [...FIELD_CHANGE_REQUEST_KEYS].sort()
    );
    expect(keysOf("ProtocolField")).toEqual([...PROTOCOL_FIELD_KEYS].sort());
    expect(keysOf("FieldChange")).toEqual([...FIELD_CHANGE_KEYS].sort());
    expect(keysOf("FieldChangeResponse")).toEqual(
      [...FIELD_CHANGE_RESPONSE_KEYS].sort()
    );
    expect(keysOf("ProtocolFieldsResponse")).toEqual(
      [...PROTOCOL_FIELDS_RESPONSE_KEYS].sort()
    );
  });

  it("keeps the protocol fields fixture within the backend keys", () => {
    const keysOf = (name: string) =>
      Object.keys(schemas[name]?.properties ?? {}).sort();

    expect(Object.keys(MOCK_PROTOCOL_FIELDS).sort()).toEqual(
      keysOf("ProtocolFieldsResponse")
    );
    for (const item of MOCK_PROTOCOL_FIELDS.fields) {
      expect(Object.keys(item).sort()).toEqual(keysOf("ProtocolField"));
    }
    for (const change of MOCK_PROTOCOL_FIELDS.changes) {
      expect(Object.keys(change).sort()).toEqual(keysOf("FieldChange"));
    }
  });
});
