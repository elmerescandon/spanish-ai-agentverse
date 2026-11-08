"use client";

import { useState } from "react";
import { BadgeCheck, CircleDashed } from "lucide-react";
import type {
  Decision,
  HumanDecision,
  TraceKind,
} from "@/lib/demo/types";

const TRACE_KIND_LABEL: Record<TraceKind, string> = {
  retrieve: "Retrieved",
  rule: "Applied rule",
  compare: "Compared",
  conclude: "Concluded",
};

// Delay between trace entries so the reasoning reads as a sequence.
const TRACE_STAGGER_MS = 80;

export interface DecisionViewProps {
  decision: Decision;
  human: HumanDecision | undefined;
  // Titles of the earlier decisions this one builds on, with a way to jump.
  parents: { decision_id: string; title: string }[];
  onDecide: (decision: HumanDecision) => void;
  onOpenParent: (decisionId: string) => void;
}

function SectionTitle({ children }: { children: string }) {
  return (
    <h2 className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
      {children}
    </h2>
  );
}

/** Deepest level: evidence, agent reasoning and the human decision. */
export default function DecisionView({
  decision,
  human,
  parents,
  onDecide,
  onOpenParent,
}: DecisionViewProps) {
  const [isDismissing, setIsDismissing] = useState(false);
  const [reason, setReason] = useState("");
  const trimmedReason = reason.trim();

  return (
    <article aria-label={decision.title} className="space-y-8">
      <header className="space-y-2">
        <h1 className="font-serif text-3xl font-normal tracking-tight text-zinc-900">
          {decision.title}
        </h1>
        <p className="font-sans text-sm text-zinc-600">{decision.claim}</p>
      </header>

      <section className="space-y-3">
        <SectionTitle>Evidence</SectionTitle>
        <ul className="space-y-3">
          {decision.evidence.map((evidence) => (
            <li
              key={evidence.evidence_id}
              className="space-y-1.5 border-l-2 border-zinc-200 pl-4"
            >
              <blockquote className="font-serif text-sm italic text-zinc-900">
                “{evidence.quote}”
              </blockquote>
              <p className="flex flex-wrap items-center gap-x-2 font-sans text-xs text-zinc-500">
                <span>{evidence.document}</span>
                {evidence.page !== null && <span>p. {evidence.page}</span>}
                <span
                  className={`inline-flex items-center gap-1 ${
                    evidence.is_verified
                      ? "text-emerald-700"
                      : "text-amber-700"
                  }`}
                >
                  {evidence.is_verified ? (
                    <BadgeCheck
                      className="h-3 w-3"
                      strokeWidth={1.5}
                      aria-hidden
                    />
                  ) : (
                    <CircleDashed
                      className="h-3 w-3"
                      strokeWidth={1.5}
                      aria-hidden
                    />
                  )}
                  {evidence.is_verified ? "Verified quote" : "Unverified"}
                </span>
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-3">
        <SectionTitle>Agent reasoning</SectionTitle>
        <ol className="space-y-3">
          {decision.trace.map((entry, index) => (
            <li
              key={`${entry.agent}-${index}`}
              className="animate-file-change flex gap-3 opacity-0"
              style={{ animationDelay: `${index * TRACE_STAGGER_MS}ms` }}
            >
              <span className="mt-0.5 font-sans text-xs tabular-nums text-zinc-400">
                {index + 1}
              </span>
              <p className="font-sans text-sm text-zinc-700">
                <span className="font-medium text-zinc-900">
                  {TRACE_KIND_LABEL[entry.kind]}
                </span>{" "}
                {entry.text}{" "}
                <span className="text-xs text-zinc-400">
                  ({entry.agent}
                  {entry.evidence_ids.length > 0 &&
                    `, cites ${entry.evidence_ids.join(", ")}`}
                  )
                </span>
              </p>
            </li>
          ))}
        </ol>
      </section>

      {decision.proposed_change && (
        <section className="space-y-3">
          <SectionTitle>Proposed change</SectionTitle>
          <div className="space-y-1.5 rounded-xl border border-zinc-200/60 bg-white/80 p-4 font-sans text-sm">
            <p className="text-xs text-zinc-500">
              {decision.proposed_change.path}
            </p>
            <p className="text-rose-700 line-through decoration-rose-300">
              {decision.proposed_change.before}
            </p>
            <p className="text-emerald-700">
              {decision.proposed_change.after}
            </p>
          </div>
        </section>
      )}

      {parents.length > 0 && (
        <section className="space-y-3">
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

      <section className="space-y-3 border-t border-zinc-200/60 pt-6">
        <SectionTitle>Your decision</SectionTitle>
        {human ? (
          <p className="font-sans text-sm text-zinc-700">
            <span className="font-medium text-emerald-700">
              {human.status === "accepted" ? "Accepted" : "Dismissed"}
            </span>
            {human.reason && <> — {human.reason}</>}
          </p>
        ) : isDismissing ? (
          <div className="space-y-3">
            <label
              htmlFor={`reason-${decision.decision_id}`}
              className="font-sans text-xs text-zinc-500"
            >
              Reason for dismissing
            </label>
            <textarea
              id={`reason-${decision.decision_id}`}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
              className="w-full rounded-lg border border-zinc-200 bg-white p-3 font-sans text-sm text-zinc-900 outline-none focus:border-emerald-500"
            />
            <div className="flex gap-2">
              <button
                type="button"
                disabled={trimmedReason === ""}
                onClick={() =>
                  onDecide({ status: "dismissed", reason: trimmedReason })
                }
                className="cursor-pointer rounded-lg bg-zinc-900 px-4 py-2 font-sans text-xs font-medium text-white transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Confirm dismissal
              </button>
              <button
                type="button"
                onClick={() => setIsDismissing(false)}
                className="cursor-pointer rounded-lg border border-zinc-200/60 px-4 py-2 font-sans text-xs font-medium text-zinc-700 transition-colors hover:bg-zinc-50"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => onDecide({ status: "accepted" })}
              className="cursor-pointer rounded-lg bg-zinc-900 px-4 py-2 font-sans text-xs font-medium text-white transition-colors hover:bg-zinc-800"
            >
              Accept
            </button>
            <button
              type="button"
              onClick={() => setIsDismissing(true)}
              className="cursor-pointer rounded-lg border border-zinc-200/60 bg-white/60 px-4 py-2 font-sans text-xs font-medium text-zinc-800 transition-colors hover:bg-zinc-50"
            >
              Dismiss
            </button>
          </div>
        )}
      </section>
    </article>
  );
}
