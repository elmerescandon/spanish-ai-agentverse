# spanish-ai-agentverse — Protocol Gap Agent

Clinical trial protocols are frequently amended (57% have at least one substantial amendment, ~45% of which are avoidable) and often fail to enroll (~18% of cooperative-group cancer trials close for low accrual). Many of these flaws are visible in the draft protocol before the trial starts.

**Protocol Gap Agent** is a multi-agent system built on Fetch.ai uAgents for the Agentverse UCL hackathon that reviews draft clinical trial protocols before launch and surfaces actionable findings as clinician **Decision Cards**.

## How It Works

1. **Ingestion & Completeness (`parser`, `completeness`)**: Parses draft protocol PDFs (plus SAP and consent forms) into a shared ICH M11 JSON contract, scores every SPIRIT 2025 / ICH M11 checklist item (`present`, `weak`, or `missing` with page citations), and checks cross-document consistency.
2. **Past-Protocol Comparison (`comparison`)**: Retrieves similar trials from ClinicalTrials.gov / AACT (same condition, phase, intervention class, last ~10 years) and flags outlier lab thresholds, heavier visit schedules, or optimistic sample-size assumptions.
3. **Cohort Simulation & Gap Analysis (`cohort`)**: Translates eligibility criteria into computable OMOP queries, simulates attrition waterfalls on patient data (Synthea and MIMIC-IV), and benchmarks subgroup representation against the disease population and peer trials.
4. **Missing-Patient & Center Extension (`extension`)**: Prioritizes under-represented subgroups using clinician-weighted factors, estimates county-level eligible/missing patient pools (SEER, CDC PLACES, Census ACS), and ranks candidate trial sites (NPPES, CMS, competing trials saturation).

Each finding is delivered as a **Decision Card** containing the verbatim evidence (page and section), estimated impact, concrete options, and decision owner. The agent proposes; clinicians decide.

See [PROJECT.md](PROJECT.md) for the complete system design, phased roadmap, data sources, evaluation metrics, and team task breakdown.

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
