"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ProtocolIngestion from "@/components/ProtocolIngestion";
import DecisionView, { type DecisionReviewState } from "./DecisionView";
import ProtocolLoading from "./ProtocolLoading";
import type { StepBarState } from "./StepBar";
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
  ReviewStatus,
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
  // Called once the last step is opened, so the page can offer the report.
  onReachEnd?: () => void;
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

const SAMPLE_LOADING_MS = 1350;

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

function isActionableDecision(decision: Decision): boolean {
  return (
    Boolean(decision.proposed_change) ||
    Boolean(decision.options?.some((option) => Boolean(option.proposed_change)))
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
  onReachEnd,
}: DemoPipelineProps) {
  const [isLoaded, setIsLoaded] = useState(false);
  const [protocolTitle, setProtocolTitle] = useState("");
  const [isSample, setIsSample] = useState(false);
  const [isInitialSampleLoad, setIsInitialSampleLoad] = useState(false);
  const [sampleRevealCount, setSampleRevealCount] = useState(0);
  useEffect(() => {
    if (!isSample) return;
    const timers = [1350, 2350, 3350, 4350].map((delay, index) =>
      setTimeout(() => setSampleRevealCount(index + 1), delay));
    return () => timers.forEach(clearTimeout);
  }, [isSample]);
  const [reviews, setReviews] = useState<Record<string, DecisionReviewState>>(
    {}
  );
  const [liveRun, setLiveRun] = useState<LiveRun | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>({
    status: "idle",
  });

  useEffect(() => {
    if (!isInitialSampleLoad) return;
    const timer = setTimeout(
      () => setIsInitialSampleLoad(false),
      SAMPLE_LOADING_MS
    );
    return () => clearTimeout(timer);
  }, [isInitialSampleLoad]);

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
    setProtocolTitle(upload.title);
    setReviews({});
    setIsLoaded(true);

    for (const [stepId, fetchStep] of Object.entries(fetchers) as [
      RecommendationStepId,
      RecommendationFetcher,
    ][]) {
      fetchStep(upload.protocol_id).then(
        (data) =>
          setLiveRun(
            (run) =>
              run && { ...run, results: { ...run.results, [stepId]: data } }
          ),
        (error: unknown) =>
          setLiveRun(
            (run) =>
              run && {
                ...run,
                errors: { ...run.errors, [stepId]: toErrorMessage(error) },
              }
          )
      );
    }
  };

  const loadSample = () => {
    setIsSample(true);
    setIsInitialSampleLoad(true);
    runPipeline(sampleUpload, sampleFetchers);
  };

  const startLiveRun = async (file: File) => {
    if (uploadState.status === "uploading") return;
    setIsSample(false);
    setIsInitialSampleLoad(false);
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

  const barItems = steps.map((step, index) => {
    const state: StepBarState = isSample && index >= sampleRevealCount
      ? "running"
      : liveRun?.results[step.id]
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
  const isOnLastStep = isLoaded && nextItem === null;

  useEffect(() => {
    if (isOnLastStep) onReachEnd?.();
  }, [isOnLastStep, onReachEnd]);

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

  useEffect(() => {
    const navigate = (event: KeyboardEvent) => {
      if (isTextEntry(event.target)) return;
      const target = event.key === "ArrowRight" ? nextItem :
        event.key === "ArrowLeft" ? previousItem : null;
      if (target && target.state !== "running") openStep(target.id);
    };
    window.addEventListener("keydown", navigate);
    return () => window.removeEventListener("keydown", navigate);
  }, [nextItem, previousItem, openStep]);

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

  if (uploadState.status === "uploading" || isInitialSampleLoad) {
    return <ProtocolLoading sample={isSample} />;
  }

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
  const actionableDecisions = steps
    .flatMap((step) => step.decisions)
    .filter(isActionableDecision);
  const reviewed = actionableDecisions.filter(
    (item) =>
      reviews[item.decision_id]?.status &&
      reviews[item.decision_id].status !== "pending"
  );
  const allFinished = steps.every(
    (step) => liveRun?.results[step.id]?.status === "completed"
  );

  const handleReview = (
    decisionId: string,
    status: ReviewStatus,
    optionId?: string
  ) => {
    setReviews((previous) => {
      const current = previous[decisionId];
      // Clicking the already-selected state toggles back to pending.
      if (
        current?.status === status &&
        current?.optionId === optionId
      ) {
        return { ...previous, [decisionId]: { status: "pending" } };
      }
      return { ...previous, [decisionId]: { status, optionId } };
    });
  };

  const exportReview = () => {
    const payload = {
      title: protocolTitle,
      kind: "Clinical review — source PDF not modified",
      sample: isSample,
      analysis_complete: allFinished,
      decisions: actionableDecisions.map((item) => {
        const state = reviews[item.decision_id];
        const selectedOption = item.options?.find(
          (opt) => opt.option_id === state?.optionId
        );
        return {
          ...item,
          review_status: state?.status ?? "pending",
          selected_option_id: state?.optionId ?? null,
          accepted_change:
            state?.status === "accepted"
              ? (selectedOption?.proposed_change ?? item.proposed_change ?? null)
              : null,
        };
      }),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      })
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "protocol-clinical-review.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-2">
      <nav aria-label="Pipeline steps"
        className="grid gap-3 pb-6 sm:grid-cols-2 lg:grid-cols-4">
        {barItems.map((item, index) => (
          <button key={item.id} type="button"
            onClick={() => openStep(item.id)}
            aria-label={item.title}
            aria-current={item.id === activeStepId ? "step" : undefined}
            aria-busy={item.state === "running"}
            disabled={item.state === "running"}
            data-loading={item.state === "running"}
            className="review-card analysis-card rounded-xl border p-5 text-left"
            style={{ animationDelay: `${index * 80}ms` }}>
            <span className="mb-3 flex h-8 w-8 items-center justify-center rounded-full border border-emerald-600 text-sm text-emerald-700">
              {index + 1}
            </span>
            <span className="text-xs text-emerald-700">
              {item.state === "running"
                ? (isSample ? "Demo analysis…" : "Analyzing…")
                : item.state === "error" ? "Needs attention" : "Ready to review"}
            </span>
            <span className="mt-2 block font-serif">{item.title}</span>
            <div className="review-scanner mt-4" aria-hidden />
          </button>
        ))}
      </nav>

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
            getReviewStatus={(decisionId) => reviews[decisionId]?.status}
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
                review={reviews[decision.decision_id]}
                onReview={(status, optionId) =>
                  handleReview(decision.decision_id, status, optionId)
                }
              />
            )}
          />
        )}
      </div>

      {reviewed.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-4 border-t border-zinc-200/60 pt-4 font-sans text-xs text-zinc-500">
          <span aria-live="polite">
            {reviewed.length} of {actionableDecisions.length} recommendations
            reviewed
          </span>
          <button
            type="button"
            onClick={exportReview}
            className="cursor-pointer text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900"
          >
            Download review JSON
          </button>
        </div>
      )}

      <nav
        aria-label="Step navigation"
        className="flex items-center justify-between border-t border-zinc-200/60 pb-16 pt-6 font-sans text-sm"
      >
          <button
            type="button"
            aria-label="Previous step"
            disabled={!previousItem}
            onClick={() => previousItem && openStep(previousItem.id)}
            className="cursor-pointer text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900"
          >
            ← Previous: {previousItem?.title ?? "Start"}
          </button>
          <button
            type="button"
            aria-label="Next step"
            disabled={!nextItem || nextItem.state === "running"}
            onClick={() => nextItem && openStep(nextItem.id)}
            className="cursor-pointer text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900 disabled:cursor-default disabled:no-underline disabled:opacity-40"
          >
            Next: {nextItem?.title ?? "End"} →
          </button>
        {!nextItem && (
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
