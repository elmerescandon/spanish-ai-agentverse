import { beforeEach, describe, expect, it, mock } from "bun:test";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DemoPage from "@/app/demo/page";
import StepBar from "@/components/demo/StepBar";
import StepView from "@/components/demo/StepView";
import { MOCK_PROTOCOL_PAGE_COUNT, MOCK_STEPS } from "@/lib/demo/mock";
import {
  findTraceabilityErrors,
  MAX_STEP_METRICS,
} from "@/lib/demo/traceability";
import type { StepData } from "@/lib/demo/types";

type User = ReturnType<typeof userEvent.setup>;

const SLOW_STEP_TIMEOUT_MS = 4000;

async function loadPreset(user: User) {
  await user.click(
    screen.getByRole("button", { name: /Run Preselected Protocol/ })
  );
}

async function waitForAllStepsDone() {
  await waitFor(
    () =>
      expect(
        screen.getByRole("button", { name: "Cohort Comparison" })
      ).toBeEnabled(),
    { timeout: SLOW_STEP_TIMEOUT_MS }
  );
}

describe("demo traceability mock data", () => {
  it("has an intact chain from every decision to its evidence", () => {
    expect(
      findTraceabilityErrors(MOCK_STEPS, MOCK_PROTOCOL_PAGE_COUNT)
    ).toEqual([]);
  });

  it("flags a trace entry citing evidence the decision does not hold", () => {
    const broken: StepData[] = structuredClone(MOCK_STEPS);
    broken[0].decisions[0].trace[0].evidence_ids = ["e-missing"];

    expect(
      findTraceabilityErrors(broken, MOCK_PROTOCOL_PAGE_COUNT)
    ).toContain("decision d-ing-01 trace cites unknown evidence e-missing");
  });

  it("flags a decision deriving from a later step", () => {
    const broken: StepData[] = structuredClone(MOCK_STEPS);
    broken[0].decisions[0].derived_from = ["d-coh-01"];

    const errors = findTraceabilityErrors(broken, MOCK_PROTOCOL_PAGE_COUNT);
    expect(errors.some((e) => e.includes("derives from d-coh-01"))).toBe(
      true
    );
  });

  it("flags a protocol page beyond the document", () => {
    const broken: StepData[] = structuredClone(MOCK_STEPS);
    broken[0].decisions[0].evidence[0].page = MOCK_PROTOCOL_PAGE_COUNT + 1;

    const errors = findTraceabilityErrors(broken, MOCK_PROTOCOL_PAGE_COUNT);
    expect(errors.some((e) => e.includes("cites page"))).toBe(true);
  });

  it("flags a step with more overview metrics than allowed", () => {
    const broken: StepData[] = structuredClone(MOCK_STEPS);
    broken[0].metrics.push({ label: "Extra", value: "1" });

    const errors = findTraceabilityErrors(broken, MOCK_PROTOCOL_PAGE_COUNT);
    expect(
      errors.some((e) => e.includes(`at most ${MAX_STEP_METRICS}`))
    ).toBe(true);
  });
});

describe("demo pipeline step bar flow", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("shows the upload entry before any protocol is loaded", () => {
    render(<DemoPage />);

    expect(
      screen.getByRole("button", { name: /Run Preselected Protocol/ })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Pipeline steps" })
    ).not.toBeInTheDocument();
  });

  it("shows the step bar on the first step after a preset loads", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);

    expect(
      screen.getByRole("navigation", { name: "Pipeline steps" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Data Ingestion" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Data Ingestion" })
    ).toBeEnabled();
  });

  it("completes steps in order and keeps later ones disabled until done", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);

    const check = screen.getByRole("button", {
      name: "Completeness & Consistency",
    });
    const cohort = screen.getByRole("button", { name: "Cohort Comparison" });
    expect(check).toBeDisabled();
    expect(cohort).toBeDisabled();

    await waitFor(() => expect(check).toBeEnabled(), {
      timeout: SLOW_STEP_TIMEOUT_MS,
    });
    expect(cohort).toBeDisabled();

    await waitForAllStepsDone();
    // The user stayed on step 1 while later steps completed.
    expect(
      screen.getByRole("heading", { name: "Data Ingestion" })
    ).toBeInTheDocument();
  });

  it("navigates with arrows, segments and keyboard keys", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);
    await waitForAllStepsDone();

    expect(
      screen.getByRole("button", { name: "Previous step" })
    ).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Next step" }));
    expect(
      screen.getByRole("heading", { name: "Completeness & Consistency" })
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Protocol Comparison" })
    );
    expect(
      screen.getByRole("heading", { name: "Protocol Comparison" })
    ).toBeInTheDocument();

    await user.keyboard("{ArrowRight}");
    expect(
      screen.getByRole("heading", { name: "Cohort Comparison" })
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next step" })).toBeDisabled();

    await user.keyboard("{ArrowLeft}");
    expect(
      screen.getByRole("heading", { name: "Protocol Comparison" })
    ).toBeInTheDocument();
  });

  it("ignores arrow keys typed inside a text input", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);
    await waitForAllStepsDone();

    const field = document.createElement("input");
    document.body.appendChild(field);
    try {
      fireEvent.keyDown(field, { key: "ArrowRight" });
      expect(
        screen.getByRole("heading", { name: "Data Ingestion" })
      ).toBeInTheDocument();
    } finally {
      field.remove();
    }
  });

  it("opens a finding under the step bar and goes back by button or Esc", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);

    await user.click(
      screen.getByRole("button", { name: /Eligibility criteria extracted/ })
    );
    expect(
      screen.getByRole("heading", { name: "Eligibility criteria extracted" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("navigation", { name: "Pipeline steps" })
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Back to findings" })
    );
    expect(
      screen.getByRole("heading", { name: "Data Ingestion" })
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /Eligibility criteria extracted/ })
    );
    await user.keyboard("{Escape}");
    expect(
      screen.queryByRole("button", { name: "Back to findings" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Data Ingestion" })
    ).toBeInTheDocument();
  });
});

describe("StepView in isolation", () => {
  it("renders any step from props alone, one row per finding", () => {
    const peers = MOCK_STEPS.find((step) => step.id === "peers")!;
    render(<StepView step={peers} onOpenDecision={() => {}} />);

    expect(
      screen.getByRole("heading", { name: "Protocol Comparison" })
    ).toBeInTheDocument();
    expect(screen.getByText("HbA1c ≥ 9.0")).toBeInTheDocument();
    for (const decision of peers.decisions) {
      expect(
        screen.getByRole("button", { name: new RegExp(decision.title) })
      ).toBeInTheDocument();
    }
  });
});

describe("StepBar in isolation", () => {
  it("marks the viewed step and only lets finished steps be opened", async () => {
    const user = userEvent.setup();
    const onSelect = mock();
    render(
      <StepBar
        items={[
          { id: "ingest", title: "Data Ingestion", state: "done" },
          { id: "check", title: "Completeness", state: "done" },
          { id: "peers", title: "Peers", state: "running" },
          { id: "cohort", title: "Cohort", state: "pending" },
        ]}
        activeId="check"
        onSelect={onSelect}
      />
    );

    expect(
      screen.getByRole("button", { name: "Completeness" })
    ).toHaveAttribute("aria-current", "step");
    expect(screen.getByRole("button", { name: "Peers" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cohort" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next step" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Previous step" }));
    expect(onSelect).toHaveBeenCalledWith("ingest");
  });
});
