"use client";

import { Check, Loader2, Lock } from "lucide-react";
import type { MetricTone, StepData, StepState } from "@/lib/demo/types";

const TONE_CLASSES: Record<MetricTone, string> = {
  neutral: "text-zinc-900",
  good: "text-emerald-700",
  warn: "text-amber-700",
  risk: "text-rose-700",
};

const STATE_LABELS: Record<StepState, string> = {
  locked: "Locked",
  ready: "Ready",
  running: "Running",
  done: "Done",
};

export interface PipelineOverviewProps {
  steps: StepData[];
  stateOf: (step: StepData) => StepState;
  onRun: (step: StepData) => void;
  onOpen: (step: StepData) => void;
}

/** Zoomed-out level: the whole flow, one headline figure per step. */
export default function PipelineOverview({
  steps,
  stateOf,
  onRun,
  onOpen,
}: PipelineOverviewProps) {
  return (
    <ol className="grid gap-4 sm:grid-cols-4">
      {steps.map((step, index) => {
        const state = stateOf(step);
        const isDone = state === "done";
        const tone = step.headline.tone ?? "neutral";
        return (
          <li
            key={step.id}
            className={`relative flex flex-col gap-4 rounded-xl border border-zinc-200/60 border-t-2 bg-white/80 p-5 transition-all duration-500 ${
              isDone ? "border-t-emerald-500" : "border-t-zinc-200"
            } ${state === "locked" ? "opacity-60" : ""}`}
          >
            <div className="flex items-center justify-between">
              <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
                Step {index + 1}
              </span>
              <span className="inline-flex items-center gap-1 font-sans text-[11px] text-zinc-500">
                {state === "locked" && (
                  <Lock className="h-3 w-3" strokeWidth={1.5} aria-hidden />
                )}
                {state === "running" && (
                  <Loader2
                    className="h-3 w-3 animate-spin"
                    strokeWidth={1.5}
                    aria-hidden
                  />
                )}
                {isDone && (
                  <Check
                    className="h-3 w-3 text-emerald-600"
                    strokeWidth={2}
                    aria-hidden
                  />
                )}
                {STATE_LABELS[state]}
              </span>
            </div>

            <h2 className="font-serif text-lg font-normal leading-snug tracking-tight text-zinc-900">
              {step.title}
            </h2>

            <div className="mt-auto space-y-3">
              {isDone ? (
                <p>
                  <span
                    className={`block font-serif text-4xl font-normal tracking-tight ${TONE_CLASSES[tone]}`}
                  >
                    {step.headline.value}
                  </span>
                  <span className="font-sans text-xs text-zinc-500">
                    {step.headline.label}
                  </span>
                </p>
              ) : (
                <p className="font-sans text-xs text-zinc-500">
                  {step.summary}
                </p>
              )}

              {isDone && (
                <button
                  type="button"
                  onClick={() => onOpen(step)}
                  aria-label={`Open ${step.title}`}
                  className="w-full cursor-pointer rounded-lg border border-zinc-200/60 bg-white/60 px-3 py-2 font-sans text-xs font-medium text-zinc-800 backdrop-blur-sm transition-colors hover:bg-zinc-50"
                >
                  Zoom in
                </button>
              )}
              {state === "ready" && (
                <button
                  type="button"
                  onClick={() => onRun(step)}
                  aria-label={`Run ${step.title}`}
                  className="w-full cursor-pointer rounded-lg bg-zinc-900 px-3 py-2 font-sans text-xs font-medium text-white transition-colors hover:bg-zinc-800"
                >
                  Run step
                </button>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
