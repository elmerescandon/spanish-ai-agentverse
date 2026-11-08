"use client";

import { useState } from "react";
import { BadgeCheck, ChevronDown, ChevronRight } from "lucide-react";
import CommentThread from "@/components/demo/CommentThread";
import type {
  Decision,
  ReviewResolution,
  ReviewThread,
  TraceKind,
} from "@/lib/demo/types";

const TRACE_KIND_LABEL: Record<TraceKind, string> = {
  retrieve: "Retrieved",
  rule: "Applied rule",
  compare: "Compared",
  conclude: "Concluded",
};

export interface DecisionViewProps {
  decision: Decision;
  thread: ReviewThread | undefined;
  // Titles of the earlier decisions this one builds on, with a way to jump.
  parents: { decision_id: string; title: string }[];
  onAddComment: (body: string) => void;
  onResolve: (resolution: ReviewResolution) => void;
  onOpenParent: (decisionId: string) => void;
}

function SectionTitle({ children }: { children: string }) {
  return (
    <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
      {children}
    </h2>
  );
}

/** Deepest level: a Docs-style page with a margin comment card. */
export default function DecisionView({
  decision,
  thread,
  parents,
  onAddComment,
  onResolve,
  onOpenParent,
}: DecisionViewProps) {
  const [isReasoningOpen, setIsReasoningOpen] = useState(false);
  const stepCount = decision.trace.length;

  // Each reasoning step names the evidence it relied on, so the chain from
  // conclusion back to source stays visible.
  const citeLabel = (evidenceId: string): string => {
    const evidence = decision.evidence.find(
      (e) => e.evidence_id === evidenceId
    );
    if (!evidence) return evidenceId;
    return evidence.page !== null
      ? `p. ${evidence.page}`
      : evidence.source.toUpperCase();
  };

  return (
    <article
      aria-label={decision.title}
      className="grid gap-8 lg:grid-cols-3"
    >
      <div className="space-y-6 lg:col-span-2">
        <header className="space-y-2">
          <h1 className="font-serif text-3xl font-normal tracking-tight text-zinc-900">
            {decision.title}
          </h1>
          <p className="font-sans text-sm text-zinc-600">{decision.claim}</p>
        </header>

        <section className="space-y-3">
          <SectionTitle>Evidence</SectionTitle>
          <ul className="space-y-4">
            {decision.evidence.map((evidence) => (
              <li key={evidence.evidence_id} className="space-y-1">
                <blockquote className="font-serif text-base text-zinc-900">
                  “
                  <mark
                    className={`rounded-sm px-0.5 text-zinc-900 ${
                      evidence.is_verified ? "bg-emerald-100" : "bg-amber-100"
                    }`}
                  >
                    {evidence.quote}
                  </mark>
                  ”
                </blockquote>
                <p className="flex flex-wrap items-center gap-x-2 font-sans text-xs text-zinc-500">
                  <span>{evidence.document}</span>
                  {evidence.page !== null && <span>p. {evidence.page}</span>}
                  {evidence.is_verified && (
                    <BadgeCheck
                      className="h-3 w-3 text-emerald-700"
                      strokeWidth={1.5}
                      aria-label="Verified quote"
                    />
                  )}
                </p>
              </li>
            ))}
          </ul>
        </section>

        {decision.proposed_change && (
          <section className="space-y-2">
            <SectionTitle>Suggested change</SectionTitle>
            <p className="font-sans text-xs text-zinc-500">
              {decision.proposed_change.path}
            </p>
            <p className="font-serif text-base text-zinc-900">
              <del className="text-rose-700 decoration-rose-300">
                {decision.proposed_change.before}
              </del>{" "}
              <ins className="rounded-sm bg-emerald-50 text-emerald-800 no-underline">
                {decision.proposed_change.after}
              </ins>
            </p>
          </section>
        )}

        <section className="space-y-3">
          <button
            type="button"
            aria-expanded={isReasoningOpen}
            onClick={() => setIsReasoningOpen((previous) => !previous)}
            className="inline-flex cursor-pointer items-center gap-1 font-sans text-xs text-zinc-600 transition-colors hover:text-emerald-700"
          >
            {isReasoningOpen ? (
              <ChevronDown className="h-3.5 w-3.5" aria-hidden />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" aria-hidden />
            )}
            {isReasoningOpen
              ? "Hide reasoning"
              : `Show reasoning (${stepCount} steps)`}
          </button>
          {isReasoningOpen && (
            <ol className="animate-file-change space-y-2">
              {decision.trace.map((entry, index) => (
                <li key={`${entry.agent}-${index}`} className="flex gap-3">
                  <span className="mt-0.5 font-sans text-xs tabular-nums text-zinc-400">
                    {index + 1}
                  </span>
                  <p className="font-sans text-sm text-zinc-700">
                    <span className="font-medium text-zinc-900">
                      {TRACE_KIND_LABEL[entry.kind]}
                    </span>{" "}
                    {entry.text}{" "}
                    <span className="text-xs text-zinc-400">
                      ({[entry.agent, ...entry.evidence_ids.map(citeLabel)]
                        .join(" · ")})
                    </span>
                  </p>
                </li>
              ))}
            </ol>
          )}
        </section>

        {parents.length > 0 && (
          <section className="space-y-2">
            <SectionTitle>Builds on</SectionTitle>
            <ul className="space-y-1">
              {parents.map((parent) => (
                <li key={parent.decision_id}>
                  <button
                    type="button"
                    onClick={() => onOpenParent(parent.decision_id)}
                    className="cursor-pointer font-sans text-sm text-zinc-700 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-emerald-700"
                  >
                    {parent.title}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <aside className="lg:pt-12">
        <CommentThread
          decisionId={decision.decision_id}
          thread={thread}
          onAddComment={onAddComment}
          onResolve={onResolve}
        />
      </aside>
    </article>
  );
}
