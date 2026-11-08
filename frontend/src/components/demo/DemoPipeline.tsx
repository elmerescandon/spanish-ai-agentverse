"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import ProtocolIngestion from "@/components/ProtocolIngestion";
import DecisionView from "./DecisionView";
import StepBar, { type StepBarState } from "./StepBar";
import StepView from "./StepView";
import {
  RECOMMENDATION_ENDPOINTS,
  uploadProtocolFile,
  type RecommendationFetcher,
} from "@/lib/api";
import {
  MOCK_RECOMMENDATION_FETCHERS,
  MOCK_STEPS,
  MOCK_UPLOAD_RESPONSE,
} from "@/lib/demo/mock";
import type {
  Decision,
  RecommendationStepId,
  StepData,
  StepId,
  UploadFileResponse,
} from "@/lib/demo/types";

export interface DemoPipelineProps {
  // Injectable so tests can pass fakes; default to the real API calls.
  uploadFile?: (file: File) => Promise<UploadFileResponse>;
  recommendationFetchers?: Record<RecommendationStepId, RecommendationFetcher>;
  // What the sample protocol button plays back: endpoint-shaped mocks.
  sampleUpload?: UploadFileResponse;
  sampleFetchers?: Record<RecommendationStepId, RecommendationFetcher>;
}

// Results of a real upload; each step fills in as its own call settles.
interface LiveRun {
  results: Partial<Record<StepId, StepData>>;
  errors: Partial<Record<StepId, string>>;
}

type UploadState =
  | { status: "idle" }
  | { status: "uploading" }
  | { status: "error"; message: string };

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
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
 * Upload (or the sample) first, then a step bar whose steps fill in as
 * each agent's response arrives. The sample runs the same flow with
 * mock responses, so it behaves like the real endpoints.
 */
export default function DemoPipeline({
  uploadFile = uploadProtocolFile,
  recommendationFetchers = RECOMMENDATION_ENDPOINTS,
  sampleUpload = MOCK_UPLOAD_RESPONSE,
  sampleFetchers = MOCK_RECOMMENDATION_FETCHERS,
}: DemoPipelineProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [liveRun, setLiveRun] = useState<LiveRun | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>({
    status: "idle",
  });
  // Until a step's data arrives, the bar still needs its title.
  const steps = useMemo<StepData[]>(
    () =>
      MOCK_STEPS.map(
        (step) =>
          liveRun?.results[step.id] ?? {
            ...step,
            summary: "",
            metrics: [],
            decisions: [],
          }
      ),
    [liveRun]
  );
  const [view, setView] = useState<View>({
    stepId: steps[0].id,
    decisionId: null,
  });
  const [stepChangeCount, setStepChangeCount] = useState(0);

  // Ingest comes with the upload; the other agents run in parallel and
  // each settles on its own.
  const runPipeline = (
    upload: UploadFileResponse,
    fetchers: Record<RecommendationStepId, RecommendationFetcher>
  ) => {
    setLiveRun({ results: { ingest: upload.step }, errors: {} });
    setIsLoaded(true);

    for (const [stepId, fetchStep] of Object.entries(fetchers) as [
      RecommendationStepId,
      RecommendationFetcher,
    ][]) {
      fetchStep(upload.protocol_id).then(
        (data) =>
          setLiveRun((run) =>
            run && { ...run, results: { ...run.results, [stepId]: data } }
          ),
        (error: unknown) =>
          setLiveRun((run) =>
            run && {
              ...run,
              errors: { ...run.errors, [stepId]: toErrorMessage(error) },
            }
          )
      );
    }
  };

  const loadSample = () => runPipeline(sampleUpload, sampleFetchers);

  const startLiveRun = async (file: File) => {
    setUploadState({ status: "uploading" });
    let upload: UploadFileResponse;
    try {
      upload = await uploadFile(file);
    } catch (error) {
      setUploadState({ status: "error", message: toErrorMessage(error) });
      return;
    }
    setUploadState({ status: "idle" });
    runPipeline(upload, recommendationFetchers);
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

  const barItems = steps.map((step) => {
    const state: StepBarState = liveRun?.results[step.id]
      ? "done"
      : liveRun?.errors[step.id]
        ? "error"
        : "running";
    return { id: step.id, title: step.title, state };
  });

  // Only a change of step animates the content; first render and opening a
  // finding within the same step do not.
  const goTo = useCallback(
    (next: View) => {
      if (next.stepId !== view.stepId) {
        setStepChangeCount((count) => count + 1);
      }
      setView(next);
    },
    [view.stepId]
  );

  const openStep = useCallback(
    (id: string) => goTo({ stepId: id as StepId, decisionId: null }),
    [goTo]
  );

  const openDecision = (decisionId: string) => {
    const decision = decisionsById.get(decisionId);
    if (!decision) return;
    goTo({ stepId: decision.step_id, decisionId });
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
        <ProtocolIngestion
          onProtocolLoaded={loadSample}
          onPdfSelected={startLiveRun}
          isCompact
        />
        {uploadState.status === "uploading" && (
          <p role="status" className="text-center font-sans text-sm text-zinc-500">
            Uploading protocol...
          </p>
        )}
        {uploadState.status === "error" && (
          <p role="alert" className="text-center font-sans text-sm text-rose-700">
            {uploadState.message}
          </p>
        )}
      </div>
    );
  }

  const currentStep = steps.find((s) => s.id === view.stepId) ?? steps[0];
  const stepError = liveRun?.errors[currentStep.id];
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
        key={stepChangeCount}
        className={stepChangeCount > 0 ? "animate-file-change" : undefined}
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
        ) : stepError ? (
          <section aria-label={currentStep.title} className="space-y-2">
            <h1 className="font-serif text-2xl font-normal tracking-tight text-zinc-900">
              {currentStep.title}
            </h1>
            <p role="alert" className="font-sans text-sm text-rose-700">
              {stepError}
            </p>
          </section>
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
