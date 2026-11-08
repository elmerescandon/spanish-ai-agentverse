"use client";

import type { ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { Severity } from "@/lib/api";
import {
  formatClockTime,
  formatConfidence,
  formatDuration,
  formatLocationParts,
  resolveDurationMs,
} from "@/lib/demo/format";
import { MAX_STEP_METRICS } from "@/lib/demo/traceability";
import type { Decision, StepData, StepStatus } from "@/lib/demo/types";
import ChartView from "./ChartView";
import Collapsible from "./Collapsible";
import DataSourceList from "./DataSourceList";
import DataTableView from "./DataTableView";
import MetricList from "./MetricList";
import SectionTitle from "./SectionTitle";
import SlideDown from "./SlideDown";
import WarningList from "./WarningList";

const SEVERITY_DOT: Record<Severity, string> = {
  info: "bg-zinc-300",
  warning: "bg-amber-500",
  critical: "bg-rose-500",
};

const SEVERITY_LABEL: Record<Severity, string> = {
  info: "Info",
  warning: "Warning",
  critical: "Critical",
};

const STATUS_STYLES: Record<StepStatus, { label: string; className: string }> =
  {
    completed: {
      label: "Completed",
      className: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    },
    partial: {
      label: "Partial",
      className: "bg-amber-50 text-amber-800 ring-amber-200",
    },
    failed: {
      label: "Failed",
      className: "bg-rose-50 text-rose-800 ring-rose-200",
    },
  };

export interface StepViewProps {
  step: StepData;
  // Findings shown open under their row; ids are unique across steps.
  expandedDecisionIds?: ReadonlySet<string>;
  onToggleDecision: (decisionId: string) => void;
  renderDecision: (decision: Decision) => ReactNode;
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
  const status = step.status ? STATUS_STYLES[step.status] : null;

  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-sans text-xs text-zinc-500">
      {status && (
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${status.className}`}
        >
          {status.label}
        </span>
      )}
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

/**
 * One step: summary and key figures side by side, then one row per agent
 * finding that opens in place, then the step's tables, charts and sources.
 */
export default function StepView({
  step,
  expandedDecisionIds = new Set<string>(),
  onToggleDecision,
  renderDecision,
}: StepViewProps) {
  const charts = step.charts ?? [];
  const tables = step.tables ?? [];
  const dataSources = step.data_sources ?? [];
  const metrics = step.metrics.slice(0, MAX_STEP_METRICS);

  return (
    <section aria-label={step.title} className="space-y-6">
      <div
        className={
          metrics.length > 0
            ? "grid gap-x-10 gap-y-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:items-start"
            : undefined
        }
      >
        <header className="space-y-1.5">
          <h1 className="font-serif text-2xl font-normal tracking-tight text-zinc-900">
            {step.title}
          </h1>
          <RunLine step={step} />
          <p className="font-sans text-sm text-zinc-500">{step.summary}</p>
        </header>
        <MetricList metrics={metrics} />
      </div>

      <WarningList warnings={step.warnings ?? []} />

      <ul className="divide-y divide-zinc-200/60 border-y border-zinc-200/60">
        {step.decisions.map((decision) => {
          const meta = findingMeta(decision);
          const isExpanded = expandedDecisionIds.has(decision.decision_id);
          const panelId = `finding-${decision.decision_id}`;
          const Chevron = isExpanded ? ChevronDown : ChevronRight;
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
                className={`flex w-full cursor-pointer items-start gap-3 px-1 py-3 text-left transition-colors hover:bg-zinc-50 ${
                  isExpanded ? "bg-zinc-50/60" : ""
                }`}
              >
                <Chevron
                  className="mt-0.5 h-4 w-4 shrink-0 text-zinc-400"
                  strokeWidth={1.5}
                  aria-hidden
                />
                <span
                  role="img"
                  aria-label={SEVERITY_LABEL[decision.severity]}
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    SEVERITY_DOT[decision.severity]
                  }`}
                />
                <span className="min-w-0 flex-1 space-y-0.5">
                  <span className="block font-sans text-sm text-zinc-900">
                    {decision.title}
                  </span>
                  {meta.length > 0 && (
                    <span className="block font-sans text-xs text-zinc-500">
                      {meta.join(" · ")}
                    </span>
                  )}
                  {decision.claim && !isExpanded && (
                    <span className="block truncate font-sans text-xs text-zinc-400">
                      {decision.claim}
                    </span>
                  )}
                </span>
                <span className="shrink-0 font-sans text-xs text-zinc-400">
                  {SEVERITY_LABEL[decision.severity]}
                </span>
              </button>
              <SlideDown
                id={panelId}
                isOpen={isExpanded}
                className="px-1 pb-6 pl-8 pt-2"
              >
                {renderDecision(decision)}
              </SlideDown>
            </li>
          );
        })}
      </ul>

      {/* Open by default: the per-item rows are what reviewers check
          before trusting a step's totals. */}
      {tables.length > 0 && (
        <Collapsible
          title="Evaluated items"
          count={tables.length}
          isInitiallyOpen
        >
          <div className="space-y-6">
            {tables.map((table) => (
              <DataTableView key={table.table_id} table={table} />
            ))}
          </div>
        </Collapsible>
      )}

      {charts.length > 0 && (
        <Collapsible title="Charts" count={charts.length} isInitiallyOpen>
          <div className="grid gap-6 lg:grid-cols-2">
            {charts.map((chart) => (
              <ChartView key={chart.chart_id} chart={chart} />
            ))}
          </div>
        </Collapsible>
      )}

      {dataSources.length > 0 && (
        <section aria-label="Data sources" className="space-y-1">
          <SectionTitle>Data sources</SectionTitle>
          <DataSourceList sources={dataSources} />
        </section>
      )}
    </section>
  );
}
