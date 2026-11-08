import { beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HomePage from "@/app/page";
import * as api from "@/lib/api";

describe("HomePage UI functionality", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("renders the active protocol summary and pipeline recommendations list", async () => {
    spyOn(api, "checkHealth").mockResolvedValue({ status: "ok" });
    spyOn(api, "getProtocols").mockResolvedValue([]);

    render(<HomePage />);

    expect(
      screen.getByText(
        "Phase III Evaluation of SGLT2 Inhibitor in High-Risk T2D Cohort"
      )
    ).toBeInTheDocument();
    expect(screen.getByText("ID: prot-t2d-001")).toBeInTheDocument();

    expect(
      screen.getByText("Missing eGFR Safety Monitoring Schedule")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Comparator Arm Dose Misalignment with Standard of Care")
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Opportunity to Broaden Inclusion Criteria for Older Adults"
      )
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Connected (FastAPI Proxy)")).toBeInTheDocument();
    });
  });

  it("filters recommendations by pipeline step (completeness, comparison, cohort)", async () => {
    spyOn(api, "checkHealth").mockResolvedValue({ status: "ok" });
    spyOn(api, "getProtocols").mockResolvedValue([]);

    const user = userEvent.setup();
    render(<HomePage />);

    // Filter by Completeness
    await user.click(screen.getByRole("button", { name: "Completeness" }));
    expect(
      screen.getByText("Missing eGFR Safety Monitoring Schedule")
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Comparator Arm Dose Misalignment with Standard of Care"
      )
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        "Opportunity to Broaden Inclusion Criteria for Older Adults"
      )
    ).not.toBeInTheDocument();

    // Filter by Comparison
    await user.click(screen.getByRole("button", { name: "Comparison" }));
    expect(
      screen.getByText("Comparator Arm Dose Misalignment with Standard of Care")
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Missing eGFR Safety Monitoring Schedule")
    ).not.toBeInTheDocument();

    // Filter by Cohort
    await user.click(screen.getByRole("button", { name: "Cohort" }));
    expect(
      screen.getByText(
        "Opportunity to Broaden Inclusion Criteria for Older Adults"
      )
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "Comparator Arm Dose Misalignment with Standard of Care"
      )
    ).not.toBeInTheDocument();

    // Reset to All Steps
    await user.click(screen.getByRole("button", { name: "All Steps" }));
    expect(
      screen.getByText("Missing eGFR Safety Monitoring Schedule")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Comparator Arm Dose Misalignment with Standard of Care")
    ).toBeInTheDocument();
  });

  it("accepts and rejects recommendations with optimistic state update and API PATCH call", async () => {
    spyOn(api, "checkHealth").mockResolvedValue({ status: "ok" });
    spyOn(api, "getProtocols").mockResolvedValue([]);
    const updateSpy = spyOn(api, "updateRecommendation").mockImplementation(
      async (protocolId, recId, payload) => ({
        recommendation_id: recId,
        protocol_id: protocolId,
        source_step: "completeness",
        severity: "warning",
        title: "Updated",
        description: "Updated",
        status: payload.status,
        comment: null,
        details: {},
      })
    );

    const user = userEvent.setup();
    render(<HomePage />);

    await waitFor(() => {
      expect(screen.getByText("Connected (FastAPI Proxy)")).toBeInTheDocument();
    });

    // Click Accept on the first recommendation (rec-001)
    const acceptButtons = screen.getAllByRole("button", { name: "Accept" });
    await user.click(acceptButtons[0]);

    expect(
      screen.getByRole("button", { name: "Accepted" })
    ).toBeInTheDocument();
    expect(updateSpy).toHaveBeenCalledWith("prot-t2d-001", "rec-001", {
      status: "accepted",
    });

    // Click Reject on the second recommendation (rec-002)
    const rejectButtons = screen.getAllByRole("button", { name: "Reject" });
    await user.click(rejectButtons[1]);

    expect(
      screen.getByRole("button", { name: "Rejected" })
    ).toBeInTheDocument();
    expect(updateSpy).toHaveBeenCalledWith("prot-t2d-001", "rec-002", {
      status: "rejected",
    });
  });
});
