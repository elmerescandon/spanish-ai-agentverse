"use client";

import { useEffect, useRef, useState } from "react";
import { AsciiProteinViewer } from "@/components/ascii-protein-viewer";
import type { ProtocolSummary, Recommendation } from "@/lib/api";

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

interface StepData {
  readonly id: string;
  readonly number: string;
  readonly phase: string;
  readonly title: string;
  readonly owner: string;
  readonly input: string;
  readonly process: string;
  readonly output: string;
  readonly summary: string;
}

const PIPELINE_STEPS: readonly StepData[] = [
  {
    id: "step-00",
    number: "00",
    phase: "Data Ingestion",
    title: "ICH M11 Document Structuring",
    owner: "Alex",
    input: "Draft Protocol PDF + SAP + Consent Forms",
    process:
      "Hierarchical section parser mapping text to ICH M11 headings, Schedule of Activities tables, and discrete criteria items",
    output: "Canonical ProtocolDocument JSON with page-level citations",
    summary:
      "Extracts unstructured clinical trial PDFs into a verified JSON structure with verbatim page quotes and Schedule of Activities matrices.",
  },
  {
    id: "step-01",
    number: "01",
    phase: "Rubric Audit",
    title: "Completeness & Consistency",
    owner: "Alex",
    input: "Structured ProtocolDocument JSON",
    process:
      "SPIRIT 2025 guideline evaluator scoring completeness (present, weak, missing) & cross-checking endpoints vs consent forms",
    output: "Consistency Audit Matrix & Missing Section Flags",
    summary:
      "Audits trial design against SPIRIT 2025 guidelines and resolves contradictions between primary endpoints, visit tables, and consent forms.",
  },
  {
    id: "step-02",
    number: "02",
    phase: "Peer Benchmarking",
    title: "Historical Peer Trial Comparison",
    owner: "Theo",
    input: "Protocol Eligibility & Design Rules",
    process:
      "AACT / ClinicalTrials.gov query matching 10-Yr Type 2 Diabetes trials by phase & intervention class across 10 clinical dimensions",
    output: "Percentile Distribution Gauge & Outlier Alert Flags",
    summary:
      "Flags statistical outliers outside peer 10th–90th percentiles for lab thresholds, washout periods, visit frequencies, and age boundaries.",
  },
  {
    id: "step-03",
    number: "03",
    phase: "Cohort Simulation",
    title: "Cohort Attrition & Diversity",
    owner: "Alvaro",
    input: "Computable Inclusion / Exclusion Rules",
    process:
      "OMOP SQL translation filtering real-world MIMIC-IV and Synthea patient populations to isolate recruitment drop-offs",
    output: "Recruitment Attrition Waterfall & Demographic Parity Benchmarks",
    summary:
      "Translates protocol criteria into executable SQL queries, simulating real patient attrition to identify criteria driving recruitment failure.",
  },
  {
    id: "step-04",
    number: "04",
    phase: "Human-in-the-Loop Review",
    title: "Clinician-Facing Decision Cards",
    owner: "Raul",
    input: "Multi-Agent Outlier & Feasibility Findings",
    process:
      "Decision Card synthesis bundling verbatim quotes, peer evidence, accrual deltas, and doctor approval actions",
    output: "Clinician-Approved Protocol Amendments & Final Report",
    summary:
      "Presents actionable Decision Cards requiring explicit physician sign-off, ensuring deliberate safety boundaries are never auto-relaxed.",
  },
];

export default function HomePage() {
  const serifFont = {
    fontFamily:
      "var(--font-serif), 'Libre Baskerville', Georgia, 'Times New Roman', serif",
  };

  const [activeStepIndex, setActiveStepIndex] = useState<number>(0);
  const [pipelineScrollProgress, setPipelineScrollProgress] =
    useState<number>(0.2);
  const [decisionAction, setDecisionAction] = useState<"pending" | "approved">(
    "pending"
  );
  const pipelineRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const handleScroll = () => {
      if (!pipelineRef.current) return;
      const rect = pipelineRef.current.getBoundingClientRect();
      const viewportHeight = window.innerHeight || 800;
      const totalDist = rect.height - viewportHeight * 0.5;
      if (totalDist > 0) {
        const scrolled = -rect.top + viewportHeight * 0.25;
        const progress = Math.max(0, Math.min(1, scrolled / totalDist));
        setPipelineScrollProgress(progress);

        const stepIdx = Math.min(
          PIPELINE_STEPS.length - 1,
          Math.max(0, Math.floor(progress * PIPELINE_STEPS.length))
        );
        setActiveStepIndex(stepIdx);
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    handleScroll();
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <main className="relative min-h-screen w-screen overflow-x-hidden bg-white text-zinc-900 font-sans selection:bg-emerald-100 selection:text-emerald-900">
      {/* Fixed 3D Rotating ASCII Protein Background */}
      <AsciiProteinViewer />

      {/* Floating Top Navigation */}
      <header className="sticky top-0 z-30 w-full border-b border-zinc-100/60 bg-white/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 sm:px-10 lg:px-12">
          <div className="flex items-center gap-3">
            <a
              href="#"
              style={serifFont}
              className="text-2xl sm:text-3xl font-normal tracking-tight text-zinc-900 hover:text-emerald-800 transition-colors"
            >
              ProtocolAI
            </a>
          </div>

          <nav className="flex items-center gap-6 sm:gap-8 font-sans text-xs sm:text-sm font-medium text-zinc-600">
            <a
              href="#problem"
              className="hover:text-zinc-950 transition-colors"
            >
              Problem
            </a>
            <a
              href="#pipeline"
              className="hover:text-zinc-950 transition-colors"
            >
              Pipeline
            </a>
            <a href="#data" className="hover:text-zinc-950 transition-colors">
              Data
            </a>
            <a
              href="#validation"
              className="hover:text-zinc-950 transition-colors"
            >
              Validation
            </a>
          </nav>
        </div>
      </header>

      {/* Hero Section: Left-Aligned so the 3D ASCII Protein dominates the Right */}
      <section className="relative z-10 mx-auto min-h-[calc(100vh-70px)] max-w-7xl px-6 pt-12 pb-24 sm:px-10 sm:pt-20 lg:px-12 flex flex-col justify-center">
        <div className="max-w-2xl lg:max-w-3xl space-y-8">
          <h1
            style={serifFont}
            className="text-2xl sm:text-3xl md:text-4xl font-normal tracking-tight text-zinc-900 leading-snug max-w-xl not-italic"
          >
            Catching avoidable clinical trial amendments and accrual bottlenecks
            before the first patient is enrolled.
          </h1>

          <p className="text-base sm:text-lg text-zinc-600 leading-relaxed font-sans max-w-xl">
            Clinical trial protocols are the blueprint of medical discovery, yet
            most require costly mid-trial amendments or stall due to overly
            restrictive eligibility criteria. Focused on Type 2 Diabetes
            Mellitus, ProtocolAI deploys a multi-agent verification pipeline
            that stress-tests draft protocols against regulatory guidelines,
            historical peer trials, and real-world patient cohorts prior to
            trial launch.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-4">
            <a
              href="#pipeline"
              className="inline-flex items-center justify-center rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 transition-colors"
            >
              Explore Verification Pipeline
            </a>
            <a
              href="#problem"
              className="inline-flex items-center justify-center rounded-lg border border-zinc-200/60 bg-white/60 px-5 py-2.5 text-sm font-medium text-zinc-800 hover:bg-zinc-50 transition-colors backdrop-blur-sm"
            >
              Clinical Problem & Evidence
            </a>
          </div>
        </div>

        {/* 3 Key Problem Metrics (#problem) without box borders */}
        <div id="problem" className="pt-20 sm:pt-28">
          <div className="grid grid-cols-1 gap-10 sm:grid-cols-3 max-w-4xl border-t border-zinc-200/40 pt-10">
            <div className="space-y-2">
              <span
                style={serifFont}
                className="text-5xl sm:text-6xl text-zinc-950 font-normal block leading-none"
              >
                57%
              </span>
              <p className="text-sm font-medium text-zinc-900">
                Protocols Require Major Amendments
              </p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                More than half of all clinical trial protocols undergo at least
                one substantial mid-study amendment, adding months to trial
                timelines.
              </p>
            </div>

            <div className="space-y-2">
              <span
                style={serifFont}
                className="text-5xl sm:text-6xl text-emerald-800 font-normal block leading-none"
              >
                45%
              </span>
              <p className="text-sm font-medium text-zinc-900">
                Amendments Are Entirely Preventable
              </p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                Nearly half of all protocol amendments stem from design flaws,
                inconsistencies, or unrealistic criteria detectable prior to
                study start.
              </p>
            </div>

            <div className="space-y-2">
              <span
                style={serifFont}
                className="text-5xl sm:text-6xl text-rose-800 font-normal block leading-none"
              >
                18%
              </span>
              <p className="text-sm font-medium text-zinc-900">
                Trials Terminated Early for Accrual
              </p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                Nearly one in five trials close early or fail to reach target
                enrollment due to recruitment bottlenecks and overly narrow
                cohort filters.
              </p>
            </div>
          </div>
          <p className="pt-4 font-sans text-xs text-zinc-400">
            Source: Getz et al., Tufts CSDD (2024); Wong et al., JNCI (2020);
            AACT Database analysis.
          </p>
        </div>
      </section>

      {/* Section 01: Multi-Agent Connected Process Pipeline (#pipeline) */}
      <section
        id="pipeline"
        ref={pipelineRef}
        className="relative z-10 border-t border-zinc-200/40 bg-zinc-50/50 backdrop-blur-[2px] py-24 sm:py-32"
      >
        <div className="mx-auto max-w-7xl px-6 sm:px-10 lg:px-12 space-y-16">
          <div className="max-w-2xl space-y-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
              Interactive Process Flow
            </span>
            <h2
              style={serifFont}
              className="text-4xl sm:text-5xl md:text-6xl font-normal text-zinc-950 tracking-tight"
            >
              End-to-End Multi-Agent Architecture
            </h2>
            <p className="text-base text-zinc-600 leading-relaxed">
              Each step is an active process transformation. An autonomous
              multi-agent loop converts draft protocol PDFs, SAPs, and consent
              forms into computable rules and clinician-approved Decision Cards.
            </p>
          </div>

          {/* Connected Process Flow Timeline */}
          <div className="relative pl-8 sm:pl-12 max-w-4xl space-y-16 sm:space-y-20">
            {/* Continuous Vertical Connecting Spine */}
            <div className="absolute left-3.5 sm:left-5 top-4 bottom-8 w-0.5 bg-zinc-200/60">
              <div
                className="w-full bg-emerald-600 transition-all duration-300 ease-out"
                style={{
                  height: `${Math.max(8, pipelineScrollProgress * 100)}%`,
                }}
              />
            </div>

            {PIPELINE_STEPS.map((step, idx) => {
              const isActive = activeStepIndex === idx;
              return (
                <div
                  key={step.id}
                  className={`relative transition-all duration-500 ${
                    isActive ? "opacity-100" : "opacity-80 hover:opacity-100"
                  }`}
                  onClick={() => setActiveStepIndex(idx)}
                >
                  {/* Step Node Marker on the Spine */}
                  <div
                    className={`absolute -left-8 sm:-left-12 top-0.5 flex h-7 w-7 sm:h-8 sm:w-8 items-center justify-center rounded-full border-2 transition-all duration-300 ${
                      isActive
                        ? "border-emerald-600 bg-emerald-50 text-emerald-800 scale-110 shadow-sm"
                        : "border-zinc-300 bg-white text-zinc-500"
                    }`}
                  >
                    <span className="font-sans text-xs font-semibold">
                      {step.number}
                    </span>
                  </div>

                  {/* Step Header */}
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
                        {step.phase}
                      </span>
                      <span className="text-zinc-300">·</span>
                      <span className="font-sans text-xs font-medium text-zinc-500">
                        Lead: {step.owner}
                      </span>
                    </div>

                    <h3
                      style={serifFont}
                      className="text-2xl sm:text-3xl font-normal text-zinc-950"
                    >
                      {step.title}
                    </h3>

                    <p className="text-sm text-zinc-600 leading-relaxed max-w-2xl font-sans">
                      {step.summary}
                    </p>

                    {/* Active Process Transformation Stage (Input ➔ Process ➔ Output) */}
                    <div className="pt-4 space-y-3">
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
                        <div className="p-3 bg-white/80 rounded-lg border-l-2 border-zinc-200 space-y-1">
                          <span className="text-[11px] font-semibold text-zinc-400 uppercase tracking-wide block">
                            Input
                          </span>
                          <span className="text-zinc-800 font-medium block">
                            {step.input}
                          </span>
                        </div>
                        <div className="p-3 bg-white/80 rounded-lg border-l-2 border-emerald-500 space-y-1">
                          <span className="text-[11px] font-semibold text-emerald-700 uppercase tracking-wide block">
                            Agent Process
                          </span>
                          <span className="text-zinc-800 font-medium block">
                            {step.process}
                          </span>
                        </div>
                        <div className="p-3 bg-white/80 rounded-lg border-l-2 border-zinc-900 space-y-1">
                          <span className="text-[11px] font-semibold text-zinc-900 uppercase tracking-wide block">
                            Output Artifact
                          </span>
                          <span className="text-zinc-800 font-medium block">
                            {step.output}
                          </span>
                        </div>
                      </div>

                      {/* Specialized Interactive Visual Transformations */}
                      {step.id === "step-01" && (
                        <div className="p-4 bg-white/70 rounded-xl space-y-2.5 max-w-xl">
                          <span className="text-xs font-semibold text-zinc-700 block">
                            SPIRIT 2025 Audit Matrix Live Status
                          </span>
                          <div className="space-y-1.5 text-xs">
                            <div className="flex justify-between text-zinc-600">
                              <span>Present & Verified Criteria</span>
                              <span className="font-semibold text-emerald-700">
                                92% (34 items)
                              </span>
                            </div>
                            <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                              <div className="h-full bg-emerald-600 w-[92%]" />
                            </div>
                            <div className="flex justify-between text-zinc-600 pt-1">
                              <span>Weak or Ambiguous Definitions</span>
                              <span className="font-semibold text-amber-700">
                                8% (3 items)
                              </span>
                            </div>
                            <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                              <div className="h-full bg-amber-500 w-[8%]" />
                            </div>
                          </div>
                        </div>
                      )}

                      {step.id === "step-02" && (
                        <div className="p-4 bg-white/70 rounded-xl space-y-2 max-w-xl">
                          <span className="text-xs font-semibold text-zinc-700 block">
                            Historical Peer Trials Distribution (AACT Diabetes
                            Trials)
                          </span>
                          <div className="relative pt-3 pb-2">
                            <div className="h-2 w-full bg-zinc-200/60 rounded-full relative">
                              <div className="absolute left-[15%] right-[20%] top-0 bottom-0 bg-sky-200/80 rounded-full" />
                              <div className="absolute left-[88%] -top-1 w-4 h-4 rounded-full bg-rose-600 border-2 border-white shadow" />
                            </div>
                            <div className="flex justify-between text-[11px] text-zinc-400 pt-1">
                              <span>10th Percentile</span>
                              <span>Peer Median</span>
                              <span className="text-rose-700 font-semibold">
                                Draft Protocol (Outlier)
                              </span>
                            </div>
                          </div>
                        </div>
                      )}

                      {step.id === "step-03" && (
                        <div className="p-4 bg-white/70 rounded-xl space-y-2 max-w-xl">
                          <span className="text-xs font-semibold text-zinc-700 block">
                            MIMIC-IV Patient Attrition Waterfall Simulation
                          </span>
                          <div className="space-y-1.5 text-xs">
                            <div className="flex justify-between">
                              <span className="text-zinc-600">
                                Initial T2D Patient Base
                              </span>
                              <span className="font-medium text-zinc-900">
                                12,400 pts (100%)
                              </span>
                            </div>
                            <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                              <div className="h-full bg-zinc-800 w-full" />
                            </div>

                            <div className="flex justify-between pt-1">
                              <span className="text-zinc-600">
                                After HbA1c &gt; 7.5% &amp; eGFR &gt; 45
                              </span>
                              <span className="font-medium text-zinc-900">
                                4,712 pts (38%)
                              </span>
                            </div>
                            <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                              <div className="h-full bg-emerald-600 w-[38%]" />
                            </div>

                            <div className="flex justify-between pt-1">
                              <span className="text-zinc-600">
                                After Concomitant Meds Washout
                              </span>
                              <span className="font-medium text-rose-700 font-semibold">
                                2,232 pts (18%)
                              </span>
                            </div>
                            <div className="h-1.5 w-full bg-zinc-100 rounded-full overflow-hidden">
                              <div className="h-full bg-rose-600 w-[18%]" />
                            </div>
                          </div>
                        </div>
                      )}

                      {step.id === "step-04" && (
                        <div className="p-4 bg-white/90 rounded-xl border-l-2 border-emerald-600 space-y-3 max-w-xl shadow-sm">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-zinc-900">
                              Decision Card: Section 6.3 Renal Safety
                            </span>
                            <span className="text-[11px] px-2 py-0.5 rounded bg-amber-50 text-amber-800 font-medium">
                              Estimated Accrual: +18%
                            </span>
                          </div>
                          <p className="text-xs text-zinc-600 leading-relaxed">
                            Recommendation: Add quarterly eGFR and uACR checks
                            for 45–60 mL/min cohort instead of outright
                            exclusion.
                          </p>
                          <div className="flex items-center gap-2 pt-1">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setDecisionAction("approved");
                              }}
                              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                                decisionAction === "approved"
                                  ? "bg-emerald-700 text-white"
                                  : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                              }`}
                            >
                              {decisionAction === "approved"
                                ? "✓ Approved by Clinician"
                                : "Approve Amendment"}
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setDecisionAction("pending");
                              }}
                              className="px-3 py-1 rounded text-xs font-medium bg-zinc-100 text-zinc-600 hover:bg-zinc-200 transition-colors"
                            >
                              Dismiss with Rationale
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Section 02: Foundational Clinical Data (#data) without boxy cards */}
      <section
        id="data"
        className="relative z-10 border-t border-zinc-200/40 bg-white py-24 sm:py-32"
      >
        <div className="mx-auto max-w-7xl px-6 sm:px-10 lg:px-12 space-y-16">
          <div className="max-w-2xl space-y-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
              Evidence & Ontology
            </span>
            <h2
              style={serifFont}
              className="text-4xl sm:text-5xl md:text-6xl font-normal text-zinc-950 tracking-tight"
            >
              Grounded in Regulatory Standards & Real-World Evidence
            </h2>
            <p className="text-base text-zinc-600 leading-relaxed">
              ProtocolAI does not rely on unconstrained general LLM speculation;
              every validation check is anchored against authoritative clinical
              trial registries, global protocol rubrics, and real-world EHR
              ontologies.
            </p>
          </div>

          <div className="divide-y divide-zinc-200/40 max-w-4xl">
            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                AACT / ClinicalTrials.gov
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Peer Protocol Corpus
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                Structured eligibility criteria, baseline enrolled
                demographics, and historical amendment logs from peer Type 2
                Diabetes trials over the last 10 years.
              </p>
            </div>

            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                SPIRIT 2025 & ICH M11
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Global Protocol Guidelines
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                Standardized completeness rubric covering trial estimands,
                Schedule of Activities tables, and predefined safety stopping
                rules.
              </p>
            </div>

            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                MIMIC-IV Real-World EHR
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Patient Cohort Filtering
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                Real-world longitudinal patient records used to simulate
                sequential criteria filtering, generate attrition waterfalls,
                and analyze subgroup inclusion.
              </p>
            </div>

            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                Synthea Synthetic Populations
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Deterministic Test Harness
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                Synthetic longitudinal patient records enabling rapid pipeline
                development, deterministic criteria rule verification, and
                continuous integration testing.
              </p>
            </div>

            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                OMOP Common Data Model & Athena
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Standardized Vocabularies
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                Standardized SNOMED, RxNorm, and LOINC clinical concepts
                powering unambiguous translation of free-text medical
                eligibility criteria into computable cohort queries.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Section 03: Validation Rigor & Safety Guardrails (#validation) */}
      <section
        id="validation"
        className="relative z-10 border-t border-zinc-200/40 bg-zinc-50/50 backdrop-blur-[2px] py-24 sm:py-32"
      >
        <div className="mx-auto max-w-7xl px-6 sm:px-10 lg:px-12 space-y-16">
          <div className="max-w-2xl space-y-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
              Clinical Safety & Governance
            </span>
            <h2
              style={serifFont}
              className="text-4xl sm:text-5xl md:text-6xl font-normal text-zinc-950 tracking-tight"
            >
              Validation Rigor & Clinical Safety Guardrails
            </h2>
            <p className="text-base text-zinc-600 leading-relaxed">
              Clinical decision support requires uncompromised transparency.
              ProtocolAI balances automated multi-agent extraction with strict
              safety controls.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-12 md:grid-cols-2 max-w-4xl border-t border-zinc-200/40 pt-10">
            {/* Left: Validation Metrics */}
            <div className="space-y-6">
              <h3
                style={serifFont}
                className="text-2xl sm:text-3xl font-normal text-zinc-950"
              >
                Ground-Truth Evaluation Metrics
              </h3>
              <ul className="space-y-5 text-sm text-zinc-600">
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-emerald-700 text-xs mt-0.5">
                    01
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Parser & Rule Extraction Accuracy
                    </strong>
                    Section-by-section extraction precision and criteria
                    fidelity benchmarked against hand-labeled gold standard
                    protocols and physician review.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-emerald-700 text-xs mt-0.5">
                    02
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Historical Amendment Hit-Rate
                    </strong>
                    Proportion of flagged outlier criteria that match actual
                    post-launch amendments recorded in AACT&apos;s History of
                    Changes.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-emerald-700 text-xs mt-0.5">
                    03
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Cohort Demographic Fidelity
                    </strong>
                    Simulated eligible demographic distributions benchmarked
                    against actual enrolled baseline populations reported on
                    ClinicalTrials.gov and FDA Drug Trials Snapshots.
                  </div>
                </li>
              </ul>
            </div>

            {/* Right: Safety Guardrails */}
            <div className="space-y-6">
              <h3
                style={serifFont}
                className="text-2xl sm:text-3xl font-normal text-zinc-950"
              >
                Clinical Risk Mitigations
              </h3>
              <ul className="space-y-5 text-sm text-zinc-600">
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-rose-700 text-xs mt-0.5">
                    01
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      No Silent Hallucinations
                    </strong>
                    Criteria that cannot be reliably modeled in electronic
                    health record data are explicitly labeled &ldquo;cannot
                    simulate&rdquo; rather than guessed or silently omitted.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-rose-700 text-xs mt-0.5">
                    02
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Transparent SQL / OMOP Query Inspection
                    </strong>
                    Generated computable query logic is rendered side-by-side
                    with verbatim protocol text inside each Decision Card for
                    immediate auditability.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-rose-700 text-xs mt-0.5">
                    03
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Clinician-Owned Safety Thresholds
                    </strong>
                    Deliberate strict safety criteria flagged as outliers are
                    routed as recommendations to reviewing physicians—never
                    auto-relaxed without clinical sign-off.
                  </div>
                </li>
              </ul>
            </div>
          </div>

          {/* Team & Project Credits Footer */}
          <div className="border-t border-zinc-200/40 pt-10 space-y-6 max-w-4xl">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <span
                  style={serifFont}
                  className="text-2xl font-normal text-zinc-950 block"
                >
                  ProtocolAI
                </span>
                <span className="text-xs text-zinc-500 font-sans">
                  Multi-Agent Verification · Diabetes Track Pipeline
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-emerald-600" />
                <span className="font-sans text-xs text-zinc-600 font-medium">
                  Built with Multi-Agent Verification Architecture
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4 font-sans text-xs pt-2">
              <div className="space-y-1">
                <span className="text-zinc-400 block text-[11px] uppercase tracking-wide">
                  Clinical Lead
                </span>
                <span className="text-zinc-900 font-medium block">Stefan</span>
                <span className="text-zinc-500 text-[11px]">
                  Guidelines & Rubric
                </span>
              </div>
              <div className="space-y-1">
                <span className="text-zinc-400 block text-[11px] uppercase tracking-wide">
                  Ingestion Lead
                </span>
                <span className="text-zinc-900 font-medium block">Alex</span>
                <span className="text-zinc-500 text-[11px]">
                  Parser & Completeness
                </span>
              </div>
              <div className="space-y-1">
                <span className="text-zinc-400 block text-[11px] uppercase tracking-wide">
                  Comparison Lead
                </span>
                <span className="text-zinc-900 font-medium block">Theo</span>
                <span className="text-zinc-500 text-[11px]">
                  Peer Trial Agent
                </span>
              </div>
              <div className="space-y-1">
                <span className="text-zinc-400 block text-[11px] uppercase tracking-wide">
                  Cohort Lead
                </span>
                <span className="text-zinc-900 font-medium block">Alvaro</span>
                <span className="text-zinc-500 text-[11px]">
                  Simulation & Waterfall
                </span>
              </div>
              <div className="space-y-1">
                <span className="text-zinc-400 block text-[11px] uppercase tracking-wide">
                  Frontend & Demo
                </span>
                <span className="text-zinc-900 font-medium block">Raul</span>
                <span className="text-zinc-500 text-[11px]">
                  Decision Cards & UI
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
