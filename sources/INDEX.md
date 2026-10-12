# Sources

External literature and data that code in this repo computes from. A citation that points at a URL
nobody archived is a citation that rots, so every load-bearing source is stored here beside the work
that uses it, with its retrieval URL, date, and checksum.

| Source | Used by | Archived |
|---|---|---|
| WHO Child Growth Standards, LMS tables | `afya.records.growth`, `afya.records.growth_standards` | `who-child-growth-standards/` |

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
the LMS columns.

| File | Indicator | Sex | Ages | SHA-256 (first 16) |
|---|---|---|---|---|
| `wfa_boys.pdf` | Weight-for-age | Boys | 0–60 months | `ca6437e29134dee2` |
| `wfa_girls.pdf` | Weight-for-age | Girls | 0–60 months | `2ecadc34b59b3309` |
| `lhfa_boys_0_2.pdf` | Length-for-age | Boys | 0–24 months | `a3cee0ae2f50a7bc` |
| `lhfa_girls_0_2.pdf` | Length-for-age | Girls | 0–24 months | `a5895dcfacfc6de9` |
| `hfa_boys_2_5.pdf` | Height-for-age | Boys | 24–60 months | `a8b1093776be24ea` |
| `hfa_girls_2_5.pdf` | Height-for-age | Girls | 24–60 months | `c6ff83bc671ac6f0` |

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
