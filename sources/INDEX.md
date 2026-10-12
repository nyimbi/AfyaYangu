# Sources

External literature and data that code in this repo computes from. A citation that points at a URL
nobody archived is a citation that rots, so every load-bearing source is stored here beside the work
that uses it, with its retrieval URL, date, and checksum.

| Source | Used by | Archived |
|---|---|---|
| WHO Child Growth Standards, LMS tables | `afya.records.growth`, `afya.records.growth_standards` | `who-child-growth-standards/` |
| CKD-EPI 2021, KDIGO CKD classification, ILAE status epilepticus, sickle cell and epilepsy guidance | `afya.chronic.conditions` | `clinical-thresholds/` |
| PHQ-9 and GAD-7 instruments, with the Pfizer instruction manual | §REC-005's screenings — the readings the section names and `afya.mental` does not yet carry | `phq9-gad7/` |

Every source is stored as the published artefact **and** as layout-preserving text (`pdftotext
-layout`), with both checksums recorded. The text copy is what a tool reads: an agent given a PDF
receives it as a base64 `document` block, which some model gateways reject outright, and which costs
far more context than the text it carries. The PDF stays because it is the artefact the citation
points at.

---

## WHO Child Growth Standards

The World Health Organization's Child Growth Standards are the reference population against which
child growth is measured worldwide. Kenya's own growth-monitoring practice and the Kenya EPI
schedule both reference them, so §REC-003's "percentile charts" and "undernutrition alerts" have no
implementation without them.

**Publisher:** World Health Organization, Department of Nutrition for Health and Development.
**Standards published:** 2006 (length/height-for-age, weight-for-age, weight-for-length, BMI-for-age);
the 0–5 year z-score tables used here are the current published revision.
**Retrieved:** 2026-10-12.

### Files

Each file is the WHO z-score table as published, a 3-page PDF whose first page carries the header and
the LMS columns. The `.txt` beside each is the same table extracted with `pdftotext -layout`, which
reproduces the `Year: Month / Month / L / M / S` columns in order; `growth_standards.py`'s 246 rows
were checked against it and agree exactly.

| File | Indicator | Sex | Ages | SHA-256 (first 16) |
|---|---|---|---|---|
| `wfa_boys.pdf` | Weight-for-age | Boys | 0–60 months | `ca6437e29134dee2` |
| `wfa_girls.pdf` | Weight-for-age | Girls | 0–60 months | `2ecadc34b59b3309` |
| `lhfa_boys_0_2.pdf` | Length-for-age | Boys | 0–24 months | `a3cee0ae2f50a7bc` |
| `lhfa_girls_0_2.pdf` | Length-for-age | Girls | 0–24 months | `a5895dcfacfc6de9` |
| `hfa_boys_2_5.pdf` | Height-for-age | Boys | 24–60 months | `a8b1093776be24ea` |
| `hfa_girls_2_5.pdf` | Height-for-age | Girls | 24–60 months | `c6ff83bc671ac6f0` |

The text copies, in the same order: `c5aeb7719aae4cc9`, `25e9bf5bde08df59`, `49ee5a7d7a85fa11`,
`afa057f52fcf39ce`, `34736c0885e3c139`, `4e634fb0cb3be7b9`.

### Retrieval URLs

```
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/weight-for-age/wfa-boys-0-5-zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/weight-for-age/wfa-girls-0-5-zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/lfa_boys_0_2_zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/lfa_girls_0_2_zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/hfa_boys_2_5_zscoresba2ba0820f064f4abf5915abac01e894.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/hfa_girls_2_5_zscores.pdf
```

The landing pages, which carry the full table listing and the `sfvrsn` query parameters, are
`https://www.who.int/tools/child-growth-standards/standards/weight-for-age` and
`.../standards/length-height-for-age`.

### The method

WHO tabulates three parameters per month of age and sex — the Box-Cox power `L`, the median `M`, and
the coefficient of variation `S` — fitted to the standards sample. The z-score of a measurement `x` is

```
z = ((x / M) ** L - 1) / (L * S)        for L != 0
z = ln(x / M) / S                       for L == 0
```

`L` is 1 for the length/height tables, where the distribution is normal and the formula reduces to
`z = (x - M) / (M * S)`. It is not 1 for weight-for-age, which is right-skewed, and an
implementation that assumes normality there understates deficit at the low end — the direction that
matters for an undernutrition alert.

`afya.records.growth_standards` holds all 246 rows verbatim: 61 months × 2 sexes for weight, 25 × 2
for length, 37 × 2 for height. `afya.records.growth` computes with them.

### Why the tables are reproduced in source rather than read at runtime

- No xlsx reader is among this deployment's dependencies, and adding one to parse a file that changes
  at most once a decade is a dependency bought for a constant.
- A clinical calculation should not depend on network egress. A growth verdict that fails when the
  CDN is unreachable is a growth verdict that fails during an outbreak.
- A standard that can change under a running service is not a standard. Pinning the parameters in
  source makes a revision a code change with a diff, a review, and a test — which is what a change to
  a clinical threshold deserves.

### Rejected options

- **Reading the PDFs at runtime.** They are the published artefact, but parsing a PDF to obtain a
  number that never changes trades a reviewable constant for an unreviewable parse.
- **Using the z-score tables' printed `-3 SD` / `-2 SD` / `Median` columns directly.** They are
  rounded to one decimal, which is a 0.1 kg error on a 3.3 kg infant — 3% of body weight, and enough
  to move a child across a classification boundary. The LMS parameters give the exact value.
- **The `weight-for-length` and `BMI-for-age` standards.** §REC-003 names weight, height, head
  circumference and MUAC against "WHO standards" without specifying which indicator, and wasting is
  the indicator for weight-for-length. It is not implemented here; the gap is recorded rather than
  papered over with a normal-approximation substitute.

---

## Clinical thresholds for the chronic disease log

§MON-003 lists seven conditions and asks for "danger thresholds with escalation". Three of the seven
had no reading behind them (epilepsy, sickle cell disease, chronic kidney disease), and a threshold
is a number that has to come from somewhere. These are the publications the numbers come from.

**Retrieved:** 2026-10-12. The two Wikipedia articles are archived as the accessible copy of the
KDIGO and ILAE tables; the primary documents (the KDIGO 2012 CKD guideline PDF and the ILAE 2015
position paper) are behind publisher paywalls or bot walls, and `kidney.org` and `ilae.org` both
answered 403 to an automated fetch. Where a number below is load-bearing it is stated in the article
with its own citation to the primary source, and the primary citation is recorded beside it here.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `ckdepi-2021-nkf.html` | NKF's CKD-EPI 2021 creatinine equation page | `0739732ac860b2ba` |
| `kdigo-ckd-classification.html` | KDIGO 2012 CKD definition, GFR and albuminuria categories | `f4b7f029aa7ae724` |
| `ilae-status-epilepticus.html` | Status epilepticus, ILAE 2015 time points | `24d726e330fdbe24` |
| `sickle-cell-disease.html` | Sickle cell disease: crises, prophylaxis, danger signs | `1691a8fb4ad181d1` |
| `epilepsy-management.html` | Epilepsy: antiseizure medicines, status epilepticus protocol | `9bda42218c266320` |
| `who-sickle-cell-factsheet.html` | WHO fact sheet, sickle cell disease | `3a5d06b544369c16` |
| `who-epilepsy-factsheet.html` | WHO fact sheet, epilepsy (the treatment gap) | `abbe6bdab575a5e9` |

Retrieval URLs are the filenames' subjects: `https://www.kidney.org/professionals/kdoqi/gfr_calculator/formula`,
`https://en.wikipedia.org/wiki/Chronic_kidney_disease`, `https://en.wikipedia.org/wiki/Status_epilepticus`,
`https://en.wikipedia.org/wiki/Sickle_cell_disease`, `https://en.wikipedia.org/wiki/Epilepsy`,
`https://www.who.int/news-room/fact-sheets/detail/sickle-cell-disease`,
`https://www.who.int/news-room/fact-sheets/detail/epilepsy`.

### Chronic kidney disease: CKD-EPI 2021 and the KDIGO categories

eGFR in mL/min/1.73 m², serum creatinine `Scr` in mg/dL standardised to IDMS, age in years:

```
eGFR = 142 × min(Scr/κ, 1)^α × max(Scr/κ, 1)^-1.200 × 0.9938^age × 1.012 (if female)

κ = 0.7 (female), 0.9 (male)      α = -0.241 (female), -0.302 (male)
```

The archived NKF page states this equation and the κ/α table in text (the calculator itself is
JavaScript, so a search for the constants has to look past the markup — they are on the page, in the
`Expressed as a single equation` block). A secondary copy of the equation, Wikipedia's CKD-EPI
article, prints the SCr-above-κ exponent as **−1.209** and the female multiplier as **143**; the
primary source says **−1.200** and **142**, so the primary is what the implementation follows. The
two differ by under 1% of eGFR, which is below the assay's own variability and would never be seen —
but a constant copied from the wrong source is a constant nobody can check, so the disagreement is
recorded rather than averaged.

The 2021 revision removed the race coefficient that the 2009 equation carried. KDIGO stages on eGFR
(G1 ≥90, G2 60-89, G3a 45-59, G3b 30-44, G4 15-29, G5 <15) and on albuminuria (A1 <30, A2 30-300,
A3 >300 mg/g), and defines CKD as an abnormality "present for at least three months" — which is why
the implementation takes two readings with a date and refuses to call a single low eGFR kidney
disease. A single creatinine is an acute finding; CKD is the sustained one.

**Rejected:** the MDRD equation (less accurate above 60, superseded), the 2009 CKD-EPI with its race
coefficient (removed in 2021, and a race term in a Kenyan deployment is a coefficient fitted on a
different population), and the Cockcroft-Gault formula (estimates creatinine clearance, not GFR, and
is weight-dependent — a weight a wallet may not hold).

### Status epilepticus: the ILAE 2015 time points

ILAE's operational definition is two time points. `t1` is when a seizure has lasted long enough to be
treated as continuous and treatment should begin: **5 minutes** for generalised tonic-clonic seizures.
`t2` is when long-term harm becomes likely and the seizure is definitively status: **30 minutes** for
generalised tonic-clonic seizures. Both are for convulsive status; the definition states that for
other seizure types the time points differ, and the archived article does not give them, so the
implementation applies the convulsive pair and says so rather than inventing a focal pair.

### Sickle cell disease and epilepsy: what the sources do and do not support

Both WHO fact sheets are thin on thresholds, and the archived copies are kept to record that: WHO
names pneumococcal/Hib/hepatitis B vaccination and folic acid for sickle cell disease but no
penicillin dose and no fever threshold, and names no antiseizure drug at all for epilepsy. The
implementation therefore carries what the sources support — the danger signs (acute chest syndrome:
wheezing, chest pain, fever, hypoxaemia; splenic sequestration: left-sided pain, a swollen spleen, a
sudden haemoglobin drop; stroke) and the drug names (carbamazepine or lamotrigine first-line for
focal, valproate for generalised, benzodiazepine then levetiracetam for convulsive status) — and
states no dose it cannot source. A dose invented to fill a table is worse than a table with a gap.

---

## PHQ-9 and GAD-7 — the instruments §REC-005 names

§REC-005 asks for "PHQ-9 and GAD-7 screenings (validated, localised)". Neither exists in the code:
`afya.mental` implements **WHO-5** only, and `content_audit` records the gap as a `missing` row
against REC-005. These three files are the instruments themselves, archived so that the feature — when
someone builds it — has the item text, the response scale and the scoring rule from the source rather
than from a summary of it.

This is a gap with its source present, not a feature. Nothing in `src/` reads these files.

**Publisher:** Pfizer Inc. (the PHQ family was developed with an educational grant from Pfizer).
**Retrieved:** 2026-10-12.
**Licence:** the instrument states *"No permission required to reproduce, translate, display or
distribute"*, which is what makes the localisation §REC-005 asks for a licensing non-issue.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `PHQ-9_English.pdf` | The PHQ-9: nine items, each scored 0–3, plus the tenth unnumbered functional-impairment question | `e3fb5b8853e3530c` |
| `GAD-7_English.pdf` | The GAD-7: seven items, each scored 0–3, with the office-coding total line | `180538a8e3f2f3cb` |
| `instructions.pdf` | The Pfizer instruction manual (9 pages): background, coding and scoring, versions, use as severity and outcome measures, translations | `6ed2f00f97e438c1` |

Text copies: `56b395d530087098`, `b26a82ab638eb3a3`, `6e34c3a1ef25c994`.

**Retrieval URLs:** `https://www.phqscreeners.com/` (the PHQ and GAD-7 screeners site). The specific
document paths are not recorded here because the site serves them behind a session; the retrieved
artefacts are the authority, and the checksums above pin them.

### What the sources support, and what they do not

- **Item text and scale are complete.** Both instruments extract with all items, the four-point
  frequency scale (`0` Not at all … `3` Nearly every day), and PHQ-9's functional-impairment question.
- **Severity bands are not in these files.** The item PDFs print the items and the total line; the
  cut-points (PHQ-9 5/10/15/20, GAD-7 5/10/15) live in the instruction manual's *Coding and Scoring*
  section, which is archived here — but the bands are **not** transcribed into `sources/INDEX.md` and
  are not implemented, because a threshold copied out of a 9-page manual into a docstring is a
  threshold nobody re-checks. Whoever implements §REC-005 should read them from
  `instructions.txt` and cite the page.
- **Localisation is a licence non-issue but not a translation.** The instruments may be translated
  freely; no validated Kiswahili PHQ-9/GAD-7 is archived here, and §REC-005's "localised" is
  therefore unmet in both senses — the instrument and its language.
- **WHO-5 is not the same instrument.** It is five items on a six-point scale, scored `raw × 4` to a
  0–100 index. Substituting it for PHQ-9 is not a narrower version of the same screen; it is a
  different instrument with different cut-points, and `afya.mental` says which one it carries.
