"use client";

import type { Severity } from "@/lib/api";
import type {
  MetricTone,
  ReviewResolution,
  ReviewThread,
  StepData,
} from "@/lib/demo/types";

const TONE_CLASSES: Record<MetricTone, string> = {
  neutral: "text-zinc-900",
  good: "text-emerald-700",
  warn: "text-amber-700",
  risk: "text-rose-700",
};

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

const RESOLUTION_LABEL: Record<ReviewResolution, string> = {
  open: "Open",
  accepted: "Accepted",
  rejected: "Rejected",
};

export interface StepViewProps {
  step: StepData;
  threads: Record<string, ReviewThread>;
  onOpenDecision: (decisionId: string) => void;
}

function commentCountLabel(count: number): string {
  return `${count} ${count === 1 ? "comment" : "comments"}`;
}

/** One step: summary line, key figures and one row per agent finding. */
export default function StepView({
  step,
  threads,
  onOpenDecision,
}: StepViewProps) {
  return (
    <section aria-label={step.title} className="space-y-5">
      <header className="space-y-1">
        <h1 className="font-serif text-2xl font-normal tracking-tight text-zinc-900">
          {step.title}
        </h1>
        <p className="font-sans text-sm text-zinc-500">{step.summary}</p>
      </header>

      <dl className="flex flex-wrap gap-x-8 gap-y-2">
        {step.metrics.map((metric) => (
          <div key={metric.label} className="flex items-baseline gap-1.5">
            <dd
              className={`font-serif text-lg font-normal ${
                TONE_CLASSES[metric.tone ?? "neutral"]
              }`}
            >
              {metric.value}
            </dd>
            <dt className="font-sans text-xs text-zinc-500">
              {metric.label}
            </dt>
          </div>
        ))}
      </dl>

      <ul className="divide-y divide-zinc-200/60 border-y border-zinc-200/60">
        {step.decisions.map((decision) => {
          const thread = threads[decision.decision_id];
          const resolution = thread?.resolution ?? "open";
          const commentCount = thread?.comments.length ?? 0;
          return (
            <li key={decision.decision_id}>
              <button
                type="button"
                onClick={() => onOpenDecision(decision.decision_id)}
                className="flex w-full cursor-pointer items-center gap-3 px-1 py-3 text-left transition-colors hover:bg-zinc-50"
              >
                <span
                  role="img"
                  aria-label={SEVERITY_LABEL[decision.severity]}
                  className={`h-2 w-2 shrink-0 rounded-full ${
                    SEVERITY_DOT[decision.severity]
                  }`}
                />
                <span className="flex-1 font-sans text-sm text-zinc-900">
                  {decision.title}
                </span>
                {commentCount > 0 && (
                  <span className="shrink-0 font-sans text-xs text-zinc-400">
                    {commentCountLabel(commentCount)}
                  </span>
                )}
                <span
                  className={`shrink-0 font-sans text-xs ${
                    resolution === "open"
                      ? "text-zinc-400"
                      : "text-emerald-700"
                  }`}
                >
                  {RESOLUTION_LABEL[resolution]}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
