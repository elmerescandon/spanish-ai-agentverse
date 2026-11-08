"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ProtocolIngestion from "@/components/ProtocolIngestion";
import DecisionView from "./DecisionView";
import type { StepBarState } from "./StepBar";
import StepView from "./StepView";
import ReviewActions from "./ReviewActions";
import SlideDown from "./SlideDown";
import ProtocolLoading from "./ProtocolLoading";
import {
  RECOMMENDATION_ENDPOINTS,
  uploadProtocolFile,
  type RecommendationFetcher,
} from "@/lib/api";
import {
  MOCK_RECOMMENDATION_FETCHERS,
  MOCK_STEPS,
  MOCK_UPLOAD_RESPONSE,
} from "@/lib/demo/mock/index";
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
  const [protocolTitle, setProtocolTitle] = useState("");
  const [isSample, setIsSample] = useState(false);
  const [animationReplay, setAnimationReplay] = useState(0);
  const [sampleRevealCount, setSampleRevealCount] = useState(0);
  useEffect(() => {
    if (!isSample) return;
    const timers = [1350, 2350, 3550, 4750].map((delay, index) =>
      setTimeout(() => setSampleRevealCount(index + 1), delay));
    return () => timers.forEach(clearTimeout);
  }, [isSample, animationReplay]);
  const [showOutput, setShowOutput] = useState(false);
  const [reviews, setReviews] = useState<Record<string, {
    status: "pending" | "accepted" | "rejected"; comment: string;
  }>>({});
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
    setProtocolTitle(upload.title);
    setReviews({});
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

  const loadSample = () => {
    setIsSample(true);
    runPipeline(sampleUpload, sampleFetchers);
  };

  const startLiveRun = async (file: File) => {
    if (uploadState.status === "uploading") return;
    setIsSample(false);
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

  if (uploadState.status === "uploading" ||
      (isLoaded && isSample && sampleRevealCount === 0)) {
    return <ProtocolLoading sample={isSample} />;
  }

  if (!isLoaded) {
    return (
      <div className="mx-auto flex min-h-[80vh] max-w-xl flex-col justify-center space-y-8">
        <h1 className="text-center font-serif text-4xl font-normal tracking-tight text-zinc-900">
          Analyze a draft protocol
        </h1>
        <p className="text-center text-sm leading-6 text-zinc-500">
          Upload your PDF. Review each analysis, inspect the evidence,
          then record your decisions and download the review.
        </p>
        <ProtocolIngestion
          onProtocolLoaded={loadSample}
          onPdfSelected={startLiveRun}
          isCompact
          isAnalyzing={false}
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
  const allDecisions = steps.flatMap((step) => step.decisions);
  const reviewed = allDecisions.filter((item) =>
    reviews[item.decision_id]?.status &&
    reviews[item.decision_id].status !== "pending");
  const allFinished = steps.every((step) =>
    liveRun?.results[step.id]?.status === "completed");
  const exportReview = () => {
    const payload = {
      title: protocolTitle,
      kind: "Clinical review — source PDF not modified",
      sample: isSample,
      analysis_complete: allFinished,
      decisions: allDecisions.map((item) => ({
        ...item,
        review_status: reviews[item.decision_id]?.status ?? "pending",
        reviewer_comment: reviews[item.decision_id]?.comment ?? "",
      })),
    };
    const url = URL.createObjectURL(new Blob(
      [JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "protocol-clinical-review.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <header className="review-card rounded-2xl bg-zinc-50 p-6 space-y-3">
        <p className="text-xs uppercase tracking-widest text-emerald-700">
          {isSample ? "Sample protocol · demonstration" : "Clinical review"}
        </p>
        <h1 className="font-serif text-2xl">{protocolTitle}</h1>
        <p className="text-sm text-zinc-500">
          Open an analysis below, review its suggestions and evidence,
          then accept or decline each finding.
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <span aria-live="polite" className="text-sm">
            {reviewed.length} of {allDecisions.length} findings reviewed
          </span>
          <button className="review-secondary" type="button"
            onClick={() => setShowOutput(!showOutput)}
            aria-expanded={showOutput}>
            Preview review output
          </button>
          {isSample && (
            <button type="button" className="review-secondary"
              onClick={() => {
                setSampleRevealCount(0);
                setAnimationReplay((value) => value + 1);
              }}>
              Replay demo animation
            </button>
          )}
        </div>
      </header>
      <SlideDown isOpen={showOutput}>
        <section className="rounded-xl border p-6 space-y-4">
          <h2 className="font-serif text-xl">Protocol review output</h2>
          <p className="text-sm text-zinc-500">
            {allFinished ? "Analysis complete." : "Analysis incomplete."}
            {" "}This download contains findings, evidence and your decisions.
            A rewritten final protocol PDF is not yet available.
          </p>
          <ul className="space-y-2 text-sm">
            {reviewed.map((item) => (
              <li key={item.decision_id}>
                {reviews[item.decision_id].status === "accepted"
                  ? "✓ Accepted: " : "Declined: "}{item.title}
                {reviews[item.decision_id].status === "accepted" &&
                  item.proposed_change && (
                    <p className="mt-1 border-l-2 pl-3 text-zinc-600">
                      {item.proposed_change.after}
                    </p>
                  )}
              </li>
            ))}
          </ul>
          <button type="button" className="review-primary"
            onClick={exportReview}>
            Download review JSON
          </button>
        </section>
      </SlideDown>
      <nav aria-label="Pipeline steps"
        className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {barItems.map((item, index) => (
          <button key={`${animationReplay}-${item.id}-${item.state}`}
            type="button"
            onClick={() => openStep(item.id)}
            disabled={item.state === "running"}
            className="review-card analysis-card rounded-xl border p-5 text-left"
            data-loading={item.state === "running"}
            aria-busy={item.state === "running"}
            aria-current={item.id === activeStepId ? "step" : undefined}
            aria-label={item.title}
            style={{ animationDelay: `${index * 80}ms` }}>
            <span className="mb-3 flex h-8 w-8 items-center justify-center rounded-full border border-emerald-600 text-sm text-emerald-700">
              {index + 1}
            </span>
            <span className="text-xs text-emerald-700">
              {item.state === "running" ?
                (isSample ? "Demo analysis…" : "Analyzing…") :
                item.state === "error" ? "Needs attention" : "Ready to review"}
            </span>
            <span className="mt-2 block font-serif">{item.title}</span>
            {item.state === "running" && (
              <div className="review-scanner mt-4" aria-hidden />
            )}
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
        {isSample && sampleRevealCount === 0 ? (
          <div role="status" className="review-card rounded-xl border p-8">
            <p className="font-serif text-xl">Reading sample protocol</p>
            <p className="my-3 text-sm text-zinc-500">
              Demonstration playback · your review decisions are preserved.
            </p>
            <div className="review-scanner" aria-hidden />
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
            expandedDecisionIds={expandedDecisionIds}
            onToggleDecision={toggleDecision}
            renderDecision={(decision) => (
              <div className="space-y-6">
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
              <ReviewActions
                status={reviews[decision.decision_id]?.status ?? "pending"}
                onReview={(status, comment) => setReviews((previous) => ({
                  ...previous, [decision.decision_id]: { status, comment },
                }))}
              />
              </div>
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
        {nextItem && (
          <button
            type="button"
            disabled={nextItem.state === "running"}
            onClick={() => openStep(nextItem.id)}
            className="cursor-pointer text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900 disabled:cursor-default disabled:no-underline disabled:opacity-40"
          >
            Next: {nextItem.title} →
          </button>
        )}
      </nav>
    </div>
  );
}
