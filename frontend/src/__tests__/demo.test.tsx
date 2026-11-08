import { beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DemoPage from "@/app/demo/page";
import StepBar from "@/components/demo/StepBar";
import StepView from "@/components/demo/StepView";
import * as api from "@/lib/api";
import DemoPipeline from "@/components/demo/DemoPipeline";
import {
  MOCK_PROTOCOL_PAGE_COUNT,
  MOCK_RECOMMENDATION_FETCHERS,
  MOCK_STEPS,
  MOCK_UPLOAD_RESPONSE,
} from "@/lib/demo/mock";
import {
  findTraceabilityErrors,
  MAX_STEP_METRICS,
} from "@/lib/demo/traceability";
import type { StepData } from "@/lib/demo/types";
import { makeStep } from "./fixtures";

type User = ReturnType<typeof userEvent.setup>;

const SLOW_STEP_TIMEOUT_MS = 4000;

async function loadPreset(user: User) {
  await user.click(
    screen.getByRole("button", { name: "Try the sample protocol" })
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

  it("shows a single CTA and the upload before any protocol is loaded", () => {
    render(<DemoPage />);

    expect(screen.getAllByRole("heading")).toHaveLength(1);
    expect(
      screen.getByRole("heading", { name: "Analyze a draft protocol" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try the sample protocol" })
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("navigation", { name: "Pipeline steps" })
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "browse" })
    ).toBeInTheDocument();
  });

  it("opens the pipeline after a file is uploaded through the box", async () => {
    spyOn(api, "createProtocol").mockResolvedValue({
      protocol_id: "proto-upl-1",
      title: "Uploaded Draft",
      status: "ready",
      data: {},
    });
    const user = userEvent.setup();
    render(<DemoPage />);

    await user.upload(
      screen.getByLabelText("Upload protocol file"),
      new File(['{"title": "Uploaded Draft"}'], "draft.json", {
        type: "application/json",
      })
    );

    await waitFor(
      () =>
        expect(
          screen.getByRole("navigation", { name: "Pipeline steps" })
        ).toBeInTheDocument(),
      { timeout: SLOW_STEP_TIMEOUT_MS }
    );
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

  it("animates content only when the step changes, not on first render", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);

    const stepContent = () =>
      screen.getByRole("region", { name: /Data Ingestion|Completeness/ })
        .parentElement!;
    expect(stepContent()).not.toHaveClass("animate-step-forward");

    const finding = screen.getByRole("button", {
      name: /Eligibility criteria extracted/,
    });
    await user.click(finding);
    await user.click(finding);
    expect(stepContent()).not.toHaveClass("animate-step-forward");

    await waitFor(
      () =>
        expect(
          screen.getByRole("button", { name: "Next step" })
        ).toBeEnabled(),
      { timeout: SLOW_STEP_TIMEOUT_MS }
    );
    await user.click(screen.getByRole("button", { name: "Next step" }));
    expect(stepContent()).toHaveClass("animate-step-forward");

    await user.click(screen.getByRole("button", { name: "Previous step" }));
    expect(stepContent()).toHaveClass("animate-step-back");
  });

  it("moves between steps from the buttons at the end of a step", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);

    const stepNavigation = () =>
      within(screen.getByRole("navigation", { name: "Step navigation" }));
    expect(
      stepNavigation().queryByRole("button", { name: /Previous/ })
    ).not.toBeInTheDocument();

    const nextButton = () =>
      stepNavigation().getByRole("button", { name: /^Next:/ });
    await waitFor(() => expect(nextButton()).toBeEnabled(), {
      timeout: SLOW_STEP_TIMEOUT_MS,
    });
    await user.click(nextButton());
    expect(
      stepNavigation().getByRole("button", { name: /^← Previous:/ })
    ).toBeInTheDocument();
  });

  it("opens a finding in place and folds it by click or Esc", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);

    const finding = screen.getByRole("button", {
      name: /Eligibility criteria extracted/,
    });
    expect(finding).toHaveAttribute("aria-expanded", "false");

    await user.click(finding);
    expect(finding).toHaveAttribute("aria-expanded", "true");
    expect(
      screen.getByRole("article", { name: "Eligibility criteria extracted" })
    ).toBeInTheDocument();
    // The step stays on screen around the open finding.
    expect(
      screen.getByRole("heading", { name: "Data Ingestion" })
    ).toBeInTheDocument();

    await user.click(finding);
    expect(
      screen.queryByRole("article", { name: "Eligibility criteria extracted" })
    ).toBeNull();

    await user.click(finding);
    await user.keyboard("{Escape}");
    expect(finding).toHaveAttribute("aria-expanded", "false");
  });

  it("jumps to the earlier step and opens the finding a finding builds on", async () => {
    const user = userEvent.setup();
    render(<DemoPage />);
    await loadPreset(user);
    await waitForAllStepsDone();

    const child = MOCK_STEPS.flatMap((step) => step.decisions).find(
      (decision) => (decision.derived_from ?? []).length > 0
    )!;
    const parentId = child.derived_from![0];
    const parent = MOCK_STEPS.flatMap((step) => step.decisions).find(
      (decision) => decision.decision_id === parentId
    )!;
    const childStep = MOCK_STEPS.find((step) => step.id === child.step_id)!;
    const parentStep = MOCK_STEPS.find((step) => step.id === parent.step_id)!;

    await user.click(screen.getByRole("button", { name: childStep.title }));
    await user.click(
      screen.getByRole("button", { name: new RegExp(child.title) })
    );
    await user.click(screen.getByRole("button", { name: parent.title }));

    expect(
      screen.getByRole("heading", { name: parentStep.title })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: parent.title })
    ).toBeInTheDocument();
  });
});

describe("StepView in isolation", () => {
  it("renders any step from props alone, one row per finding", () => {
    const peers = MOCK_STEPS.find((step) => step.id === "peers")!;
    render(<StepView step={peers} onToggleDecision={() => {}}
        renderDecision={() => null} />);

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

describe("live upload fans out to the recommendation agents", () => {
  interface Deferred {
    promise: Promise<StepData>;
    resolve: (step: StepData) => void;
    reject: (error: Error) => void;
  }

  function deferred(): Deferred {
    let resolve!: Deferred["resolve"];
    let reject!: Deferred["reject"];
    const promise = new Promise<StepData>((res, rej) => {
      resolve = res;
      reject = rej;
    });
    return { promise, resolve, reject };
  }

  function setup() {
    const pending = { check: deferred(), peers: deferred(), cohort: deferred() };
    const fetchers = {
      check: mock(() => pending.check.promise),
      peers: mock(() => pending.peers.promise),
      cohort: mock(() => pending.cohort.promise),
    };
    const uploadFile = mock(async () => ({
      protocol_id: "p-1",
      title: "Draft",
      page_count: 2,
      step: makeStep("ingest", "Data Ingestion"),
    }));
    render(
      <DemoPipeline
        uploadFile={uploadFile}
        recommendationFetchers={fetchers}
      />
    );
    return { pending, fetchers, uploadFile };
  }

  async function uploadPdf(user: User) {
    await user.upload(
      screen.getByLabelText("Upload protocol file"),
      new File(["%PDF-1.7"], "draft.pdf", { type: "application/pdf" })
    );
  }

  beforeEach(() => {
    mock.restore();
  });

  it("calls all three agents in parallel with the uploaded protocol id", async () => {
    const user = userEvent.setup();
    const { fetchers, uploadFile } = setup();
    await uploadPdf(user);

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Data Ingestion" })).toBeInTheDocument()
    );
    expect(uploadFile).toHaveBeenCalledTimes(1);
    for (const fetcher of Object.values(fetchers)) {
      expect(fetcher).toHaveBeenCalledWith("p-1");
    }
    // None has resolved yet, so none is openable.
    expect(screen.getByRole("button", { name: "Protocol Comparison" })).toBeDisabled();
  });

  it("fills each step as soon as its own agent resolves", async () => {
    const user = userEvent.setup();
    const { pending } = setup();
    await uploadPdf(user);
    await screen.findByRole("heading", { name: "Data Ingestion" });

    // The cohort agent finishes first; the others are still running.
    pending.cohort.resolve(makeStep("cohort", "Cohort Comparison"));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Cohort Comparison" })).toBeEnabled()
    );
    expect(screen.getByRole("button", { name: "Protocol Comparison" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Completeness & Consistency" })
    ).toBeDisabled();

    pending.check.resolve(makeStep("check", "Completeness & Consistency"));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Completeness & Consistency" })
      ).toBeEnabled()
    );
    expect(screen.getByRole("button", { name: "Protocol Comparison" })).toBeDisabled();
  });

  it("shows an error only on the step whose agent failed", async () => {
    const user = userEvent.setup();
    const { pending } = setup();
    await uploadPdf(user);
    await screen.findByRole("heading", { name: "Data Ingestion" });

    pending.peers.reject(new Error("Peer search unavailable"));
    pending.check.resolve(makeStep("check", "Completeness & Consistency"));
    pending.cohort.resolve(makeStep("cohort", "Cohort Comparison"));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Cohort Comparison" })).toBeEnabled()
    );
    expect(
      screen.getByRole("button", { name: "Completeness & Consistency" })
    ).toBeEnabled();

    const failed = screen.getByRole("button", { name: "Protocol Comparison" });
    expect(failed).toBeEnabled();
    expect(failed).toHaveTextContent("Failed");
    await user.click(failed);
    expect(screen.getByRole("alert")).toHaveTextContent("Peer search unavailable");

    await user.click(screen.getByRole("button", { name: "Cohort Comparison" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Cohort Comparison" })
    ).toBeInTheDocument();
  });

  it("shows the upload error and stays on the upload screen", async () => {
    const uploadFile = mock(async () => {
      throw new Error("Only PDF files are supported");
    });
    const fetchers = {
      check: mock(async () => makeStep("check", "x")),
      peers: mock(async () => makeStep("peers", "x")),
      cohort: mock(async () => makeStep("cohort", "x")),
    };
    const user = userEvent.setup();
    render(
      <DemoPipeline uploadFile={uploadFile} recommendationFetchers={fetchers} />
    );
    await uploadPdf(user);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Only PDF files are supported"
    );
    expect(
      screen.queryByRole("navigation", { name: "Pipeline steps" })
    ).not.toBeInTheDocument();
    expect(fetchers.check).not.toHaveBeenCalled();
  });
});

describe("sample protocol plays endpoint-shaped mocks", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("runs the sample through the same fan-out as a real upload", async () => {
    const step = makeStep("check", "Completeness & Consistency");
    const sampleFetchers = {
      check: mock(async () => step),
      peers: mock(() => new Promise<StepData>(() => {})),
      cohort: mock(() => new Promise<StepData>(() => {})),
    };
    const uploadFile = mock(async () => MOCK_UPLOAD_RESPONSE);
    const user = userEvent.setup();
    render(
      <DemoPipeline uploadFile={uploadFile} sampleFetchers={sampleFetchers} />
    );

    await loadPreset(user);

    for (const fetcher of Object.values(sampleFetchers)) {
      expect(fetcher).toHaveBeenCalledWith(MOCK_UPLOAD_RESPONSE.protocol_id);
    }
    // The sample never touches the real upload endpoint.
    expect(uploadFile).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Completeness & Consistency" })
      ).toBeEnabled()
    );
    expect(
      screen.getByRole("button", { name: "Protocol Comparison" })
    ).toBeDisabled();
  });

  it("resolves each mock endpoint with its own step", async () => {
    const protocolId = MOCK_UPLOAD_RESPONSE.protocol_id;
    const [check, peers, cohort] = await Promise.all([
      MOCK_RECOMMENDATION_FETCHERS.check(protocolId),
      MOCK_RECOMMENDATION_FETCHERS.peers(protocolId),
      MOCK_RECOMMENDATION_FETCHERS.cohort(protocolId),
    ]);

    expect([check.id, peers.id, cohort.id]).toEqual([
      "check",
      "peers",
      "cohort",
    ]);
  });

  it("rejects an unknown protocol id like the real endpoint's 404", async () => {
    await expect(
      MOCK_RECOMMENDATION_FETCHERS.check("proto-unknown")
    ).rejects.toThrow("Uploaded protocol 'proto-unknown' not found");
  });
});
