# spanish-ai-agentverse — Protocol Gap Agent

Clinical trial protocols are frequently amended (57%, nearly half avoidable) and often fail to enroll (~18% close for low accrual). **Protocol Gap Agent** is a multi-agent system built on Fetch.ai uAgents for the Agentverse UCL hackathon that reviews draft **Diabetes** clinical trial protocols with a doctor-in-the-loop workflow before the trial starts.

## Pipeline & Team Workflow

- **Clinical Rules & Guidelines (Stefan)**: Defines Diabetes protocol guidelines (SPIRIT 2025 / ICH M11) and templated comparison rules.
- **Step 0 — Data Ingestion (Alex)**: Parses draft protocol PDFs into a shared structured JSON contract.
- **Step 1 — Completeness & Consistency Check (Alex)**: Scores the protocol against clinical guidelines, verifies completeness with a human in the loop, and applies automated fixes.
- **Step 2 — Protocol Comparison (Theo)**: Retrieves similar Diabetes protocols from ClinicalTrials.gov, flags outliers using templated rules, presents reasoning traces for doctor review, and applies approved edits.
- **Step 3 — Cohort Comparison (Alvaro)**: Converts eligibility criteria into computable rules, filters MIMIC-IV / Synthea patient cohorts, benchmarks diversity and retention against peer trials, and isolates the criteria driving the largest patient drop-offs.
- **Step 4 — Reporting**: Groups recommendations into actionable **Decision Cards** (evidence, impact, options, and decision owner).

See [PROJECT.md](PROJECT.md) for the full system design, task checklists, data sources, and evaluation metrics.

## Setup

You need [uv](https://docs.astral.sh/uv/) installed.

```bash
make install          # installs Python 3.14, dependencies and pre-commit hooks
cp .env.example .env  # then fill in the keys
make dev              # runs the backend with hot reload
```

## Before you push

```bash
make check            # format + lint + test
```

Read [CONVENTIONS.md](CONVENTIONS.md) before writing code. It covers naming, typing, tests and the git workflow.
