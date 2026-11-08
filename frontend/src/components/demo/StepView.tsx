"use client";

import type { ReactNode } from "react";
import type { Severity } from "@/lib/api";
import {
  formatClockTime,
  formatConfidence,
  formatDuration,
  formatLocationParts,
  resolveDurationMs,
} from "@/lib/demo/format";
import { MAX_STEP_METRICS } from "@/lib/demo/traceability";
import type {
  Decision,
  ReviewStatus,
  StepData,
  StepStatus,
} from "@/lib/demo/types";
import ChartView from "./ChartView";
import Collapsible from "./Collapsible";
import DataSourceList from "./DataSourceList";
import DataTableView from "./DataTableView";
import MetricList from "./MetricList";
import SectionTitle from "./SectionTitle";
import SlideDown from "./SlideDown";
import WarningList from "./WarningList";

// Only findings that need attention get a coloured severity word.
const SEVERITY_TEXT: Record<Severity, string> = {
  info: "text-zinc-400",
  warning: "text-amber-700",
  critical: "text-rose-700",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  info: "Info",
  warning: "Warning",
  critical: "Critical",
};

const STATUS_LABEL: Record<StepStatus, string> = {
  completed: "Completed",
  partial: "Partial",
  failed: "Failed",
};

export interface StepViewProps {
  step: StepData;
  // Findings shown open under their row; ids are unique across steps.
  expandedDecisionIds?: ReadonlySet<string>;
  onToggleDecision: (decisionId: string) => void;
  renderDecision: (decision: Decision) => ReactNode;
  getReviewStatus?: (decisionId: string) => ReviewStatus | undefined;
}

/** "Completeness agent · 4.2 s · 10:31:04–10:31:08", empty parts dropped. */
function RunLine({ step }: { step: StepData }) {
  const durationMs = resolveDurationMs(
    step.duration_ms,
    step.started_at,
    step.completed_at
  );
  const startTime = step.started_at ? formatClockTime(step.started_at) : null;
  const endTime = step.completed_at
    ? formatClockTime(step.completed_at)
    : null;
  const timeRange = [startTime, endTime].filter(Boolean).join("–");
  const parts = [
    step.agent ?? null,
    durationMs != null ? formatDuration(durationMs) : null,
    timeRange || null,
  ].filter((part): part is string => Boolean(part));

  if (!step.status && parts.length === 0) return null;
  return (
    <p className="font-sans text-sm text-zinc-500">
      {step.status && <span>{STATUS_LABEL[step.status]}</span>}
      {step.status && parts.length > 0 && " · "}
      {parts.length > 0 && <span>{parts.join(" · ")}</span>}
    </p>
  );
}

/** Category, confidence and location under a finding's title. */
function findingMeta(decision: Decision): string[] {
  return [
    decision.category ?? null,
    decision.confidence != null
      ? formatConfidence(decision.confidence)
      : null,
    ...formatLocationParts(decision.location),
  ].filter((part): part is string => Boolean(part));
}

const SECTION_ANCHORS = {
  findings: "section-findings",
  tables: "section-tables",
  charts: "section-charts",
  sources: "section-sources",
} as const;

/**
 * One step as a single column, top to bottom: title and run line, summary,
 * key figures, warnings, findings (each opens in place), then tables,
 * charts and sources. A slim "Jump to" line comes after the figures.
 */
export default function StepView({
  step,
  expandedDecisionIds = new Set<string>(),
  onToggleDecision,
  renderDecision,
  getReviewStatus,
}: StepViewProps) {
  const charts = step.charts ?? [];
  const tables = step.tables ?? [];
  const dataSources = step.data_sources ?? [];
  const metrics = step.metrics.slice(0, MAX_STEP_METRICS);

  const jumpLinks = [
    step.decisions.length > 0 && ["Findings", SECTION_ANCHORS.findings],
    tables.length > 0 && ["Tables", SECTION_ANCHORS.tables],
    charts.length > 0 && ["Charts", SECTION_ANCHORS.charts],
    dataSources.length > 0 && ["Data sources", SECTION_ANCHORS.sources],
  ].filter((link): link is string[] => Array.isArray(link));

  return (
    <section
      aria-label={step.title}
      className="space-y-10 pb-16 pt-4"
    >
      <header className="space-y-3">
        <h1 className="font-serif text-3xl font-normal tracking-tight text-zinc-900">
          {step.title}
        </h1>
        <RunLine step={step} />
        {step.summary && (
          <p className="pt-2 font-serif text-base leading-relaxed text-zinc-800">
            {step.summary}
          </p>
        )}
      </header>

      {metrics.length > 0 && <MetricList metrics={metrics} />}

      <WarningList warnings={step.warnings ?? []} />

      {jumpLinks.length > 1 && (
        <nav
          aria-label="Jump to"
          className="font-sans text-sm text-zinc-500"
        >
          Jump to:{" "}
          {jumpLinks.map(([label, anchor], index) => (
            <span key={anchor}>
              {index > 0 && " · "}
              <a
                href={`#${anchor}`}
                className="underline underline-offset-4 hover:text-zinc-900"
              >
                {label}
              </a>
            </span>
          ))}
        </nav>
      )}

      {step.decisions.length > 0 && (
        <section
          id={SECTION_ANCHORS.findings}
          aria-label="Findings"
          className="scroll-mt-32 space-y-2"
        >
          <SectionTitle>Findings</SectionTitle>
          <ul className="divide-y divide-zinc-200/60">
            {step.decisions.map((decision) => {
              const meta = findingMeta(decision);
              const isExpanded = expandedDecisionIds.has(
                decision.decision_id
              );
              const panelId = `finding-${decision.decision_id}`;
              const reviewStatus = getReviewStatus?.(decision.decision_id);
              return (
                <li
                  key={decision.decision_id}
                  id={`finding-row-${decision.decision_id}`}
                  // Clears the sticky header and step bar when jumped to.
                  className="scroll-mt-44"
                >
                  <button
                    type="button"
                    aria-expanded={isExpanded}
                    aria-controls={panelId}
                    onClick={() => onToggleDecision(decision.decision_id)}
                    className="flex w-full cursor-pointer items-start gap-6 py-4 text-left"
                  >
                    <span className="min-w-0 flex-1 space-y-1">
                      <span className="block font-sans text-base font-medium text-zinc-900">
                        {decision.title}
                      </span>
                      {decision.claim && (
                        <span className="block font-serif text-base leading-relaxed text-zinc-700">
                          {decision.claim}
                        </span>
                      )}
                      {meta.length > 0 && (
                        <span className="block font-sans text-sm text-zinc-500">
                          {meta.join(" · ")}
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 space-y-1 text-right font-sans text-sm">
                      {reviewStatus === "accepted" && (
                        <span className="block text-emerald-700">
                          ✓ Accepted
                        </span>
                      )}
                      {reviewStatus === "rejected" && (
                        <span className="block text-zinc-500">Declined</span>
                      )}
                      {decision.severity !== "info" && (
                        <span
                          className={`block ${
                            SEVERITY_TEXT[decision.severity]
                          }`}
                        >
                          {SEVERITY_LABEL[decision.severity]}
                        </span>
                      )}
                      <span
                        aria-hidden
                        className="block text-zinc-500 underline underline-offset-4"
                      >
                        {isExpanded ? "Collapse" : "Expand"}
                      </span>
                    </span>
                  </button>
                  <SlideDown id={panelId} isOpen={isExpanded} className="pb-6">
                    {renderDecision(decision)}
                  </SlideDown>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Open by default: the per-item rows are what reviewers check
          before trusting a step's totals. */}
      {tables.length > 0 && (
        <Collapsible
          id={SECTION_ANCHORS.tables}
          title="Evaluated items"
          count={tables.length}
          isInitiallyOpen
        >
          <div className="space-y-8">
            {tables.map((table) => (
              <DataTableView key={table.table_id} table={table} />
            ))}
          </div>
        </Collapsible>
      )}

      {charts.length > 0 && (
        <Collapsible
          id={SECTION_ANCHORS.charts}
          title="Charts"
          count={charts.length}
          isInitiallyOpen
        >
          <div className="grid gap-8 lg:grid-cols-2">
            {charts.map((chart) => (
              <ChartView key={chart.chart_id} chart={chart} />
            ))}
          </div>
        </Collapsible>
      )}

      {dataSources.length > 0 && (
        <section
          id={SECTION_ANCHORS.sources}
          aria-label="Data sources"
          className="scroll-mt-32 space-y-3"
        >
          <SectionTitle>Data sources</SectionTitle>
          <DataSourceList sources={dataSources} />
        </section>
      )}
    </section>
  );
}
