"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  checkHealth,
  getProtocols,
  getRecommendations,
  updateRecommendation,
  type ProtocolSummary,
  type Recommendation,
  type RecommendationStatus,
  type Severity,
  type PipelineStep,
} from "@/lib/api";

export const DEFAULT_PROTOCOL: ProtocolSummary = {
  protocol_id: "prot-t2d-001",
  title: "Phase III Evaluation of SGLT2 Inhibitor in High-Risk T2D Cohort",
  status: "ready",
  data: {
    indication: "Type 2 Diabetes Mellitus",
    phase: "Phase 3",
    target_enrollment: 1200,
    primary_endpoint: "Mean HbA1c reduction from baseline at Week 24",
  },
};

export const DEFAULT_RECOMMENDATIONS: Recommendation[] = [
  {
    recommendation_id: "rec-001",
    protocol_id: "prot-t2d-001",
    source_step: "completeness",
    severity: "warning",
    title: "Missing eGFR Safety Monitoring Schedule",
    description:
      "Renal safety monitoring intervals are undefined for participants with baseline eGFR between 45-60 mL/min/1.73m².",
    status: "pending",
    comment: null,
    details: {
      section: "Safety Monitoring 6.3",
      suggested_action:
        "Add quarterly eGFR and urine albumin-to-creatinine ratio (uACR) checks.",
    },
  },
  {
    recommendation_id: "rec-002",
    protocol_id: "prot-t2d-001",
    source_step: "comparison",
    severity: "critical",
    title: "Comparator Arm Dose Misalignment with Standard of Care",
    description:
      "Active comparator arm specifies Sitagliptin 50mg daily instead of standard 100mg daily dosing for normal renal function.",
    status: "pending",
    comment: null,
    details: {
      comparator: "Sitagliptin",
      standard_dose: "100 mg QD",
      protocol_dose: "50 mg QD",
    },
  },
  {
    recommendation_id: "rec-003",
    protocol_id: "prot-t2d-001",
    source_step: "cohort",
    severity: "info",
    title: "Opportunity to Broaden Inclusion Criteria for Older Adults",
    description:
      "Upper age limit is capped at 70 years; peer diabetes trials include participants up to 75 years with frailty score criteria.",
    status: "pending",
    comment: null,
    details: {
      current_age_limit: "70 years",
      suggested_age_limit: "75 years",
      estimated_benefit: "+18% eligible patient population",
    },
  },
];

export default function HomePage() {
  const [backendStatus, setBackendStatus] = useState<
    "checking" | "connected" | "offline"
  >("checking");
  const [activeProtocol, setActiveProtocol] =
    useState<ProtocolSummary>(DEFAULT_PROTOCOL);
  const [recommendations, setRecommendations] =
    useState<Recommendation[]>(DEFAULT_RECOMMENDATIONS);
  const [selectedStep, setSelectedStep] = useState<"all" | PipelineStep>("all");
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function initData() {
      try {
        const health = await checkHealth();
        if (isMounted && health?.status) {
          setBackendStatus("connected");

          // Try fetching real protocols
          try {
            const protocols = await getProtocols();
            if (protocols.length > 0) {
              setActiveProtocol(protocols[0]);
              const recs = await getRecommendations(protocols[0].protocol_id);
              if (recs.length > 0) {
                setRecommendations(recs);
              }
            }
          } catch {
            // Keep default mock data if specific endpoints are still in progress
          }
        }
      } catch {
        if (isMounted) {
          setBackendStatus("offline");
        }
      }
    }

    initData();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!actionMessage) return;
    const timer = setTimeout(() => {
      setActionMessage(null);
    }, 4000);
    return () => clearTimeout(timer);
  }, [actionMessage]);

  const handleDecision = async (
    recId: string,
    decision: RecommendationStatus
  ) => {
    // Optimistic local state update
    setRecommendations((prev) =>
      prev.map((rec) =>
        rec.recommendation_id === recId ? { ...rec, status: decision } : rec
      )
    );

    try {
      if (backendStatus === "connected") {
        await updateRecommendation(activeProtocol.protocol_id, recId, {
          status: decision,
        });
        setActionMessage(`Recommendation ${recId} marked as ${decision}.`);
      } else {
        setActionMessage(
          `Recommendation ${recId} marked as ${decision} (demo mode: updated locally).`
        );
      }
    } catch {
      setActionMessage(
        `Recommendation ${recId} updated locally (backend returned an error).`
      );
    }
  };

  const severityBadge = (severity: Severity) => {
    const styles: Record<Severity, string> = {
      critical: "bg-red-100 text-red-800 border-red-300 dark:bg-red-950 dark:text-red-300 dark:border-red-800",
      warning: "bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-800",
      info: "bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-950 dark:text-blue-300 dark:border-blue-800",
    };
    return (
      <span
        className={`px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider rounded border ${styles[severity]}`}
      >
        {severity}
      </span>
    );
  };

  const stepBadge = (step: PipelineStep) => {
    const labels: Record<PipelineStep, string> = {
      completeness: "Completeness Check",
      comparison: "Protocol Comparison",
      cohort: "Cohort Feasibility",
    };
    return (
      <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-100 text-gray-700 dark:bg-zinc-800 dark:text-zinc-300">
        Step: {labels[step]}
      </span>
    );
  };

  const statusBadge = (status: RecommendationStatus) => {
    const styles: Record<RecommendationStatus, string> = {
      pending: "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-950 dark:text-yellow-300 dark:border-yellow-900",
      accepted: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-900",
      rejected: "bg-zinc-100 text-zinc-600 border-zinc-200 dark:bg-zinc-800 dark:text-zinc-400 dark:border-zinc-700",
    };
    return (
      <span
        className={`px-2 py-0.5 text-xs font-medium rounded border capitalize ${styles[status]}`}
      >
        {status}
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-950 text-zinc-900 dark:text-zinc-100">
      {/* Top Header */}
      <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-6 py-4">
        <div className="max-w-6xl mx-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold tracking-tight">
              Protocol Gap Agent — Diabetes Pipeline
            </h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              Foundational Review &amp; Recommendation Management
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Link
              href="/demo"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors shadow-sm"
            >
              Open Demo Pipeline (/demo) &rarr;
            </Link>

            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Backend Status:
            </span>
            {backendStatus === "connected" && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                Connected (FastAPI Proxy)
              </span>
            )}
            {backendStatus === "offline" && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                <span className="w-2 h-2 rounded-full bg-amber-500"></span>
                Backend Offline (Demo Fallback)
              </span>
            )}
            {backendStatus === "checking" && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                <span className="w-2 h-2 rounded-full bg-zinc-400 animate-pulse"></span>
                Checking API...
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        {actionMessage && (
          <div className="p-4 rounded-lg border border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-200 text-sm flex items-center justify-between">
            <span>{actionMessage}</span>
            <button
              onClick={() => setActionMessage(null)}
              className="text-xs font-semibold underline hover:opacity-75"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Protocol Summary Section */}
        <section className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg p-6 shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-zinc-100 dark:border-zinc-800 pb-4">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400">
                Active Protocol
              </span>
              <h2 className="text-lg font-semibold mt-1">
                {activeProtocol.title}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-zinc-500 dark:text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-2 py-1 rounded">
                ID: {activeProtocol.protocol_id}
              </span>
              <span className="px-2.5 py-1 text-xs font-semibold rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300 capitalize">
                Status: {activeProtocol.status}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-2">
            {Object.entries(activeProtocol.data).map(([key, value]) => (
              <div
                key={key}
                className="p-3 bg-zinc-50 dark:bg-zinc-800/50 rounded border border-zinc-100 dark:border-zinc-800"
              >
                <span className="text-xs text-zinc-500 dark:text-zinc-400 capitalize block">
                  {key.replace(/_/g, " ")}
                </span>
                <span className="text-sm font-medium mt-0.5 block truncate">
                  {String(value)}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Recommendations Section */}
        <section className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">
                Pipeline Recommendations
              </h2>
              <p className="text-sm text-zinc-500 dark:text-zinc-400">
                Actionable findings generated by the analysis pipeline steps.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <div
                role="group"
                aria-label="Filter recommendations by step"
                className="inline-flex rounded-lg border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-1"
              >
                {(
                  [
                    { value: "all", label: "All Steps" },
                    { value: "completeness", label: "Completeness" },
                    { value: "comparison", label: "Comparison" },
                    { value: "cohort", label: "Cohort" },
                  ] as const
                ).map((tab) => (
                  <button
                    key={tab.value}
                    type="button"
                    onClick={() => setSelectedStep(tab.value)}
                    className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                      selectedStep === tab.value
                        ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                        : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
              <div className="text-sm text-zinc-500 dark:text-zinc-400">
                Total: {recommendations.length} | Pending:{" "}
                {recommendations.filter((r) => r.status === "pending").length}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            {recommendations
              .filter(
                (rec) =>
                  selectedStep === "all" || rec.source_step === selectedStep
              )
              .map((rec) => (
              <div
                key={rec.recommendation_id}
                className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg p-5 shadow-sm space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {severityBadge(rec.severity)}
                      {stepBadge(rec.source_step)}
                      {statusBadge(rec.status)}
                      <span className="text-xs font-mono text-zinc-400">
                        {rec.recommendation_id}
                      </span>
                    </div>
                    <h3 className="text-base font-semibold pt-1">
                      {rec.title}
                    </h3>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                    <button
                      onClick={() =>
                        handleDecision(rec.recommendation_id, "accepted")
                      }
                      className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                        rec.status === "accepted"
                          ? "bg-emerald-600 text-white font-semibold cursor-default"
                          : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-300 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-800"
                      }`}
                    >
                      {rec.status === "accepted" ? "Accepted" : "Accept"}
                    </button>
                    <button
                      onClick={() =>
                        handleDecision(rec.recommendation_id, "rejected")
                      }
                      className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                        rec.status === "rejected"
                          ? "bg-red-600 text-white font-semibold cursor-default"
                          : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border border-zinc-300 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700"
                      }`}
                    >
                      {rec.status === "rejected" ? "Rejected" : "Reject"}
                    </button>
                  </div>
                </div>

                <p className="text-sm text-zinc-600 dark:text-zinc-300 leading-relaxed">
                  {rec.description}
                </p>

                {Object.keys(rec.details).length > 0 && (
                  <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
                    {Object.entries(rec.details).map(([k, v]) => (
                      <div
                        key={k}
                        className="text-xs bg-zinc-50 dark:bg-zinc-800/40 px-2.5 py-1.5 rounded"
                      >
                        <span className="text-zinc-400 capitalize block font-mono">
                          {k.replace(/_/g, " ")}:
                        </span>
                        <span className="font-medium text-zinc-700 dark:text-zinc-200">
                          {String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
