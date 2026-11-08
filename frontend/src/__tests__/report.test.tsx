import { beforeEach, describe, expect, it, mock, spyOn } from "bun:test";
import { render, screen, within } from "@testing-library/react";
import ReportPage from "@/app/report/page";
import * as api from "@/lib/api";
import type { ProtocolFieldsResponse } from "@/lib/api";
import { fieldLabel, groupFieldsBySection } from "@/lib/report";

const HBA1C_FIELD = "comparison.hba1c_upper_bound";

const REVIEW: ProtocolFieldsResponse = {
  protocol_id: "proto-dummy01",
  title: "Dummy T2D Glycemic Control Trial",
  page_count: 42,
  uploaded_at: "2026-11-08T12:00:00+00:00",
  fields: [
    { field: HBA1C_FIELD, value: "10", unit: "%", page: null },
    { field: "design.phase", value: "PHASE3", unit: null, page: 1 },
    { field: "eligibility.age_min", value: "18", unit: "years", page: 12 },
  ],
  changes: [
    {
      change_id: 1,
      field: HBA1C_FIELD,
      old_value: "11",
      new_value: "10",
      decision_id: "cmp-hba1c_upper_bound",
      option_id: "cmp-hba1c_upper_bound-recent",
      rationale: "10% is in line with 23 recent peer trials.",
      changed_at: "2026-11-08T12:05:00+00:00",
    },
  ],
};

describe("report page", () => {
  beforeEach(() => {
    mock.restore();
  });

  it("shows the latest review's changes and fields by section", async () => {
    spyOn(api, "getLatestReview").mockResolvedValue(REVIEW);
    render(<ReportPage />);

    expect(
      await screen.findByRole("heading", { name: REVIEW.title })
    ).toBeInTheDocument();
    const changes = within(
      screen.getByRole("region", { name: "Accepted changes" })
    );
    expect(changes.getByText("11")).toBeInTheDocument();
    expect(changes.getByText("10")).toBeInTheDocument();
    expect(changes.getByText(REVIEW.changes[0].rationale)).toBeInTheDocument();

    const comparison = within(screen.getByRole("table", { name: "Comparison" }));
    expect(comparison.getByText("10%")).toBeInTheDocument();
    expect(comparison.getByText("Changed")).toBeInTheDocument();
    const eligibility = within(
      screen.getByRole("table", { name: "Eligibility" })
    );
    expect(eligibility.getByText("18 years")).toBeInTheDocument();
    expect(eligibility.queryByText("Changed")).not.toBeInTheDocument();

    expect(
      within(screen.getByRole("banner")).getByRole("link", {
        name: "Download report (PDF)",
      })
    ).toHaveAttribute("href", api.LATEST_REPORT_PDF_URL);
  });

  it("shows a report-shaped placeholder until the review arrives", () => {
    spyOn(api, "getLatestReview").mockReturnValue(new Promise(() => {}));
    render(<ReportPage />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading report");
    expect(
      screen.queryByRole("link", { name: "Download report (PDF)" })
    ).not.toBeInTheDocument();
  });

  it("says so when no change has been accepted yet", async () => {
    spyOn(api, "getLatestReview").mockResolvedValue({ ...REVIEW, changes: [] });
    render(<ReportPage />);

    expect(
      await screen.findByText(/No changes accepted yet/)
    ).toBeInTheDocument();
    expect(screen.queryByText("Changed")).not.toBeInTheDocument();
  });

  it("shows the reason and no download when there is nothing to report", async () => {
    spyOn(api, "getLatestReview").mockRejectedValue(
      new Error("Failed to fetch the latest review: No uploaded protocol")
    );
    render(<ReportPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No uploaded protocol"
    );
    expect(
      screen.queryByRole("link", { name: "Download report (PDF)" })
    ).not.toBeInTheDocument();
  });
});

describe("report field grouping", () => {
  it("groups by prefix in first-seen order and keeps unprefixed fields", () => {
    const sections = groupFieldsBySection([
      { field: "design.phase", value: "3", unit: null, page: null },
      { field: "title", value: "T", unit: null, page: null },
      { field: "design.arms", value: "2", unit: null, page: null },
    ]);

    expect(sections.map((section) => section.title)).toEqual([
      "Design",
      "General",
    ]);
    expect(sections[0].fields).toHaveLength(2);
  });

  it("reads nested stored names as text", () => {
    expect(fieldLabel("statistics.sample_size")).toBe("Sample size");
    expect(fieldLabel("analysis.primary.method")).toBe("Primary · method");
  });
});
