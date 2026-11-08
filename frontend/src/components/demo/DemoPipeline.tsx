"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import ProtocolIngestion from "@/components/ProtocolIngestion";
import DecisionView from "./DecisionView";
import StepBar, { type StepBarState } from "./StepBar";
import StepView from "./StepView";
import { MOCK_STEPS } from "@/lib/demo/mock";
import type { Decision, StepData, StepId } from "@/lib/demo/types";

// Fake agent latency so the running state is visible in the mock.
const RUN_DELAY_MS = 700;

export interface DemoPipelineProps {
  steps?: StepData[];
}

interface View {
  stepId: StepId;
  decisionId: string | null;
}

function isTextEntry(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return (
    element?.tagName === "INPUT" ||
    element?.tagName === "TEXTAREA" ||
    element?.isContentEditable === true
  );
}

/**
 * Upload (or preset) first, then a step bar over a sequential flow that
 * runs by itself. Steps are presentational and take their data as props.
 */
export default function DemoPipeline({
  steps = MOCK_STEPS,
}: DemoPipelineProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [completedCount, setCompletedCount] = useState(0);
  const [view, setView] = useState<View>({
    stepId: steps[0].id,
    decisionId: null,
  });

  // The rest of the steps follow the upload one by one.
  useEffect(() => {
    if (!isLoaded) return;
    if (completedCount >= steps.length) return;
    const timer = setTimeout(
      () => setCompletedCount((count) => count + 1),
      RUN_DELAY_MS
    );
    return () => clearTimeout(timer);
  }, [isLoaded, completedCount, steps.length]);

  // Ingest is the upload itself, so it is done as soon as it loads.
  const loadProtocol = () => {
    setIsLoaded(true);
    setCompletedCount(1);
  };

  const decisionsById = useMemo(() => {
    const index = new Map<string, Decision>();
    for (const step of steps) {
      for (const decision of step.decisions) {
        index.set(decision.decision_id, decision);
      }
    }
    return index;
  }, [steps]);

  const barItems = steps.map((step, index) => {
    const state: StepBarState =
      index < completedCount
        ? "done"
        : index === completedCount
          ? "running"
          : "pending";
    return { id: step.id, title: step.title, state };
  });

  const openStep = useCallback((id: string) => {
    setView({ stepId: id as StepId, decisionId: null });
  }, []);

  const openDecision = (decisionId: string) => {
    const decision = decisionsById.get(decisionId);
    if (!decision) return;
    setView({ stepId: decision.step_id, decisionId });
  };

  const closeDecision = useCallback(() => {
    setView((current) => ({ ...current, decisionId: null }));
  }, []);

  const hasOpenDecision = view.decisionId !== null;
  useEffect(() => {
    if (!hasOpenDecision) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isTextEntry(event.target)) {
        closeDecision();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasOpenDecision, closeDecision]);

  if (!isLoaded) {
    return (
      <div className="mx-auto flex min-h-[80vh] max-w-xl flex-col justify-center space-y-8">
        <h1 className="text-center font-serif text-4xl font-normal tracking-tight text-zinc-900">
          Analyze a draft protocol
        </h1>
        <ProtocolIngestion onProtocolLoaded={loadProtocol} isCompact />
      </div>
    );
  }

  const currentStep = steps.find((s) => s.id === view.stepId) ?? steps[0];
  const currentDecision = view.decisionId
    ? (decisionsById.get(view.decisionId) ?? null)
    : null;

  return (
    <div className="space-y-6">
      <StepBar
        items={barItems}
        activeId={view.stepId}
        onSelect={openStep}
      />

      <div
        key={`${currentStep.id}-${currentDecision?.decision_id ?? ""}`}
        className="animate-file-change"
      >
        {currentDecision ? (
          <div className="space-y-4">
            <button
              type="button"
              onClick={closeDecision}
              aria-label="Back to findings"
              className="inline-flex cursor-pointer items-center gap-1.5 font-sans text-xs text-zinc-500 transition-colors hover:text-zinc-900"
            >
              <ArrowLeft className="h-3 w-3" strokeWidth={1.5} />
              All findings
            </button>
            <DecisionView
              key={currentDecision.decision_id}
              decision={currentDecision}
              parents={(currentDecision.derived_from ?? []).flatMap((id) => {
                const parent = decisionsById.get(id);
                return parent
                  ? [{ decision_id: id, title: parent.title }]
                  : [];
              })}
              onOpenParent={openDecision}
            />
          </div>
        ) : (
          <StepView
            step={currentStep}
            onOpenDecision={openDecision}
          />
        )}
      </div>
    </div>
  );
}
