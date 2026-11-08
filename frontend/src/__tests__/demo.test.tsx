import { beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DemoPage from "@/app/demo/page";
import * as api from "@/lib/api";

describe("DemoPage Step 0 Protocol Ingestion Experience", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("renders the /demo page with Step 0 ingestion and NO active protocol or recommendations", async () => {
    spyOn(api, "checkHealth").mockResolvedValue({ status: "ok" });

    render(<DemoPage />);

    // Step 0 Intake section is present with icon header
    expect(
      screen.getByRole("heading", {
        name: "Protocol Intake & Data Ingestion",
      })
    ).toBeInTheDocument();

    // Top header and Home redirect button were removed per design
    expect(
      screen.queryByText("Protocol Gap Agent — Interactive Demo")
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Step 0 Ingestion")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Home/i })
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Connected (FastAPI Proxy)")
    ).not.toBeInTheDocument();

    // Verify Active Protocol and Pipeline Recommendations are NOT shown
    expect(screen.queryByText("Active Protocol")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Pipeline Recommendations")
    ).not.toBeInTheDocument();
  });

  it("handles clicking 'Run Preselected Protocol' to trigger protocol ingestion", async () => {
    spyOn(api, "checkHealth").mockResolvedValue({ status: "ok" });

    const user = userEvent.setup();
    render(<DemoPage />);

    const runButton = screen.getByRole("button", {
      name: /Run Preselected Protocol/i,
    });
    expect(runButton).toBeInTheDocument();

    await user.click(runButton);

    // Displays the preselected file intake card
    expect(
      screen.getByText("Phase_3_SGLT2_High_Risk_T2D_Protocol.json")
    ).toBeInTheDocument();

    // Shows protocol title in the UI
    expect(
      screen.getAllByText(
        /Phase III Evaluation of SGLT2 Inhibitor in High-Risk T2D Cohort/i
      ).length
    ).toBeGreaterThanOrEqual(1);

    // Still does NOT render Active Protocol or Recommendations
    expect(screen.queryByText("Active Protocol")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Pipeline Recommendations")
    ).not.toBeInTheDocument();
  });

  it("handles JSON protocol file upload and displays ingested file status", async () => {
    spyOn(api, "checkHealth").mockResolvedValue({ status: "ok" });
    const uploadedSummary: api.ProtocolSummary = {
      protocol_id: "proto-upl-999",
      title: "Phase 2 Oncology Protocol Draft",
      status: "ready",
      data: {
        phase: "Phase 2",
        indication: "Advanced Melanoma",
        target_enrollment: 350,
        primary_endpoint: "Progression-Free Survival at 12 Months",
        source_file: "custom_oncology.json",
        file_size: "1.2 KB",
      },
    };

    const createSpy = spyOn(api, "createProtocol").mockResolvedValue(
      uploadedSummary
    );

    const user = userEvent.setup();
    render(<DemoPage />);

    const fileInput = screen.getByLabelText(/Upload protocol file/i);

    const jsonPayload = JSON.stringify({
      title: "Phase 2 Oncology Protocol Draft",
      data: {
        phase: "Phase 2",
        indication: "Advanced Melanoma",
      },
    });

    const file = new File([jsonPayload], "custom_oncology.json", {
      type: "application/json",
    });

    await user.upload(fileInput, file);

    await waitFor(
      () => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            title: "Phase 2 Oncology Protocol Draft",
          })
        );
      },
      { timeout: 3000 }
    );

    // Displays uploaded file badge and loaded toast
    await waitFor(
      () => {
        expect(
          screen.getAllByText("custom_oncology.json").length
        ).toBeGreaterThanOrEqual(1);
        expect(
          screen.getAllByText(/Phase 2 Oncology Protocol Draft/i).length
        ).toBeGreaterThanOrEqual(1);
      },
      { timeout: 3000 }
    );

    // Confirms sections remain hidden
    expect(screen.queryByText("Active Protocol")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Pipeline Recommendations")
    ).not.toBeInTheDocument();
  });

  it("handles PDF protocol file upload", async () => {
    spyOn(api, "checkHealth").mockResolvedValue({ status: "ok" });
    const pdfProtocolSummary: api.ProtocolSummary = {
      protocol_id: "proto-pdf-777",
      title: "Clinical Protocol Draft: Pediatric Diabetes Protocol",
      status: "ready",
      data: {
        source_file: "pediatric_diabetes_protocol.pdf",
        document_format: "PDF Clinical Protocol",
      },
    };

    const createSpy = spyOn(api, "createProtocol").mockResolvedValue(
      pdfProtocolSummary
    );

    const user = userEvent.setup();
    render(<DemoPage />);

    const fileInput = screen.getByLabelText(/Upload protocol file/i);
    const pdfFile = new File(
      ["dummy pdf bytes"],
      "pediatric_diabetes_protocol.pdf",
      {
        type: "application/pdf",
      }
    );

    await user.upload(fileInput, pdfFile);

    await waitFor(
      () => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            title: "Clinical Protocol Draft: Pediatric Diabetes Protocol",
          })
        );
      },
      { timeout: 3000 }
    );

    await waitFor(
      () => {
        expect(
          screen.getAllByText("pediatric_diabetes_protocol.pdf").length
        ).toBeGreaterThanOrEqual(1);
      },
      { timeout: 3000 }
    );

    expect(screen.queryByText("Active Protocol")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Pipeline Recommendations")
    ).not.toBeInTheDocument();
  });
});
