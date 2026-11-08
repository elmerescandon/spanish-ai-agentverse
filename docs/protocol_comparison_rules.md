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

## 3. Tiers, weights and when to flag

These follow Stefan's *Comparison Thresholds* (sections 1.1, 1.2, 1.4
and 3.1). Where we simplify or add to them, it says so.

**Tiers and weights.** Every peer gets one tier and a weight:

| Tier | Match | Base weight |
| --- | --- | --- |
| Same drug (T1) | Shares a drug with the draft | 1.0 |
| Same class (T2) | Shares a drug class, not a drug | 0.6 |
| Same disease (T3) | Neither | 0.3 |

The weight halves for every 5 years between the peer's start and the
protocol date (continuously, so 2.5 years is ×0.71), and is ×0.8 for a
trial still running. A peer with no start date is not discounted.
Simplified for now: all peers are phase 3 (the search asks for it), so
the phase modifier is always ×1.0; start date stands in for
registration date; the era, region and sponsor-programme rules are not
applied yet.

**Effective number of peers.** n_eff = (Σw)² / Σw², over the peers
stating a value. It decides which rule applies:

| n_eff | Rule | Severity |
| --- | --- | --- |
| below 5 | No flag: "insufficient comparators" | — |
| 5 to 9 | Flag only a value beyond **every** peer | S3 (advisory) |
| 10 or more | Flag a value outside the 10th–90th percentile | S2 |

Both directions flag: stricter and looser. A value exactly on the 10th
or 90th percentile, or equal to the most extreme peer, is not flagged.
Percentiles are weighted with linear interpolation; with equal weights
they equal numpy's default. Looser values tied to a known safety signal
(Stefan's S1 case) are not detected yet and get S2.

**Official verdict and category breakdown.** The official verdict uses
all peers, weighted. As a breakdown, the same rule also runs unweighted
on three categories, each with its own verdict:

| Category | Members |
| --- | --- |
| All peers | Every screened peer |
| Recent peers | Started in the 3 years before the protocol date |
| Same drug | Tier T1 |

A category flag is shown but is not an official flag.

**Same-drug note (our addition).** When the draft is stricter or looser
than every same-drug peer, the card shows a note, even with no flag.
Stefan ranks earlier trials of the same drug above general comparator
norms, and the weighting can hide them because there are usually few.

## 4. Dimensions

For now the draft's values are read from its own registry record, like
the peers'. They will come from the parsed protocol, because the
registry shows the protocol after its amendments.

| Dimension | Unit | Stricter when | Peers' value from |
| --- | --- | --- | --- |
| Minimum age | years | higher | registry `minimumAge` |
| Maximum age | years | lower | registry `maximumAge` |
| Enrollment | participants | higher (more to recruit) | registry `enrollmentInfo` |
| HbA1c lower bound | % | higher | eligibility text, read by the LLM |
| HbA1c upper bound | % | lower | eligibility text, read by the LLM |
| ALT/AST exclusion limit | × ULN | lower | eligibility text, read by the LLM |
| eGFR exclusion cut-off | mL/min/1.73 m² | higher | eligibility text, read by the LLM |

**Lab limits from eligibility text.** The LLM lists every numeric HbA1c,
ALT, AST and eGFR limit as a predicate (test, operator, value, unit,
inclusion or exclusion, exact quote). Code then:

- rejects any predicate whose quote is not in the text;
- treats an inclusion bound and its mirror-image exclusion as the same
  limit ("include HbA1c ≤ 10.5%" = "exclude HbA1c > 10.5%");
- converts HbA1c in mmol/mol to % with Stefan's formula, and rejects
  ALT/AST limits in absolute U/L (only multiples of ULN compare);
- when a trial states several limits for one dimension (usually for
  different subgroups), uses the loosest, since together they bound the
  eligible population.

eGFR cut-offs are compared whatever equation they use; Stefan's rule
against comparing different equations is not applied yet. The LLM's
replies are cached in `data/peers/lab_limits/` and reused while the text
is unchanged.

Registry ages in months, weeks or days are converted to years. A peer
with no value, or one that cannot be read, is left out of that
dimension and shows as "not stated" in the evidence; it still counts in
the group's size. A peer with no maximum age is treated as not stating
one, not as having no limit.

Peers' enrollment is usually the number actually enrolled, while a
draft states a target; the evidence shows which each value is.

## 5. Suggestions and reasoning

A dimension gets a card when the official verdict or any category
flags it, or when the same-drug note applies. Each flagging category
gets one suggested value, always taken from the peers' own values:

| Rule that flagged | Suggested value |
| --- | --- |
| Outside the 10th–90th percentile | The nearest edge of that range |
| Beyond every peer | The nearest peer value |

The card says whether the flag is official, with its severity.

An LLM then writes the reasoning for the doctor from the same facts:
what is out of line, why it matters, what changing it could cost, and a
leaning (bring in line, keep as is, or needs clinical judgement). It
never proposes numbers. Any trial it cites that is not among the
compared peers is shown as a warning on the card.

The doctor decides: bring the value in line with one suggestion, or
keep it, with a reason.
