# Clinical Trial Protocol Data Gathering & Feature Engineering Guide

This guide details how clinical trial protocol data is gathered from the **ClinicalTrials.gov REST API v2**, how raw records are normalized and mapped into feature vectors, and how protocols are clustered to detect design defects before trials launch.

---

## 1. Data Source & Protocol Registry Overview

- **Source**: [ClinicalTrials.gov API v2](https://clinicaltrials.gov/api/v2/)
- **Protocol Records**: Over 450,000 global clinical studies with standardized protocol sections.
- **Access Protocol**:
  - Base URL: `https://clinicaltrials.gov/api/v2/studies`
  - Rate Limiting: 1 request per second (polite client).
  - Format: JSON.
  - License / Usage: Public domain biomedical research registry, terms documented in `.licenses/clinical_trials_database_LICENSE.txt`.

---

## 2. API Endpoints & Query Formulation

### 2.1 Core Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/studies` | `GET` | Filter, search, and paginate multiple protocol records. |
| `/studies/{nctId}` | `GET` | Retrieve the complete detailed protocol for a single trial. |
| `/studies/metadata` | `GET` | List available modules and fields across the registry. |

### 2.2 Target Query Formulation (Focus: Diabetes)

To study protocol design, amendment risks, and termination failure modes in **Diabetes**, we query interventional studies across both successful (`COMPLETED`) and halted/failed (`TERMINATED`, `WITHDRAWN`, `SUSPENDED`) trials:

```http
GET https://clinicaltrials.gov/api/v2/studies?query.cond=diabetes&filter.overallStatus=COMPLETED,TERMINATED,WITHDRAWN,SUSPENDED&filter.advanced=AREA[StudyType]INTERVENTIONAL&pageSize=100&countTotal=true&fields=NCTId,BriefTitle,OfficialTitle,OverallStatus,WhyStopped,StartDate,CompletionDate,LeadSponsorName,OversightModule,Phase,DesignModule,ArmsInterventionsModule,OutcomesModule,EligibilityModule,ContactsLocationsModule,DerivedSection
```

### 2.3 Parameter Breakdown

- `query.cond`: Disease / condition keyword (e.g. `diabetes`, `Type 2 Diabetes Mellitus`).
- `filter.overallStatus`: Comma-separated list of target statuses.
- `filter.advanced`: Essie expression (e.g. `AREA[StudyType]INTERVENTIONAL` to isolate active treatment protocols from purely observational registries).
- `pageSize`: Number of studies per page (max 1,000; recommended 50–100 for network stability).
- `pageToken`: Cursor returned in the previous response to retrieve the next page.
- `fields`: Restricts payload size, ensuring high throughput and fast extraction.

---

## 3. Protocol Field Mapping & Extraction

Every protocol record returned by the API is parsed into a structured schema:

| API Field Path | Type | Feature Extracted | Clinical & Risk Significance |
|---|---|---|---|
| `protocolSection.identificationModule.nctId` | string | `nct_id` | Unique primary key (e.g., `NCT00976456`). |
| `protocolSection.identificationModule.briefTitle` | string | `title` | Study title for semantic search & display. |
| `protocolSection.statusModule.overallStatus` | string | `status` | Ground truth label (`COMPLETED`, `TERMINATED`, `WITHDRAWN`). |
| `protocolSection.statusModule.whyStopped` | string \| None | `termination_reason` | Free-text reason for early trial halting. Categorized into: `ENROLLMENT_SHORTFALL`, `SAFETY_TOXICITY`, `FUTILITY_EFFICACY`, `SPONSOR_BUSINESS`, `REGULATORY_CMC`. |
| `protocolSection.designModule.phases` | list[str] | `phase` | Standardized trial phase (`PHASE1` to `PHASE4`). |
| `protocolSection.designModule.designInfo.allocation` | string | `allocation` | `RANDOMIZED` vs `NON_RANDOMIZED`. |
| `protocolSection.designModule.designInfo.interventionModel` | string | `intervention_model` | `PARALLEL`, `CROSSOVER`, `FACTORIAL`, `SINGLE_GROUP`. |
| `protocolSection.designModule.designInfo.maskingInfo.masking` | string | `masking` | `NONE` (open label), `SINGLE`, `DOUBLE`, `TRIPLE`, `QUADRUPLE`. |
| `protocolSection.designModule.enrollmentInfo.count` | int | `target_enrollment` | Target sample size; evaluated against site count. |
| `protocolSection.armsInterventionsModule.armGroups` | list | `arm_count` | Topology complexity of treatment arms. |
| `protocolSection.outcomesModule.primaryOutcomes` | list | `num_primary_outcomes` | Number of primary endpoints (>1 raises multiplicity & sample size burden). |
| `protocolSection.outcomesModule.secondaryOutcomes` | list | `num_secondary_outcomes` | Number of secondary endpoints (>15 signals protocol assessment fatigue). |
| `protocolSection.eligibilityModule.eligibilityCriteria` | string | `num_inclusion`, `num_exclusion`, `exclusion_ratio` | Parsed list of inclusion/exclusion rules. High exclusion counts directly drive enrollment shortfalls. |
| `protocolSection.eligibilityModule.minimumAge` / `maximumAge` | string | `min_age_years`, `max_age_years`, `age_span` | Standardized numeric ages in years. |
| `protocolSection.eligibilityModule.healthyVolunteers` | bool | `healthy_volunteers` | Population restriction indicator. |
| `protocolSection.contactsLocationsModule.locations` | list | `site_count`, `country_count`, `patients_per_site` | Accrual feasibility metric (patients / site). Too high = unrealistic recruitment rate; too low = excessive site activation delay. |
| `protocolSection.oversightModule.oversightHasDmc` | bool | `has_dmc` | Data Monitoring Committee presence (regulatory requirement for randomized multi-center trials). |
| `derivedSection.conditionBrowseModule.meshes` | list[dict] | `mesh_conditions` | Standard NLM MeSH ontology terms (e.g., `Diabetes Mellitus, Type 2`). |

---

## 4. How Protocols Are Clustered

Protocols are clustered in a **hybrid vector space**:

```
                       [ Candidate Protocol ]
                                 │
           ┌─────────────────────┴─────────────────────┐
           ▼                                           ▼
 [ Semantic Disease & Drug Vector ]        [ Design & Feasibility Vector ]
  - NLM MeSH headings                       - Standardized Phase (1..4)
  - Indication keywords                     - Log-transformed Target Enrollment
  - Intervention classes (e.g. GLP-1, SGLT2) - Number of Arms & Allocation
  - TF-IDF on Brief Description             - Inclusion & Exclusion Criteria Counts
                                            - Primary & Secondary Endpoint Counts
                                            - Site Count & Patients per Site
                                            - Masking Level & DMC Oversight
           └─────────────────────┬─────────────────────┘
                                 ▼
                     [ Protocol Cluster / Cohort ]
        e.g., "Phase 3 Randomized Parallel Type 2 Diabetes CVOT"
```

### 4.1 Diabetes Sub-Cohorts Observed in Practice

In diabetes, clinical protocols naturally stratify into distinct operational clusters:
1. **Early Phase 1/2 PK/PD & Clamp Studies**: Small sample size (10–40 patients), single-site, healthy volunteers or mild T2D, intensive metabolic testing.
2. **Phase 3 Glycemic Efficacy (Add-on Therapy)**: Multi-center (50–150 sites), parallel randomized double-blind, 400–1,200 patients, primary endpoint HbA1c at 24–52 weeks.
3. **Cardiovascular Outcomes Trials (CVOT)**: Megatrials (4,000–10,000 patients), global multi-center (300+ sites), long-term timeframes (2–5 years), complex adjudication.
4. **Type 1 Autoimmune & Beta-Cell Preservation**: Pediatric and young adult inclusion, tight immunological exclusion, biomarker endpoints (C-peptide).
5. **Digital Health & CGM / Technology Trials**: Non-drug or device interventional, open-label, outpatient monitoring.

---

## 5. Detecting Risks & Providing Recommendations

When a new protocol is evaluated:
1. It is mapped into the hybrid vector space and its **nearest peer cluster** of historical trials is identified.
2. We compute statistical distributions (median, 25th percentile, 75th percentile, 90th percentile) among **successful (completed) trials** vs. **failed/terminated trials** in that exact cohort.
3. Outliers trigger automated, rule-and-distribution-backed warnings:
   - **Exclusion Criteria Alert**: If a candidate specifies 26 exclusion criteria while completed trials in the cluster have a median of 11 (and terminated trials with slow accrual averaged 24), flag as high-risk for enrollment shortfall.
   - **Site Accrual Feasibility**: If a candidate plans 800 patients across 10 sites (80 pts/site) in an indication where peer trials enrolled 6.5 pts/site, recommend expanding the site network.
   - **Regulatory Oversight**: If a Phase 3 randomized trial lacks a DMC, flag for potential regulatory rejection or protocol amendment.
