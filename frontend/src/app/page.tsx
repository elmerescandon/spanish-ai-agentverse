"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AsciiProteinViewer } from "@/components/ascii-protein-viewer";
import { InsulinIcon } from "@/components/insulin-icon";
import { LogoIntro } from "@/components/logo-intro";
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
  readonly summary: string;
}

const PIPELINE_STEPS: readonly StepData[] = [
  {
    id: "step-00",
    number: "00",
    phase: "Read",
    title: "Understand the protocol",
    summary:
      "Turns the PDF into structured sections and criteria, each linked to its source page.",
  },
  {
    id: "step-01",
    number: "01",
    phase: "Check",
    title: "Find missing or conflicting parts",
    summary:
      "Flags gaps and contradictions before they turn into amendments.",
  },
  {
    id: "step-02",
    number: "02",
    phase: "Compare",
    title: "Compare with similar trials",
    summary:
      "Flags criteria that fall outside what comparable diabetes trials used.",
  },
  {
    id: "step-03",
    number: "03",
    phase: "Simulate",
    title: "Count the patients you would lose",
    summary:
      "Shows how many real patients each criterion removes from the pool.",
  },
  {
    id: "step-04",
    number: "04",
    phase: "Decide",
    title: "Doctors make the call",
    summary:
      "Each finding becomes a card. Nothing changes without physician sign-off.",
  },
];

export default function HomePage() {
  const serifFont = {
    fontFamily:
      "var(--font-serif), 'Libre Baskerville', Georgia, 'Times New Roman', serif",
  };

  const [activeStepIndex, setActiveStepIndex] = useState<number>(0);
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
      <LogoIntro />

      {/* Fixed 3D Rotating ASCII Protein Background */}
      <AsciiProteinViewer />

      {/* Floating Top Navigation */}
      <header className="sticky top-0 z-30 w-full border-b border-zinc-100/60 bg-white/70 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 sm:px-10 lg:px-12">
          <div className="flex items-center gap-3">
            <a
              href="#"
              style={serifFont}
              className="flex items-center gap-2.5 text-2xl sm:text-3xl font-normal tracking-tight text-zinc-950"
            >
              <InsulinIcon className="h-8 w-8 sm:h-9 sm:w-9 shrink-0" />
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
        <div className="glass-panel max-w-2xl lg:max-w-3xl space-y-8">
          <h1
            style={serifFont}
            className="text-2xl sm:text-3xl md:text-4xl font-normal tracking-tight text-zinc-900 leading-snug max-w-xl not-italic"
          >
            Find protocol problems before the first patient is enrolled.
          </h1>

          <p className="text-base sm:text-lg text-zinc-600 leading-relaxed font-sans max-w-xl">
            More than half of trial protocols need amendments mid-study.
            ProtocolAI checks a draft type 2 diabetes protocol against peer
            trials and real patient data, then gives doctors clear cards to
            act on.
          </p>

          <div className="pt-2 flex flex-wrap items-center gap-4">
            <Link
              href="/demo"
              className="inline-flex items-center justify-center rounded-lg bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 transition-colors"
            >
              Try demo
            </Link>
          </div>
        </div>

        {/* 3 Key Problem Metrics (#problem) without box borders */}
        <div id="problem" className="glass-panel mt-20 sm:mt-28 max-w-4xl">
          <div className="grid grid-cols-1 gap-10 sm:grid-cols-3">
            <div className="space-y-2">
              <span
                style={serifFont}
                className="text-5xl sm:text-6xl text-zinc-950 font-normal block leading-none"
              >
                57%
              </span>
              <p className="text-sm font-medium text-zinc-900">
                Need major amendments
              </p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                Over half change after the trial starts, adding months.
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
                Could have been avoided
              </p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                Nearly half come from flaws visible before launch.
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
                Close early for low enrollment
              </p>
              <p className="text-xs text-zinc-500 leading-relaxed">
                Criteria that are too narrow leave trials short of patients.
              </p>
            </div>
          </div>
          <p className="pt-4 font-sans text-xs text-zinc-400">
            Sources: Getz et al., Tufts CSDD (2024); Wong et al., JNCI (2020).
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
          <div className="glass-panel max-w-2xl space-y-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
              How it works
            </span>
            <h2
              style={serifFont}
              className="text-4xl sm:text-5xl md:text-6xl font-normal text-zinc-950 tracking-tight"
            >
              From draft protocol to doctor-approved changes
            </h2>
            <p className="text-base text-zinc-600 leading-relaxed">
              Five steps. Each one catches a different kind of problem.
            </p>
          </div>

          {/* Connected Process Flow Timeline */}
          <div className="max-w-4xl space-y-16 sm:space-y-20">
            {PIPELINE_STEPS.map((step, idx) => {
              const isActive = activeStepIndex === idx;
              const isDone = idx < activeStepIndex;
              const isLast = idx === PIPELINE_STEPS.length - 1;
              return (
                <div
                  key={step.id}
                  className={`relative pl-12 sm:pl-16 transition-opacity duration-500 ${
                    isActive ? "opacity-100" : "opacity-80 hover:opacity-100"
                  }`}
                  onClick={() => setActiveStepIndex(idx)}
                >
                  {/* Connector to the next marker. It starts at the bottom of
                      its own marker and ends at the top of the next one:
                      step gap (64/80px) + marker offset (24/32px) below. */}
                  {!isLast && (
                    <div
                      aria-hidden="true"
                      className="absolute left-[15px] top-14 -bottom-[88px] w-0.5 bg-zinc-200 sm:top-16 sm:-bottom-28"
                    >
                      <div
                        className={`w-full bg-emerald-600 transition-[height] duration-500 ease-out ${
                          isDone ? "h-full" : "h-0"
                        }`}
                      />
                    </div>
                  )}

                  {/* Step Node Marker: sits on the panel's first line */}
                  <div
                    className={`absolute left-0 top-6 sm:top-8 z-10 flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors duration-300 ${
                      isActive
                        ? "border-emerald-600 bg-emerald-50 text-emerald-800 shadow-sm"
                        : isDone
                          ? "border-emerald-600 bg-emerald-600 text-white"
                          : "border-zinc-300 bg-white text-zinc-500"
                    }`}
                  >
                    <span className="font-sans text-xs font-semibold">
                      {step.number}
                    </span>
                  </div>

                  {/* Step Header */}
                  <div className="glass-panel mx-0 space-y-3">
                    <div className="flex flex-wrap items-center gap-2.5">
                      <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
                        {step.phase}
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

                    <div className="pt-4 space-y-3">
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
                        <div className="p-4 bg-white/90 rounded-xl space-y-3 max-w-xl shadow-sm">
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
          <div className="glass-panel max-w-2xl space-y-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
              Evidence
            </span>
            <h2
              style={serifFont}
              className="text-4xl sm:text-5xl md:text-6xl font-normal text-zinc-950 tracking-tight"
            >
              Every finding points to real data
            </h2>
            <p className="text-base text-zinc-600 leading-relaxed">
              No guessing. Each check is tied to a public source.
            </p>
          </div>

          <div className="glass-panel divide-y divide-zinc-200/40 max-w-4xl py-0 sm:py-0">
            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                ClinicalTrials.gov
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Peer trials
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                Ten years of type 2 diabetes trials to compare against.
              </p>
            </div>

            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                SPIRIT 2025 &amp; ICH M11
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Clinical guidelines
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                A checklist of what a complete protocol must contain.
              </p>
            </div>

            <div className="py-7 space-y-1.5">
              <span className="font-sans text-xs font-semibold uppercase tracking-wide text-emerald-800">
                MIMIC-IV &amp; Synthea
              </span>
              <h4
                style={serifFont}
                className="text-2xl font-normal text-zinc-900"
              >
                Patient records
              </h4>
              <p className="text-sm text-zinc-600 leading-relaxed">
                Real and synthetic patients to test who would qualify.
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
          <div className="glass-panel max-w-2xl space-y-4">
            <span className="font-sans text-xs font-semibold uppercase tracking-wider text-emerald-800">
              Safety
            </span>
            <h2
              style={serifFont}
              className="text-4xl sm:text-5xl md:text-6xl font-normal text-zinc-950 tracking-tight"
            >
              Built so doctors stay in control
            </h2>
            <p className="text-base text-zinc-600 leading-relaxed">
              The tool suggests. Clinicians decide.
            </p>
          </div>

          <div className="glass-panel grid grid-cols-1 gap-12 md:grid-cols-2 max-w-4xl">
            <div className="space-y-6">
              <h3
                style={serifFont}
                className="text-2xl sm:text-3xl font-normal text-zinc-950"
              >
                How we measure accuracy
              </h3>
              <ul className="space-y-5 text-sm text-zinc-600">
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-emerald-700 text-xs mt-0.5">
                    01
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Extraction
                    </strong>
                    Checked against hand-labeled protocols.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-emerald-700 text-xs mt-0.5">
                    02
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Amendment hit-rate
                    </strong>
                    Flags compared with amendments that really happened.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-emerald-700 text-xs mt-0.5">
                    03
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Patient mix
                    </strong>
                    Simulated cohorts compared with enrolled populations.
                  </div>
                </li>
              </ul>
            </div>

            <div className="space-y-6">
              <h3
                style={serifFont}
                className="text-2xl sm:text-3xl font-normal text-zinc-950"
              >
                How we manage risk
              </h3>
              <ul className="space-y-5 text-sm text-zinc-600">
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-rose-700 text-xs mt-0.5">
                    01
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      No silent guesses
                    </strong>
                    Anything we cannot simulate is labeled as such.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-rose-700 text-xs mt-0.5">
                    02
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Visible logic
                    </strong>
                    Each card shows the query next to the protocol text.
                  </div>
                </li>
                <li className="flex items-start gap-3">
                  <span className="font-sans font-semibold text-rose-700 text-xs mt-0.5">
                    03
                  </span>
                  <div>
                    <strong className="text-zinc-900 block font-medium">
                      Physician sign-off
                    </strong>
                    Safety criteria are never relaxed automatically.
                  </div>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative z-10 border-t border-zinc-200/60 bg-white/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-6 py-12 sm:px-10 md:flex-row md:items-start md:justify-between lg:px-12">
          <div className="max-w-sm space-y-3">
            <a
              href="#"
              style={serifFont}
              className="flex items-center gap-2.5 text-2xl font-normal tracking-tight text-zinc-950"
            >
              <InsulinIcon className="h-8 w-8 shrink-0" />
              ProtocolAI
            </a>
            <p className="text-sm text-zinc-600 leading-relaxed">
              Catch protocol problems in type 2 diabetes trials before the first
              patient is enrolled.
            </p>
          </div>

          <nav
            aria-label="Footer"
            className="flex flex-wrap gap-x-8 gap-y-3 font-sans text-sm font-medium text-zinc-600"
          >
            <a href="#problem" className="hover:text-zinc-950 transition-colors">
              Problem
            </a>
            <a href="#pipeline" className="hover:text-zinc-950 transition-colors">
              Pipeline
            </a>
            <a href="#data" className="hover:text-zinc-950 transition-colors">
              Data
            </a>
            <a href="#validation" className="hover:text-zinc-950 transition-colors">
              Validation
            </a>
          </nav>
        </div>

        <div className="border-t border-zinc-200/60">
          <p className="mx-auto max-w-7xl px-6 py-5 font-sans text-xs text-zinc-500 sm:px-10 lg:px-12">
            Decision support only. Clinicians make the final call.
          </p>
        </div>
      </footer>
    </main>
  );
}
