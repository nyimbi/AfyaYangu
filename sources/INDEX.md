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
| WHO Pocket Book of Hospital Care for Children, 2nd ed. (2013) | `afya.medicine.formulary` — §MED-003's dose ranges, formulations and maximum doses | `who-pocket-book/` |
| WHO fact sheets, menopause (2024) and family planning/contraception (2025); NHS UK, fertility in the menstrual cycle | `afya.women.content` — §REC-004's contraception, fertility awareness, menopause support and referral | `who-reproductive-health/` |

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

**Two rows above do not match their committed blobs, and the cause is now fixed.** These two WHO
fact sheets are served with CRLF line endings, and `core.autocrlf=input` stripped the CR at commit
time, so the object store holds LF-rewritten copies — `87f834e958c31cbe` and `b1b231f4ac545ea1`
respectively. The checksums above are the **worktree** bytes, which is what the extraction was taken
from and what a reader re-hashing the file on disk will get. `.gitattributes` now marks `sources/**`
`-text` so no future source is rewritten, but these two are left as they are rather than re-added:
re-committing them would change a hash a reader may already have checked against this table, and the
worktree hash is the one that answers the question the table exists to answer. The six files under
`who-reproductive-health/` were added after the fix and their blobs match.

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

---

## WHO Pocket Book of Hospital Care for Children, second edition

The World Health Organization's clinical manual for the care of children under five at first-level
referral hospitals. §MED-003 is a weight-based dosing calculator "especially paediatric", and a
calculator has no answer without a table of dose-per-kilogram figures to compute from: the current
route asked the *caller* to supply `mg_per_kg`, which is the one constant a person opens the app to
look up. The Pocket Book is where the five formulations the section names are dosed.

**Publisher:** World Health Organization. **Edition:** second, 2013. **ISBN:** 978 92 4 154837 3
(NLM classification: WS 29).
**Retrieved:** 2026-10-12.
**Record page:** `https://iris.who.int/handle/10665/81170`

### Files

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| `who-pocket-book-2nd-ed.pdf` | 3103071 | `e17581cf0829bea6` |
| `who-pocket-book-2nd-ed.txt` | 1331021 | `e670e643f873b462` |

The PDF is the publisher's own file. The `.txt` is `pdftotext -layout` over it; the appendix's
"Drug / Dosage / Form / 3–< 6 kg / 6–< 10 kg / …" columns survive the extraction in order, which is
what makes the table checkable against the code row by row rather than by eye.

**The download path is not the record page.** `iris.who.int/handle/10665/81170` is an Angular
landing page; the file is behind a UUID bitstream URL that the page's own `<link rel="item"
type="application/pdf">` tag carries. Fetching the record page and saving it as `.pdf` stores 674 KB
of HTML — check `file` on anything retrieved this way before computing its checksum.

### What the source supports, and what it does not

- **Dose per kilogram, for five drugs, with the formulation each is dispensed as.** Paracetamol
  10–15 mg/kg up to six times a day, as a 100-mg tablet and a 500-mg tablet (Appendix 2, p. 367).
  Amoxicillin 25 mg/kg twice a day generally, 40 mg/kg twice a day for pneumonia, as a 250-mg
  chewable/dispersible tablet and a 250 mg/5 ml syrup (p. 357). Artemether–lumefantrine 2 mg/kg
  artemether with 12 mg/kg lumefantrine twice a day, as the 20 mg/120 mg combined tablet, with the
  weight bands stated as tablets rather than mg/kg (p. 164). Zinc 10 mg/day under 6 months and
  20 mg/day from 6 months, for 10–14 days (p. 134). ORS 50–100 ml after each loose stool under 2
  years and 100–200 ml from 2 years (p. 136), plus about 5 ml/kg per hour alongside IV rehydration
  (p. 135).
- **The maximum doses the section's last bullet asks for.** Aminophylline loading "5–6 mg/kg
  (max. 300 mg)", chloramphenicol "max, 1 g per dose" (p. 360), cefotaxime "max single dose, 4 g" (p. 359),
  chloramphenicol oily "max, 3 g" (p. 360) — the appendix states a ceiling per drug where one
  exists. Each page reference here was read off the source's own footer marker, not estimated:
  the footer closes the page it prints on, so a text position maps to the *next* marker at or
  after it.
- **What it does *not* give: a numeric ceiling for paracetamol, amoxicillin or zinc.** The Pocket
  Book states paracetamol's frequency ceiling ("up to six times a day") and not a mg/kg-per-day
  total, and gives no maximum for amoxicillin or zinc. The code therefore warns on *frequency and
  weight band*, never on an invented daily milligram ceiling, and `afya.medicine.formulary` records
  `max_mg_per_dose=None` for those rather than filling the gap. A number invented to fill a table
  is worse than a table with a gap.
- **The source's weight bands are for dispensing a tablet, not for computing a milligram dose.**
  Where the Pocket Book gives "child weighing 5 – < 15 kg: one tablet twice a day", that is a
  tablet count for a fixed-strength combined tablet and it is what the code returns for
  artemether–lumefantrine; it is not a mg/kg figure, and the code does not pretend to derive one.
- **Age is used for a threshold, not for a dose.** The zinc and ORS rules turn on 6 months and 2
  years. Nothing in the source doses by age alone, so the calculator takes age only to select those
  bands and refuses to guess when it is absent.
- **It is a hospital-care manual for children under five.** Adult dosing is out of its scope
  entirely; the calculator is therefore bounded to a paediatric weight range and says so rather
  than extrapolating an adult dose from a child's table.

---

## WHO reproductive health — §REC-004's contraception, fertility awareness and menopause

§REC-004's six Features are period logging, cycle prediction, contraception reminders, fertility
awareness, menopause support and referral to services. The first two were implemented; the other
four are statements about reproductive physiology, and a threshold in them has to come from
somewhere. These two WHO fact sheets are where the numbers come from.

**Publisher:** World Health Organization.
**Fact sheets:** "Menopause", 16 October 2024; "Family planning/contraception methods", 3 July 2025.
**Retrieved:** 2026-10-13.

The fertile-window arithmetic needs a source of its own: neither WHO fact sheet states when ovulation
happens. NHS UK's "Fertility in the menstrual cycle" page does, and it is archived here for that one
purpose. It is a national health service's patient-facing page, which is the right standing for a
figure the app shows a person about their own body — but it is a *different publisher* from the two
WHO fact sheets, and the two must not be conflated: WHO supplies the contraception and menopause
claims, NHS supplies the ovulation timing.

**Publisher (fertile window):** NHS UK.
**Retrieved:** 2026-10-13.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `who-menopause-factsheet.html` | WHO fact sheet, menopause — perimenopause, the 12-month rule, symptoms | `5e7e0121f34f4a2c` |
| `who-menopause-factsheet.txt` | the same, layout-preserving text | `533511f14fff04ac` |
| `who-family-planning-factsheet.html` | WHO fact sheet, family planning/contraception methods | `6fd0098338805078` |
| `who-family-planning-factsheet.txt` | the same, layout-preserving text | `9f5caeccd83b0486` |
| `nhs-fertility-menstrual-cycle.html` | NHS UK, fertility in the menstrual cycle — ovulation timing | `2cb57edbcca4099c` |
| `nhs-fertility-menstrual-cycle.txt` | the same, layout-preserving text | `1dd1a35d05d6a0d3` |

Retrieval URLs: `https://www.who.int/news-room/fact-sheets/detail/menopause`,
`https://www.who.int/news-room/fact-sheets/detail/family-planning-contraception` and
`https://www.nhs.uk/conditions/periods/fertility-in-the-menstrual-cycle/`.

### What the sources support, and what they do not

- **The 12-month rule, which is the load-bearing figure.** The menopause fact sheet states:
  "Pregnancy is still possible during perimenopause. Contraception is recommended to avoid
  unintended pregnancy until after 12 consecutive months without menstruation." That is the one
  number that ties §REC-004's contraception reminder to its menopause support — a person is
  *perimenopausal*, and still needs contraception, until twelve consecutive months have passed with
  no period. The code computes those months from the person's own logged cycles and reports the
  count; it does not decide on its own that someone has reached menopause.
- **The age range, as a population fact and not a rule about a person.** "Most women experience
  menopause between the ages of 45 and 55 years." The fact sheet says *most*, and the code repeats
  that framing — an age outside the range is not treated as an error, and the tracker never tells
  someone they are or are not menopausal on the strength of their age.
- **Perimenopause is defined, and its end is defined relative to the last period.** "Perimenopause
  refers to the period from when these signs are first observed and ends one year after the final
  menstrual period." The tracker's own state therefore turns on the last logged period, not on a
  date a user types.
- **The symptoms the section's "menopause support" can name, verbatim.** Hot flushes and night
  sweats, changes in the regularity and flow of the cycle culminating in cessation, vaginal dryness
  and pain during intercourse, incontinence, difficulty sleeping, and changes in mood, depression
  and anxiety. The fact sheet also notes loss of bone density as a contributor to osteoporosis and
  fractures, and that the cardiovascular advantage women have over men "gradually disappears" after
  menopause.
- **Contraceptive methods, as WHO groups them, with the effectiveness distinction the fact sheet
  itself draws.** "Some, like implants, intrauterine devices (IUDs), and sterilization, are highly
  effective and long-lasting. Others, such as pills, injections, patches, and vaginal rings, are
  used regularly and work well when taken correctly. Barrier methods like condoms are effective at
  preventing pregnancy, if used correctly." And the one method that does more: "Only one
  contraceptive method, condoms, can prevent both pregnancy and the transmission of sexually
  transmitted infections, including HIV."
- **Fertility-awareness methods are grouped as *less reliable*, and the code must say so.** The
  fact sheet lists "fertility awareness-based methods or withdrawal" among the options and states
  they "are less reliable". This is the sentence the tracker's own fertile-window output has to
  carry: a calendar estimate is not a contraceptive method of the same standing as an implant, and
  presenting the window as a green light would be the tracker causing the pregnancy it exists to
  help avoid.
- **The fertile window is derived from two NHS figures, and both are stated with their spread.** NHS
  UK gives the luteal phase as "around 10 to 16 days" before the next period and sperm survival as
  "up to 7 days after sex". The window is therefore *ovulation minus sperm survival* to *ovulation
  plus the egg's own viability* — and NHS gives no egg-viability figure, so the code takes the
  conservative end: the window is reported as the 7 days before the estimated ovulation day, and
  `EGG_VIABILITY_DAYS` is 1 with the gap recorded rather than a 24-hour figure invented to fill it.
  The ovulation day is `median cycle length - 14`, and NHS states the caveat the code must repeat:
  "Women who have a regular, 28-day cycle are likely to be fertile around day 14 of their menstrual
  cycle, but this won't apply to women whose cycles are shorter or longer."
- **What the NHS source does *not* give: a probability, or a window the app may call safe.** It
  says a regular 28-day cycle makes day 14 likely, and that it is "difficult to pinpoint exactly
  when ovulation happens". Nothing here supports a green day or a red day, so the tracker reports a
  window and never a verdict.
- **What the sources do *not* give: any efficacy percentage, any method-specific failure rate, and
  any clinical threshold for when a symptom needs review.** The fact sheet groups methods into
  "highly effective", "work well when taken correctly" and "less reliable" and states no number for
  any of them. The code repeats WHO's own three groups and invents no percentage, and the
  menopause-support output says a symptom affecting health and well-being "should be discussed with
  a health-care provider" — the fact sheet's own sentence — rather than naming a threshold it does
  not state.
- **What it does *not* give: a definition of infertility the tracker may apply to a person.** The
  fact sheet defines it as "the inability to conceive after 12 months of regular unprotected sex",
  which is a definition and not a diagnosis, and it states that "modern contraceptive methods do not
  cause infertility" — the misconception the tracker's contraception output corrects. The code
  repeats both and diagnoses neither.

---

## Ebola transmission, exposure and the 21-day window

§11.2 TRI-003 names four exposure routes (funeral attendance, healthcare work, contact with a case,
consumption of bushmeat) and an isolation status; §8.1's triage rests on the incubation period and on
contact with a case. Those are clinical facts with a source, and the two publications below are where
they come from. They are archived because a claim about transmission that cites a URL nobody kept is
a claim resting on something unreadable.

**Retrieved:** 2026-10-13.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `who-ebola-factsheet.html` | WHO fact sheet, Ebola disease, 24 April 2025 | `d23ffbf0f470ec65` |
| `cdc-ebola-about.html` | CDC, About Ebola Disease | `fedfc577a53bceeb` |

URLs: `https://www.who.int/news-room/fact-sheets/detail/ebola-disease`,
`https://www.cdc.gov/ebola/about/index.html`.

**What the WHO fact sheet supports, quoted:**

- **Incubation period.** "The incubation period or interval from infection to onset of symptoms
  varies from 2 to 21 days." This is the 21-day window §MON-009 and §COM-102 both rest on, and it is
  a *range with a lower bound* — the source says 2 to 21, so a follow-up scheduled on day 3 is inside
  the window and one scheduled on day 1 would be before symptoms could appear.
- **Transmission by direct contact.** "People can get infected with the virus from a [person] …
  through close contact with patients when infection control precautions are not strictly practiced.
  Burial ceremonies that involve direct contact with the body of a person who has died can also
  contribute to the transmission of Ebola disease." This is the source for treating funeral
  attendance and healthcare work without precautions as exposures.
- **Animal-source exposure.** "The virus can get into the human population when people have close
  contact with the blood, secretions, organs or other bodily fluids of infected animals such as fruit
  bats, chimpanzees, gorillas, monkeys, forest antelope or porcupines found ill or dead or in the
  rainforest." This is the bushmeat route. The source's own wording is **contact with an infected
  animal or its fluids** — it does not say that eating cooked bushmeat transmits Ebola, and the code
  below does not claim it does.
- **Bleeding is not the common presentation.** "Despite a perception that bleeding is a common
  symptom, this is less [common] …" — the fact sheet's own correction, which is why `bleeding` is
  one red flag among eight and not the definition of the disease.

**What the WHO fact sheet does NOT support:** any *household* isolation procedure. It states that
outbreak control includes "infection prevention and control" and "safe and dignified burials" but
gives no home-care instructions. The household guidance in `afya.triage.views` therefore does not
claim to be WHO's — it is written from the transmission mechanism the source states (direct contact
with blood or body fluids) plus the CDC page's "avoid contact with" list below, and it says so.

**What the CDC page supports, quoted:** the avoid-contact list — "Clothes, bedding, needles, medical
equipment, or other items that may have touched an infected person's blood or body fluids; The body
of someone who is suspected or confirmed to have had Ebola disease (for instance, as part of a
funeral or burial practices); Bats, forest antelopes, primates, and blood, fluids, or raw meat from
these or unknown animals" — and "Wear personal protective equipment if you come in contact with
people who are sick or have died from Ebola disease". The code's "one caregiver, no visitors, own
latrine" is the standard Ebola treatment-unit arrangement, not a sentence either source prints; it is
carried as guidance with that provenance recorded here rather than attributed to a page that does not
say it.

---

## Helpline directory — §INF-006's GBV and child helplines

§INF-006's Contents name a "mental health helpline", a "GBV helpline" and a "child helpline". The
tree held numbers for the first and for none of the other two, so two of the eight rows the section
prints had no carrier at all. The three sources below are the operators' and UN Women's own pages for
the numbers now in `afya.info.service.HOTLINES`.

They are archived because a helpline number is a life-safety fact: a number that cites a URL nobody
kept is a number that cannot be re-checked, and the failure mode is a person in crisis dialling a
dead line.

**Retrieved:** 2026-10-13.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `unwomen-1195-gbv-hotline.html` | UN Women Africa, "Kenya's national toll-free helpline 1195: A lifeline for gender-based violence survivors" | `c4bd318f5c6da073` |
| `childline-kenya-116.html` | Childline Kenya's own site, home and "Our Story" | `20c5d65e9bae5a27` |
| `gvrc-0800720565.html` | Gender Violence Recovery Centre (GVRC) own site | `bb859c587ce9feeea` |

URLs: `https://africa.unwomen.org/en/stories/feature-story/2023/12/kenyas-national-toll-free-helpline-1195-a-lifeline-for-gender-based-violence-survivors`,
`https://childlinekenya.co.ke/`, `https://gvrc.or.ke/`.

**What the UN Women page supports, quoted:**

- **That 1195 is national, toll-free and for GBV.** "Kenya's national toll-free helpline 1195" and
  "The National Gender-Based Violence Toll-Free Helpline, 1195, serves as a crucial resource for
  survivors". This is the whole basis for the row existing.
- **24/7 staffing.** "Trained counselors are available 24/7 to offer survivors emotional support".
- **An SMS route.** "The helpline's SMS-based system allows survivors to discreetly report incidents
  and receive medical advice, including guidance on preventing sexually transmitted infections (STIs)
  and HIV." This matters for the directory's second Feature: "one-tap SMS" is only a real capability
  on a line that reads texts, and this is the source that says 1195 does.
- **Multilingual.** "the helpline is multilingual, offering services in several local languages,
  including Swahili, Kikuyu, Luhya, and Kalenjin".
- **Who operates it.** "HAK, a local NGO and a UN Women partner, operates the helpline in partnership
  with the Kenyan government." The row does not name the operator; the source is recorded here so a
  reader can find it.

**What the UN Women page does NOT support:** any statement by the Ministry of Health or PHEOC that
1195 is the line the health system routes GBV cases to. It is UN Women reporting a UN Women partner's
work. That is why the row is `verified=False` — §18.4's verification is a confirmation by the
deploying authority, and no source here is that authority speaking.

**What Childline Kenya's own site supports, quoted:**

- **116 is the National Child Helpline, and the Government owns the number.** "In a public private
  partnership arrangement, Childline Kenya and the Government of Kenya, through the Department of
  Children Services, manage the Child Helpline 116" and "The number 116 belongs to the Government and
  Childline manages it on behalf of the Government as a technical partner."
- **24-hour, toll-free, free from any mobile.** "Our core service is the National Child Helpline 116,
  Kenya's only 24-hour, toll-free telephone and web-based helpline for children"; on the earlier
  0800 221 0800 line, "which was easier to remember, and was also available on mobile devices for
  free from anywhere in Kenya".
- **It is a reporting platform as well as a counselling line.** "The National Helpline 116 is a
  confidential reporting platform that is accessible to children and adults who have identified or
  witnessed violence".

**What Childline Kenya's own site does NOT support:** that 116 reaches a health facility. It routes
to child protection services. The directory lists it under the section's "child helpline" Content
without claiming it is a clinical line.

**What GVRC's own site supports, quoted:**

- **0800720565 is 24/7 and toll-free.** "If you or someone you know is in immediate danger or in need
  of urgent assistance, please call our 24/7 toll-free helpline: 0800720565".
- **Free comprehensive medical, legal and psychosocial support.** "GVRC offers free, comprehensive
  medical, legal, and psychosocial support" and "comprehensive free medical treatment and psychosocial
  support to survivors who have suffered any form of violence such as sexual, physical, psychologi[cal]".
  This is the one of the three that is a *clinical* service, which is why it is carried as a second
  `gbv_helpline` row beside the national line rather than folded into it.
- **It runs one-stop centres inside hospitals.** "This Gender Based Violence Recovery Centre (GBVRC)
  model has been adopted in various county and sub-county hospitals including: Centre for Assault and
  Recovery in Eldoret (CARE) situated in Moi Teaching and Referral Centre" and a list naming Kenyatta
  National Hospital, Makueni County Hospital, Homabay County Referral Hospital and others. That list
  is the reason the row is a helpline rather than a facility: GVRC is the number that reaches the
  network, and which centre a caller is nearest is a question for `nearest_facility`, not this row.

**What GVRC's own site does NOT support:** that the line is answered by clinicians, or that it
dispatches an ambulance. The site states the *service* is medical; it does not state the *line* is a
clinical triage line.

**None of the three has been confirmed against MoH/PHEOC**, which is the confirmation §18.4 asks for
and the reason every row added from these sources is `verified=False`. A row that arrived looking
checked would be worse than a row with a gap: the `updated_line` the directory serves is None for
these, which a client renders as "never verified" rather than inferring freshness from silence.

---

## County adjacency — §INF-001's "and neighbouring counties"

§INF-001's Description asks for a dashboard of "health risks in the user's county **and neighbouring
counties**", and nothing in the repo recorded that Busia is next to Bungoma. The table in
`afya.info.counties` is derived from the boundary file below rather than typed from memory, and
`tests/ci/test_county_adjacency.py` re-derives it from the archived copy on every run.

It is archived because the derivation is the whole claim. A hand-typed list of 113 pairs is a claim
about geography with no source, and the failure mode is a dashboard that omits a county the reader's
own outbreak will cross into — a screen that looks complete and is not.

**Publisher:** geoBoundaries (William & Mary geoLab), `gbOpen` release, Kenya ADM1 ("Counties").
Boundary source: RCMRD GeoPortal / Africa GeoPortal. **Licence:** Public Domain.
**Boundary year represented:** 2020. **Retrieved:** 2026-10-13.
**API metadata:** `https://www.geoboundaries.org/api/current/gbOpen/KEN/ADM1/`
**GeoJSON:** `https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/KEN/ADM1/geoBoundaries-KEN-ADM1_simplified.geojson`

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `geoBoundaries-KEN-ADM1_simplified.geojson` | The 47 county polygons, simplified release (861,584 bytes, `admUnitCount` 47) | `4d9e1b8a6d305ee2` |
| `geoBoundaries-KEN-ADM1.api-metadata.json` | The API's own record of that release: source, licence, year, unit count, vertex statistics | `fd14563ea85bd690` |
| `county-adjacency.txt` | The derivation — one line per county, its neighbours, plus the pair count | `1550965c862a703b` |

**The derivation rule**, stated here so the table, the text copy and the test cannot drift:

> Two counties are adjacent when their polygons share a boundary **segment** at least **1 km** long,
> with coordinates rounded to **3 decimal places** (about 110 m at Kenya's latitudes).

Both constants are load-bearing. The **1 km threshold** is what makes the answer a *border* rather
than a meeting point: four counties meet at one vertex in western Kenya, and a shared vertex is not a
shared border — a rule based on shared vertices gives 112 pairs including pairs that touch at a point.
The **3-decimal rounding** is what makes a shared segment *findable*: the two sides of a border are
stored as separate rings, so without rounding their vertices differ in the last decimals and no edge
ever compares equal, and the rule would return zero pairs while looking correct.

**What the source supports:** that these 47 polygons, and the simplified release's own metadata
(`admUnitCount: 47`), are the boundary set the table was derived from; and, given the rule above, that
the derivation is reproducible — the test recomputes it and compares all 113 pairs.

**What it does not support, and where the code says so:**

- **It is not a legal boundary.** It is a simplified cartographic release. Where a county boundary is
  disputed on the ground, this table is not evidence about it, and no code here treats it as such —
  the table answers one question, "which counties does a reader's outbreak cross into".
- **It does not support the spelling of any county name.** The names are the file's `shapeName`
  values, including `Murang'a` with its apostrophe and `Tharaka` (the county is Tharaka-Nithi). They
  are the keys `afya.info.counties` matches on, so a caller using a different spelling gets an empty
  neighbour list rather than an error — which the module's `neighbours` docstring states.
- **It says nothing about distance, travel time or road access.** Two counties that share a 1 km
  border may be a day apart by road; the table is adjacency, not proximity.
- **It is not a sub-county or ward boundary set.** §INF-001's third Display needs sub-counties and
  `SubCountyStatus` takes them as caller-supplied strings. ADM2 would be the source for those and is
  not archived here, because nothing in the code derives from it yet — the sub-county row records
  what a county health team reports, not a boundary join.
