import { beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProtocolIngestion from "@/components/ProtocolIngestion";
import * as api from "@/lib/api";

describe("ProtocolIngestion Component", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("renders icon header and action choices", () => {
    render(<ProtocolIngestion />);

    expect(
      screen.getByText("Protocol Intake & Data Ingestion")
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /run preselected protocol/i })
    ).toBeInTheDocument();
    expect(screen.getByText("Upload Protocol Document")).toBeInTheDocument();
  });

  it("loads preselected protocol immediately on button click", async () => {
    const handleLoaded = mock();
    const user = userEvent.setup();

    render(<ProtocolIngestion onProtocolLoaded={handleLoaded} />);

    const runBtn = screen.getByRole("button", {
      name: /run preselected protocol/i,
    });
    await user.click(runBtn);

    expect(handleLoaded).toHaveBeenCalledTimes(1);
    expect(handleLoaded).toHaveBeenCalledWith(api.PRESELECTED_PROTOCOL);

    expect(screen.getByText("Status: Ready")).toBeInTheDocument();
    expect(
      screen.getByText("Phase_3_SGLT2_High_Risk_T2D_Protocol.json")
    ).toBeInTheDocument();
  });

  it("handles JSON protocol file upload and parses clinical fields", async () => {
    const createdProtocol: api.ProtocolSummary = {
      protocol_id: "proto-json-999",
      title: "Extracted Clinical Protocol Title",
      status: "uploaded",
      data: {
        indication: "Type 2 Diabetes",
        phase: "Phase 2b",
      },
    };

    const createSpy = spyOn(api, "createProtocol").mockResolvedValueOnce(
      createdProtocol
    );
    const handleLoaded = mock();
    const user = userEvent.setup();

    const { container } = render(
      <ProtocolIngestion onProtocolLoaded={handleLoaded} />
    );

    const jsonContent = JSON.stringify({
      title: "Extracted Clinical Protocol Title",
      data: {
        indication: "Type 2 Diabetes",
        phase: "Phase 2b",
      },
    });

    const file = new File([jsonContent], "custom_protocol.json", {
      type: "application/json",
    });

    const input = container.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    expect(input).not.toBeNull();

    await user.upload(input, file);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Extracted Clinical Protocol Title",
          data: expect.objectContaining({
            indication: "Type 2 Diabetes",
            phase: "Phase 2b",
            source_file: "custom_protocol.json",
          }),
        })
      );
    });

    await waitFor(() => {
      expect(handleLoaded).toHaveBeenCalledWith(createdProtocol);
      expect(screen.getByText("custom_protocol.json")).toBeInTheDocument();
    });
  });

  it("handles PDF file upload and defaults to formatted clinical draft title", async () => {
    const createdProtocol: api.ProtocolSummary = {
      protocol_id: "proto-pdf-111",
      title: "Clinical Protocol Draft: Sglt2 Trial Diabetes Draft",
      status: "uploaded",
      data: {
        document_format: "PDF Clinical Protocol",
        source_file: "sglt2_trial_diabetes_draft.pdf",
      },
    };

    const createSpy = spyOn(api, "createProtocol").mockResolvedValueOnce(
      createdProtocol
    );
    const handleLoaded = mock();
    const user = userEvent.setup();

    const { container } = render(
      <ProtocolIngestion onProtocolLoaded={handleLoaded} />
    );

    const file = new File(["fake-pdf-content"], "sglt2_trial_diabetes_draft.pdf", {
      type: "application/pdf",
    });

    const input = container.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    expect(input).not.toBeNull();

    await user.upload(input, file);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Clinical Protocol Draft: Sglt2 Trial Diabetes Draft",
        })
      );
    });

    await waitFor(() => {
      expect(handleLoaded).toHaveBeenCalledWith(createdProtocol);
      expect(
        screen.getByText("sglt2_trial_diabetes_draft.pdf")
      ).toBeInTheDocument();
    });
  });

  it("falls back to local protocol generation when backend API is offline", async () => {
    spyOn(api, "createProtocol").mockRejectedValueOnce(
      new Error("API offline")
    );
    const handleLoaded = mock();
    const user = userEvent.setup();

    const { container } = render(
      <ProtocolIngestion onProtocolLoaded={handleLoaded} />
    );

    const file = new File(["dummy text"], "offline_protocol.txt", {
      type: "text/plain",
    });

    const input = container.querySelector(
      'input[type="file"]'
    ) as HTMLInputElement;
    expect(input).not.toBeNull();

    await user.upload(input, file);

    await waitFor(() => {
      expect(handleLoaded).toHaveBeenCalledTimes(1);
      expect(screen.getByText("offline_protocol.txt")).toBeInTheDocument();
      expect(screen.getByText("Status: Ready")).toBeInTheDocument();
    });
  });

  it("displays the next process buttons once protocol is loaded and triggers onStepSelected", async () => {
    const handleStepSelected = mock();
    const user = userEvent.setup();

    render(<ProtocolIngestion onStepSelected={handleStepSelected} />);

    // Before loading, next process buttons are not shown
    expect(
      screen.queryByRole("button", { name: /compare against guidelines/i })
    ).not.toBeInTheDocument();

    // Load preselected protocol
    const runBtn = screen.getByRole("button", {
      name: /run preselected protocol/i,
    });
    await user.click(runBtn);

    // Next process buttons appear
    const guidelinesBtn = screen.getByRole("button", {
      name: /compare against guidelines/i,
    });
    const protocolsBtn = screen.getByRole("button", {
      name: /compare with previous protocols/i,
    });
    const cohortBtn = screen.getByRole("button", {
      name: /cohort analysis/i,
    });

    expect(guidelinesBtn).toBeInTheDocument();
    expect(protocolsBtn).toBeInTheDocument();
    expect(cohortBtn).toBeInTheDocument();

    await user.click(guidelinesBtn);
    expect(handleStepSelected).toHaveBeenCalledWith("completeness");

    await user.click(protocolsBtn);
    expect(handleStepSelected).toHaveBeenCalledWith("comparison");

    await user.click(cohortBtn);
    expect(handleStepSelected).toHaveBeenCalledWith("cohort");
  });
});
