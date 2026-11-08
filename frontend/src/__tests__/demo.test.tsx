import { beforeEach, describe, expect, it, mock } from "bun:test";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DemoPage from "@/app/demo/page";
import StepView from "@/components/demo/StepView";
import { MOCK_PROTOCOL_PAGE_COUNT, MOCK_STEPS } from "@/lib/demo/mock";
import {
  findTraceabilityErrors,
  MAX_STEP_METRICS,
} from "@/lib/demo/traceability";
import type { StepData } from "@/lib/demo/types";

type User = ReturnType<typeof userEvent.setup>;

async function runStep(user: User, title: string) {
  await user.click(screen.getByRole("button", { name: `Run ${title}` }));
  await waitFor(
    () =>
      expect(
        screen.getByRole("button", { name: `Open ${title}` })
      ).toBeInTheDocument(),
    { timeout: 2000 }
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

describe("demo pipeline zoom flow", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("starts zoomed out with only the first step runnable", () => {
    render(<DemoPage />);

    expect(
      screen.getByRole("button", { name: "Run Data Ingestion" })
    ).toBeInTheDocument();
    for (const title of [
      "Completeness & Consistency",
      "Protocol Comparison",
      "Cohort Comparison",
    ]) {
      expect(
        screen.queryByRole("button", { name: `Run ${title}` })
      ).not.toBeInTheDocument();
    }
  });

  it("unlocks the next step only after the previous one finishes", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);

    await runStep(user, "Data Ingestion");

    expect(
      screen.getByRole("button", { name: "Run Completeness & Consistency" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Run Protocol Comparison" })
    ).not.toBeInTheDocument();
  });

  it("zooms from pipeline to step to decision and back out", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await runStep(user, "Data Ingestion");
    await runStep(user, "Completeness & Consistency");

    await user.click(
      screen.getByRole("button", { name: "Open Completeness & Consistency" })
    );
    expect(
      screen.getByRole("heading", { name: "Completeness & Consistency" })
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /Endpoint week conflicts/ })
    );
    const nav = screen.getByRole("navigation", { name: "Zoom level" });
    expect(within(nav).getByText("Pipeline")).toBeInTheDocument();
    expect(
      within(nav).getByText("Endpoint week conflicts with schedule")
    ).toHaveAttribute("aria-current", "page");

    // Evidence carries its document and page.
    expect(
      screen.getByText(/mean change in HbA1c from baseline at Week 24/)
    ).toBeInTheDocument();
    expect(screen.getByText("p. 12")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(
      screen.getByRole("heading", { name: "Completeness & Consistency" })
    ).toBeInTheDocument();

    await user.click(within(nav).getByRole("button", { name: "Pipeline" }));
    expect(
      screen.getByRole("heading", {
        name: "From draft protocol to reviewed decisions",
      })
    ).toBeInTheDocument();
  });

  it("follows a decision back to the earlier finding it builds on", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await runStep(user, "Data Ingestion");
    await runStep(user, "Completeness & Consistency");

    await user.click(
      screen.getByRole("button", { name: "Open Completeness & Consistency" })
    );
    await user.click(
      screen.getByRole("button", { name: /Endpoint week conflicts/ })
    );
    await user.click(
      screen.getByRole("button", {
        name: "Schedule of Activities partly unreadable",
      })
    );

    expect(
      screen.getByRole("heading", {
        name: "Schedule of Activities partly unreadable",
      })
    ).toBeInTheDocument();
    expect(
      within(screen.getByRole("navigation", { name: "Zoom level" })).getByText(
        "Data Ingestion"
      )
    ).toBeInTheDocument();
  });

  it("requires a reason before a finding can be dismissed", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await runStep(user, "Data Ingestion");
    await user.click(
      screen.getByRole("button", { name: "Open Data Ingestion" })
    );
    await user.click(
      screen.getByRole("button", { name: /Eligibility criteria extracted/ })
    );

    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    const confirm = screen.getByRole("button", { name: "Confirm dismissal" });
    expect(confirm).toBeDisabled();

    await user.type(
      screen.getByLabelText("Reason for dismissing"),
      "   "
    );
    expect(confirm).toBeDisabled();

    await user.type(
      screen.getByLabelText("Reason for dismissing"),
      "Counts checked by hand"
    );
    await user.click(confirm);
    expect(screen.getByText(/Counts checked by hand/)).toBeInTheDocument();
  });

  it("runs all four steps and shows an accepted decision in its step", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    for (const step of MOCK_STEPS) {
      await runStep(user, step.title);
    }

    await user.click(
      screen.getByRole("button", { name: "Open Cohort Comparison" })
    );
    await user.click(
      screen.getByRole("button", { name: /eGFR exclusion removes/ })
    );
    await user.click(screen.getByRole("button", { name: "Accept" }));
    await user.click(screen.getByRole("button", { name: "Zoom out" }));

    const row = screen.getByRole("button", {
      name: /eGFR exclusion removes/,
    });
    expect(within(row).getByText("Accepted")).toBeInTheDocument();
  });
});

describe("StepView in isolation", () => {
  it("renders any step from props alone, without the pipeline", () => {
    const peers = MOCK_STEPS.find((step) => step.id === "peers")!;
    render(
      <StepView step={peers} humanDecisions={{}} onOpenDecision={() => {}} />
    );

    expect(
      screen.getByRole("heading", { name: "Protocol Comparison" })
    ).toBeInTheDocument();
    expect(screen.getByText("HbA1c ≥ 9.0")).toBeInTheDocument();
    expect(screen.getAllByText("Pending")).toHaveLength(
      peers.decisions.length
    );
  });
});
