# Sources

External literature and data that code in this repo computes from. A citation that points at a URL
nobody archived is a citation that rots, so every load-bearing source is stored here beside the work
that uses it, with its retrieval URL, date, and checksum.

| Source | Used by | Archived |
|---|---|---|
| WHO Child Growth Standards, LMS tables | `afya.records.growth`, `afya.records.growth_standards` | `who-child-growth-standards/` |
| CKD-EPI 2021, KDIGO CKD classification, ILAE status epilepticus, sickle cell and epilepsy guidance | `afya.chronic.conditions` | `clinical-thresholds/` |
| PHQ-9 and GAD-7 instruments, with the Pfizer instruction manual | `afya.mental.instruments`, `afya.mental.service` — §REC-005's screenings | `phq9-gad7/` |
| Psychological first aid: guide for field workers (WHO, 2011), English and Kiswahili | `afya.mental.support` — §REC-005's coping strategies and outbreak-specific support | `who-pfa/` |

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
| `PHQ-9_Kiswahili.pdf` | The PHQ-9 in Kiswahili ("PHQ9_Swahili for Africa"): all nine items, the four response options and the licence statement translated | `771671cb4f3c5750` |

Text copies: `56b395d530087098`, `b26a82ab638eb3a3`, `6e34c3a1ef25c994`, `fba4e765828a168c`.

**Retrieval URLs** (all under `https://www.phqscreeners.com/images/sites/g/files/`):

| File | URL |
|---|---|
| `instructions.pdf` | `…/g10016261/f/201412/instructions.pdf` |
| `PHQ-9_English.pdf` | `…/g10060481/f/201412/PHQ-9_English.pdf` |
| `GAD-7_English.pdf` | `…/g10060481/f/201412/GAD-7_English.pdf` — **404s live**; retrieved from `https://web.archive.org/web/20250912043959if_/` + that path |

The two live URLs above answered on 2026-10-12. The GAD-7 form did not, and its copy came from the
Wayback Machine's 2025-09-12 capture of the same path — so the checksum pins a *capture*, not the
publisher's current bytes, and a re-retrieval that fails is expected rather than a drift signal.

### What the sources support, and what they do not

- **Item text and scale are complete.** Both instruments extract with all items, the four-point
  frequency scale (`0` Not at all … `3` Nearly every day), and PHQ-9's functional-impairment question.
- **The cut-points are in the manual, not in the item forms.** The item PDFs print the items and the
  total line; the thresholds live in the instruction manual, and they are:

  | Instrument | Cut-points | Where |
  |---|---|---|
  | PHQ-9 | 5 / 10 / 15 / 20 → Mild / Moderate / Moderately Severe / Severe (0–4 None-minimal) | p. 6, Table 4 |
  | GAD-7 | 5 / 10 / 15 → Mild / Moderate / Severe; **≥10 is the recommended cut-point for further evaluation** | pp. 6–7 |
  | PHQ-2, GAD-2 | ≥3 on either (each 0–6) | p. 7 |
  | PHQ-4 | PHQ-2 + GAD-2, 0–12 | p. 7 |

  Table 4 also carries the treatment actions per band, which are the manual's proposals and not
  protocol: `afya.mental` uses the bands for triage only and names no drug.
- **Localisation: PHQ-9 yes, GAD-7 no — and the gap is in the source, not here.** A Kiswahili PHQ-9
  is archived (`PHQ-9_Kiswahili.pdf`). There is **no** Kiswahili GAD-7: the publisher's own language
  listing carries Afrikaans, Arabic, Bulgarian, Cebuano, Chinese, Croatian, Czech, Danish, Dutch,
  English, Filipino, Finnish, French, German, Greek, Gujarati, Hebrew, Hindi, Hungarian, Indonesian,
  Italian, Kannada, Korean, Lithuanian, Malayalam, Marathi, Norwegian, Polish, Portuguese, Punjabi,
  Romanian, Russian, Slovak, Spanish, Swedish, Tamil, Telugu, Thai, Turkish, Ukrainian and Urdu — no
  Swahili. So a Kiswahili self-check can screen depression in the person's own language and anxiety
  only in English or not at all, and that asymmetry is the publisher's, recorded here so that nobody
  later reads it as an omission in this repo. The manual's own caveat (p. 7) is that the translations
  "are linguistically valid" but "unlike the English versions … few … have been psychometrically
  validated against an independent structured psychiatric interview" — so the archived Kiswahili
  PHQ-9 is a *linguistically valid* translation, not a psychometrically validated one, and the word
  "validated" in §REC-005's bullet is discharged only for the English forms.
- **WHO-5 is not the same instrument.** It is five items on a six-point scale, scored `raw × 4` to a
  0–100 index. Substituting it for PHQ-9 is not a narrower version of the same screen; it is a
  different instrument with different cut-points, and `afya.mental` says which one it carries.

---

## WHO Psychological first aid — §REC-005's coping and outbreak support

§REC-005 asks for "coping strategies and psychoeducation" and for outbreak-specific support for
isolation distress, grief and healthcare worker burnout. That content makes claims about what helps
a distressed person, so it is transcribed from a source rather than written here — and the source is
archived in **both** the languages the app serves, so the Kiswahili is a published edition and not a
rendering of the English one.

**Publisher:** World Health Organization, War Trauma Foundation and World Vision International.
**Retrieved:** 2026-10-12.
**Licence:** WHO publications are distributed under CC BY-NC-SA 3.0 IGO; the guide itself carries no
"no permission required" statement, so it is cited and quoted rather than reproduced wholesale.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `who-pfa-en.pdf` | *Psychological first aid: Guide for field workers*, English, 62 pp. | `9e688553fbacc1f7` |
| `who-pfa-sw.pdf` | The same guide in Kiswahili (the publisher's own translation) | `f0f0522ab964819e` |

Text copies: `de8e17474ba32c75`, `109ba96cf1a6a4b8`.

**Retrieval URLs:**
`https://iris.who.int/server/api/core/bitstreams/e7e129fb-b306-496d-84a5-67bb70abc130/content`
(English) and `…/8dcf5921-af76-4995-953c-611d325b143b` (Kiswahili). The bitstream ids are recorded
because the human-readable `iris.who.int/bitstream/handle/…` paths answer `200` with an HTML landing
page rather than the PDF — a `curl -o` against one silently stores a web page under a `.pdf` name.
The record page is `https://www.who.int/publications/i/item/9789241548205`.

### What the source supports, and what it does not

- **The three action principles are the source's structure.** Look, listen, link — rendered in the
  Kiswahili edition as *Tazama, Sikiliza, Unganisha*. `afya.mental.support`'s six coping strategies
  follow them, and the Kiswahili titles are that edition's own wording.
- **What PFA is *not* is load-bearing, and it is what shapes the content.** The guide states PFA "is
  not professional counselling", "is not 'psychological debriefing'", and "is not about pressuring
  people to tell you their feelings". `tests/ci/test_rec005.py` asserts the served coping text does
  not push anyone to recount the event, and its canary plants a sentence that does.
- **Grief is listed as an expected reaction, not an illness.** The guide's distress-reaction list
  includes "crying, sadness, depressed mood, grief". The served grief guidance says so in as many
  words, so the app does not send bereaved people to a clinic for being bereaved.
- **The guide is addressed to a *helper*, not to the affected person.** Its imperatives are
  "wasikize watu na uwasaidie kutulia" — listen to people and help them feel calm. `afya.mental`
  speaks to the person directly, so where it does, the text is *adapted* from the helper's
  instruction rather than quoted, and `support.py` says so at the point of adaptation. It is not
  presented as the guide's own words to a sufferer.
- **No clinical protocol, and none is implied.** The guide is psychological first aid for field
  workers; it is not a treatment manual. Nothing in `afya.mental` prescribes, and the PHQ-9
  instruction manual's per-band treatment actions (Table 4) are deliberately *not* carried into
  served advice — those are a clinician's options, and a drug name in a self-check response is a
  prescription nobody wrote.
- **The Kiswahili edition is the publisher's, and that is the whole of the claim.** It is not a
  psychometrically validated Kiswahili instrument; it is WHO's own translation of WHO's own guidance,
  which is what makes it citable. The instruments' localisation caveat is in the `phq9-gad7/`
  section above and is a separate matter.
