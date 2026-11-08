import { beforeEach, describe, expect, it, mock } from "bun:test";
import { render, screen, within } from "@testing-library/react";
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
    const headerTitle = within(screen.getByRole("banner")).getByRole(
      "link",
      { name: "ProtocolAI" }
    );
    expect(headerTitle).toBeInTheDocument();

    // Main hero thesis heading is rendered as h1
    const mainHeading = screen.getByRole("heading", {
      name: /Find protocol problems before the first patient/i,
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
      screen.getByText("From draft protocol to doctor-approved changes")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Understand the protocol")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Find missing or conflicting parts")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Compare with similar trials")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Count the patients you would lose")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Doctors make the call")
    ).toBeInTheDocument();

    // Foundational Clinical Data & Validation Guardrails
    expect(
      screen.getByText("Every finding points to a source")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Built so doctors stay in control")
    ).toBeInTheDocument();
  });

  it("describes a condition-agnostic process", () => {
    render(<HomePage />);

    expect(screen.getByRole("link", { name: "Try demo" })).toHaveAttribute(
      "href",
      "/demo"
    );
    expect(screen.queryByText(/diabetes/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/MIMIC/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Synthea/i)).not.toBeInTheDocument();
  });

  it("shows the decision card as review options, not a live approval", () => {
    render(<HomePage />);

    expect(
      screen.queryByRole("button", { name: /Approve Amendment/i })
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Option: keep, with a written reason")
    ).toBeInTheDocument();
  });
});
