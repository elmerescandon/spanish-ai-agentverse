"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Download } from "lucide-react";
import ProtocolIngestion from "@/components/ProtocolIngestion";
import DecisionView from "./DecisionView";
import StepBar, { type StepBarState } from "./StepBar";
import StepView from "./StepView";
import {
  LATEST_REPORT_PDF_URL,
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
  const [activeStepId, setActiveStepId] = useState<StepId>(steps[0].id);
  // Findings opened in place; kept per id so returning to a step keeps them.
  const [expandedDecisionIds, setExpandedDecisionIds] = useState<
    ReadonlySet<string>
  >(new Set());
  // Set when a "builds on" link opens a finding, so it scrolls into view.
  const scrollTargetId = useRef<string | null>(null);
  const [stepChangeCount, setStepChangeCount] = useState(0);
  // Which way the last step change moved, so the content slides in from
  // that side.
  const [slideDirection, setSlideDirection] = useState<"forward" | "back">(
    "forward"
  );

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

  const activeIndex = barItems.findIndex((item) => item.id === activeStepId);
  const previousItem = activeIndex > 0 ? barItems[activeIndex - 1] : null;
  const nextItem =
    activeIndex >= 0 && activeIndex < barItems.length - 1
      ? barItems[activeIndex + 1]
      : null;

  // Only a change of step animates the content; first render and opening a
  // finding within the same step do not.
  const openStep = useCallback(
    (id: string) => {
      if (id !== activeStepId) {
        const stepIds = steps.map((step) => step.id as string);
        setSlideDirection(
          stepIds.indexOf(id) < stepIds.indexOf(activeStepId)
            ? "back"
            : "forward"
        );
        setStepChangeCount((count) => count + 1);
      }
      setActiveStepId(id as StepId);
    },
    [activeStepId, steps]
  );

  const toggleDecision = (decisionId: string) =>
    setExpandedDecisionIds((current) => {
      const next = new Set(current);
      if (!next.delete(decisionId)) next.add(decisionId);
      return next;
    });

  const openParentDecision = (decisionId: string) => {
    const decision = decisionsById.get(decisionId);
    if (!decision) return;
    openStep(decision.step_id);
    setExpandedDecisionIds((current) => new Set(current).add(decisionId));
    scrollTargetId.current = decisionId;
  };

  // Runs after the jump renders the target step with the finding open.
  useEffect(() => {
    if (!scrollTargetId.current) return;
    document
      .getElementById(`finding-row-${scrollTargetId.current}`)
      // jsdom has no scrollIntoView.
      ?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    scrollTargetId.current = null;
  }, [activeStepId, expandedDecisionIds]);

  const hasExpandedDecision = expandedDecisionIds.size > 0;
  useEffect(() => {
    if (!hasExpandedDecision) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isTextEntry(event.target)) {
        setExpandedDecisionIds(new Set());
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [hasExpandedDecision]);

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

  const currentStep = steps.find((s) => s.id === activeStepId) ?? steps[0];
  const stepError = liveRun?.errors[currentStep.id];

  return (
    <div className="space-y-2">
      <StepBar
        items={barItems}
        activeId={activeStepId}
        onSelect={openStep}
        trailing={
          nextItem === null && (
            <a
              href={LATEST_REPORT_PDF_URL}
              download
              className="flex shrink-0 items-center gap-1.5 rounded-full border border-zinc-900 bg-zinc-900 px-3 py-1.5 font-sans text-xs text-white transition-colors hover:bg-zinc-700"
            >
              <Download className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden />
              Download report (PDF)
            </a>
          )
        }
      />

      <div
        key={stepChangeCount}
        className={
          stepChangeCount > 0
            ? slideDirection === "back"
              ? "animate-step-back"
              : "animate-step-forward"
            : undefined
        }
      >
        {stepError ? (
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
            expandedDecisionIds={expandedDecisionIds}
            onToggleDecision={toggleDecision}
            renderDecision={(decision) => (
              <DecisionView
                decision={decision}
                parents={(decision.derived_from ?? []).flatMap((id) => {
                  const parent = decisionsById.get(id);
                  return parent
                    ? [{ decision_id: id, title: parent.title }]
                    : [];
                })}
                onOpenParent={openParentDecision}
                isInline
              />
            )}
          />
        )}
      </div>

      <nav
        aria-label="Step navigation"
        className="flex items-center justify-between border-t border-zinc-200/60 pb-16 pt-6 font-sans text-sm"
      >
        {previousItem ? (
          <button
            type="button"
            onClick={() => openStep(previousItem.id)}
            className="cursor-pointer text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900"
          >
            ← Previous: {previousItem.title}
          </button>
        ) : (
          <span />
        )}
        {nextItem ? (
          <button
            type="button"
            disabled={nextItem.state === "running"}
            onClick={() => openStep(nextItem.id)}
            className="cursor-pointer text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900 disabled:cursor-default disabled:no-underline disabled:opacity-40"
          >
            Next: {nextItem.title} →
          </button>
        ) : (
          <a
            href={LATEST_REPORT_PDF_URL}
            download
            className="cursor-pointer text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900"
          >
            Download report (PDF)
          </a>
        )}
      </nav>
    </div>
  );
}
