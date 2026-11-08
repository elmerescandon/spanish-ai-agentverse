import { beforeEach, describe, expect, it, mock } from "bun:test";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HomePage from "@/app/page";

describe("HomePage ProtocolAI editorial presentation with Three.js ASCII background", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("renders HomePage with header title, thesis heading, problem metrics, and connected pipeline", () => {
    const { container } = render(<HomePage />);

    const mainElement = container.querySelector("main");
    expect(mainElement).toBeInTheDocument();
    expect(mainElement).toHaveClass("bg-white");
    expect(mainElement).toHaveClass("text-zinc-900");

    // Product title "ProtocolAI" is in the header link
    const headerTitle = screen.getByRole("link", { name: "ProtocolAI" });
    expect(headerTitle).toBeInTheDocument();

    // Main hero thesis heading is rendered as h1
    const mainHeading = screen.getByRole("heading", {
      name: /Catching avoidable clinical trial amendments/i,
    });
    expect(mainHeading).toBeInTheDocument();

    // Removed redundant badges
    expect(screen.queryByText(/UCL Agentverse/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Clinical Trial Protocol Intelligence/i)
    ).not.toBeInTheDocument();

    // Three.js 3D ASCII protein viewer runs in the background
    const viewer = screen.getByRole("img", {
      name: /Rotating 3D ASCII structure of Human Insulin/i,
    });
    expect(viewer).toBeInTheDocument();

    // 3 Key Problem Metrics
    expect(screen.getByText("57%")).toBeInTheDocument();
    expect(screen.getByText("45%")).toBeInTheDocument();
    expect(screen.getByText("18%")).toBeInTheDocument();

    // Multi-Agent Pipeline Architecture Steps
    expect(
      screen.getByText("End-to-End Multi-Agent Architecture")
    ).toBeInTheDocument();
    expect(
      screen.getByText("ICH M11 Document Structuring")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Completeness & Consistency")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Historical Peer Trial Comparison")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Cohort Attrition & Diversity")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Clinician-Facing Decision Cards")
    ).toBeInTheDocument();

    // Foundational Clinical Data & Validation Guardrails
    expect(
      screen.getByText("Grounded in Regulatory Standards & Real-World Evidence")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Validation Rigor & Clinical Safety Guardrails")
    ).toBeInTheDocument();
  });

  it("supports interactive clinician amendment approval in step 04", async () => {
    const user = userEvent.setup();
    render(<HomePage />);

    const approveButton = screen.getByRole("button", {
      name: /Approve Amendment/i,
    });
    expect(approveButton).toBeInTheDocument();

    await user.click(approveButton);
    expect(
      screen.getByRole("button", { name: /Approved by Clinician/i })
    ).toBeInTheDocument();
  });

  it("provides a floating Tune ASCII button that toggles the studio popover", async () => {
    const user = userEvent.setup();
    render(<HomePage />);

    // Floating Tune ASCII button is visible, tuner popover initially closed
    const tuneButton = screen.getByRole("button", { name: "Tune ASCII" });
    expect(tuneButton).toBeInTheDocument();
    expect(
      screen.queryByText("Live Three.js ASCII Studio")
    ).not.toBeInTheDocument();

    // Clicking opens the floating tuner popover
    await user.click(tuneButton);
    expect(
      screen.getByText("Live Three.js ASCII Studio")
    ).toBeInTheDocument();

    // The floating button now offers close
    const closeButton = screen.getByRole("button", { name: "Close" });
    expect(closeButton).toBeInTheDocument();

    // Clicking closes the floating tuner popover
    await user.click(closeButton);
    expect(
      screen.queryByText("Live Three.js ASCII Studio")
    ).not.toBeInTheDocument();
  });

  it("allows switching protein presets and adjusting parameters via the floating tuner popover", async () => {
    const user = userEvent.setup();
    render(<HomePage />);

    // Open tuner
    await user.click(screen.getByRole("button", { name: "Tune ASCII" }));
    expect(
      screen.getByText("Live Three.js ASCII Studio")
    ).toBeInTheDocument();

    // Switch structure preset to SGLT2 Cotransporter Pocket
    await user.click(
      screen.getByRole("button", { name: "SGLT2 Cotransporter Pocket" })
    );

    // Verify the rotating 3D ASCII protein viewer updates its active structure
    expect(
      screen.getByRole("img", {
        name: /Rotating 3D ASCII structure of SGLT2 Cotransporter Pocket/i,
      })
    ).toBeInTheDocument();

    // Toggle Auto Rotation
    const pauseButton = screen.getByRole("button", { name: "Pause Spin" });
    await user.click(pauseButton);
    expect(
      screen.getByRole("button", { name: "Resume Spin" })
    ).toBeInTheDocument();

    // Close via header close button
    const headerCloseButton = screen.getByRole("button", { name: "✕" });
    await user.click(headerCloseButton);
    expect(
      screen.queryByText("Live Three.js ASCII Studio")
    ).not.toBeInTheDocument();
  });
});
