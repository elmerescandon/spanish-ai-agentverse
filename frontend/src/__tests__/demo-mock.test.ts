import { describe, expect, it } from "bun:test";
import { MOCK_STEPS } from "@/lib/demo/mock";
import { RUBRIC } from "@/lib/demo/mock/check";
import { CRITERIA } from "@/lib/demo/mock/criteria";
import { PEER_FIELDS } from "@/lib/demo/mock/peers";
import type { StepData, StepId } from "@/lib/demo/types";

// The sample data is meant to earn trust, so every number shown in one
// place must agree with the same number shown anywhere else.

function step(id: StepId): StepData {
  return MOCK_STEPS.find((candidate) => candidate.id === id)!;
}

function metricValue(stepData: StepData, label: string): string {
  return stepData.metrics.find((metric) => metric.label === label)!.value;
}

function tableRows(stepData: StepData, tableId: string) {
  return stepData.tables!.find((table) => table.table_id === tableId)!.rows;
}

describe("sample protocol mock consistency", () => {
  it("lists every extracted criterion, matching the ingest headline", () => {
    const ingest = step("ingest");
    const rows = tableRows(ingest, "tbl-ing-criteria-list");
    expect(rows).toHaveLength(Number(ingest.headline.value));
    expect(rows.filter((row) => row.type === "inclusion")).toHaveLength(14);
    expect(rows.filter((row) => row.type === "exclusion")).toHaveLength(20);
  });

  it("counts rubric statuses exactly as the check metrics say", () => {
    const check = step("check");
    const countOf = (status: string) =>
      RUBRIC.filter((row) => row.status === status).length;
    expect(RUBRIC).toHaveLength(14);
    expect(String(countOf("present"))).toBe(metricValue(check, "Present"));
    expect(String(countOf("weak"))).toBe(metricValue(check, "Weak"));
    expect(String(countOf("missing"))).toBe(metricValue(check, "Missing"));
    expect(String(countOf("missing"))).toBe(check.headline.value);
    expect(
      String(RUBRIC.filter((row) => row.flag === "contradiction").length)
    ).toBe(metricValue(check, "Contradictions"));
  });

  it("marks as outliers exactly the peer fields outside P10-P90", () => {
    for (const field of PEER_FIELDS) {
      const isOutside = field.draft < field.p10 || field.draft > field.p90;
      expect(field.verdict).toBe(isOutside ? "outlier" : "in range");
    }
    const outliers = PEER_FIELDS.filter((row) => row.verdict === "outlier");
    expect(String(outliers.length)).toBe(metricValue(step("peers"), "Outliers"));
  });

  it("adds the attrition waterfall up to the eligible count", () => {
    const cohort = step("cohort");
    const points = cohort.charts!.find(
      (chart) => chart.kind === "waterfall"
    )!.series[0].points;
    const total = points.reduce((sum, point) => sum + point.value, 0);
    expect(points[0].value).toBe(18_402);
    expect(points.slice(1).every((point) => point.value < 0)).toBe(true);
    expect(total).toBe(2_115);
    expect(points.find((point) => point.label === "eGFR below 45")!.value)
      .toBe(-3_066);
  });

  it("runs the per-criterion funnel from 18,402 to 2,115", () => {
    const rows = tableRows(step("cohort"), "tbl-coh-filters");
    expect(rows.map((row) => row.criterion_id).sort()).toEqual(
      CRITERIA.map((criterion) => criterion.id).sort()
    );
    const simulated = rows.filter((row) => row.status === "simulated");
    expect(simulated[0].before).toBe(18_402);
    expect(simulated.at(-1)!.remaining).toBe(2_115);
    const egfr = rows.find((row) => row.criterion_id === "E-05")!;
    expect([egfr.before, egfr.removed]).toEqual([9_891, 3_066]);
    expect(
      rows.filter((row) => row.status === "cannot simulate")
    ).toHaveLength(Number(metricValue(step("cohort"), "Cannot simulate")));
  });

  it("recommends exactly one option whenever a decision has options", () => {
    for (const decision of MOCK_STEPS.flatMap((s) => s.decisions)) {
      if (!decision.options?.length) continue;
      const recommended = decision.options.filter((o) => o.is_recommended);
      expect(recommended).toHaveLength(1);
    }
  });

  it("keeps every quote verbatim inside its context", () => {
    for (const decision of MOCK_STEPS.flatMap((s) => s.decisions)) {
      for (const evidence of decision.evidence) {
        if (evidence.context) {
          expect(evidence.context).toContain(evidence.quote);
        }
      }
    }
  });

  it("times every step and trace entry consistently", () => {
    for (const stepData of MOCK_STEPS) {
      const startMs = Date.parse(stepData.started_at!);
      const endMs = Date.parse(stepData.completed_at!);
      expect(endMs - startMs).toBe(stepData.duration_ms!);
      for (const decision of stepData.decisions) {
        for (const entry of decision.trace) {
          const entryStartMs = Date.parse(entry.timestamp!);
          expect(entryStartMs).toBeGreaterThanOrEqual(startMs);
          expect(entryStartMs + entry.duration_ms!).toBeLessThanOrEqual(endMs);
        }
      }
    }
  });

  it("uses only placeholder trial registry IDs", () => {
    const ids = JSON.stringify(MOCK_STEPS).match(/NCT\d+/g) ?? [];
    expect(ids.length).toBeGreaterThan(0);
    for (const id of ids) expect(id).toMatch(/^NCT0000000\d$/);
  });
});
