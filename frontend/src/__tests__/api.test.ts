import { beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import {
  checkHealth,
  createProtocol,
  fetchChecklistRecommendation,
  fetchCohortRecommendation,
  fetchProtocolRecommendation,
  RECOMMENDATION_ENDPOINTS,
  uploadProtocolFile,
  getProtocols,
  getRecommendations,
  updateRecommendation,
} from "@/lib/api";
import { MOCK_PROTOCOL, MOCK_RECOMMENDATIONS, MOCK_STEP } from "./fixtures";

describe("Frontend API client", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("fetches health check status from /api/health", async () => {
    const fetchSpy = spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok" }),
    } as unknown as Response);

    const res = await checkHealth();
    expect(res.status).toBe("ok");
    expect(fetchSpy).toHaveBeenCalledWith("/api/health");
  });

  it("fetches protocols and recommendations for a protocol", async () => {
    spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ protocols: [MOCK_PROTOCOL] }),
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ recommendations: MOCK_RECOMMENDATIONS }),
      } as unknown as Response);

    const protocols = await getProtocols();
    expect(protocols).toHaveLength(1);
    expect(protocols[0].protocol_id).toBe(MOCK_PROTOCOL.protocol_id);

    const recommendations = await getRecommendations(MOCK_PROTOCOL.protocol_id);
    expect(recommendations).toHaveLength(1);
    expect(recommendations[0].recommendation_id).toBe(
      MOCK_RECOMMENDATIONS[0].recommendation_id
    );
  });

  it("sends PATCH request when updating a recommendation status", async () => {
    const updatedRec = {
      ...MOCK_RECOMMENDATIONS[0],
      status: "accepted" as const,
    };

    const fetchSpy = spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => updatedRec,
    } as unknown as Response);

    const result = await updateRecommendation(
      MOCK_PROTOCOL.protocol_id,
      MOCK_RECOMMENDATIONS[0].recommendation_id,
      { status: "accepted" }
    );

    expect(result.status).toBe("accepted");
    expect(fetchSpy).toHaveBeenCalledWith(
      `/api/protocols/${MOCK_PROTOCOL.protocol_id}/recommendations/${MOCK_RECOMMENDATIONS[0].recommendation_id}`,
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ status: "accepted" }),
      })
    );
  });

  it("sends POST request to create a new protocol", async () => {
    const newProtocol = {
      protocol_id: "proto-new-123",
      title: "New Diabetes Phase 3 Trial",
      status: "uploaded" as const,
      data: { phase: "Phase 3" },
    };

    const fetchSpy = spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => newProtocol,
    } as unknown as Response);

    const result = await createProtocol({
      title: "New Diabetes Phase 3 Trial",
      data: { phase: "Phase 3" },
    });

    expect(result.protocol_id).toBe("proto-new-123");
    expect(result.title).toBe("New Diabetes Phase 3 Trial");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/protocols",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: "New Diabetes Phase 3 Trial",
          data: { phase: "Phase 3" },
        }),
      })
    );
  });

  it("uploads the protocol PDF as multipart form data under `file`", async () => {
    const upload = {
      protocol_id: "p-1",
      title: "Draft",
      page_count: 3,
      step: MOCK_STEP,
    };
    const fetchSpy = spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => upload,
    } as unknown as Response);
    const file = new File(["%PDF"], "draft.pdf", { type: "application/pdf" });

    const result = await uploadProtocolFile(file);

    expect(result).toEqual(upload);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/upload-file");
    expect(init.method).toBe("POST");
    const sent = (init.body as FormData).get("file") as File;
    expect(sent.name).toBe("draft.pdf");
    expect(sent.type).toBe("application/pdf");
  });

  it("surfaces the backend detail when an upload is rejected", async () => {
    spyOn(globalThis, "fetch").mockResolvedValueOnce({
      ok: false,
      status: 415,
      statusText: "Unsupported Media Type",
      json: async () => ({ detail: "Only PDF files are supported" }),
    } as unknown as Response);

    await expect(
      uploadProtocolFile(new File(["x"], "a.txt"))
    ).rejects.toThrow("Only PDF files are supported");
  });

  it("posts the protocol id to each recommendation endpoint", async () => {
    const cases = [
      [fetchChecklistRecommendation, "/api/checklist-recommendation"],
      [fetchProtocolRecommendation, "/api/protocol-recommendation"],
      [fetchCohortRecommendation, "/api/cohort-recommendation"],
    ] as const;

    for (const [fetchStep, path] of cases) {
      const fetchSpy = spyOn(globalThis, "fetch").mockResolvedValueOnce({
        ok: true,
        json: async () => MOCK_STEP,
      } as unknown as Response);

      expect(await fetchStep("p-1")).toEqual(MOCK_STEP);
      expect(fetchSpy).toHaveBeenCalledWith(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ protocol_id: "p-1" }),
      });
      fetchSpy.mockRestore();
    }
  });

  it("maps every post-ingest step to its fetcher", () => {
    expect(RECOMMENDATION_ENDPOINTS).toEqual({
      check: fetchChecklistRecommendation,
      peers: fetchProtocolRecommendation,
      cohort: fetchCohortRecommendation,
    });
  });

  it("surfaces a 404 detail and falls back to status text without JSON", async () => {
    spyOn(globalThis, "fetch")
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({ detail: "Unknown protocol p-9" }),
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        json: async () => {
          throw new SyntaxError("not json");
        },
      } as unknown as Response);

    await expect(fetchCohortRecommendation("p-9")).rejects.toThrow(
      "Unknown protocol p-9"
    );
    await expect(fetchCohortRecommendation("p-9")).rejects.toThrow(
      "Bad Gateway"
    );
  });
});
