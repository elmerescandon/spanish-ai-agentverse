# Protocol comparison rules (Step 2)

What the comparison agent treats as a peer, how it groups peers, and when
it flags a draft protocol. This is the version for clinical sign-off; the
same rules live as typed data in
`backend/agents/protocol_comparison/rules.py`. Change both together.

A flag means **unusual compared with peers**, never **wrong**. Strict
criteria can be deliberate (safety, enrichment); the doctor decides.

## 1. Which trials are peers

**Search** (ClinicalTrials.gov API v2): interventional trials with the same
condition, the same phase, the same population (pediatric or adult), that
started in the ten years before the draft protocol was issued. Trials that
started later could not have informed the draft, so they are left out.

**Screening** (on the registry's normalised fields, after the search):

| Rule | Why |
| --- | --- |
| Condition MeSH terms include the target condition (e.g. *Diabetes Mellitus, Type 2*) | The free-text search also matches trials that only mention it |
| Condition MeSH terms do not include an excluded condition (e.g. *Diabetes Mellitus, Type 1*) | Mixed or "double diabetes" trials study a different population |
| At least one non-placebo drug or biological intervention | Behavioural and supplement trials have different eligibility and design |
| Primary purpose is treatment | Prevention trials enrol a different population |

A record missing a field fails that rule. Every excluded trial is kept
with its reasons so a reviewer can check the screening.

## 2. Drug classes

Peers are grouped by drug class to find same-class trials. A study's
classes come from its non-placebo intervention names and the registry's
intervention MeSH terms, matched against generic names and known
development codes:

| Class | Drugs |
| --- | --- |
| SGLT2 inhibitor | canagliflozin, dapagliflozin, empagliflozin, ertugliflozin, sotagliflozin |
| GLP-1 receptor agonist | exenatide, liraglutide, dulaglutide (LY2189265), semaglutide, lixisenatide, albiglutide |
| GIP/GLP-1 receptor agonist | tirzepatide |
| DPP-4 inhibitor | sitagliptin, saxagliptin, alogliptin, linagliptin, vildagliptin |
| Biguanide | metformin |
| Insulin | any insulin |
| Sulfonylurea | glimepiride, glipizide, glyburide, glibenclamide, gliclazide |
| Thiazolidinedione | pioglitazone, rosiglitazone |

A drug not in the table gets no class, so it never counts as same-class.

## 3. Peer groups and when to flag (proposed, needs sign-off)

Each dimension is compared against three peer groups:

| Group | Members |
| --- | --- |
| All peers | Every screened peer that states a value |
| Recent peers | Peers that started in the 3 years before the draft |
| Same-class peers | Peers sharing a drug class with the draft |

Flag when either:

- the draft's value is outside the 10th–90th percentile of all peers, or
- the draft is stricter than **every** recent peer, or than every
  same-class peer, and that group has at least 3 peers.

No flag is raised from fewer than 10 peers overall ("insufficient peers").
Every card shows how many peers each group contains and how many state a
value (coverage).

## 4. Dimensions

To be filled in as each dimension is built, with: definition and unit,
where the draft's value comes from, where peers' values come from, which
direction counts as stricter.
