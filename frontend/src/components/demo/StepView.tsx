"use client";

import type { Severity } from "@/lib/api";
import type {
  HumanDecision,
  MetricTone,
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

export interface StepViewProps {
  step: StepData;
  humanDecisions: Record<string, HumanDecision>;
  onOpenDecision: (decisionId: string) => void;
}

function statusLabel(human: HumanDecision | undefined): string {
  if (!human) return "Pending";
  return human.status === "accepted" ? "Accepted" : "Dismissed";
}

/** Zoomed-in level: key figures and one line per agent finding. */
export default function StepView({
  step,
  humanDecisions,
  onOpenDecision,
}: StepViewProps) {
  return (
    <section aria-label={step.title} className="space-y-8">
      <header className="space-y-1">
        <h1 className="font-serif text-3xl font-normal tracking-tight text-zinc-900">
          {step.title}
        </h1>
        <p className="font-sans text-sm text-zinc-500">{step.summary}</p>
      </header>

      <dl className="grid grid-cols-2 gap-x-6 gap-y-5 border-l-2 border-emerald-500 pl-5 sm:grid-cols-4">
        {step.metrics.map((metric) => (
          <div key={metric.label} className="space-y-0.5">
            <dd
              className={`font-serif text-2xl font-normal tracking-tight ${
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

      <div className="space-y-3">
        <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
          Agent findings
        </h2>
        <ul className="divide-y divide-zinc-200/60 rounded-xl border border-zinc-200/60 bg-white/80">
          {step.decisions.map((decision) => {
            const human = humanDecisions[decision.decision_id];
            return (
              <li key={decision.decision_id}>
                <button
                  type="button"
                  onClick={() => onOpenDecision(decision.decision_id)}
                  className="flex w-full cursor-pointer items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-zinc-50"
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
                  <span
                    className={`shrink-0 font-sans text-xs ${
                      human ? "text-emerald-700" : "text-zinc-400"
                    }`}
                  >
                    {statusLabel(human)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
