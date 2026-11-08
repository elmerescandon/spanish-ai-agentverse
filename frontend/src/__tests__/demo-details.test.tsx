import { describe, expect, it } from "bun:test";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ChartView from "@/components/demo/ChartView";
import DataTableView from "@/components/demo/DataTableView";
import DecisionView from "@/components/demo/DecisionView";
import StepView from "@/components/demo/StepView";
import {
  formatConfidence,
  formatDuration,
  formatLocationParts,
} from "@/lib/demo/format";
import { MAX_STEP_METRICS } from "@/lib/demo/traceability";
import {
  CHART_KINDS,
  type Chart,
  type DataTable,
  type Decision,
  type StepData,
} from "@/lib/demo/types";
import { makeStep } from "./fixtures";

const RICH_TABLE: DataTable = {
  table_id: "t-sites",
  title: "Enrolment by site",
  description: "Projected from peer trials.",
  columns: [
    { key: "site", label: "Site" },
    { key: "weeks", label: "Weeks", unit: "wk" },
    { key: "is_active", label: "Active" },
  ],
  rows: [
    { site: "London", weeks: 36, is_active: true },
    { site: "Leeds", weeks: null, is_active: false },
  ],
};

const RICH_CHART: Chart = {
  chart_id: "c-duration",
  kind: "comparison",
  title: "Recruitment duration",
  description: "This protocol against peer trials.",
  x_label: "Weeks",
  y_label: "Trial",
  unit: "wk",
  series: [
    {
      name: "This protocol",
      points: [
        {
          label: "Duration",
          value: 52,
          lower: 44,
          upper: 60,
          annotation: "Longest in class",
        },
      ],
    },
    { name: "Peer median", points: [{ label: "Duration", value: 36 }] },
  ],
};

const RICH_DECISION: Decision = {
  decision_id: "d-rich",
  step_id: "check",
  severity: "warning",
  title: "HbA1c window too narrow",
  claim: "The inclusion window excludes most real-world patients.",
  category: "Eligibility",
  confidence: 0.92,
  location: {
    section_heading: "5.1",
    section_title: "Inclusion",
    start_page: 12,
    end_page: 13,
    criterion_id: "IC-3",
  },
  decision_owner: "Clinical lead",
  review_status: "pending",
  tags: ["eligibility", "recruitment"],
  evidence: [
    {
      evidence_id: "e1",
      source: "protocol",
      document: "Protocol v2",
      page: 12,
      quote: "HbA1c between 7.0% and 7.5%",
      is_verified: true,
      section_title: "Inclusion criteria",
      context:
        "Participants must have HbA1c between 7.0% and 7.5% at screening.",
      url: "https://example.org/protocol",
      confidence: 0.88,
    },
    {
      evidence_id: "e2",
      source: "aact",
      document: "AACT export",
      page: null,
      quote: "Median HbA1c 8.1%",
      is_verified: false,
      context: "Across 40 peer trials the inclusion range was wider.",
    },
  ],
  trace: [
    {
      agent: "Completeness",
      kind: "compare",
      text: "Compared the window with peer trials.",
      evidence_ids: ["e1", "e2"],
      duration_ms: 1250,
    },
  ],
  proposed_change: {
    path: "eligibility.inclusion[2]",
    before: "7.0% to 7.5%",
    after: "7.0% to 10.0%",
    change_type: "modify",
    section_title: "Inclusion",
    page: 12,
    rationale: "Matches the peer median range.",
  },
  impact: [
    {
      label: "eligible",
      value: "41",
      unit: "%",
      benchmarks: [{ label: "peer median", value: "55" }],
    },
  ],
  options: [
    {
      option_id: "o1",
      title: "Widen to 10.0%",
      rationale: "Aligns with peers.",
      is_recommended: true,
      impact: [{ label: "eligible after", value: "63", unit: "%" }],
      risks: ["More heterogeneous cohort"],
    },
    {
      option_id: "o2",
      title: "Keep current window",
      rationale: "Tighter efficacy signal.",
      proposed_change: {
        path: "eligibility.inclusion[2]",
        before: "",
        after: "Add rescue arm",
        change_type: "add",
      },
    },
  ],
  references: [
    {
      label: "ADA Standards of Care 2026",
      url: "https://example.org/ada",
      quote: "Individualise glycaemic targets.",
    },
    { label: "Internal SOP 12" },
  ],
  charts: [RICH_CHART],
  tables: [RICH_TABLE],
};

function makeRichStep(): StepData {
  return {
    ...makeStep("check", "Completeness"),
    status: "partial",
    agent: "Completeness agent",
    duration_ms: 4200,
    warnings: [
      {
        code: "AACT_TIMEOUT",
        message: "AACT lookup timed out; peers may be incomplete.",
        severity: "warning",
      },
    ],
    data_sources: [
      {
        source: "aact",
        name: "ClinicalTrials.gov (AACT)",
        description: "Registry of past trials.",
        url: "https://aact.ctti-clinicaltrials.org",
        version: "2026-10",
        record_count: 12345,
      },
    ],
    metrics: [
      {
        label: "recruitment",
        value: "52",
        unit: "wk",
        description: "Projected time to full enrolment.",
        benchmarks: [{ label: "peer median", value: "36" }],
      },
    ],
    decisions: [RICH_DECISION],
    charts: [RICH_CHART],
    tables: [RICH_TABLE],
  };
}

function renderDecision(decision: Decision) {
  render(
    <DecisionView decision={decision} parents={[]} onOpenParent={() => {}} />
  );
}

describe("StepView rich step details", () => {
  it("shows the run status, agent, duration and warnings", () => {
    render(<StepView step={makeRichStep()} onToggleDecision={() => {}}
        renderDecision={() => null} />);

    expect(screen.getByText("Partial")).toBeInTheDocument();
    expect(
      screen.getByText(/^Completeness agent · 4\.2 s/)
    ).toBeInTheDocument();
    const warnings = screen.getByRole("list", { name: "Run warnings" });
    expect(
      within(warnings).getByText(/AACT lookup timed out/)
    ).toBeInTheDocument();
    expect(within(warnings).getByText("AACT_TIMEOUT")).toBeInTheDocument();
  });

  it("shows metric units, benchmarks and descriptions", () => {
    render(<StepView step={makeRichStep()} onToggleDecision={() => {}}
        renderDecision={() => null} />);

    expect(screen.getByText("52")).toBeInTheDocument();
    expect(screen.getByText("wk")).toBeInTheDocument();
    expect(screen.getByText("peer median 36 wk")).toBeInTheDocument();
    expect(
      screen.getByText("Projected time to full enrolment.")
    ).toBeInTheDocument();
  });

  it("previews category, confidence, location and claim per finding", () => {
    render(<StepView step={makeRichStep()} onToggleDecision={() => {}}
        renderDecision={() => null} />);

    const row = screen.getByRole("button", {
      name: /HbA1c window too narrow/,
    });
    expect(
      within(row).getByText(
        "Eligibility · 92% · § 5.1 Inclusion · pp. 12–13 · IC-3"
      )
    ).toBeInTheDocument();
    expect(within(row).getByText(RICH_DECISION.claim)).toBeInTheDocument();
  });

  it("lists data sources with version, size and a link", () => {
    render(<StepView step={makeRichStep()} onToggleDecision={() => {}}
        renderDecision={() => null} />);

    const sources = screen.getByRole("region", { name: "Data sources" });
    expect(
      within(sources).getByRole("link", { name: /ClinicalTrials\.gov/ })
    ).toHaveAttribute("href", "https://aact.ctti-clinicaltrials.org");
    expect(
      within(sources).getByText("AACT · v2026-10 · 12,345 records")
    ).toBeInTheDocument();
  });

  it("shows every evaluated item and chart open, and lets them fold", async () => {
    const user = userEvent.setup();
    render(<StepView step={makeRichStep()} onToggleDecision={() => {}}
        renderDecision={() => null} />);

    expect(
      screen.getByRole("table", { name: /Enrolment by site/ })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Recruitment duration/ })
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Evaluated items/ }));
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("renders no extra sections for a bare step", () => {
    render(
      <StepView
        step={makeStep("check", "Completeness")}
        onToggleDecision={() => {}}
        renderDecision={() => null}
      />
    );

    expect(screen.getAllByRole("heading")).toHaveLength(1);
    expect(screen.queryByRole("list", { name: "Run warnings" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Data sources" })).toBeNull();
    expect(screen.queryByText("Completed")).toBeNull();
  });

  it(`shows at most ${MAX_STEP_METRICS} figures`, () => {
    const step = {
      ...makeStep("check", "Completeness"),
      metrics: Array.from({ length: MAX_STEP_METRICS + 2 }, (_, index) => ({
        label: `figure ${index}`,
        value: String(index),
      })),
    };
    render(<StepView step={step} onToggleDecision={() => {}}
        renderDecision={() => null} />);

    expect(screen.getAllByText(/^figure \d$/)).toHaveLength(MAX_STEP_METRICS);
  });
});

describe("DecisionView rich finding details", () => {
  it("shows the meta line and tags", () => {
    renderDecision(RICH_DECISION);

    for (const text of [
      "Eligibility",
      "92% confidence",
      "§ 5.1 Inclusion",
      "pp. 12–13",
      "IC-3",
      "Owner: Clinical lead",
      "Awaiting review",
    ]) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    const tags = screen.getByRole("list", { name: "Tags" });
    expect(within(tags).getByText("recruitment")).toBeInTheDocument();
  });

  it("highlights the quote inside its context, else shows context below", () => {
    renderDecision(RICH_DECISION);

    const highlighted = screen.getByText(RICH_DECISION.evidence[0].quote);
    expect(highlighted.tagName).toBe("MARK");
    expect(highlighted.closest("blockquote")).toHaveTextContent(
      "Participants must have HbA1c between 7.0% and 7.5% at screening."
    );

    const standalone = screen.getByText("Median HbA1c 8.1%");
    expect(standalone.closest("blockquote")).not.toHaveTextContent(
      "peer trials"
    );
    expect(
      screen.getByText("Across 40 peer trials the inclusion range was wider.")
    ).toBeInTheDocument();
  });

  it("shows evidence section, match confidence and source link", () => {
    renderDecision(RICH_DECISION);

    expect(screen.getByText("Inclusion criteria")).toBeInTheDocument();
    expect(screen.getByText("88% match")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open source" })
    ).toHaveAttribute("href", "https://example.org/protocol");
  });

  it("labels the suggested change with its type, place and rationale", () => {
    renderDecision(RICH_DECISION);

    expect(
      screen.getByText("Modify · eligibility.inclusion[2] · Inclusion · p. 12")
    ).toBeInTheDocument();
    expect(
      screen.getByText("Matches the peer median range.")
    ).toBeInTheDocument();
  });

  it("shows options with the recommended one badged, impact and risks", () => {
    renderDecision(RICH_DECISION);

    const recommended = screen.getByRole("listitem", {
      name: "Widen to 10.0%",
    });
    expect(within(recommended).getByText("Recommended")).toBeInTheDocument();
    expect(
      within(recommended).getByText("eligible after")
    ).toBeInTheDocument();
    expect(
      within(recommended).getByText("More heterogeneous cohort")
    ).toBeInTheDocument();

    const other = screen.getByRole("listitem", {
      name: "Keep current window",
    });
    expect(within(other).queryByText("Recommended")).toBeNull();
    expect(within(other).getByText("Add rescue arm")).toBeInTheDocument();
  });

  it("links references and shows their quotes", () => {
    renderDecision(RICH_DECISION);

    expect(
      screen.getByRole("link", { name: "ADA Standards of Care 2026" })
    ).toHaveAttribute("href", "https://example.org/ada");
    expect(
      screen.getByText("“Individualise glycaemic targets.”")
    ).toBeInTheDocument();
    expect(screen.getByText("Internal SOP 12")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Internal SOP 12" })
    ).toBeNull();
  });

  it("shows impact, charts and tables, and trace timing on expand", async () => {
    const user = userEvent.setup();
    renderDecision(RICH_DECISION);

    expect(screen.getByText("peer median 55%")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /Recruitment duration/ })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Weeks (wk)" })
    ).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Show reasoning (1 steps)" })
    );
    expect(screen.getByText("1.3 s")).toBeInTheDocument();
  });

  it("renders no headings for empty optional fields", () => {
    renderDecision({
      decision_id: "d-bare",
      step_id: "check",
      severity: "info",
      title: "Bare finding",
      claim: "Nothing else known.",
      evidence: [],
      trace: [],
      options: [],
      references: [],
      impact: [],
      tags: [],
      charts: [],
      tables: [],
      proposed_change: null,
      location: null,
      confidence: null,
    });

    expect(
      screen.getAllByRole("heading").map((heading) => heading.textContent)
    ).toEqual(["Bare finding", "Evidence"]);
    expect(screen.queryByRole("list", { name: "Tags" })).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("ChartView", () => {
  for (const kind of CHART_KINDS) {
    it(`draws a ${kind} chart named by its title and values`, () => {
      render(<ChartView chart={{ ...RICH_CHART, kind }} />);

      const chart = screen.getByRole("img", {
        name: /^Recruitment duration\./,
      });
      expect(chart).toHaveAccessibleName(
        "Recruitment duration. This protocol: Duration 52 wk " +
          "(44 wk–60 wk) (Longest in class); Peer median: Duration 36 wk"
      );
      expect(screen.getByText("Weeks")).toBeInTheDocument();
      expect(screen.getByText("Trial")).toBeInTheDocument();
      expect(screen.getByText("Peer median")).toBeInTheDocument();
    });
  }

  it("draws nothing when no series has points", () => {
    const { container } = render(
      <ChartView chart={{ ...RICH_CHART, series: [{ name: "x", points: [] }] }} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("DataTableView", () => {
  it("shows headers with units and formats cells", () => {
    render(<DataTableView table={RICH_TABLE} />);

    const table = screen.getByRole("table", { name: /Enrolment by site/ });
    expect(
      within(table).getAllByRole("columnheader").map((h) => h.textContent)
    ).toEqual(["Site", "Weeks (wk)", "Active"]);
    expect(within(table).getByRole("cell", { name: "36" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "—" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Yes" })).toBeInTheDocument();
  });
});

describe("demo format helpers", () => {
  it("formats durations, confidence and locations at the edges", () => {
    expect(formatDuration(850)).toBe("850 ms");
    expect(formatDuration(4200)).toBe("4.2 s");
    expect(formatDuration(125_000)).toBe("2 min 5 s");
    expect(formatConfidence(0.925)).toBe("93%");
    expect(formatConfidence(1)).toBe("100%");
    expect(formatLocationParts(null)).toEqual([]);
    expect(formatLocationParts({ start_page: 3, end_page: 3 })).toEqual([
      "p. 3",
    ]);
  });
});
