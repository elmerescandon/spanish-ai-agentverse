import { beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import {
  checkHealth,
  getProtocols,
  getRecommendations,
  updateRecommendation,
} from "@/lib/api";
import { MOCK_PROTOCOL, MOCK_RECOMMENDATIONS } from "./fixtures";

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
});
