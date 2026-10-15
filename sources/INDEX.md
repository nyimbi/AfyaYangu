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
| WHO Model Formulary 2008, Appendices 1–3 and the monographs' contraindication lines | `afya.medicine.interactions`, `afya.medicine.contraindications` — §MED-002's interaction table, and the pregnancy, breastfeeding, age and condition axes | `who-model-formulary/` |
| WHO fact sheets, menopause (2024) and family planning/contraception (2025); NHS UK, fertility in the menstrual cycle | `afya.women.content` — §REC-004's contraception, fertility awareness, menopause support and referral | `who-reproductive-health/` |
| Radford et al., *Robust Speech Recognition via Large-Scale Weak Supervision* (arXiv:2212.04356); OpenAI `mel_filters.npz` (MIT) | `afya.ml.speech` — §ACC-002's log-Mel front end and the whisper-tiny recogniser | `whisper-asr/` |
| OpenStreetMap wiki, `Key:healthcare` — the `blood_donation` and `blood_bank` values | `afya.places.views.PlaceKind`, `afya.integrations.overpass` — §REC-006's donation centres | `osm-healthcare-tags/` |
| WHO, *Larval source management: a supplementary measure for malaria vector control — an operational manual* (2013) | `afya.monitoring.views.LARVICIDE_CLASSES`, `afya.monitoring.service.MonitoringService.publish_larviciding` — §MON-007's larviciding notices and protection reminders | `who-larval-source-management/` |
| FAO Crop Calendar for Kenya (GIEWS, `lastUpdated` 26/02/2021) | `afya.monitoring.views.SEASONAL_FOODS` — §MON-008's seasonal food availability | `fao-crop-calendar-kenya/` |
| FEWS NET Kenya seasonal calendar, 2024 | `afya.monitoring.views.SEASONAL_FOODS` — the cross-check on the FAO harvest windows | `fews-net-kenya-seasonal-calendar/` |
| Kenya National Guideline for Integrated Management of Acute Malnutrition (IMAM), 2020 | `afya.monitoring.views.IMAM_PROGRAMMES`, `afya.facilities.views.FacilityKind` — §MON-008's therapeutic feeding programme locations | `kenya-imam-guidelines/` |
| WHO/UNICEF/WFP/SC, *Community-based management of severe acute malnutrition — a joint statement* (2007) | `afya.monitoring.views.THERAPEUTIC_FEEDING_LABEL` — §MON-008's community-based treatment vocabulary | `who-cmam-joint-statement/` |
| WHO Disease Outbreak News (DON613, DON619) and AFRO Kenya, plus the *Rapid risk assessment, Ebola disease caused by Bundibugyo virus, DRC, v4* (14 August 2026) | `afya.location.advisories` — §INF-005's country risk bands, the WHO travel advice, the border note and the post-travel steps | `who-ebola-outbreak-news/` |

Five directories below carry a section of their own but were missing from this table, which is the
list a reader checks against `ls sources/` before trusting it. A table that enumerates four of the
five ways to spell a source is the same defect as the internal-link checker that read only
`href="/…"`: the sections were all present and the index still under-reported the archive.

| Source | Used by | Archived |
|---|---|---|
| WHO Global air quality guidelines (2021) and the US EPA AQI technical assistance document | `afya.alerts.views.PM25_BREAKPOINTS`, `afya.alerts.service.AlertsService.air_alert` — §MON-006's AQI breakpoints, categories and outdoor-activity window | `air-quality/` |
| geoBoundaries `gbOpen` Kenya ADM1 (2020), boundary source RCMRD GeoPortal | `afya.info.counties.ADJACENCY` — §INF-001's "and neighbouring counties" | `county-adjacency/` |
| WHO fact sheet, Ebola disease (24 April 2025); CDC, About Ebola Disease | `afya.triage` — §11.2 TRI-003's exposure routes and the 21-day incubation window | `ebola-transmission/` |
| Befrienders Kenya, UN Women and the operators' own pages for the GBV and child helplines | `afya.info.service.HOTLINES` — §INF-006's helpline rows | `helpline-directory/` |
| WHO household water treatment guidance and the Round II report of the International Scheme to Evaluate Household Water Treatment Technologies | `afya.alerts.service.AlertsService.water_safety`, `afya.alerts.views.TreatmentMethod` — §MON-005's treatment, storage and reminder guidance | `water-treatment/` |
| Android Developers: the `supports-screens` element (the 320dp / 600dp / 720dp `smallestWidth` figures), window size classes, and the density bucket table | `afya.access.views.SCREEN_BUCKETS`, `afya.access.service.SCREEN_LAYOUTS` — §ACC-005's "support for low-resolution screens" | `android-screen-compatibility/` |

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
**Standards published:** 2006 (length/height-for-age, weight-for-age, weight-for-length, BMI-for-age,
head circumference-for-age, arm circumference-for-age); the 0–5 year z-score tables used here are the
current published revision.
**Retrieved:** 2026-10-12 for the first six files; 2026-10-13 for the head- and arm-circumference
tables.

### Files

Each file is the WHO z-score table as published, a 3-page PDF whose first page carries the header and
the LMS columns. The `.txt` beside each is the same table extracted with `pdftotext -layout`, which
reproduces the `Year: Month / Month / L / M / S` columns in order; `growth_standards.py`'s rows were
checked against it and agree exactly.

| File | Indicator | Sex | Ages | SHA-256 (first 16) |
|---|---|---|---|---|
| `wfa_boys.pdf` | Weight-for-age | Boys | 0–60 months | `ca6437e29134dee2` |
| `wfa_girls.pdf` | Weight-for-age | Girls | 0–60 months | `2ecadc34b59b3309` |
| `lhfa_boys_0_2.pdf` | Length-for-age | Boys | 0–24 months | `a3cee0ae2f50a7bc` |
| `lhfa_girls_0_2.pdf` | Length-for-age | Girls | 0–24 months | `a5895dcfacfc6de9` |
| `hfa_boys_2_5.pdf` | Height-for-age | Boys | 24–60 months | `a8b1093776be24ea` |
| `hfa_girls_2_5.pdf` | Height-for-age | Girls | 24–60 months | `c6ff83bc671ac6f0` |
| `hcfa_boys_0_5_zscores.pdf` | Head circumference-for-age | Boys | 0–60 months | `9f1a00bfc1613689` |
| `hcfa_girls_0_5_zscores.pdf` | Head circumference-for-age | Girls | 0–60 months | `647c885089c95dbc` |
| `acfa_boys_3_5_zscores.pdf` | Arm circumference-for-age | Boys | **3**–60 months | `2e5cf56f5ed80ea6` |
| `acfa_girls_3_5_zscores.pdf` | Arm circumference-for-age | Girls | **3**–60 months | `6740a0da96616b4d` |

The text copies, in the same order: `c5aeb7719aae4cc9`, `25e9bf5bde08df59`, `49ee5a7d7a85fa11`,
`afa057f52fcf39ce`, `34736c0885e3c139`, `4e634fb0cb3be7b9`, `0785e8976411b278`, `9a4a7ffcabefef55`,
`ef86181a77b6986a`, `bf91b80540752954`.

### What the head-circumference and arm-circumference tables do and do not support

Both were added on 2026-10-13 to close §REC-003's two `missing` rows, and both carry limits a reader
needs before using them.

- **Head circumference runs 0–60 months, 61 rows per sex, and `L` is 1 on every one of them.** The
  distribution is normal, so the Box-Cox transform reduces to the ordinary standard score. This is
  the same shape as the length and height tables and unlike weight.
- **Arm circumference starts at 3 months, not 0.** WHO publishes no arm-circumference-for-age
  standard below three months, and the tables here begin at row 3 because that is where the source
  begins. There is no value to interpolate down to and none is invented.
- **Arm circumference is right-skewed and `L` is never 1** — it is `+0.3928` for boys at 3 months
  and `−0.3981` by 60, crossing zero in between. An implementation that assumes normality
  understates the deficit at the low end, which is the direction a malnutrition screen may not fail
  in.
- **These are two different instruments from Kenya's IMAM MUAC cut-offs.** The WHO z-score answers
  "how far is this arm from the reference median"; the IMAM table answers "which programme is this
  child admitted to". `afya.records.growth` computes both and serves them in separate fields, and
  neither stands in for the other.
- **The two age floors do not coincide.** WHO's arm standard begins at 3 months; the IMAM MUAC
  admission rule begins at 6 (its Table 1.5 is titled "children 6 to 59 months" and refers infants
  below that to Section 3, the inpatient protocol). Between 3 and 6 months a child therefore has a
  z-score and no admission category, which is the correct answer and is reported as such.
- **Neither table is a percentile chart.** WHO's printed z-score columns are the SD lines; a
  percentile is derived from the z-score by the normal CDF and is not tabulated here.

The extraction was checked against the source rather than read off it: all four tables' L/M/S columns
were recomputed to WHO's own printed `−3 SD` … `+3 SD` columns, **238 rows, 0 disagreements** at a
0.05 cm tolerance. `growth_standards.py` now holds 484 rows across the five indicators, and its
module-level assert loop walks all five.

### Retrieval URLs

```
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/weight-for-age/wfa-boys-0-5-zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/weight-for-age/wfa-girls-0-5-zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/lfa_boys_0_2_zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/lfa_girls_0_2_zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/hfa_boys_2_5_zscoresba2ba0820f064f4abf5915abac01e894.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/length-height-for-age/hfa_girls_2_5_zscores.pdf
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/head-circumference-for-age/hcfa_boys_0_5_zscores.pdf?sfvrsn=701b4c5f_9
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/head-circumference-for-age/hcfa_girls_0_5_zscores.pdf?sfvrsn=85107050_9
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/arm-circumference-for-age/acfa_boys_3_5_zscores.pdf?sfvrsn=29b59481_11
https://cdn.who.int/media/docs/default-source/child-growth/child-growth-standards/indicators/arm-circumference-for-age/acfa_girls_3_5_zscores.pdf?sfvrsn=42dfdbfe_10
```

The landing pages, which carry the full table listing and the `sfvrsn` query parameters, are
`https://www.who.int/tools/child-growth-standards/standards/weight-for-age`,
`.../standards/length-height-for-age`, `.../standards/head-circumference-for-age` and
`.../standards/arm-circumference-for-age`. The last two are the pages the 2026-10-13 files were
taken from; the four above are those pages' own download links with their `sfvrsn` revision
parameters, which the earlier six rows omit because they were fetched before the parameter was
recorded.

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

`afya.records.growth_standards` holds all 484 rows verbatim across the five indicators: 61 months ×
2 sexes for weight, 25 × 2 for length, 37 × 2 for height, 61 × 2 for head circumference, and 58 × 2
for arm circumference (which starts at month 3, where WHO's table does). `afya.records.growth`
computes with them.

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
- **The arm-circumference z-score as an admission criterion.** Kenya's guideline admits on the
  absolute MUAC, not on the z-score, so the z-score is served as a measurement and never as a
  category. The two are separate fields for that reason.

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

**Where §LOC-001's 21-day sentence comes from, and where it does not.** The zone alert says
"Monitor for symptoms for 21 days. Call 719 if you feel unwell." The **window** is the WHO fact
sheet's incubation range above — "varies from 2 to 21 days" — and §MON-009, §COM-102 and the travel
advisory's five steps all rest on the same number. The **sentence** is the spec's own: §8.6 prints
its Alert content in full, and `afya.strings:zone_transition` reproduces it with `[specific
location]` resolved. The **719 line** is this deployment's, as it is everywhere else in the product:
neither source names a Kenyan hotline. No new archive directory was added for §LOC-001 because the
unit introduced no new external fact — the incubation window was already archived here, and the
alert's wording is the specification's. Said plainly so the absence of a new source directory is not
read as a missing citation.

**§LOC-004's check-in follow-up is the same 21 days, and a third consumer of it.** `LocationService`
(`afya.location.service:LocationService.follow_up`) derives the symptom watch from the check-in
instant over `LOCATION_WINDOW_DAYS = 21`, and schedules its asks on
`EXPOSURE_FOLLOWUP_DAYS = (1, 3, 7, 14, 21)`. The **window** is the WHO fact sheet's range above; the
**days** are the same five §LOC-005's enrolment states and §COM-102's peer alert carries, so three
sections schedule one window and this is where the number is read from. One consequence is load-
bearing and is why the note a closed window prints does not say the person is clear: the source gives
a **range with a lower bound**, so the app can say when its own watch ends and cannot say the person
was never exposed. `window_closed` therefore reports the closing date and says to call 719 if unwell
at any time. No new archive directory was added for §LOC-004 for the same reason as §LOC-001 — the
unit introduced no new external fact. The archive holds the fact sheet as `.html`, not as a PDF with
a `pdftotext` extraction beside it; the quotations above are from that HTML copy, checksummed at the
top of this section.

**Where §ALT-002's SMS check-in comes from, and where it does not.** The family safety check-in's
"works over SMS when data is unavailable" is carried by `afya.alerting.service:AlertingService.check_in`
(the fan-out) and `:check_in_by_msisdn` (the inbound message), and the strings it prints are
`afya.strings:SMS_FAMILY_*`. Every one of those strings is **this deployment's own copy**, written
here rather than reproduced from a source: the specification names the feature, the button and the
SMS channel, and prints none of the sentences. The **719 line** is the deployment's, as everywhere
else. No new archive directory was added for §ALT-002 because the unit introduced no new external
fact.

Two constraints the strings do carry, and neither is from a source in this tree:

- **The GSM7 alphabet.** §5.3's zero-rating and `afya.channels.service:segment_sms` both turn on the
  character set, and an em dash, a curly quote or a degree sign is refused at the gateway. That is a
  property of the SMS standard, not of a document archived here, so `tests/ci/test_alt002.py` asserts
  the alphabet over every table and every language rather than citing one.
- **What the message may name.** The reply carries counts and never the members' subject references,
  because an SMS lands on a handset that may be shared. The reason is §17.2's, from the
  specification, not from a source here.

The negation and third-party vocabularies (`afya.alerting.service:_NEGATIONS`, `_THIRD_PARTY`,
`_NEG_PREFIXES`) are likewise this deployment's own: no archived source enumerates the ways a
Kiswahili speaker says "not safe", and inventing a citation for them would be worse than recording
that they are ours. They are listed here for the same reason the strings are — so a later reader can
see that the absence of a citation is a decision and not an omission.

**Where §COM-101's offline report queue comes from, and where it does not.** The bullet is carried by
`afya.community.service:CommunityService._queue_case`, and what it writes is a `SyncOp` under the
dataset `case_reports`. That name and its strategy are **§16.3's own table**, which is part of the
specification this repository implements and is archived with the section it comes from — so the
matrix is cited by section rather than by a new archive directory.

Nothing else here is sourced from a publication, and the unit introduced no new external fact. No
source states how long an offline case report may wait before it must reach the server, what it must
carry, or how a replayed report is deduplicated; the answers in the code are §16.1's five principles,
§16.2's flow and §16.4's delta, all from the specification. Recorded so the absence of a new source
directory is not read as a missing citation — the same note §LOC-001 and §ALT-002 carry.

**Where §COM-103's encrypted contact-list share comes from, and where it does not.** The bullet is
carried by `afya.community.service:CommunityService.share_contacts`, and three things in it are
cited rather than invented. The **second key** is §SEC-003's own standard ("Contact lists and
location history: additional application-layer encryption"), archived with that section and
implemented since it was written as `CryptoService(app_layer_key=…)` with `contact_lists` first in
`APP_LAYER_DATASETS`. The **21-day window** is §COM-103's "deleted after the contact-tracing window
closes", and the number is read from §COM-102's `ALERT_WINDOW_DAYS` rather than typed again, because
three features that each wrote their own 21 would be three answers to one question. The **recipient**
is an office ("County Disease Surveillance Team") and not a person, which is a design choice the
section's own wording supports rather than a sourced fact.

Nothing else here is a claim about the world. No source states how a Kenyan county health team
receives a contact list, what transport it uses, or what a person must be told when a share cannot be
delivered; the answers in the code are §COM-103's data-handling clause and §16.1 principle 5. The
ADaM leg reuses §18.1's integration point, which is archived with its section. Recorded so the
absence of a new source directory is not read as a missing citation — the same note §LOC-001,
§ALT-002 and §COM-101 carry.

**Where §COM-104's media payload and flagger notification come from, and where they do not.** The
first bullet is carried by `afya.community.views:MisinfoSubmission`, and the one thing in it that is
cited rather than chosen is the consent gate: §SEC-002's own line for this data — "Photos encrypted
and only shared with explicit per-item consent" — is why `evidence_consent` is per *report* and not a
setting, and why the model carries a reference instead of bytes. The second is carried by
`afya.community.service:CommunityService.notify_flaggers`, and §ALT-003's Options list is what makes
`community_alerts` the category: it is the section's own "community alerts" toggle, so no twelfth
switch is invented and the notice is one a person can decline. §11.4's flow supplies the order
("aggregated → verified → correction drafted → published → flagger notified"), which is why an
undrafted rumour produces no notice.

Nothing else here is a claim about the world. No source states how a Kenyan county receives a voice
note or a screenshot, what a person must be told when a correction is ready, or whether a rumour
reporter is notified by push rather than SMS. The transport is §COM-103's own answer to the same
question and is reused deliberately: a transport that fails degrades to *held*, and the correction is
readable in the app either way (§16.1 principle 5). The correction text and its authority come from
the myth corpus archived with §INF-004, not from a new document. Recorded so the absence of a new
source directory is not read as a missing citation — the same note §LOC-001, §ALT-002, §COM-101 and
§COM-103 carry.

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

## Household water treatment — §MON-005's treatment, storage and reminder guidance

§10.2 MON-005 lists five Features and three of them were bullets with no carrier: "treatment
guidance", "safe storage guidance" and "point-of-use treatment reminders". The advisory string that
existed said "do not drink without boiling", which is a warning and not guidance — it names no method
a household can perform, says nothing about the container the water goes back into, and schedules
nothing. Writing those three meant answering questions the section does not answer: *which* methods
may be offered, when one must be withheld, how long treated water keeps, and what residual protects
it in storage. Every one of those answers is a figure or a condition from a WHO document, so the
documents are archived here rather than paraphrased from memory.

**Publisher:** World Health Organization. **Licence:** WHO publications — CC BY-NC-SA 3.0 IGO
(the technical brief carries the WHO copyright line; the Round II report is the Scheme's own
publication). **Retrieved:** 2026-10-13.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `who-boil-water-technical-brief-2015.pdf` | WHO/FWC/WSH/15.02, *Boil water*, technical brief, 14 January 2015, 2 pp. | `136d2e2bc676c981` |
| `who-boil-water-technical-brief-2015.txt` | `pdftotext -layout` extraction of the above | `ee1914cf0cf39698` |

**Retrieval URLs:**
`https://www.who.int/publications/i/item/WHO-FWC-WSH-15.02` (landing page);
`https://iris.who.int/server/api/core/bitstreams/6d37bdcd-04b0-48d7-9a88-1e18b36c2b56/content`
(the PDF itself; the `iris.who.int/bitstream/handle/...` path serves an HTML shell, not the file).

**A second source, cited but not archived.** WHO's *Results of Round II of the WHO International
Scheme to Evaluate Household Water Treatment Technologies* (2019, ISBN 978-92-4-151603-7,
`https://www.who.int/publications/i/item/9789241516037`) is where the two turbidity figures and the
chlorine-residual guidance come from. Its PDF is 3.2 MB and is **not** committed; the specific
sentences relied on are quoted verbatim in the code and in the tests, and each is attributed to the
report by name. This is a deliberate departure from the two-copy rule and it is recorded as one: the
quotes are short, they are the whole of what is used, and a reader can check each against the
published report without the archive.

**What the sources support, and what the code takes from each:**

- **Boiling inactivates pathogens, including in turbid water and at altitude.** The technical brief:
  boiling "is highly efficacious, killing human pathogens even in turbid water and at high altitude",
  and "the process of heating water to a rolling boil ... is sufficient to inactivate pathogenic
  bacteria, viruses and protozoa". This is why `boil` is the one method offered on **every** reading
  and led with on all of them — it is the only method with no condition attached, and therefore the
  only one the advisory can name without knowing more about the water.
- **Boiling leaves no residual protection.** The same brief: boiling "does not provide any residual
  protection", and the water should be "allowed to cool naturally, without the addition of ice, and
  protected from post-treatment recontamination during storage". This is `TREATMENT_CAVEATS[boil]`
  and the first three storage steps.
- **Chlorine products are evaluated for nonturbid water only.** Round II: the evaluated products
  "should only be used in nonturbid water (<5 NTU)". This is `CHLORINE_TURBIDITY_LIMIT_NTU = 5.0`,
  the threshold at which `chlorinate` is withheld.
- **Chlorine is ineffective against Cryptosporidium.** Round II: chlorine is "ineffective against
  most protozoan cysts including Cryptosporidium". This is `TREATMENT_CAVEATS[chlorinate]`.
- **The residual that protects stored chlorinated water.** Round II, Box 6: a dose should "maintain
  an FRC concentration of >=0.5 mg/L after 30 minutes of contact time, or >=0.2 mg/L in stored
  household water". The **stored** figure — 0.2 — is the one `StorageGuidance` carries, because the
  field is on a storage block; the 0.5 mg/L / 30-minute figure is stated in the chlorination step
  text.
- **Safe storage is not a lesser measure than treatment.** Round II, Box 5: "filtration and
  integrated safe storage can reduce the risk of diarrhoeal disease by 61% compared to 51% from
  filtration only". This is why storage guidance is served on every reading, including a safe one.
- **Solar disinfection is slow.** The brief groups it under heat methods; the six-hour/full-sun and
  two-day/overcast figures in `TREATMENT_STEPS[solar]` are the standard SODIS exposure and are
  **not** stated in either archived document — they are recorded here as unsourced rather than
  presented as WHO's. A household following that step on a source that does not carry the number is
  relying on the repo's own figure, and the caveat on the same method says the method is slow and
  conditional on clear bottles and clear weather, which the brief does support for heat methods
  generally.

**What the sources do not support, and where the code says so:**

- **Neither document states a boiling duration.** The brief's conclusion is a *rolling boil* with no
  minute count, and the repo does not invent one — `TREATMENT_STEPS[boil]` says "bubbling vigorously,
  not merely steaming", which is what "rolling boil" means, and states no time. A one-minute or
  three-minute figure is common in national guidance and appears in neither source here, so it is not
  in the code.
- **Neither document states how long treated water keeps.** The 24-hour interval is the repo's own
  parameter (`REMINDER_INTERVAL_HOURS`), named as such in the code and here. What the sources support
  is that recontamination during storage is the risk being managed, which is why there is an interval
  at all and why it is short.
- **Neither document states a turbidity limit for boiling or filtration.** The 5 NTU figure is
  chlorine-specific. `filter` and `solar` are therefore offered without a turbidity condition, and
  the code does not attach one to them.
- **Round II evaluates specific products, not methods.** Its figures are what the *tested products*
  achieve and the conditions they were tested in. The code uses them as conditions on a *method*,
  which is the conservative reading — a household's chlorine product is not necessarily one of the
  evaluated ones — and the storage step tells the reader to check the smell rather than trust a
  number.
- **No document here is Kenyan national guidance.** A county may publish its own treatment
  thresholds, and nothing in the code claims to override them.

## Air quality — §MON-006's index, window and source

§10.2 MON-006 lists five Features and three of them were bullets with no carrier: "AQI for user's
location", "best times for outdoor activity" and "pollution source information". What existed was
`air_alert`, which branches on two ad-hoc cuts at 35 and 55 µg/m³ of raw PM2.5. Two things had to be
answered from a source rather than invented, and they come from two different bodies: the *index* —
its breakpoints, its interpolation, its categories — and the *reason a time of day is the right
unit*, plus the categories a source can be named from. Neither document is Kenyan national guidance,
and neither is the other's substitute.

**Publisher:** World Health Organization (the guidelines); United States Environmental Protection
Agency, Office of Air Quality Planning and Standards (the AQI technical assistance document).
**Retrieved:** 2026-10-13.

### `who-global-air-quality-guidelines-2021.pdf`

WHO global air quality guidelines: particulate matter (PM2.5 and PM10), ozone, nitrogen dioxide,
sulfur dioxide and carbon monoxide. Geneva: World Health Organization; 2021. Licence CC BY-NC-SA
3.0 IGO. ISBN 978-92-4-003422-8.

- `who-global-air-quality-guidelines-2021.pdf` — SHA-256 `32f3bf1470e20803…` (6.3 MB)
- `who-global-air-quality-guidelines-2021.txt` — SHA-256 `36a2e120560a84d4…` (`pdftotext -layout`)

**What it supports, and where the code uses it:**

- **Why exposure is concentration × time.** The guidelines state that the health risk from PM "is a
  product of the pollutant concentration and the time over which a person is in contact with that
  pollutant". This is the whole justification for a *time of day* answer rather than a number, and it
  is why `AlertsService.outdoor_window` returns hours and not a threshold.
- **Why concentrations vary by hour.** The same document attributes the temporal pattern to "the
  temporal pattern of operation of outdoor sources (e.g. traffic) but also on indoor sources (e.g.
  the daily cycle of cooking)". This is why a household cooking on charcoal and a road at rush hour
  are both visible in an hourly series and neither is visible in a daily mean.
- **The source categories.** The sources-of-emissions discussion names "land, air and water
  transportation; industry and power generation; and biomass burning, which includes controlled and
  uncontrolled forest and savannah fires and agricultural waste burning, as well as waste burning in
  urban areas". `AlertsService.pollution_source` names road traffic, waste or agricultural burning
  and forest or savannah fire from exactly these. Household fuel combustion is defined as its own
  source by the same document and is the fourth, which in Kenya is the one a person can act on.
- **Susceptible populations.** The guidelines define the groups at greater risk (people with
  pre-existing cardiopulmonary disease, older adults, children, pregnant women), which is what
  `air_alert`'s "sensitive groups" branches address.

**What it does not support, and where the code says so:**

- **WHO publishes no AQI.** The guidelines give guideline levels and interim targets in µg/m³; they
  do not define a 0–500 index, categories, or breakpoints. The index in the code is the **EPA's**, and
  the code and this entry name it as such. Presenting the EPA table as WHO's would be the attribution
  error this section exists to prevent.
- **WHO's four interim targets are not the index's bands.** WHO's interim targets for annual and
  24-hour PM2.5 are a *policy* scale for setting limits; the index's category boundaries are a
  *communication* scale. They are close in places and are not the same thing, and the code does not
  merge them.
- **WHO does not recommend masks.** The guidelines say individual-level interventions "such as the
  use of personal respiratory protection (e.g. masks, respirators, air purifiers) or behavioural
  measures, are addressed in another document". So `AlertsService.mask_guidance`'s text is the
  **repo's own** and is written to state what a mask does not do; the source supports the *absence*
  of a WHO recommendation, not the recommendation itself.
- **No national guidance.** A county or the Ministry may publish its own advisory thresholds, and
  nothing in the code claims to override them.

### `us-epa-aqi-technical-assistance-document-2018.pdf`

*Technical Assistance Document for the Reporting of Daily Air Quality — the Air Quality Index
(AQI).* EPA-454/B-18-002. U.S. Environmental Protection Agency, Office of Air Quality Planning and
Standards, Research Triangle Park, NC; December 2018 (supersedes EPA-454/B-06-001).

- `us-epa-aqi-technical-assistance-document-2018.pdf` — SHA-256 `173f8d8668e37bc4…` (2.2 MB)
- `us-epa-aqi-technical-assistance-document-2018.txt` — SHA-256 `41e5bec4851ec96a…` (`pdftotext -layout`)

**What it supports, and where the code uses it:**

- **The PM2.5 breakpoint table.** Table 5 gives the seven bands and their index ranges, from
  (0.0–12.0 → 0–50) through (350.5–500.4 → 401–500). `PM25_BREAKPOINTS` in `src/afya/alerts/views.py`
  is this table row for row, and `test_every_band_boundary_lands_on_its_own_index` reads the code's
  table rather than a second copy of it.
- **The interpolation.** The document's linear interpolation, `I = (I_hi − I_lo)/(BP_hi − BP_lo) ×
  (C − BP_lo) + I_lo`, is what `pm25_aqi` implements. The document also states that the concentration
  is **truncated to one decimal place before the band is chosen** — its own worked example truncates
  0.07853333 to 0.078 — which is why `pm25_aqi` truncates before it looks up rather than after.
  Canary #1 in `tests/ci/canary_mon006.py` removes that truncation and the test catches it at 35.45,
  the value the boundaries put in the band below.
- **The categories.** Table 3's six categories and their index ranges are `AQI_CATEGORIES`:
  good, moderate, unhealthy for sensitive groups, unhealthy, very unhealthy, hazardous. The document
  also names the sensitive groups each category is about, which is the source for the wording.
- **The worked example.** The document's own interpolation of 35.9 µg/m³ to index 102 is asserted
  verbatim in `test_the_index_reproduces_the_sources_own_worked_example` — the one figure in either
  source that is both a specific input and a specific output, which makes it the arithmetic's check.

**What it does not support, and where the code says so:**

- **It is not Kenyan guidance, and its scale is the US one.** The categories are the EPA's
  communication scale; a Kenyan bulletin may use different wording or different boundaries. The code
  carries the EPA's numbers and names them.
- **The top row carries a footnote the lower rows do not.** Above 250.4 µg/m³ the 24-hour PM2.5
  standard is not the basis for the band — the document's own Table 5 marks it with a significance
  note that the upper range extends to the highest index value without a corresponding 24-hour
  standard. The code carries the row because the scale needs a top, and `AirQuality.pm25` is bounded
  at `le=500` so the top row is defence in depth rather than the common path.
- **Nothing above 500.4.** The scale has no answer past the table, and `pm25_aqi` returns 500 rather
  than extrapolating: an extrapolated index is a number no screen is designed for and no guidance is
  written against. `test_a_reading_above_the_table_is_capped_rather_than_extrapolated` pins it.
- **No source information at all.** The AQI is a concentration index; the document does not say where
  the pollution came from. That is why `pollution_source` names a source only where the *caller*
  reports evidence for one and serves an empty list with an explanation otherwise — a monitor reads a
  concentration and cannot read a source.
- **No hourly forecasting.** The document describes reporting a daily AQI. The hourly window is built
  from readings the caller supplies, never from a curve the service invents; with no series the window
  is empty and says so.

## Kenya Data Protection Act 2019 — the statute §SEC-001's consent rests on

§12.6 SEC-001's first Feature is "plain-language explanations in local languages", and the reason that
bullet is load-bearing rather than decorative is the Act: consent a person cannot read is not
*informed* consent, and the Act recognises only consent that is informed. The code leans on that
property in `src/afya/privacy/service.py`'s `REGULATORY_INSTRUMENTS`, which is the spec's §17 table
reproduced.

**The Act is not archived here, and four attempts to archive it failed.** Recorded rather than left as
an unexplained gap in this file:

- `https://www.odpc.go.ke/data-protection-act/` → **404**
- `https://www.odpc.go.ke/downloads` → **404**
- `https://www.odpc.go.ke/regulatory-framework/` → **404**
- `https://kenyalaw.org/kl/fileadmin/pdfdownloads/Acts/2019/TheDataProtectionAct_No24of2019.pdf`
  and `https://new.kenyalaw.org/akn/ke/act/2019/24/eng@2019-11-08/source.pdf` → **403**, to both a
  fetch and a `curl` carrying a browser user agent

`https://www.odpc.go.ke/` itself answers: it states the Office's mandate, cites "section 25 of the
Act" for the data-protection principles, reproduces no text of the Act, and offers **no Kiswahili
version** of anything.

**What this file therefore does not support.** No section number and no quoted wording of the
informed-consent requirement is recorded here, because none was read from a primary source in this
repo. The claim in the code is a citation the repo has not independently archived, and it should be
read that way. The consequence for §SEC-001 is bounded: the unit does not rest on a figure from the
Act — the consent sentences are this repo's own, and no external source states a Kenyan consent
explanation in Dholuo, which is the §LOC-005 decision again. What is *not* claimed is that the Act was
read. A future pass that can reach the text should archive it and record the section number here.

**Why not fetch it through a mirror.** A second-hand copy of a statute is a citation that points at
something other than the law, and a summary of a consent provision is exactly the kind of source this
file exists to refuse. Better an honest gap than a paraphrase presented as the Act.

---

## Border and point-of-entry — §LOC-005's traveller language tables

§11.5 LOC-005's sixth Feature is "multi-language support for cross-border travellers" and it had no
carrier: `TravelerDeclaration.lang` was accepted and never read, so every acknowledgement went out
in English whatever the traveller said they read. Writing it meant deciding *which* languages this
path answers in, and that is a decision about sources, so it is recorded here.

**No new document is archived for this section, deliberately.** The strings are the repo's own, and
the reasoning is the same as §MON-006's mask text: no source states a Kenyan border advisory in
Dholuo, and inventing a citation for a translation would be worse than the gap. What *is* sourced is
the set of languages, and it comes from two places already in the tree:

- **§ACC-002's priority order**, carried as `LANGUAGE_MATRIX` in `src/afya/access/views.py` — tier 1
  is Kiswahili, English, Dholuo, Luhya (Bukusu) and Kikuyu, tier 2 the rest.
- **§ACC-002's own language list for voice-guided symptom reporting** — Swahili, Dholuo, Luhya,
  Kalenjin, Kikuyu and English.

**What the code does with them, and what it refuses to claim.** `SUPPORTED_LANGS` in
`src/afya/strings.py` is `{'en', 'sw'}` — the languages with a *hand-written string table* — and it
is deliberately narrow. `TRAVELLER_STRINGS` therefore has two entries, and `traveller()` falls back
through `answerable()` for the rest. Three consequences are asserted rather than left implicit:

- **A language with no table is served English and told so.** The payload carries the language the
  traveller *declared* (`TravellerEnrolment.lang`, `PostArrivalVerdict.lang`) alongside the message
  they actually got, so a Dholuo speaker reads English knowing it is English rather than believing
  it is Dholuo. A wrong instruction at a point of entry is worse than an honest English one.
- **The mobile catalogue offers only the languages the path can answer in.** `TRAVELLER_LANGS` is
  `sorted(SUPPORTED_LANGS)`, not `LANGUAGE_MATRIX`'s key set: a dropdown offering Dholuo on this
  path would promise a language the path answers in English. This is the deliberate difference from
  §ACC-002, which requires six languages for *voice triage* and is a separate, still-open gap.
- **A missing key raises rather than returning a placeholder.** A silent empty string is a screen
  that renders blank where an instruction should be, and nothing reports it.

**What the strings are not.** They are not clinically reviewed translations, not back-translated, and
not community-validated — §6.5's workflow governs published health *content*, and these are UI
strings. A Dholuo, Luhya or Kikuyu table added later should go through that workflow; a
machine-translated table would report this gap as closed, which is the failure the whole file is
written to avoid.

---

## Travel advisory — §INF-005's country risk bands and post-travel steps

§INF-005's first Feature is "Country and county advisories" and the country half was a constant:
`LocationService.advisory(destination, origin_country)` interpolated its two arguments into one
fixed paragraph, so Kampala, Kinshasa and Kinshasa-from-Nairobi were answered identically. Making it
a table meant answering *which countries, at what band, on whose authority* — and the authority
publishes a band per **group** of countries, not a row per country. That distinction is the whole
reason this section exists, because the tempting shortcut (read every country's band off the group
it sits in) answers "low" about Kenya.

**Publisher:** World Health Organization. **Licence:** WHO publications — CC BY-NC-SA 3.0 IGO.
**Retrieved:** 2026-10-13.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `who-rapid-risk-assessment-bvd-drc-v4-2026-08-14.pdf` | *Rapid risk assessment — Ebola disease caused by Bundibugyo virus, Democratic Republic of the Congo*, v4, 14 August 2026 | `662eed758b9c8393` |
| `who-rapid-risk-assessment-bvd-drc-v4-2026-08-14.txt` | `pdftotext -layout` extraction of the above | `72914f78710e6faf` |
| `who-don-2026-DON619.html` | WHO Disease Outbreak News 619, 8 October 2026 — the notice carrying the Kenya case and the current risk assessment | `500f4ad32beafa0b` |
| `who-don-2026-DON613.html` | WHO Disease Outbreak News 613 — the earlier notice, where the land-border band was first stated | `b8fed0ee11761e6e` |
| `who-afro-kenya-first-imported-bvd-case.html` | WHO AFRO, *Kenya confirms first imported Bundibugyo virus disease case* | `d2d919f3993b6dcf` |

URLs: `https://cdn.who.int/media/docs/default-source/_sage-2026/web_20260814_ebola-bundibugyo-virus-disease--democratic-republic-of-the-congo_v4.pdf?sfvrsn=b0081e9d_3&download=true`,
`https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON619`,
`https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON613`,
`https://afro.who.int/countries/kenya/news/kenya-confirms-first-imported-bundibugyo-virus-disease-case-who-supports-control-efforts`.

### What the sources support, quoted

- **The four-row risk table, verbatim.** DON619: "the risk in the Democratic Republic of the Congo
  was assessed as very high, the risk for countries sharing land borders with the Democratic Republic
  of the Congo was assessed as high, and the risks for the rest of the African region and at the
  global level was again assessed as low." `WHO_RISK_TABLE` is these four rows in this order, and
  `WHO_CONFIDENCE` carries the assessment's own confidence beside each (the DRC and land-border rows
  are "Moderate"; only "Global" is "High").
- **Three countries named inside the high band.** v4: "Countries sharing land borders with the
  Democratic Republic of the Congo remain at risk because of frequent cross-border population
  movement. Uganda, the Central African Republic and South Sudan are of particular concern for
  importation given their proximity, high population mobility and connectivity with areas of the
  Democratic Republic of the Congo currently experiencing intense transmission." Each of the three
  rows carries this sentence, and for the CAR and South Sudan the source adds: "these risks are
  further compounded by high humanitarian needs, population displacement, insecurity and underlying
  limitations in health-system capacity."
- **WHO's advice on travel restrictions, verbatim, and it is not a per-country verdict.** DON619:
  "Based on the currently available information, WHO advises against any restriction of travel to, or
  trade with, affected countries." The source does not say "do not travel to X". `WHO_TRAVEL_ADVICE`
  is this sentence, served unchanged.
- **Why the advice is not a licence to ignore the outbreak.** v4: "Entry and exit health screening
  and surveillance measures are in place at airports, ports and official land border crossings;
  however, movement through informal border crossing routes may occur, presenting an ongoing risk of
  virus exportation, importation and onward transmission." This is `WHO_BORDER_NOTE`.
- **The counterweight, and it is served because the bands alone imply its opposite.** CDC's About
  Ebola Disease page: the viruses that cause Ebola disease "pose little risk to travelers or the
  general public", a person is contagious only once symptomatic, and the disease does not spread
  through the air. `TRAVELLER_RISK_NOTE`.
- **The post-travel steps.** "Monitor your health for 21 days after you return from an area with an
  ongoing Ebola outbreak" and "Seek medical care immediately if you develop symptoms" are CDC's; the
  symptom set ("fever, fatigue, malaise, muscle pain, headache and sore throat, followed by vomiting,
  diarrhoea, abdominal pain, rash, and symptoms of impaired kidney and liver functions") is the WHO
  fact sheet's. Both are archived under `ebola-transmission/` above, and `STEP_SOURCES` names them.

### What the sources do NOT support

- **They do not enumerate the DRC's land-border countries.** WHO names three "of particular concern"
  and stops. **Burundi shares a land border with the Democratic Republic of the Congo and has no row
  in either source**, and the same is true of Rwanda, Tanzania and Zambia. `COUNTRIES` therefore
  carries exactly seven rows, and `tests/ci/test_inf005.py` asserts that Burundi, Rwanda and Tanzania
  resolve to *nothing* rather than to the regional band. A `low` for Burundi read off "rest of the
  African Region" would be the single most consequential invented number in this file — the regional
  band is about the Region, and the land-border band is where Burundi actually sits.
- **They do not assess Kenya.** DON619: "A detailed rapid risk assessment is currently ongoing to
  assess the risk in Kenya and will be reported once available." Kenya's row is `not_assessed` with
  that sentence, and `BAND_LABELS` renders `not_assessed` and `unknown` alike as "not assessed" — a
  refusal to answer, never `low`. Kenya is inside the "rest of the African Region" band and the
  tempting read is precisely the wrong one.
- **They state no county-level advisory.** §INF-005 asks for "country **and county** advisories" and
  no WHO document has a Kenyan county row. The county half therefore reads §INF-001's own dashboard
  (`CountyRisk`, archived under `county-adjacency/` and the county-office feeds) rather than a second
  table here, and `PlaceAdvisory.kind` records which of the two tables a row came from because the
  two use **different vocabularies** — a country carries WHO's `very_high|high|low|not_assessed`, a
  county carries `low|moderate|high`. They overlap on `high` and `low`, and that overlap is why
  `kind` is load-bearing rather than decorative.
- **They state no threshold for anything.** There is no figure in §INF-005 to get wrong, which is
  itself worth recording: the section is bands and sentences, and a number invented to fill a table
  would have no source to check it against.
- **The 719 line and the arrival declaration are not in either source.** They are this deployment's
  operating rule, and `STEP_SOURCES` says so in the served payload — "not stated by either source" —
  so a reader can tell the authority's instruction from the product's.

**The band moves.** WHO reassessed on 14 August 2026 (v4) and published DON619 on 8 October; the
country rows carry `assessed_on_iso = 2026-08-14` and not the serve date, because a risk band is a
statement about a moment and a payload stamped at serve time would present an August assessment as
this morning's. Re-check `sources/INDEX.md`'s table against `afya/location/advisories.py` when the
next assessment is published.

---

## Whisper ASR — §ACC-002's recogniser

`models/speech/` carries a whisper-tiny speech recogniser, and `src/afya/ml/speech.py` implements its
front end in numpy. Two things are load-bearing enough to archive: the paper the architecture and
front-end constants come from, and the Mel filterbank the engine actually multiplies by.

| Source | Used by | Archived |
|---|---|---|
| Radford, Kim, Xu, Brockman, McLeavey, Sutskever, *Robust Speech Recognition via Large-Scale Weak Supervision*, OpenAI, arXiv:2212.04356 | `afya.ml.speech` — the log-Mel front end, the prompt token sequence, the 30 s window | `whisper-asr/whisper-2212.04356.pdf` + `.txt` |
| `whisper/assets/mel_filters.npz` (MIT, © 2022 OpenAI) | `afya.ml.speech:log_mel` — the `mel_80` matrix | `whisper-asr/mel_filters.npz` |

Checksums (sha256, first 16 hex):

| File | sha256[:16] |
|---|---|
| `whisper-asr/whisper-2212.04356.pdf` | `6337bde031b2f237` |
| `whisper-asr/whisper-2212.04356.txt` | `23f8f8ebef3c3175` |
| `whisper-asr/mel_filters.npz` | `7450ae70723a5ef9` |

Retrieved 2026-10-13 from `https://arxiv.org/pdf/2212.04356` and
`https://github.com/openai/whisper/raw/main/whisper/assets/mel_filters.npz`. Whisper is MIT-licensed;
the ONNX export is `onnx-community/whisper-tiny` (quantized, int8), and the tokenizer, vocabulary and
`preprocessor_config.json` in `models/speech/` come from that repository.

**What the paper does and does not support.** §2.2 states the front end precisely: audio resampled to
16,000 Hz, an 80-channel log-Mel spectrogram, computed over 25-millisecond windows with a stride of
10 milliseconds. Those are the constants `speech.py` asserts against `preprocessor_config.json`, and
they are what the paper is archived for. The paper does **not** name the window function. That
whisper uses the *periodic* Hann window rather than the symmetric one is read from the reference
implementation, not from the paper — `test_acc002.py::test_the_window_is_periodic_not_symmetric`
pins the distinction, and `canary_acc002.py` #1 pins that the test can fail. This is recorded because
a reader who follows only the citation would conclude the window is unspecified, and the two differ
by one sample of phase.

**What is measured rather than cited.** The deployed `models/speech/mel_80.npy` is byte-identical to
`mel_80` in the archived `.npz` (verified by `np.array_equal`, 2026-10-13), so the filterbank is the
one this source describes and not a re-derivation. The paper also does not state the merge strategy
of the exported decoder, and the KV-cache branch of `decoder_model_merged_quantized.onnx` produces
confidently wrong text — `speech.py`'s docstring records that finding and decodes without the cache.

**The six-language bullet stays open.** §ACC-002's first bullet names Swahili, Dholuo, Luhya,
Kalenjin, Kikuyu and English. `LANGUAGE_MATRIX` carries `asr: False` for `luo`, `bxk`, `kln` and `ki`,
and whisper-tiny's language tokens cover 98 languages of which `sw` and `en` are the two this repo
ships. No source here supports recognition in the other four, and none is claimed.

## WHO Model Formulary 2008

The World Health Organization's formulary — a monograph per medicine, plus appendices that
cross-reference them. §MED-002 asks for a checker that flags "contraindications for pregnancy,
children, and common conditions", and the repo had no clinical data behind that clause: the
interaction table was four rows typed into `service.py` and there was no contraindication axis at
all. This is where all four axes come from — Appendix 1 for drug pairs, Appendix 2 for pregnancy,
Appendix 3 for breastfeeding, and each monograph's own `Contraindications:` line for age and
condition.

**Publisher:** World Health Organization. **Edition:** 2008, published 2009. **ISBN:**
978 92 4 154765 9. **Editors:** Marc C. Stuart, Maria Kouimtzi, Suzanne R. Hill.
**Retrieved:** 2026-10-13.
**Record page:** `https://iris.who.int/handle/10665/44053` (IRIS uuid `8bdde138-003e-4b61-9208-1abe1e7b0d02`).

### Files

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| `who-model-formulary-2008.pdf` | 3698742 | `2d4252dedd830557` |
| `who-model-formulary-2008.txt` | 1611743 | `5a0c07e8802b3ccf` |

The PDF is the publisher's own file, 644 pages. The `.txt` is `pdftotext -layout` over it, and the
`-layout` flag is load-bearing here in a way it is not for most sources: Appendix 1 and Appendix 2
are two-column tables, and IRIS's own plain-text extraction of the same document interleaves the
columns into unreadable runs. With `-layout` the columns survive in order and the tables can be
checked against the code row by row.

**The download path is a bitstream UUID, not the record page.** The PDF came from
`https://iris.who.int/server/api/core/bitstreams/614b1dd8-8006-489d-a83c-51c657f8d3f2/content`; the
record page is an Angular landing page whose `<link rel="item" type="application/pdf">` tag carries
that URL. Check `file` on anything retrieved this way before checksumming it — the same trap the
Pocket Book entry records.

### What the source supports, and what it does not

- **Appendix 1 (Interactions), p. 503–581** — for each drug, the drugs it interacts with and the
  effect. 2,853 rows over 223 drug headings, which reduce to **1,452 unique unordered pairs**
  because the appendix lists each pair **twice**, once under each drug. **1,370** pairs appear under
  both; **7** carry a *different* hazard marking in the two listings, and the table keeps the more
  severe one. A pair listed once is not evidence of anything — the appendix is not exhaustive, and
  a drug absent from it has not been cleared.
- **Appendix 1's severity axis is two-valued, not graded.** Its own words: "the symbol * indicates a
  potentially hazardous interaction and the combined administration of the drugs involved should be
  avoided, or only taken with caution and appropriate monitoring. Interactions with no symbol do not
  usually have serious consequences." The repo stores `hazardous` or `noted` and carries that
  sentence as `HAZARD_DEFINITION`, because "noted" is not a reassurance and a client that renders it
  as one has misread the source. There is no `minor|moderate|major` scale in this document.
- **Appendix 2 (Pregnancy), p. 582–598** — 221 drugs with the source's comment for each. Its own
  caveat, which travels with every pregnancy answer the service gives: **"Absence of a medicine from
  the list does not imply safety"**, and "Drugs should be prescribed in pregnancy only if the
  expected benefits to the mother are thought to be greater than the risk to the fetus." A checker
  that returns "no flag" without those sentences turns an absent row into a reassurance the source
  explicitly refuses to give.
- **Appendix 3 (Breastfeeding), p. 599–610** — 202 drugs. A separate table from Appendix 2, and the
  service does not infer one from the other: they are different clinical states and the source keeps
  them apart.
- **The monographs' `Contraindications:` lines** — the age axis (21 drugs stating a floor, as a
  number or as the bare word "children"/"neonates") and the condition axis (19 condition families,
  187 drug/condition pairs). Where a monograph states a word rather than a number the table stores
  `None` rather than converting it to a figure the source did not write — the same reason
  `afya.medicine.formulary` leaves `max_mg_per_dose` empty where no maximum is stated.
- **Not every drug has a `Contraindications:` line.** Paracetamol has only `Precautions:`, so it has
  no condition or age flags and none may be invented for it. This is the row that a window-based
  extraction gets wrong: reading a fixed character window past the end of the monograph attributes
  the *next* drug's contraindications to paracetamol. `test_med002.py` pins the correct behaviour.

**Two extraction defects worth recording, because each was invisible in the output.** The appendix's
running headers (the folio line and the repeated section title) are filtered out by a test that read
`A or B and C`, which Python parses as `A or (B and C)` — so only the folio line was dropped and
every section title was appended to the comment above it. And the two-column tables typeset a few
wrapped drug names with a single space between the name and its comment, and one name (`Pentamidine
isetionate`) is longer than the comment column, so neither a 2+-space rule nor a column position
finds the boundary. Both are fixed in the generator scripts, which are committed beside this source
under `who-model-formulary/tools/`.

**What the source does not support.** It is a 2008 formulary and its interaction list is a
selection, not a database: absence from Appendix 1 is not clearance, and the checker says so by
returning unmatched names separately rather than reporting them as safe. It states no severity
grading beyond the starred/not-starred mark. It carries no dose for the condition axis and no
paediatric dose at all — that is the Pocket Book, a separate source above.

## OpenStreetMap healthcare tags — §REC-006's donation centres

§REC-006 asks the app to "Find donation centres". The repo's `PlaceKind` enum had eight members and
none of them was a donation centre, so the vocabulary had to come from somewhere rather than be
invented — and the obvious guess is wrong. OpenStreetMap does **not** define `amenity=blood_donation`;
the donation tags live under the separate `healthcare` key, and the two values are documented as
*different things*. A finder that collapsed them would return a storage site as a place to give
blood, which is a result the person asking cannot use.

**Publisher:** OpenStreetMap wiki (OSM contributors). **Retrieved:** 2026-10-13.
**Licence:** the wiki pages themselves state Creative Commons Attribution-ShareAlike 2.0 (the
`Wiki content license` link in the archived HTML). The OSM *data* the tags describe is separately
ODbL 1.0 — this archive holds wiki text only, no OSM data.
**URLs:** `https://wiki.openstreetmap.org/wiki/Tag:healthcare%3Dblood_donation` and
`https://wiki.openstreetmap.org/wiki/Tag:healthcare%3Dblood_bank`, both reached from
`https://wiki.openstreetmap.org/wiki/Key:healthcare`.

### Files

| File | SHA-256 (first 16) |
|---|---|
| `healthcare-blood_donation.html` | `40fbe400b2ce8132` |
| `healthcare-blood_donation.txt` | `8833f7760171a7a0` |
| `healthcare-blood_bank.html` | `f962df9c281b1754` |
| `healthcare-blood_bank.txt` | `a7a9f0b5ec683bef` |

### What the source states

- **`healthcare=blood_donation`** — "A facility where you can donate blood, plasma and/or platelets,
  and possibly have stem cell samples taken."
- **`healthcare=blood_bank`** — "a facility where blood gathered as a result of blood donation is
  stored and preserved for later use in blood transfusion", which the page adds "are often found in
  a hospital or medical centre".
- Both are values of the **`healthcare`** key. The `amenity` key carries neither, which is why the
  Overpass query in `afya.integrations.overpass` asks under `healthcare` and the parser reads both
  keys rather than one.

### What the source does and does not support

- **It defines the tags; it does not enumerate the sites.** Nothing here says how many donation
  centres or blood banks exist in Kenya, or in any county. The finder's answer is whatever the OSM
  import holds, and a county with nothing imported gets an empty list — which is an absence of data,
  not a statement that the county has no donation centre.
- **`amenity=blood_donation` is not a value OSM defines.** A query written against it returns the
  empty set while appearing to work, which is the failure the archived 404 on that tag's page
  documents. The `healthcare` key is the one that carries the donation vocabulary.
- **The two kinds are not interchangeable and the source does not rank them.** It states what each
  is for; the choice to default the finder to `blood_donation` is the repo's, made because the
  section's bullet is the question a donor asks.
- **Tagging is voluntary and uneven.** A facility that takes donations may be tagged as neither, so
  the finder's list is a floor rather than a census — the same caveat the `amenity` import carries.

---

## WHO larval source management manual — §MON-007's larviciding and protection reminders

Larviciding is a malaria intervention with an operational manual behind it, and §MON-007 asks for
its campaign notices. The manual supplies the two things a notice and a reminder need and cannot
invent: the re-treatment interval per larvicide class, and the source's own conditions on when
larviciding is worth doing at all.

**Publisher:** World Health Organization, Global Malaria Programme. **Published:** 2013.
**ISBN:** 978 92 4 150582 7. **Retrieved:** 2026-10-13.
**Record page:** `https://iris.who.int/handle/10665/85879`.

### Files

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| `lsm-manual.pdf` | 3961378 | `0c5573d971d6fe63` |
| `lsm-manual.txt` | 440308 | `2f64b103c0551634` |

The `.txt` is `pdftotext -layout` over the publisher's PDF. `-layout` matters for the larvicide
class tables, where the interval and the product share a row.

### What the source supports

- **Re-treatment intervals, by class.** Bacterial larvicides: "Frequency of re-treatment with
  bacterial larvicides can range from 1 to 4 weeks for Anopheles", with "typical re-treatment
  intervals with Bti … 7–10 days" and `Bs` formulations "up to 4-week re-treatment intervals".
  Surface films: "Re-treatment is needed weekly". Insect growth regulators (methoprene briquettes):
  "slowly release methoprene for up to four months". Organophosphates (temephos granules): "every
  1 to 3 months". `LARVICIDE_CLASSES` carries one interval per class, and
  `LARVICIDE_INTERVAL_FLOOR_DAYS` is the shortest of them.
- **Biting time.** "biting tends to occur between dusk and dawn (and especially during the early
  hours of the morning …)", and `An. gambiae s.l.` and `An. funestus` "peak biting occurs an hour
  before dawn". This is why the net reminder is anchored at dusk.
- **Larval development.** Larvae go from hatching to "metamorphosing into pupae after 5–10 days",
  which is the window habitat manipulation works in.
- **The supplement rule.** "larviciding measures should normally be used only as a supplement to
  the core interventions (ITNs or IRS); larviciding should never be seen as a substitute for ITNs
  or IRS in areas with significant malaria risk". Reproduced verbatim as `SUPPLEMENT_RULE` and
  appended to every published notice by the service.
- **The feasibility condition.** "larviciding will generally be most effective in areas where
  larval habitats are few, fixed and findable", and "larviciding is most likely to be
  cost-effective in urban areas … in rural settings, larviciding is not recommended unless there
  are particular circumstances limiting the larval habitats". Reproduced as `LSM_FEASIBILITY`.

### What the source does not support

- **It states no schedule for a household.** The intervals are for a county re-treating a habitat,
  not for a person clearing a container. The reminder's interval is derived from the larvicide
  table so it cannot be shorter than a county's own re-treatment, and that derivation is the
  repo's choice, not the manual's instruction.
- **It ranks no larvicide above another.** The manual discusses classes and conditions; the four
  in `LARVICIDE_CLASSES` are the classes it names, not a preference order, and the model does not
  imply one.
- **It states no dusk hour.** "Dusk" is a local astronomical event; `DUSK_HOUR = 18` is the repo's
  fixed approximation, recorded as such rather than presented as the source's figure.

## FAO Crop Calendar for Kenya — §MON-008's seasonal food availability

§MON-008's "Seasonal food availability" had a field name and a fixed list behind it. The FAO Crop
Calendar is the published source of Kenyan harvest windows, and it is machine-readable.

**Publisher:** FAO, Global Information and Early Warning System (GIEWS). **Source `lastUpdated`:**
26/02/2021. **Retrieved:** 2026-10-13.
**URL:** `https://api-cropcalendar.apps.fao.org/api/v1/countries/KE/cropCalendar`.

### Files

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| `crop-calendar-ke.json` | 286785 | `6e68bbebaca29c40` |

The JSON is the API's own response, saved unmodified: 283 records, one per (crop,
agro-ecological zone) pair, each carrying `sessions` with `early_harvest`/`late_harvest` as
`{month, day}` and an `all_year` flag. `SEASONAL_FOODS` is generated from it, not typed: a crop's
months are the union of its harvest months across all 22 zones.

### What the source supports

- **29 crops with a stated harvest month**, and **5 flagged `all_year: "yes"`** in at least one
  zone (`Canne à sucre`, `Manioc`, `Noix de cajou`, `Noix de coco`, `Riz`).
- **The union-across-zones reading is the only one the source admits.** There is no national
  harvest month in the data.

### What the source does not support

- **It states no national season.** The data is disaggregated by agro-ecological zone, so a month
  in `SEASONAL_FOODS` means "harvested this month somewhere in Kenya". That is the right
  granularity for a national app and the wrong one for county advice; the field is used to answer
  "what is in season", never "what is in season in Siaya".
- **It covers 30 crops and no others.** `Épinard` carries a record and **no harvest month in any
  zone**, so it is served nowhere. Avocado, mango, banana, amaranth (*terere*) and fish — all of
  which `NUTRITION_BY_AGE` names — **are absent from the data entirely**, and are therefore absent
  from the seasonal table rather than given invented months.
- **Its crop names are French.** The JSON is FAO's French-language rendering of the Kenyan crop
  list (`Fève, vert`, `Maïs, sucré`). `SEASONAL_FOODS` carries the source's own name beside the
  English label so the rendering can be checked; a translation asserted by position alone would be
  unverifiable.
- **It is not a nutrition source.** It says when a crop is harvested, not what a child of a given
  age should eat. The two lists in `NutritionGuidance` are kept apart for exactly this reason.

## FEWS NET Kenya seasonal calendar — the cross-check on the harvest windows

FEWS NET publishes Kenya's seasonal calendar — the long and short rains, their typical onset, and
the lean periods between harvests. It was consulted to check the FAO harvest months against an
independent source, and to confirm the two rainy seasons the vector-risk bands are read against.

**Publisher:** FEWS NET (USAID). **Edition:** 2024 (June and October releases). **Retrieved:**
2026-10-13.

### Files

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| `seasonal-calendar-202406.pdf` | 240846 | `f9fa5c9e234a85a9` |
| `seasonal-calendar-202410.png` | 1220424 | `ab6490218e3f6ed6` |

The PNG is the calendar graphic itself; the PDF is the release it appeared in. There is no text
extraction beside these two: the calendar is a figure, and the figure is the artefact.

### What the source supports

- **Two rainy seasons**, the long rains and the short rains, with the lean periods that follow
  each. This is the seasonal shape the §MON-007 rain bands sit inside.

### What the source does not support

- **It is not disaggregated by crop and carries no per-crop harvest month**, so it could not
  generate `SEASONAL_FOODS` and is not used to. It is archived as the cross-check, and the check
  it supports is the *seasonal shape*, not the crop table — the crop months rest on the FAO data
  alone, which is stated here so the citation is not read as broader than it is.

## Kenya IMAM guideline — §MON-008's therapeutic feeding vocabulary

There is **no OpenStreetMap tag** for a therapeutic feeding centre or a malnutrition treatment
site. That was established three ways: the `healthcare` key's 31 values include only
`healthcare=nutrition_counselling`, which is dietary counselling and not treatment; the `amenity`
key's feeding values are all animal feeding (`feeding_place` for livestock); and a live taginfo
search for `malnutrition` returns no structured keys. A place-based vocabulary therefore had no
source, while the national clinical guideline has one.

**Publisher:** Government of Kenya, Ministry of Health, Division of Nutrition and Dietetics.
**Published:** 2020. **Retrieved:** 2026-10-13.

### Files

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| `imam-guidelines-2020.pdf` | 4201070 | `52f9c3dcd0102349` |
| `imam-guidelines-2020.txt` | 461630 | `4faa0a3c8df9305d` |

The `.txt` is `pdftotext -layout` over the publisher's PDF, which keeps the abbreviation list and
the treatment-flow tables in reading order.

### What the source supports

- **The three programme types, as the guideline's own abbreviation list prints them:**
  `OTP: Out-patient Therapeutic Programme`, `SC: Stabilization Center`,
  `SFP: Supplementary Feeding Programme`. Body text gives the same vocabulary in full: "the
  out-patient setting known as Out-Patient Therapeutic care/programme (OTP)".
- **Who goes where.** "Individuals who present with MAM can be treated within a targeted
  supplementary feeding programme at the health facility (i.e., MCH clinic) or at an outreach
  center." Severe acute malnutrition without complications is treated at an OTP; with
  complications, or in an infant under six months, admission to an SC. `IMAM_PROGRAMMES` carries
  each definition so a parent can see which door is which.
- **That the programmes are not interchangeable**, which is why the definitions travel with every
  site rather than a per-site claim.
- **The MUAC admission cut-offs, which §REC-003 now reads.** Table 1.5, "MUAC cut-offs for children
  6 to 59 months": `MUAC < 11.5cm` is severe acute malnutrition, `11.5 to 12.4cm` moderate acute
  malnutrition, `12.5 to 13.4cm` at risk. The table's own footnote is "*Anthropometric criteria
  based on WHO Child Growth Standards (2006)" — the cut-offs are Kenya's, the reference population
  behind them is WHO's, which is why `classify_muac` and the WHO z-score are two fields and not one.
  Body text states the severe rule unconditionally: "Any child older than six months and a MUAC
  <11.5cm must be admitted to the nutrition programme for treatment of severe acute malnutrition."
  `afya.records.growth.MUAC_ALERTS` carries that rule in the words a caregiver is given, and the
  category is computed only at and above six months because the table's own scope is 6–59 and the
  guideline refers an infant below it to Section 3.
- **Section 3, the under-six-month protocol**, which is what a child below the MUAC table's floor
  is routed to instead: "Infants less than six months who are malnourished are always treated in an
  in-patient unit." Table 3.1 admits on weight-for-length or weight-for-age below −3 z-scores,
  bilateral pitting oedema, being too weak to suckle, or recent weight loss. This is why the arm
  z-score and the MUAC category have different age floors rather than one being extended to cover
  the other.
- **Annex 9, the developmental milestone checklist** (§REC-003's last bullet). Eight age bands and
  30 milestones, listed under ASSESS with a three-outcome CLASSIFY chart: **DELAY** is absence from
  the current group *and* absence from an earlier one, or a regression; **ALERT** is absence from the
  current group alone; **NORMAL** is every current-band milestone present. `MILESTONES` reproduces
  the bands and the milestone wording verbatim — the label is the sentence a caregiver is read — and
  `RecordsService.milestone_check` applies the three-way rule. Two properties of the annex are worth
  recording because they are easy to get wrong: the bands **meet at their endpoints** (0–2 and 2–4
  both name month 2), and the 0–2 month band lists **only two** milestones where every other band
  lists four, so a count of 32 is a miscount of the annex rather than of the extraction.

### What the source does not support

- **It is not a facility registry.** It states the programme types and the admission criteria; it
  does not list which facility runs which. `TherapeuticFeedingSite.programmes` is therefore the
  national vocabulary and not a claim about the site returned beside it — the registry records
  *that* a facility is a therapeutic feeding site and not which programme it runs, and inventing
  that per row would be the registry telling a parent something nobody filed.
- **It supplies no geographic data**, so the finder's distances come from §FND-001's registry, not
  from this source.
- **It is not a growth standard.** The MUAC cut-offs and Annex 9's checklist are Kenya's clinical
  rules; the LMS parameters behind the z-scores are WHO's. Neither substitutes for the other, and
  the annex states no threshold for *how far* behind a child may be — it classifies presence and
  absence only, so no severity grade is invented for a missing milestone.

## WHO/UNICEF/WFP/SC joint statement on community-based management of SAM

The joint statement is the origin of the community-based approach the IMAM guideline implements,
and it is archived because §MON-008's therapeutic feeding bullet is about finding treatment in the
community rather than at a hospital.

**Publishers:** WHO, UNICEF, WFP and Save the Children. **Published:** 2007. **Retrieved:**
2026-10-13.

### Files

| File | Bytes | SHA-256 (first 16) |
|---|---|---|
| `unicef-cmam-statement.pdf` | 277435 | `b90d834038878917` |
| `unicef-cmam-statement.txt` | 35016 | `0eacebb7fe4e855c` |

### What the source supports

- **The community-based approach itself:** "The community-based approach involves timely detection
  of severe acute malnutrition in the community and provision of treatment for those without
  medical complications with ready-to-use therapeutic foods or other nutrient-dense foods at
  home."

### What the source does not support

- **It supplies no vocabulary the code uses.** It writes "therapeutic feeding centre" only
  descriptively, and names no programme types — the programme vocabulary in `IMAM_PROGRAMMES` is
  the Kenyan guideline's, not this statement's. The statement is archived as the provenance of the
  community-based model and as a check that the guideline's three programmes are the national
  rendering of it, **not** as the source of any string served. Said plainly so the citation is not
  read as carrying more than it does.

## `android-screen-compatibility/` — §ACC-005's screen buckets

§ACC-005's Target is "Support for low-resolution screens" and the section states no dimension for
it. A bucket boundary invented here would be a figure this deployment made up and then had to live
with, so the two boundaries are Android's own published numbers.

| File | What it is | SHA-256 (first 16) |
|---|---|---|
| `supports-screens-element.html` | `<supports-screens>`: the `smallestWidth` figures — "a typical handset screen has a `smallestWidth` of 320dp, a 7-inch tablet has a `smallestWidth` of 600dp, and a 10-inch tablet has a `smallestWidth` of 720dp" | `325654dd14cd04ae` |
| `use-window-size-classes.html` | The window size class breakpoints, width and height separately (compact / medium / expanded, and the large and extra-large additions) | `700474ac616853fa` |
| `screendensities.html` | The density bucket table (ldpi–xxxhdpi) and the definition of dp | `7c7a1eff0331cb46` |

Retrieved 2026-10-14 from `developer.android.com`. Each `.html` has a `.txt` extraction beside it
(`supports-screens-element.txt` `376dca50a1704ce4`, `use-window-size-classes.txt` `657bba508a0682e7`,
`screendensities.txt` `7e1427892cd5da6e`) — HTML rather than PDF, so the extraction is a tag strip
rather than `pdftotext -layout`, and the quoted sentences were checked against it rather than
against the rendered page.

**What the source does and does not support.**

- It states **320dp** for a typical handset and **600dp** for a 7-inch tablet, and those are the two
  boundaries `SCREEN_BUCKETS` uses. It states **720dp** for a 10-inch tablet, which this table does
  **not** use: §ACC-005 names no tablet tier, and adding a third bucket would be a commitment the
  section does not make. Above 600dp the regular layout is served, which is what the page's own
  window-size-class guidance implies — a layout that fits a narrow window renders correctly in a
  wide one, and not the reverse.
- The page gives **no** minimum resolution in pixels, no physical size in inches for "low
  resolution", and no definition of what a low-resolution *screen* is beyond the `smallestWidth`
  figure. `smallest_width_dp` is therefore the only axis recorded, and no pixel dimension appears in
  the code.
- `smallestWidth` is the **shorter** of the two sides and is orientation-independent. That is the
  page's own property and the reason the bucket is keyed on it: a layout keyed on width would give a
  phone two columns in landscape and one in portrait.
- The window size class page's breakpoints are stated for **width and height separately** and it
  says explicitly that they "are not determined by physical device screen size" and can change
  during an app's lifetime (rotation, multitasking, folding). This code does **not** use them for
  layout selection — it uses the static `smallestWidth`, because the bucket has to be answerable
  server-side for a device the server is not running on, and a class that changes mid-session cannot
  be. The page is archived because it is the modern statement of the same axis and because it is
  where the "don't reason from physical hardware" caution comes from.
- The density table is archived for the **definition of dp** ("roughly equal to one pixel on a
  medium-density screen (160 dpi, or the 'baseline' density)") and for the ldpi bucket at ~120 dpi,
  which is what makes "low resolution" legible as a density claim as well as a size one. The code
  records no dpi and picks no density bucket: §ACC-001's targets are already in dp, which is the
  unit that makes density irrelevant.
- The Android client reads `Configuration.smallestScreenWidthDp` and selects 56dp or 64dp from it.
  **The client's own number is not verified by anything in this repo** — no Android build runs in CI
  — so the client change is a rendering of the served table and not an independently checked claim.
  The server-side table is what the audit row cites.

## WHO adolescent health — §17.6's "Extra protections for adolescent reproductive health data"

The World Health Organization's adolescent health topic page, retrieved 2026-10-15 from
`https://www.who.int/health-topics/adolescent-health`. Archived as
`who-adolescent-health/who-adolescent-health.html` and a text extraction beside it.

	sha256  2e2acabe1faadb3fa7a45fdd07879335d5a7395c7a980c94fa8a9b87b1533677  who-adolescent-health.html
	sha256  0e99fb3b4d436127567e24bba5554319527158292369ee6c64e1f3dfdd9e7cf3  who-adolescent-health.txt

Used by `afya.records.service.ADOLESCENT_YEARS` and `afya.women.content.is_reproductive_health_data`,
which carry §17.6's last line.

**What the source supports.**

- The definition of the phase the section's word names, verbatim: *"Adolescence is the phase of life
  between childhood and adulthood, from ages 10 to 19."* That is the whole basis for the band's lower
  bound of 10. The upper bound is 17 rather than the source's 19 because it is intersected with this
  tree's `MAJORITY_YEARS = 18` — above 18 `owns` already refuses a guardian, so the 18–19 half is
  unreachable and a bound carrying it would name no member. The intersection is asserted in code
  (`ADOLESCENT_YEARS[1] < MAJORITY_YEARS`), so the two cannot drift.
- The mechanism, in the page's own list of what keeps adolescents from care: *"Restrictive laws and
  policies, parental or partner control, limited knowledge, distance, cost, lack of confidentiality,
  and provider bias can all restrict adolescents from getting the care they need to grow and develop
  in good health."* "Parental or partner control" and "lack of confidentiality" are the two the code
  acts on: the protection with content is the one that withholds an adolescent's reproductive health
  records from the guardian and leaves them with the person they are about.

**What the source does not support, and what is therefore not claimed.**

- It gives **no** list of what "reproductive health data" is, and **no** rule about who may read a
  record. `REPRODUCTIVE_TERMS` is therefore derived from the WHO family-planning method table and the
  SRH referral services this repo already archives at `who-reproductive-health/` — so the classifier
  reads the same method vocabulary the contraception feature records against, rather than a second
  list that could drift from it. The spec names no vocabulary either; §17.6's line is the whole of it.
- It states no **legal** rule for Kenya. The Kenyan position is the Data Protection Act 2019's
  s.33 (a child's data) and the age of majority, which this tree already carries as `MAJORITY_YEARS`;
  the page is cited for the *phase* and the *barrier*, not for a statutory threshold. The Kenyan
  statute is **not archived in this repo** — see the Kenya Data Protection Act section below for the
  four retrieval attempts that failed — so no citation here rests on it.
- It gives **no** age-specific consent rule for reproductive health services, and the code invents
  none. The protection implemented is a **read** restriction inside the app, not a claim about
  whether a Kenyan adolescent may consent to care without a guardian — that is a clinical and legal
  question this repo does not answer and does not need to, because withholding a record from a
  guardian in the wallet is not the same act as providing a service without consent.
