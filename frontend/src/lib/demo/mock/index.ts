import type { RecommendationFetcher } from "@/lib/api";
import type {
  RecommendationStepId,
  StepData,
  StepId,
  UploadFileResponse,
} from "../types";
import { CHECK_STEP } from "./check";
import { COHORT_STEP } from "./cohort";
import { INGEST_STEP } from "./ingest";
import { PEERS_STEP } from "./peers";
import { MOCK_PROTOCOL_PAGE_COUNT, PROTOCOL_DOCUMENT } from "./shared";

// All demo content is illustrative mock data for the Phase III SGLT2 T2D
// protocol. IDs and evidence cross-reference across steps so the
// traceability chain can be walked end to end. Each step lives in its own
// module; this one wires them into endpoint-shaped mocks.

export { MOCK_PROTOCOL_PAGE_COUNT };

const MOCK_PROTOCOL_ID = "proto-sample";
const MOCK_FILE_SIZE_BYTES = 2_830_059;

// Fake agent latency per endpoint, staggered so the steps visibly settle
// one after another, as parallel agents of different speeds would.
const MOCK_LATENCY_MS: Record<RecommendationStepId, number> = {
  check: 700,
  peers: 1400,
  cohort: 2100,
};

export const MOCK_STEPS: StepData[] = [
  INGEST_STEP,
  CHECK_STEP,
  PEERS_STEP,
  COHORT_STEP,
];

function mockStep(id: StepId): StepData {
  const step = MOCK_STEPS.find((candidate) => candidate.id === id);
  if (!step) throw new Error(`expected a mock step '${id}', found none`);
  return step;
}

// What POST /api/upload-file returns for the sample protocol.
export const MOCK_UPLOAD_RESPONSE: UploadFileResponse = {
  protocol_id: MOCK_PROTOCOL_ID,
  title: PROTOCOL_DOCUMENT.replace(/\.pdf$/, ""),
  page_count: MOCK_PROTOCOL_PAGE_COUNT,
  step: mockStep("ingest"),
  filename: PROTOCOL_DOCUMENT,
  file_size_bytes: MOCK_FILE_SIZE_BYTES,
};

function mockFetcher(id: RecommendationStepId): RecommendationFetcher {
  return (protocolId) => {
    if (protocolId !== MOCK_PROTOCOL_ID) {
      return Promise.reject(
        new Error(`Uploaded protocol '${protocolId}' not found`)
      );
    }
    return new Promise((resolve) =>
      setTimeout(() => resolve(mockStep(id)), MOCK_LATENCY_MS[id])
    );
  };
}

// Stand-ins for the three recommendation endpoints: same signature, same
// StepData shape, same 404 for an unknown protocol id.
export const MOCK_RECOMMENDATION_FETCHERS: Record<
  RecommendationStepId,
  RecommendationFetcher
> = {
  check: mockFetcher("check"),
  peers: mockFetcher("peers"),
  cohort: mockFetcher("cohort"),
};
