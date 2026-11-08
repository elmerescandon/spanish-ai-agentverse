"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import Breadcrumb, { type BreadcrumbItem } from "./Breadcrumb";
import DecisionView from "./DecisionView";
import PipelineOverview from "./PipelineOverview";
import StepView from "./StepView";
import { MOCK_STEPS } from "@/lib/demo/mock";
import type {
  Decision,
  HumanDecision,
  StepData,
  StepId,
  StepState,
} from "@/lib/demo/types";

// Fake agent latency so the running state is visible in the mock.
const RUN_DELAY_MS = 700;

type View =
  | { level: "pipeline" }
  | { level: "step"; stepId: StepId }
  | { level: "decision"; stepId: StepId; decisionId: string };

export interface DemoPipelineProps {
  steps?: StepData[];
}

/**
 * Three zoom levels over one sequential flow: pipeline, step, decision.
 * Steps are presentational and take their data as props, so other flows can
 * recombine them.
 */
export default function DemoPipeline({
  steps = MOCK_STEPS,
}: DemoPipelineProps) {
  const [view, setView] = useState<View>({ level: "pipeline" });
  const [completed, setCompleted] = useState<StepId[]>([]);
  const [running, setRunning] = useState<StepId | null>(null);
  const [humanDecisions, setHumanDecisions] = useState<
    Record<string, HumanDecision>
  >({});

  useEffect(() => {
    if (running === null) return;
    const timer = setTimeout(() => {
      setCompleted((previous) => [...previous, running]);
      setRunning(null);
    }, RUN_DELAY_MS);
    return () => clearTimeout(timer);
  }, [running]);

  const decisionsById = useMemo(() => {
    const index = new Map<string, Decision>();
    for (const step of steps) {
      for (const decision of step.decisions) {
        index.set(decision.decision_id, decision);
      }
    }
    return index;
  }, [steps]);

  const stateOf = (step: StepData): StepState => {
    if (completed.includes(step.id)) return "done";
    if (running === step.id) return "running";
    const position = steps.findIndex((s) => s.id === step.id);
    const previous = steps[position - 1];
    const isUnlocked =
      running === null && (!previous || completed.includes(previous.id));
    return isUnlocked ? "ready" : "locked";
  };

  const openDecision = (decisionId: string) => {
    const decision = decisionsById.get(decisionId);
    if (!decision) return;
    setView({
      level: "decision",
      stepId: decision.step_id,
      decisionId,
    });
  };

  const currentStep =
    view.level === "pipeline"
      ? null
      : (steps.find((s) => s.id === view.stepId) ?? null);
  const currentDecision =
    view.level === "decision"
      ? (decisionsById.get(view.decisionId) ?? null)
      : null;

  const crumbs: BreadcrumbItem[] = [
    {
      label: "Pipeline",
      onSelect: () => setView({ level: "pipeline" }),
    },
  ];
  if (currentStep) {
    crumbs.push({
      label: currentStep.title,
      onSelect: () => setView({ level: "step", stepId: currentStep.id }),
    });
  }
  if (currentDecision) {
    crumbs.push({ label: currentDecision.title });
  }

  const goBack = () => {
    if (view.level === "decision") {
      setView({ level: "step", stepId: view.stepId });
    } else {
      setView({ level: "pipeline" });
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center gap-4">
        {view.level !== "pipeline" && (
          <button
            type="button"
            onClick={goBack}
            aria-label="Zoom out"
            className="cursor-pointer rounded-full border border-zinc-200/60 p-1.5 text-zinc-500 transition-colors hover:text-zinc-900"
          >
            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        )}
        <Breadcrumb items={crumbs} />
      </div>

      {/* Re-keyed per view so each zoom level fades in. */}
      <div
        key={`${view.level}-${currentStep?.id ?? ""}-${
          currentDecision?.decision_id ?? ""
        }`}
        className="animate-file-change"
      >
        {view.level === "pipeline" && (
          <div className="space-y-10">
            <header className="space-y-2">
              <p className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
                Protocol Gap Agent
              </p>
              <h1 className="font-serif text-4xl font-normal tracking-tight text-zinc-900">
                From draft protocol to reviewed decisions
              </h1>
              <p className="font-sans text-sm text-zinc-500">
                Run each step in order, then zoom in to see what the agent
                found and why.
              </p>
            </header>
            <PipelineOverview
              steps={steps}
              stateOf={stateOf}
              onRun={(step) => setRunning(step.id)}
              onOpen={(step) =>
                setView({ level: "step", stepId: step.id })
              }
            />
          </div>
        )}

        {view.level === "step" && currentStep && (
          <StepView
            step={currentStep}
            humanDecisions={humanDecisions}
            onOpenDecision={openDecision}
          />
        )}

        {view.level === "decision" && currentDecision && (
          <DecisionView
            key={currentDecision.decision_id}
            decision={currentDecision}
            human={humanDecisions[currentDecision.decision_id]}
            parents={(currentDecision.derived_from ?? []).flatMap((id) => {
              const parent = decisionsById.get(id);
              return parent
                ? [{ decision_id: id, title: parent.title }]
                : [];
            })}
            onDecide={(decision) =>
              setHumanDecisions((previous) => ({
                ...previous,
                [currentDecision.decision_id]: decision,
              }))
            }
            onOpenParent={openDecision}
          />
        )}
      </div>
    </div>
  );
}
