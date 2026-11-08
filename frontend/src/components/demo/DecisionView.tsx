"use client";

import { useState } from "react";
import {
  BadgeCheck,
  ChevronDown,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import type { Severity } from "@/lib/api";
import {
  formatClockTime,
  formatConfidence,
  formatDuration,
  formatLocationParts,
} from "@/lib/demo/format";
import type {
  Decision,
  DecisionOption,
  Evidence,
  ReviewStatus,
  TraceKind,
} from "@/lib/demo/types";
import ChangeDiff from "./ChangeDiff";
import ChartView from "./ChartView";
import Collapsible from "./Collapsible";
import DataTableView from "./DataTableView";
import MetricList from "./MetricList";
import SectionTitle from "./SectionTitle";
import SlideDown from "./SlideDown";

const TRACE_KIND_LABEL: Record<TraceKind, string> = {
  retrieve: "Retrieved",
  rule: "Applied rule",
  compare: "Compared",
  conclude: "Concluded",
};

const SEVERITY_STYLES: Record<Severity, { label: string; className: string }> =
  {
    info: { label: "Info", className: "text-zinc-500" },
    warning: { label: "Warning", className: "text-amber-700" },
    critical: { label: "Critical", className: "text-rose-700" },
  };

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: "Awaiting review",
  accepted: "Accepted by reviewer",
  rejected: "Rejected by reviewer",
};

const LINK_CLASSES =
  "inline-flex items-center gap-1 underline decoration-zinc-300 " +
  "underline-offset-4 transition-colors hover:text-emerald-700";

export interface DecisionViewProps {
  decision: Decision;
  // Titles of the earlier decisions this one builds on, with a way to jump.
  parents: { decision_id: string; title: string }[];
  onOpenParent: (decisionId: string) => void;
  // Rendered under its finding row, which already shows the title.
  isInline?: boolean;
}

function ExternalAnchor({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={LINK_CLASSES}
    >
      {label}
      <ExternalLink className="h-3 w-3" aria-hidden />
    </a>
  );
}

/** Severity, category, confidence, location, owner, review state, tags. */
function DecisionMeta({ decision }: { decision: Decision }) {
  const severity = SEVERITY_STYLES[decision.severity];
  const parts = [
    decision.category ?? null,
    decision.confidence != null
      ? `${formatConfidence(decision.confidence)} confidence`
      : null,
    ...formatLocationParts(decision.location),
    decision.decision_owner ? `Owner: ${decision.decision_owner}` : null,
    decision.review_status
      ? REVIEW_STATUS_LABEL[decision.review_status]
      : null,
  ].filter((part): part is string => Boolean(part));
  const tags = decision.tags ?? [];

  return (
    <div className="space-y-1.5">
      <p className="flex flex-wrap gap-x-2 gap-y-0.5 font-sans text-xs text-zinc-500">
        <span className={`font-medium ${severity.className}`}>
          {severity.label}
        </span>
        {parts.map((part) => (
          <span key={part} className="before:mr-2 before:content-['·']">
            {part}
          </span>
        ))}
      </p>
      {tags.length > 0 && (
        <ul aria-label="Tags" className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <li
              key={tag}
              className="rounded-full bg-zinc-100 px-2 py-0.5 font-sans text-[11px] text-zinc-600"
            >
              {tag}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * The quote, highlighted inside its surrounding text when the context
 * contains it verbatim; otherwise the context follows the quote.
 */
function EvidenceQuote({ evidence }: { evidence: Evidence }) {
  const highlight = (
    <mark
      className={`rounded-sm px-0.5 text-zinc-900 ${
        evidence.is_verified ? "bg-emerald-100" : "bg-amber-100"
      }`}
    >
      {evidence.quote}
    </mark>
  );
  const context = evidence.context ?? "";
  const quoteIndex = evidence.quote ? context.indexOf(evidence.quote) : -1;

  if (quoteIndex >= 0) {
    return (
      <blockquote className="font-serif text-base text-zinc-500">
        “{context.slice(0, quoteIndex)}
        {highlight}
        {context.slice(quoteIndex + evidence.quote.length)}”
      </blockquote>
    );
  }
  return (
    <>
      <blockquote className="font-serif text-base text-zinc-900">
        “{highlight}”
      </blockquote>
      {context && (
        <p className="border-l-2 border-zinc-200 pl-3 font-serif text-sm text-zinc-500">
          {context}
        </p>
      )}
    </>
  );
}

function EvidenceItem({ evidence }: { evidence: Evidence }) {
  return (
    <li className="space-y-1">
      <EvidenceQuote evidence={evidence} />
      <p className="flex flex-wrap items-center gap-x-2 font-sans text-xs text-zinc-500">
        <span>{evidence.document}</span>
        {evidence.section_title && <span>{evidence.section_title}</span>}
        {evidence.page !== null && <span>p. {evidence.page}</span>}
        {evidence.confidence != null && (
          <span>{formatConfidence(evidence.confidence)} match</span>
        )}
        {evidence.is_verified && (
          <BadgeCheck
            className="h-3 w-3 text-emerald-700"
            strokeWidth={1.5}
            aria-label="Verified quote"
          />
        )}
        {evidence.url && (
          <ExternalAnchor href={evidence.url} label="Open source" />
        )}
      </p>
    </li>
  );
}

function OptionCard({ option }: { option: DecisionOption }) {
  const risks = option.risks ?? [];
  return (
    <li
      aria-label={option.title}
      className={`space-y-2 rounded-md border p-3 ${
        option.is_recommended
          ? "border-emerald-300 bg-emerald-50/40"
          : "border-zinc-200"
      }`}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <h3 className="font-serif text-base text-zinc-900">{option.title}</h3>
        {option.is_recommended && (
          <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-sans text-[11px] font-medium text-emerald-800">
            Recommended
          </span>
        )}
      </div>
      {option.rationale && (
        <p className="font-sans text-sm text-zinc-600">{option.rationale}</p>
      )}
      {option.proposed_change && (
        <ChangeDiff change={option.proposed_change} />
      )}
      <MetricList
        metrics={option.impact ?? []}
        size="small"
        ariaLabel={`Impact of ${option.title}`}
      />
      {risks.length > 0 && (
        <div className="space-y-0.5">
          <p className="font-sans text-xs font-medium text-zinc-500">Risks</p>
          <ul className="list-disc space-y-0.5 pl-4 font-sans text-xs text-zinc-600">
            {risks.map((risk) => (
              <li key={risk}>{risk}</li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

/**
 * Deepest level: what one agent concluded, from what evidence, and how.
 * Wide screens split it in two: why (evidence, reasoning) on the left and
 * what to do about it (change, options, sources, data) on the right.
 */
export default function DecisionView({
  decision,
  parents,
  onOpenParent,
  isInline = false,
}: DecisionViewProps) {
  const [isReasoningOpen, setIsReasoningOpen] = useState(false);
  const stepCount = decision.trace.length;
  const impact = decision.impact ?? [];
  const options = decision.options ?? [];
  const references = decision.references ?? [];
  const tables = decision.tables ?? [];
  const charts = decision.charts ?? [];
  const hasActionColumn =
    decision.proposed_change != null ||
    options.length > 0 ||
    references.length > 0 ||
    charts.length > 0 ||
    tables.length > 0;

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
    <article aria-label={decision.title} className="space-y-6">
      <header className="space-y-2">
        {/* Inline, the finding row above already shows the title. */}
        {!isInline && (
          <h1 className="font-serif text-3xl font-normal tracking-tight text-zinc-900">
            {decision.title}
          </h1>
        )}
        <DecisionMeta decision={decision} />
        <p className="max-w-3xl font-sans text-sm text-zinc-600">
          {decision.claim}
        </p>
        {decision.reviewer_comment && (
          <p className="border-l-2 border-zinc-200 pl-3 font-sans text-xs text-zinc-500">
            Reviewer note: {decision.reviewer_comment}
          </p>
        )}
      </header>

      {impact.length > 0 && (
        <section className="space-y-2">
          <SectionTitle>Impact</SectionTitle>
          <MetricList metrics={impact} ariaLabel="Impact" />
        </section>
      )}

      <div
        className={
          hasActionColumn
            ? "grid gap-x-10 gap-y-6 lg:grid-cols-2"
            : "max-w-3xl"
        }
      >
        <div className="min-w-0 space-y-6">
          <section className="space-y-3">
            <SectionTitle>Evidence</SectionTitle>
            <ul className="space-y-4">
              {decision.evidence.map((evidence) => (
                <EvidenceItem key={evidence.evidence_id} evidence={evidence} />
              ))}
            </ul>
          </section>

          <section>
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
            <SlideDown isOpen={isReasoningOpen} className="pt-3">
              <ol className="space-y-2">
                {decision.trace.map((entry, index) => {
                  const timing = [
                    entry.duration_ms != null
                      ? formatDuration(entry.duration_ms)
                      : null,
                    entry.timestamp ? formatClockTime(entry.timestamp) : null,
                  ].filter(Boolean);
                  return (
                    <li
                      key={entry.trace_id ?? `${entry.agent}-${index}`}
                      className="flex gap-3"
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
                          ({[entry.agent, ...entry.evidence_ids.map(citeLabel)]
                            .join(" · ")})
                        </span>
                        {timing.length > 0 && (
                          <span className="ml-1.5 text-xs tabular-nums text-zinc-400">
                            {timing.join(" · ")}
                          </span>
                        )}
                      </p>
                    </li>
                  );
                })}
              </ol>
            </SlideDown>
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

        {hasActionColumn && (
          <div className="min-w-0 space-y-6">
            {decision.proposed_change && (
              <section className="space-y-2">
                <SectionTitle>Suggested change</SectionTitle>
                <ChangeDiff change={decision.proposed_change} />
              </section>
            )}

            {options.length > 0 && (
              <section className="space-y-3">
                <SectionTitle>Options</SectionTitle>
                <ul className="space-y-3">
                  {options.map((option) => (
                    <OptionCard key={option.option_id} option={option} />
                  ))}
                </ul>
              </section>
            )}

            {references.length > 0 && (
              <section className="space-y-2">
                <SectionTitle>References</SectionTitle>
                <ul className="space-y-2">
                  {references.map((reference) => (
                    <li key={reference.label} className="space-y-0.5">
                      <p className="font-sans text-sm text-zinc-800">
                        {reference.url ? (
                          <ExternalAnchor
                            href={reference.url}
                            label={reference.label}
                          />
                        ) : (
                          reference.label
                        )}
                      </p>
                      {reference.quote && (
                        <blockquote className="border-l-2 border-zinc-200 pl-3 font-serif text-sm text-zinc-600">
                          “{reference.quote}”
                        </blockquote>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {charts.length > 0 && (
              <Collapsible
                title="Charts"
                count={charts.length}
                isInitiallyOpen
              >
                <div className="space-y-6">
                  {charts.map((chart) => (
                    <ChartView key={chart.chart_id} chart={chart} />
                  ))}
                </div>
              </Collapsible>
            )}

            {tables.length > 0 && (
              <Collapsible
                title="Tables"
                count={tables.length}
                isInitiallyOpen
              >
                <div className="space-y-6">
                  {tables.map((table) => (
                    <DataTableView key={table.table_id} table={table} />
                  ))}
                </div>
              </Collapsible>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
