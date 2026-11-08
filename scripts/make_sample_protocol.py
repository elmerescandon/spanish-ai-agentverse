"""Generate the synthetic diabetes protocol PDF used to try /demo.

The protocol imitates the layout of the real demo protocols (title page,
synopsis, Schedule of Activities, eligibility, statistics, ethics) but
describes a fictional trial. It carries deliberate gaps, listed in
data/protocols/sample/README.md, so every agent has something to find.

Run with `make sample-protocol`; the output is deterministic, so the
committed PDF only changes when this file does.
"""

import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("data/protocols/sample/SYN-T2D-301_protocol.pdf")
PROTOCOL_NUMBER = "SYN-T2D-301"
PROTOCOL_VERSION = "Version 2.0"
PROTOCOL_DATE = "14 March 2026"
# Fixed date keeps the PDF bytes identical between runs.
CREATION_DATE = datetime(2026, 3, 14, 9, 0, tzinfo=UTC)
FONT_FAMILY = "Helvetica"
BODY_FONT_SIZE_PT = 10
HEADING_1_FONT_SIZE_PT = 13
HEADING_2_FONT_SIZE_PT = 11
HEADER_FONT_SIZE_PT = 8
LINE_HEIGHT_MM = 5
TABLE_LINE_HEIGHT_MM = 4.5
PAGE_MARGIN_MM = 20
BULLET_INDENT_MM = 6
PARAGRAPH_GAP_MM = 2
PAGE_BREAK_MARKER = "<<<PAGE>>>"
TABLE_MARKER_PREFIX = "<<<TABLE:"
SYNTHETIC_NOTICE = (
    "SYNTHETIC TEST PROTOCOL - FICTIONAL STUDY, NOT FOR CLINICAL USE"
)

SCHEDULE_OF_ACTIVITIES: list[list[str]] = [
    ["Procedure", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"],
    ["Study week", "-2", "0", "4", "12", "26", "39", "52", "56"],
    [
        "Visit window (days)",
        "+/-3",
        "0",
        "+/-3",
        "+/-5",
        "+/-5",
        "+/-7",
        "+/-7",
        "+/-7",
    ],
    ["Informed consent", "X", "", "", "", "", "", "", ""],
    ["Eligibility review", "X", "X", "", "", "", "", "", ""],
    ["Medical history", "X", "", "", "", "", "", "", ""],
    ["Physical examination", "X", "", "", "", "", "", "X", ""],
    ["Vital signs", "X", "X", "X", "X", "X", "X", "X", "X"],
    ["Body weight", "X", "X", "", "X", "X", "", "X", ""],
    ["12-lead ECG", "X", "", "", "", "", "", "X", ""],
    ["HbA1c (central lab)", "X", "X", "", "X", "", "", "X", ""],
    ["Fasting plasma glucose", "X", "X", "X", "X", "X", "X", "X", ""],
    ["Serum chemistry and eGFR", "X", "", "X", "X", "X", "", "X", "X"],
    ["Lipid panel", "", "X", "", "", "", "", "X", ""],
    ["Pregnancy test (WOCBP)", "X", "X", "", "X", "X", "X", "X", ""],
    ["Randomization (IWRS)", "", "X", "", "", "", "", "", ""],
    ["Dispense study drug", "", "X", "X", "X", "X", "X", "", ""],
    ["Drug accountability", "", "", "X", "X", "X", "X", "X", ""],
    ["Adverse event review", "", "X", "X", "X", "X", "X", "X", "X"],
    ["Concomitant medications", "X", "X", "X", "X", "X", "X", "X", "X"],
    ["SMBG diary review", "", "X", "X", "X", "X", "X", "X", ""],
    ["PRO questionnaires", "", "X", "", "", "X", "", "X", ""],
]

OBJECTIVES_AND_ENDPOINTS: list[list[str]] = [
    ["Objective", "Endpoint", "Time frame"],
    [
        (
            "Primary: demonstrate superiority of SYN-4417 14 mg over placebo "
            "in glycemic control"
        ),
        "Change from baseline in HbA1c (%)",
        "Week 26",
    ],
    [
        "Key secondary: effect on body weight",
        "Change from baseline in body weight (kg)",
        "Week 26",
    ],
    [
        "Key secondary: glycemic target attainment",
        "Proportion of participants with HbA1c < 7.0%",
        "Week 26",
    ],
    [
        "Secondary: fasting glucose",
        "Change from baseline in fasting plasma glucose (mg/dL)",
        "Weeks 26 and 52",
    ],
    [
        "Secondary: durability",
        "Change from baseline in HbA1c (%)",
        "Week 52",
    ],
    [
        "Safety",
        (
            "Incidence of treatment-emergent adverse events, including "
            "gastrointestinal events and hypoglycemia"
        ),
        "Week 0 to Week 56",
    ],
    [
        "Exploratory: patient-reported outcomes",
        "Change in DTSQ and IWQOL-Lite-CT total scores",
        "Week 52",
    ],
]

TABLE_OF_CONTENTS: list[list[str]] = [
    ["1 PROTOCOL SUMMARY", "4"],
    ["1.1 Synopsis", "4"],
    ["1.2 Schedule of Activities", "5"],
    ["2 INTRODUCTION", "6"],
    ["3 OBJECTIVES AND ENDPOINTS", "7"],
    ["4 STUDY DESIGN", "8"],
    ["5 STUDY POPULATION", "9"],
    ["6 STUDY INTERVENTION", "11"],
    ["7 DISCONTINUATION AND WITHDRAWAL", "12"],
    ["8 STUDY ASSESSMENTS AND PROCEDURES", "12"],
    ["9 STATISTICAL CONSIDERATIONS", "13"],
    ["10 REGULATORY, ETHICAL AND STUDY OVERSIGHT", "14"],
    ["11 REFERENCES", "15"],
    ["12 ABBREVIATIONS", "15"],
]


@dataclass(frozen=True)
class TableSpec:
    """Rows of a table plus how to lay it out."""

    rows: list[list[str]]
    column_widths_mm: tuple[float, ...]
    has_borders: bool = True


TABLES: dict[str, TableSpec] = {
    "toc": TableSpec(TABLE_OF_CONTENTS, (150, 20), has_borders=False),
    # Wide first column so procedure names don't wrap mid-word.
    "soa": TableSpec(SCHEDULE_OF_ACTIVITIES, (50,) + (15,) * 8),
    "objectives": TableSpec(OBJECTIVES_AND_ENDPOINTS, (65, 75, 30)),
}

# Body in a light markup: "# " and "## " are headings, "- " starts a
# bullet, blank lines separate blocks, wrapped lines are joined.
PROTOCOL_BODY = """
<<<PAGE>>>
# STATEMENT OF COMPLIANCE

The trial will be carried out in accordance with International Council
for Harmonisation Good Clinical Practice (ICH GCP E6(R3)), the Declaration
of Helsinki, and all applicable national regulations. All personnel
involved in the conduct of this study have completed Human Subjects
Protection and ICH GCP training.

The protocol, informed consent form(s), recruitment materials, and all
participant materials will be submitted to the Institutional Review Board
(IRB) or Independent Ethics Committee (IEC) for review and approval.
Approval of both the protocol and the consent form must be obtained
before any participant is enrolled.

# INVESTIGATOR'S SIGNATURE

I have read this protocol and agree to conduct the study as outlined
herein, in accordance with ICH GCP and all applicable regulatory
requirements.

Principal Investigator: ______________________ Date: ____________

Site name and number: ______________________

<<<PAGE>>>
# TABLE OF CONTENTS

<<<TABLE:toc>>>

<<<PAGE>>>
# 1 PROTOCOL SUMMARY

## 1.1 Synopsis

Title: A Phase 3, Randomized, Double-Blind, Placebo-Controlled,
Parallel-Group Study to Evaluate the Efficacy and Safety of Once-Daily
Oral SYN-4417 as Add-on to Metformin in Adults with Type 2 Diabetes
Mellitus Inadequately Controlled on Metformin Monotherapy

Brief title: GLYDE-2

Protocol number: SYN-T2D-301

Phase: Phase 3

Study description: This is a 52-week, multicenter, randomized,
double-blind, placebo-controlled, parallel-group study of SYN-4417, an
oral small-molecule glucagon-like peptide-1 (GLP-1) receptor agonist,
given once daily in addition to stable metformin. Participants are
randomized in a 1:1:1 ratio to SYN-4417 7 mg, SYN-4417 14 mg, or matching
placebo. A 2-week screening period precedes randomization and a 4-week
safety follow-up period follows the last dose.

Population: Approximately 600 adults aged 18 to 70 years with type 2
diabetes mellitus (T2DM), HbA1c between 7.5% and 9.5% inclusive, and a
stable dose of metformin of at least 1500 mg/day for at least 12 weeks
before screening.

Number of sites: Approximately 85 sites in 6 countries (United States,
Canada, United Kingdom, Germany, Spain and Poland).

Study intervention: SYN-4417 7 mg, SYN-4417 14 mg, or placebo tablets,
taken orally once daily in the morning for 52 weeks. Participants
randomized to 14 mg start on 7 mg for 4 weeks before escalating.

Primary endpoint: Change from baseline in HbA1c at Week 26.

Key secondary endpoints: Change from baseline in body weight at Week 26;
proportion of participants reaching HbA1c < 7.0% at Week 26.

Study duration: Approximately 58 weeks per participant (2-week
screening, 52-week treatment, 4-week follow-up). Total study duration
from first participant screened to last participant's last visit is
estimated at 30 months.

Masking: Double-blind (participant, investigator, outcomes assessor and
sponsor study team).

Sample size: 600 participants (200 per arm) provide 90% power to detect
a 0.3% difference in HbA1c change between SYN-4417 14 mg and placebo,
assuming a standard deviation of 1.1% and a two-sided alpha of 0.05.

<<<PAGE>>>
## 1.2 Schedule of Activities

<<<TABLE:soa>>>

Abbreviations: V = visit; WOCBP = women of childbearing potential;
IWRS = interactive web response system; SMBG = self-monitoring of blood
glucose; PRO = patient-reported outcome. Week 56 (V8) is the safety
follow-up visit, 4 weeks after the last dose.

<<<PAGE>>>
# 2 INTRODUCTION

## 2.1 Study Rationale

Type 2 diabetes mellitus affects more than 500 million adults worldwide,
and roughly half of treated patients do not reach the glycemic target of
HbA1c < 7.0%. Metformin remains first-line therapy, but most patients
require a second agent within a few years of diagnosis. Injectable GLP-1
receptor agonists lower HbA1c and body weight, yet the injection burden
limits uptake. An oral, small-molecule GLP-1 receptor agonist that does
not require fasting administration could widen access to this class.

## 2.2 Background

SYN-4417 is a non-peptide, orally bioavailable GLP-1 receptor agonist
with a half-life of approximately 21 hours, supporting once-daily
dosing without food restrictions. In the 12-week Phase 2 study
SYN-T2D-201 (N = 312), SYN-4417 14 mg reduced HbA1c by 1.2% from a
baseline of 8.1%, compared with 0.3% for placebo, and reduced body
weight by 3.4 kg compared with 0.8 kg. The most common adverse events
were nausea (18%), diarrhea (9%) and vomiting (5%), mostly mild and
occurring during dose escalation.

## 2.3 Risk/Benefit Assessment

Known potential risks include gastrointestinal adverse events, acute
pancreatitis, gallbladder events, and hypoglycemia when combined with
insulin secretagogues. Rodent studies showed thyroid C-cell tumours, a
class finding of uncertain relevance to humans; participants with a
personal or family history of medullary thyroid carcinoma are excluded.
Potential benefits include improved glycemic control and weight loss.
The sponsor considers the overall benefit/risk balance favourable.

<<<PAGE>>>
# 3 OBJECTIVES AND ENDPOINTS

<<<TABLE:objectives>>>

The primary estimand compares the mean change in HbA1c from baseline to
Week 26 between SYN-4417 14 mg and placebo in the randomized population.

<<<PAGE>>>
# 4 STUDY DESIGN

## 4.1 Overall Design

This is a Phase 3, multicenter, randomized, double-blind,
placebo-controlled, parallel-group study with three arms. Eligible
participants are randomized 1:1:1 by IWRS, stratified by baseline HbA1c
(<= 8.5% or > 8.5%) and region (North America or Europe). Randomization
uses permuted blocks of size 6.

Participants receive study drug for 52 weeks. The primary efficacy
assessment is at Week 26; the treatment period continues to Week 52 to
characterise durability and longer-term safety.

## 4.2 Scientific Rationale for Study Design

A placebo comparator on a background of metformin is the accepted
design for registration of a new glucose-lowering agent and allows the
treatment effect to be estimated without confounding by an active
comparator. Rescue medication is allowed for persistent hyperglycemia
so that participants are not left with uncontrolled glucose.

## 4.3 Justification for Dose

The 7 mg and 14 mg doses were selected from the Phase 2 dose-response
study, in which 14 mg gave near-maximal HbA1c reduction and doses above
14 mg increased gastrointestinal events without additional efficacy.

## 4.4 End-of-Study Definition

A participant has completed the study when they complete the Week 56
follow-up visit. The end of the study is the last visit of the last
participant.

<<<PAGE>>>
# 5 STUDY POPULATION

## 5.1 Inclusion Criteria

To be eligible, an individual must meet all of the following criteria:

- 1. Provision of signed and dated informed consent form.

- 2. Male or female, aged 18 to 70 years inclusive at screening.

- 3. Diagnosis of type 2 diabetes mellitus for at least 6 months before
  screening.

- 4. HbA1c >= 7.5% and <= 9.5% at screening (central laboratory).

- 5. Treatment with a stable dose of metformin >= 1500 mg/day for at
  least 12 weeks before screening.

- 6. Body mass index (BMI) >= 25.0 and <= 40.0 kg/m2 at screening.

- 7. Estimated glomerular filtration rate (eGFR) >= 60 mL/min/1.73m2
  (CKD-EPI 2021) at screening.

- 8. Able to read and speak English and to complete study
  questionnaires without assistance.

- 9. Women of childbearing potential must agree to use a highly
  effective method of contraception for the duration of the study and
  for 30 days after the last dose.

- 10. Willing and able to comply with all study procedures, including
  daily SMBG and the electronic diary.

## 5.2 Exclusion Criteria

An individual who meets any of the following criteria will be excluded:

- 1. Type 1 diabetes, latent autoimmune diabetes in adults, or diabetes
  secondary to pancreatitis or pancreatectomy.

- 2. Treatment with any glucose-lowering agent other than metformin
  within 12 weeks before screening, including any prior use of a GLP-1
  receptor agonist or insulin at any time.

- 3. Fasting plasma glucose > 240 mg/dL at screening.

- 4. Myocardial infarction, stroke, unstable angina, or hospitalisation
  for heart failure within 12 months before screening.

- 5. New York Heart Association (NYHA) class II to IV heart failure.

- 6. Alanine aminotransferase (ALT) or aspartate aminotransferase (AST)
  > 2.0 x upper limit of normal (ULN) at screening.

- 7. History of acute or chronic pancreatitis.

- 8. Personal or family history of medullary thyroid carcinoma or
  multiple endocrine neoplasia type 2.

- 9. Proliferative diabetic retinopathy or maculopathy requiring
  treatment.

- 10. History of bariatric surgery or planned weight-loss surgery.

- 11. Systolic blood pressure >= 160 mmHg or diastolic blood pressure
  >= 100 mmHg at screening.

- 12. Any malignancy within 5 years, except treated basal cell
  carcinoma of the skin.

- 13. Pregnant or breastfeeding, or planning to become pregnant during
  the study.

- 14. Participation in another interventional study within 90 days
  before screening.

- 15. Any condition that, in the investigator's opinion, would make the
  participant unsuitable for the study.

## 5.3 Lifestyle Considerations

Participants will continue their usual diet and physical activity and
will receive standardised diabetes self-management counselling at
randomization.

## 5.4 Screen Failures

Screen failures are individuals who consent but are not randomized.
Rescreening is allowed once, at least 4 weeks after the screen failure,
except for participants excluded for HbA1c, who may not be rescreened.

## 5.5 Strategies for Recruitment and Retention

Participants will be recruited from site clinic databases and primary
care referral networks. Retention will be supported by visit reminders,
travel reimbursement and a participant newsletter.

<<<PAGE>>>
# 6 STUDY INTERVENTION

## 6.1 Study Intervention Administration

SYN-4417 is supplied as 7 mg and 14 mg film-coated tablets with matching
placebo tablets identical in appearance. Participants take one tablet
orally once daily in the morning with or without food. Participants in
the 14 mg arm take 7 mg for the first 4 weeks; the escalation is masked
with placebo so that all arms follow the same visible regimen.

## 6.2 Measures to Minimize Bias

Treatment assignment is concealed through the IWRS. Investigators,
participants and the sponsor study team remain blinded until database
lock. Emergency unblinding is available through the IWRS when knowledge
of the treatment is needed for the participant's medical care.

## 6.3 Study Intervention Compliance

Compliance is assessed by tablet counts at each dispensing visit.
Participants taking fewer than 80% of expected doses between two visits
will be counselled.

## 6.4 Concomitant Therapy and Rescue Medication

Metformin must be continued at the screening dose throughout the
study. Rescue medication (any approved agent except GLP-1 receptor
agonists and DPP-4 inhibitors) may be started if fasting plasma glucose
is above 270 mg/dL from Week 0 to Week 12, above 240 mg/dL from Week 12
to Week 26, or HbA1c is above 8.5% after Week 26, confirmed on repeat
testing.

<<<PAGE>>>
# 7 DISCONTINUATION AND WITHDRAWAL

Participants may discontinue study drug for adverse events, pregnancy,
confirmed pancreatitis, or at the investigator's discretion.
Participants who stop study drug are asked to remain in the study and
attend all remaining visits. Participants may withdraw consent at any
time without giving a reason.

# 8 STUDY ASSESSMENTS AND PROCEDURES

## 8.1 Efficacy Assessments

HbA1c, fasting plasma glucose and body weight are measured at the visits
shown in the Schedule of Activities. All laboratory samples are analysed
by a central laboratory. Body weight is measured in light clothing
without shoes on a calibrated scale.

## 8.2 Safety Assessments

Safety assessments include adverse events, vital signs, physical
examination, 12-lead ECG, clinical laboratory tests and hypoglycemic
events recorded in the electronic diary. Participants record SMBG values
at least twice weekly and whenever they have symptoms of hypoglycemia.

## 8.3 Adverse Events and Serious Adverse Events

An adverse event (AE) is any untoward medical occurrence in a
participant, whether or not related to study drug. Serious adverse
events (SAEs) must be reported to the sponsor within 24 hours of the
site becoming aware of them. AEs are collected from randomization until
the Week 56 follow-up visit.

## 8.4 Hypoglycemia

Hypoglycemia is classified according to the American Diabetes
Association: level 1 (glucose < 70 and >= 54 mg/dL), level 2
(glucose < 54 mg/dL), and level 3 (severe event requiring assistance).

## 8.5 Adverse Events of Special Interest

Adverse events of special interest are acute pancreatitis, gallbladder
events, thyroid neoplasms, severe gastrointestinal events and diabetic
retinopathy complications. Suspected pancreatitis events are
adjudicated by an external adjudication committee.

<<<PAGE>>>
# 9 STATISTICAL CONSIDERATIONS

## 9.1 Statistical Hypotheses

The primary null hypothesis is that the mean change from baseline in
HbA1c at Week 26 is equal for SYN-4417 14 mg and placebo. The 7 mg
comparison is tested next in a fixed sequence, followed by the key
secondary endpoints, to control the overall type I error at 0.05.

## 9.2 Sample Size Determination

A total of 600 participants (200 per arm) will be randomized. With 200
participants per arm, the study has 90% power to detect a difference of
0.3% in mean HbA1c change from baseline at Week 26 between SYN-4417
14 mg and placebo, assuming a common standard deviation of 1.1% and a
two-sided significance level of 0.05.

## 9.3 Populations for Analyses

The full analysis set (FAS) includes all randomized participants who
take at least one dose of study drug. The safety set includes all
participants who take at least one dose, analysed by treatment
received.

## 9.4 Statistical Analyses

The primary endpoint is analysed with a mixed model for repeated
measures (MMRM) with treatment, visit, stratification factors and
treatment-by-visit interaction as fixed effects and baseline HbA1c as a
covariate. Data collected after initiation of rescue medication are
included. Missing data are assumed to be missing at random.

Binary endpoints are analysed with logistic regression adjusted for the
stratification factors. Safety data are summarised descriptively.

## 9.5 Interim Analyses

No interim analysis for efficacy is planned.

<<<PAGE>>>
# 10 REGULATORY, ETHICAL AND STUDY OVERSIGHT

## 10.1 Informed Consent Process

The investigator or a delegate explains the study to each potential
participant before any study procedure. The participant is told that
the study involves 12 clinic visits over about 14 months, daily study
tablets, regular blood tests and a home glucose diary. Consent is
documented with the participant's signed and dated consent form, and a
copy is given to the participant.

## 10.2 Confidentiality and Privacy

Participant data are identified by a study number only. Records are
stored securely at the site and in the sponsor's validated electronic
data capture system in accordance with applicable data protection law.

## 10.3 Safety Oversight

Safety oversight will be performed by the sponsor's medical monitor,
who reviews blinded safety data on an ongoing basis. Individual safety
findings may be escalated to the sponsor's internal safety review team.

## 10.4 Clinical Monitoring

Sites are monitored through a combination of on-site and remote visits
following a risk-based monitoring plan.

## 10.5 Quality Assurance and Quality Control

The sponsor or its delegate may audit any site. Sites must allow
direct access to source data and documents for monitoring, audits and
regulatory inspections.

## 10.6 Publication and Data Sharing

The study will be registered in a public trial registry before the
first participant is enrolled, and results will be published regardless
of outcome.

## 10.7 Conflict of Interest

Any investigator with a financial interest in the sponsor must disclose
it before taking part in the study.

<<<PAGE>>>
# 11 REFERENCES

- 1. American Diabetes Association Professional Practice Committee.
  Standards of Care in Diabetes. Diabetes Care, current edition.

- 2. ICH E9(R1) Addendum on Estimands and Sensitivity Analysis in
  Clinical Trials, 2019.

- 3. ICH M11 Clinical electronic Structured Harmonised Protocol (CeSHarP)
  guideline.

- 4. Synthetic Therapeutics. Clinical Study Report SYN-T2D-201
  (fictional), 2025.

# 12 ABBREVIATIONS

- AE: adverse event
- ALT: alanine aminotransferase
- AST: aspartate aminotransferase
- BMI: body mass index
- eGFR: estimated glomerular filtration rate
- FAS: full analysis set
- GLP-1: glucagon-like peptide-1
- HbA1c: glycated haemoglobin
- IWRS: interactive web response system
- MMRM: mixed model for repeated measures
- SAE: serious adverse event
- SMBG: self-monitoring of blood glucose
- T2DM: type 2 diabetes mellitus
- ULN: upper limit of normal
"""

TITLE_PAGE_LINES: list[tuple[str, float, str]] = [
    # (text, font size in points, font style)
    ("GLYDE-2 Study Protocol", 18, "B"),
    ("", 10, ""),
    (
        (
            "A Phase 3, Randomized, Double-Blind, Placebo-Controlled, "
            "Parallel-Group Study to Evaluate the Efficacy and Safety of "
            "Once-Daily Oral SYN-4417 as Add-on to Metformin in Adults with "
            "Type 2 Diabetes Mellitus Inadequately Controlled on Metformin "
            "Monotherapy"
        ),
        12,
        "B",
    ),
    ("", 10, ""),
    (f"Protocol Number: {PROTOCOL_NUMBER}", 11, ""),
    ("National Clinical Trial (NCT) Identified Number: Pending", 11, ""),
    ("EudraCT / EU CT Number: Pending", 11, ""),
    (
        "Investigational Product: SYN-4417 (oral GLP-1 receptor agonist)",
        11,
        "",
    ),
    ("Sponsor: Synthetic Therapeutics Ltd (fictional)", 11, ""),
    ("Coordinating Investigator: Dr. Jane Example, MD PhD", 11, ""),
    (f"Protocol {PROTOCOL_VERSION}", 11, ""),
    (f"Date: {PROTOCOL_DATE}", 11, ""),
    ("", 10, ""),
    (
        (
            "CONFIDENTIAL: This document contains confidential information "
            "belonging to the sponsor. It is a synthetic protocol created to "
            "test protocol-review software; the drug, sponsor, investigators "
            "and data are fictional."
        ),
        9,
        "I",
    ),
]


@dataclass(frozen=True)
class Block:
    """One renderable piece of the body: heading, paragraph, bullet..."""

    kind: str  # "h1", "h2", "paragraph", "bullet", "table" or "page"
    text: str = ""


def parse_body(body: str) -> list[Block]:
    """Split the markup body into blocks, joining wrapped lines."""
    blocks: list[Block] = []
    for chunk in body.strip().split("\n\n"):
        lines = [line.strip() for line in chunk.strip().splitlines()]
        if not lines:
            continue
        if lines[0] == PAGE_BREAK_MARKER:
            blocks.append(Block("page"))
            lines = lines[1:]
            if not lines:
                continue
        if lines[0].startswith(TABLE_MARKER_PREFIX):
            table_name = lines[0].removeprefix(TABLE_MARKER_PREFIX)
            blocks.append(Block("table", table_name.removesuffix(">>>")))
            continue
        if all(line.startswith("- ") for line in lines):
            blocks.extend(Block("bullet", line[2:]) for line in lines)
            continue
        text = " ".join(lines)
        if text.startswith("## "):
            blocks.append(Block("h2", text[3:]))
        elif text.startswith("# "):
            blocks.append(Block("h1", text[2:]))
        elif text.startswith("- "):
            blocks.append(Block("bullet", text[2:]))
        else:
            blocks.append(Block("paragraph", text))
    return blocks


class ProtocolPdf(FPDF):
    """FPDF with the running header and footer of a sponsor protocol."""

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font(FONT_FAMILY, size=HEADER_FONT_SIZE_PT)
        self.cell(
            0,
            4,
            f"SYN-4417 (oral GLP-1 RA)    Clinical Protocol "
            f"{PROTOCOL_NUMBER}    {PROTOCOL_VERSION}",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.cell(
            0,
            4,
            f"CONFIDENTIAL    Status: Approved, Date: {PROTOCOL_DATE}",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font(FONT_FAMILY, style="I", size=HEADER_FONT_SIZE_PT)
        self.cell(0, 4, SYNTHETIC_NOTICE, align="C")
        self.ln(4)
        self.cell(0, 4, f"Page {self.page_no()}", align="C")


def _render_title_page(pdf: ProtocolPdf) -> None:
    pdf.add_page()
    pdf.ln(30)
    for text, size_pt, style in TITLE_PAGE_LINES:
        pdf.set_font(FONT_FAMILY, style=style, size=size_pt)
        pdf.multi_cell(0, size_pt * 0.55, text, align="C")
        pdf.ln(2)


def _render_table(pdf: ProtocolPdf, spec: TableSpec) -> None:
    pdf.set_font(FONT_FAMILY, size=HEADER_FONT_SIZE_PT)
    with pdf.table(
        line_height=TABLE_LINE_HEIGHT_MM,
        col_widths=spec.column_widths_mm,
        borders_layout="ALL" if spec.has_borders else "NONE",
        first_row_as_headings=spec.has_borders,
    ) as table:
        for row_cells in spec.rows:
            row = table.row()
            for cell_text in row_cells:
                row.cell(cell_text)
    pdf.ln(PARAGRAPH_GAP_MM)


def _render_block(pdf: ProtocolPdf, block: Block) -> None:
    match block.kind:
        case "page":
            pdf.add_page()
        case "h1":
            pdf.ln(PARAGRAPH_GAP_MM)
            pdf.set_font(FONT_FAMILY, style="B", size=HEADING_1_FONT_SIZE_PT)
            pdf.multi_cell(0, 7, block.text)
            pdf.ln(PARAGRAPH_GAP_MM)
        case "h2":
            pdf.set_font(FONT_FAMILY, style="B", size=HEADING_2_FONT_SIZE_PT)
            pdf.multi_cell(0, 6, block.text)
            pdf.ln(1)
        case "paragraph":
            pdf.set_font(FONT_FAMILY, size=BODY_FONT_SIZE_PT)
            pdf.multi_cell(0, LINE_HEIGHT_MM, block.text)
            pdf.ln(PARAGRAPH_GAP_MM)
        case "bullet":
            pdf.set_font(FONT_FAMILY, size=BODY_FONT_SIZE_PT)
            pdf.set_x(PAGE_MARGIN_MM + BULLET_INDENT_MM)
            pdf.multi_cell(0, LINE_HEIGHT_MM, block.text)
            pdf.ln(1)
        case "table":
            _render_table(pdf, TABLES[block.text])
        case _:
            raise ValueError(
                "expected block kind h1, h2, paragraph, bullet, table or "
                f"page, got {block.kind!r}"
            )


def build_protocol_pdf() -> bytes:
    """Render the synthetic protocol and return the PDF bytes."""
    pdf = ProtocolPdf()
    pdf.set_margins(PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM)
    pdf.set_auto_page_break(auto=True, margin=PAGE_MARGIN_MM)
    pdf.set_title(f"{PROTOCOL_NUMBER} GLYDE-2 Clinical Study Protocol")
    pdf.set_author("Synthetic Therapeutics Ltd (fictional)")
    pdf.set_creator("scripts/make_sample_protocol.py")
    pdf.set_creation_date(CREATION_DATE)
    _render_title_page(pdf)
    for block in parse_body(PROTOCOL_BODY):
        _render_block(pdf, block)
    return bytes(pdf.output())


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(build_protocol_pdf())
    logger.info("sample protocol written: output_path=%s", output_path)


if __name__ == "__main__":
    main()
