"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import type { Severity } from "@/lib/api";
import {
  formatClockTime,
  formatConfidence,
  formatDuration,
  formatWithUnit,
  formatLocationParts,
} from "@/lib/demo/format";
import type {
  Decision,
  DecisionOption,
  Evidence,
  Metric,
  ReviewStatus,
  TraceKind,
} from "@/lib/demo/types";
import ChangeDiff from "./ChangeDiff";
import ChartView from "./ChartView";
import DataTableView from "./DataTableView";

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

export interface DecisionReviewState {
  status: ReviewStatus;
  optionId?: string;
}

export interface DecisionViewProps {
  decision: Decision;
  // Titles of the earlier decisions this one builds on, with a way to jump.
  parents: { decision_id: string; title: string }[];
  onOpenParent: (decisionId: string) => void;
  // Rendered under its finding row, which already shows the title.
  isInline?: boolean;
  // Optional clinician review state and callback for actionable recommendations.
  review?: DecisionReviewState;
  onReview?: (status: ReviewStatus, optionId?: string) => void;
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

const SECTION_CLASSES = "space-y-3 border-t border-zinc-200 pt-5";

function SectionTitle({ children }: { children: string }) {
  return (
    <h2 className="font-sans text-sm font-semibold text-zinc-900">
      {children}
    </h2>
  );
}

/** One plain line: severity, then category, confidence, place, owner. */
function DecisionMeta({ decision }: { decision: Decision }) {
  const severity = SEVERITY_STYLES[decision.severity];
  const details = [
    decision.category ?? null,
    decision.confidence != null
      ? `${formatConfidence(decision.confidence)} confidence`
      : null,
    ...formatLocationParts(decision.location),
    decision.decision_owner ? `Owner: ${decision.decision_owner}` : null,
  ]
    .filter((part): part is string => Boolean(part))
    .join(", ");

  return (
    <p className="font-sans text-sm text-zinc-500">
      <span className={`font-medium ${severity.className}`}>
        {severity.label}
      </span>
      {details && <span>{`. ${details}`}</span>}
    </p>
  );
}

/** Figures as plain "Label: value" lines, peer benchmarks after. */
function PlainMetrics({
  metrics,
  ariaLabel,
}: {
  metrics: readonly Metric[];
  ariaLabel: string;
}) {
  if (metrics.length === 0) return null;
  return (
    <dl aria-label={ariaLabel} className="space-y-1 font-sans text-sm">
      {metrics.map((metric) => {
        const benchmarks = metric.benchmarks ?? [];
        return (
          <div
            key={metric.metric_id ?? metric.label}
            className="flex flex-wrap gap-x-2"
          >
            <dt className="text-zinc-500 after:content-[':']">
              {metric.label}
            </dt>
            <dd className="text-zinc-900">
              {formatWithUnit(metric.value, metric.unit)}
            </dd>
            {benchmarks.map((benchmark) => (
              <dd key={benchmark.label} className="text-zinc-500">
                {`${benchmark.label} ${
                  metric.unit && !benchmark.value.endsWith(metric.unit)
                    ? formatWithUnit(benchmark.value, metric.unit)
                    : benchmark.value
                }`}
              </dd>
            ))}
            {metric.description && (
              <dd className="text-zinc-500">{metric.description}</dd>
            )}
          </div>
        );
      })}
    </dl>
  );
}

/** The verbatim quote and, on one line, where it comes from. */
function EvidenceItem({ evidence }: { evidence: Evidence }) {
  const source = [
    evidence.document,
    evidence.section_title,
    evidence.page !== null ? `p. ${evidence.page}` : null,
  ].filter(Boolean);
  return (
    <li className="space-y-1">
      <blockquote className="font-sans text-sm text-zinc-900">
        “<mark className="bg-transparent text-inherit">{evidence.quote}</mark>”
      </blockquote>
      <p className="flex flex-wrap gap-x-2 font-sans text-xs text-zinc-500">
        <span>{source.join(", ")}</span>
        {evidence.confidence != null && (
          <span>{formatConfidence(evidence.confidence)} match</span>
        )}
        {evidence.is_verified && <span>Verified</span>}
        {evidence.url && (
          <ExternalAnchor href={evidence.url} label="Open source" />
        )}
      </p>
    </li>
  );
}

function OptionItem({
  option,
  isAccepted = false,
  isDeclined = false,
  onAccept,
  onDecline,
}: {
  option: DecisionOption;
  isAccepted?: boolean;
  isDeclined?: boolean;
  onAccept?: () => void;
  onDecline?: () => void;
}) {
  const risks = option.risks ?? [];
  return (
    <li aria-label={option.title} className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h3 className="font-sans text-sm font-medium text-zinc-900">
          {option.title}
          {option.is_recommended && (
            <span className="ml-2 font-normal text-emerald-700">
              Recommended
            </span>
          )}
        </h3>
        {onAccept && (
          <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            aria-pressed={isAccepted}
            aria-label={`Accept ${option.title}`}
            onClick={onAccept}
            className="decision-action decision-accept"
          >
            <span aria-hidden="true">✓</span>
            {isAccepted ? "Accepted" : "Accept"}
          </button>
          <button type="button"
            aria-label={`Decline ${option.title}`}
            aria-pressed={isDeclined}
            onClick={onDecline}
            className="decision-action decision-decline">
            <span aria-hidden="true">✕</span>
            {isDeclined ? "Declined" : "Decline"}
          </button>
          </div>
        )}
      </div>
      {option.rationale && (
        <p className="font-sans text-sm text-zinc-700">{option.rationale}</p>
      )}
      {option.proposed_change && (
        <ChangeDiff change={option.proposed_change} />
      )}
      {(option.impact ?? []).length > 0 && (
        <section aria-label={`Impact of ${option.title}`}
          className="rounded-xl border border-emerald-100 bg-emerald-50/40 p-4">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-emerald-800">
            Expected impact / target
          </p>
          <dl className="flex flex-wrap gap-x-8 gap-y-4">
            {option.impact!.map((metric, index) => (
              <div key={`${metric.label}-${index}`}>
                <dt className="text-xs text-zinc-600">{metric.label}</dt>
                <dd className="mt-1 text-lg font-semibold text-emerald-900">
                  {metric.value}
                </dd>
                {metric.description && (
                  <p className="mt-1 text-xs text-zinc-500">
                    {metric.description}
                  </p>
                )}
              </div>
            ))}
          </dl>
        </section>
      )}
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
 * One linear column, read top to bottom like a document: claim, evidence,
 * suggested change, options, impact, charts and tables. Secondary material
 * (reasoning, evidence context, references, review notes) sits behind a
 * single plain Expand button.
 */
export default function DecisionView({
  decision,
  parents,
  onOpenParent,
  isInline = false,
  review,
  onReview,
}: DecisionViewProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const impact = decision.impact ?? [];
  const allOptions = decision.options ?? [];
  const actionableOptions = allOptions.filter((option) =>
    Boolean(option.proposed_change)
  );
  const options =
    onReview && actionableOptions.length > 0 ? actionableOptions : allOptions;
  const references = decision.references ?? [];
  const tables = decision.tables ?? [];
  const charts = decision.charts ?? [];
  const tags = decision.tags ?? [];
  // The same edit is shown once: inside the option that carries it.
  const proposed = decision.proposed_change;
  const hasRecommendation =
    Boolean(proposed) || actionableOptions.length > 0;
  const canReview = Boolean(onReview) && hasRecommendation;
  const effectiveStatus = review?.status ?? decision.review_status ?? "pending";
  const acceptedOption = options.find(
    (option) => option.option_id === review?.optionId
  );
  const isChangeInOption =
    proposed != null &&
    options.some(
      (option) =>
        option.proposed_change?.before === proposed.before &&
        option.proposed_change?.after === proposed.after
    );
  const contexts = decision.evidence.filter((e) => Boolean(e.context));
  const reviewLines = [
    effectiveStatus ? REVIEW_STATUS_LABEL[effectiveStatus] : null,
    decision.reviewer_comment
      ? `Reviewer note: ${decision.reviewer_comment}`
      : null,
    tags.length > 0 ? `Tags: ${tags.join(", ")}` : null,
  ].filter((line): line is string => Boolean(line));
  const hasSecondary =
    decision.trace.length > 0 ||
    contexts.length > 0 ||
    references.length > 0 ||
    reviewLines.length > 0;

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
    <article aria-label={decision.title} className="max-w-6xl space-y-6">
      <header className="space-y-2">
        {/* Inline, the finding row above already shows the title. */}
        {!isInline && (
          <h1 className="font-serif text-3xl font-normal tracking-tight text-zinc-900">
            {decision.title}
          </h1>
        )}
        <DecisionMeta decision={decision} />
        <p className="font-sans text-base text-zinc-900">{decision.claim}</p>
      </header>

      <section className={SECTION_CLASSES}>
        <SectionTitle>Evidence</SectionTitle>
        <ul className="space-y-4">
          {decision.evidence.map((evidence) => (
            <EvidenceItem key={evidence.evidence_id} evidence={evidence} />
          ))}
        </ul>
      </section>

      {proposed && !isChangeInOption && (
        <section className={SECTION_CLASSES}>
          <div className="flex flex-wrap items-baseline justify-between gap-4">
            <SectionTitle>Proposed change</SectionTitle>
            {canReview && (
              <div className="flex items-center gap-4 font-sans text-xs">
                <button
                  type="button"
                  aria-pressed={effectiveStatus === "accepted"}
                  onClick={() => onReview?.("accepted")}
                  className="decision-action decision-accept"
                >
                  <span aria-hidden="true">✓</span>
                  {effectiveStatus === "accepted"
                    ? "Accepted"
                    : "Accept recommendation"}
                </button>
                <button
                  type="button"
                  aria-pressed={effectiveStatus === "rejected"}
                  onClick={() => onReview?.("rejected")}
                  className="decision-action decision-decline"
                >
                  <span aria-hidden="true">✕</span>
                  {effectiveStatus === "rejected" ? "Declined" : "Decline"}
                </button>
              </div>
            )}
          </div>
          <ChangeDiff change={proposed} />
        </section>
      )}

      {options.length > 0 && (
        <section className={SECTION_CLASSES}>
          <div className="flex flex-wrap items-baseline justify-between gap-4">
            <SectionTitle>
              {canReview && options.length > 1 ? "Recommendations" : "Options"}
            </SectionTitle>
            {canReview && (
              <div className="flex items-center gap-4 font-sans text-xs">
                {effectiveStatus === "accepted" && (
                  <span className="text-emerald-700">
                    ✓ Accepted
                    {acceptedOption ? `: ${acceptedOption.title}` : ""}
                  </span>
                )}
              </div>
            )}
          </div>
          <ul className="divide-y divide-zinc-200 [&>li]:py-4 first:[&>li]:pt-0">
            {options.map((option) => (
              <OptionItem
                key={option.option_id}
                option={option}
                isAccepted={
                  effectiveStatus === "accepted" &&
                  (review?.optionId === option.option_id ||
                    (!review?.optionId && Boolean(option.is_recommended)))
                }
                onAccept={
                  canReview && Boolean(option.proposed_change)
                    ? () => onReview?.("accepted", option.option_id)
                    : undefined
                }
                isDeclined={effectiveStatus === "rejected" &&
                  review?.optionId === option.option_id}
                onDecline={() => onReview?.("rejected", option.option_id)}
              />
            ))}
          </ul>
        </section>
      )}

      {impact.length > 0 && (
        <section className={SECTION_CLASSES}>
          <SectionTitle>Impact</SectionTitle>
          <PlainMetrics metrics={impact} ariaLabel="Impact" />
        </section>
      )}

      {charts.length > 0 && (
        <section className={SECTION_CLASSES}>
          <SectionTitle>Charts</SectionTitle>
          <div className="grid gap-8 lg:grid-cols-2">
            {charts.map((chart) => (
              <ChartView key={chart.chart_id} chart={chart} />
            ))}
          </div>
        </section>
      )}

      {tables.length > 0 && (
        <section className={SECTION_CLASSES}>
          <SectionTitle>Tables</SectionTitle>
          {tables.map((table) => (
            <DataTableView key={table.table_id} table={table} />
          ))}
        </section>
      )}

      {parents.length > 0 && (
        <section className={SECTION_CLASSES}>
          <SectionTitle>Builds on</SectionTitle>
          <ul className="flex flex-wrap gap-x-4 gap-y-1">
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

      {hasSecondary && (
        <section className={SECTION_CLASSES}>
          <button
            type="button"
            aria-expanded={isExpanded}
            onClick={() => setIsExpanded((previous) => !previous)}
            className="cursor-pointer font-sans text-sm text-zinc-600 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-emerald-700"
          >
            {isExpanded ? "Collapse" : "Expand"}
          </button>
          {isExpanded && (
            <div className="space-y-6">
              {decision.trace.length > 0 && (
                <div className="space-y-2">
                  <SectionTitle>Reasoning</SectionTitle>
                  <ol className="space-y-2">
                    {decision.trace.map((entry, index) => {
                      const timing = [
                        entry.duration_ms != null
                          ? formatDuration(entry.duration_ms)
                          : null,
                        entry.timestamp
                          ? formatClockTime(entry.timestamp)
                          : null,
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
                              (
                              {[
                                entry.agent,
                                ...entry.evidence_ids.map(citeLabel),
                              ].join(" · ")}
                              )
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
                </div>
              )}

              {contexts.length > 0 && (
                <div className="space-y-2">
                  <SectionTitle>Evidence context</SectionTitle>
                  {contexts.map((evidence) => (
                    <p
                      key={evidence.evidence_id}
                      className="border-l-2 border-zinc-200 pl-3 font-serif text-sm text-zinc-500"
                    >
                      {evidence.context}
                    </p>
                  ))}
                </div>
              )}

              {references.length > 0 && (
                <div className="space-y-2">
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
                </div>
              )}

              {reviewLines.length > 0 && (
                <div className="space-y-1 font-sans text-xs text-zinc-500">
                  {reviewLines.map((line) => (
                    <p key={line}>{line}</p>
                  ))}
                </div>
              )}
            </div>
          )}
        </section>
      )}
    </article>
  );
}
