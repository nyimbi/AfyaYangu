"""§REC-003's growth assessment, computed from the WHO standards rather than read off a band.

`RecordsService.growth_flag` compares a measurement against a hand-written table of low/high weights
and median heights at six ages. That answers "underweight" with no magnitude, at six ages out of
sixty, from numbers traceable to nothing. §REC-003 asks for "percentile charts" and "undernutrition
alerts", and both need a z-score: how many standard deviations from the median of a reference
population the child is, at their exact age.

The z-score here is exact, not interpolated. WHO publishes the LMS parameters for every month of
age, so the Box-Cox transform below evaluates the standard at the child's own age. An earlier
version of this interpolated between medians, which is wrong in the direction that matters: weight
is right-skewed, and a normal approximation understates the deficit of a child at the low end.

`afya.records.growth_standards` holds the parameters and `sources/INDEX.md` records where they came
from. This module holds the arithmetic and the classification, which is the part that can be wrong.
"""
import math

from afya.records.growth_standards import (
	ARM_CIRCUMFERENCE_FOR_AGE, HEAD_CIRCUMFERENCE_FOR_AGE, HEIGHT_FOR_AGE, LENGTH_FOR_AGE, SEXES,
	STANDING_FROM_MONTHS, WEIGHT_FOR_AGE,
)

SEVERE_Z = -3.0
"""WHO's cut-off for severe wasting/stunting. §REC-003's "undernutrition alerts" hang on this."""

MODERATE_Z = -2.0
"""WHO's cut-off for moderate undernutrition. Between this and `SEVERE_Z` the child needs feeding
support; below it they need referral, which is why the two are separate verdicts and not one."""

MAX_AGE_MONTHS = 60
"""The standards cover 0-60 months. Past it the WHO reference is the 5-19 year growth reference,
which is a different publication this deployment does not hold — so an older child is refused here
rather than measured against an infant standard that would call them enormous."""


def lms(table: dict[str, tuple[tuple[int, float, float, float], ...]],
        sex: str, age_months: int) -> tuple[float, float, float]:
	"""The (L, M, S) WHO tabulates for this sex at this month, or an assertion.

	A missing age is refused rather than interpolated. The tables are complete by month over their
	range, so a miss means the caller asked for an age outside the standard — and interpolating
	across the 24-month boundary of the two height tables would mix recumbent length with standing
	height, which differ by about 0.7 cm.
	"""
	assert sex in SEXES, f'WHO tabulates two sexes, not {sex!r}'
	assert 0 <= age_months <= MAX_AGE_MONTHS, f'{age_months} months is outside 0-{MAX_AGE_MONTHS}'
	rows = table[sex]
	by_month = {row[0]: row for row in rows}
	assert age_months in by_month, (
		f'{age_months} months is not in this table, which covers '
		f'{rows[0][0]}-{rows[-1][0]} — the standard is not defined here'
	)
	_, l, m, s = by_month[age_months]
	return (l, m, s)


def zscore(value: float, l: float, m: float, s: float) -> float:
	"""WHO's Box-Cox z-score. `L` is the power that removes the skew.

	For length and height WHO's `L` is exactly 1, so the expression reduces to `(x - M) / (M * S)`,
	the ordinary standard score. For weight it is not 1, and using the normal form there is the
	error this function exists to avoid.
	"""
	assert value > 0, 'a measurement is positive'
	assert m > 0 and s > 0, 'the standard has a positive median and spread'
	if abs(l) < 1e-9:
		return math.log(value / m) / s
	return ((value / m) ** l - 1) / (l * s)


def weight_z(sex: str, age_months: int, weight_kg: float) -> float:
	"""Weight-for-age z-score. §REC-003's "weight" against the WHO standard."""
	l, m, s = lms(WEIGHT_FOR_AGE, sex, age_months)
	return zscore(weight_kg, l, m, s)


def height_z(sex: str, age_months: int, height_cm: float) -> float:
	"""Height-for-age z-score, from whichever of the two tables covers this age.

	WHO splits the tables at 24 months because below it the child is measured lying down and at or
	above it standing. Serving the wrong one is not a rounding error: it is the wrong measurement.
	"""
	table = LENGTH_FOR_AGE if age_months < STANDING_FROM_MONTHS else HEIGHT_FOR_AGE
	l, m, s = lms(table, sex, age_months)
	return zscore(height_cm, l, m, s)


def head_circumference_z(sex: str, age_months: int, head_cm: float) -> float:
	"""Head circumference-for-age z-score, 0-60 months.

	The one measurement a growth tracker takes in the first year, and the one §REC-003's row was
	written against: `GrowthRecord` carried it and nothing read it. Head circumference is tabulated
	with `L == 1` on every row, so this reduces to the ordinary standard score — but it is computed
	through `zscore` rather than by hand so that a change to the standard reaches it the same way it
	reaches the other three.
	"""
	l, m, s = lms(HEAD_CIRCUMFERENCE_FOR_AGE, sex, age_months)
	return zscore(head_cm, l, m, s)


def muac_z(sex: str, age_months: int, muac_cm: float) -> float:
	"""Arm circumference-for-age z-score, 3-60 months.

	WHO tabulates no arm-circumference standard below three months, so `lms` refuses a younger child
	rather than interpolating a value the standard does not define. That refusal is the right answer
	and not a limitation: MUAC is not a valid screening measurement in early infancy, and Kenya's own
	IMAM guideline routes an infant under six months to its inpatient section on weight-for-length
	and clinical signs instead of to a MUAC cut-off.
	"""
	l, m, s = lms(ARM_CIRCUMFERENCE_FOR_AGE, sex, age_months)
	return zscore(muac_cm, l, m, s)


def weight_reference(sex: str) -> list[dict[str, float]]:
	"""The lines §REC-003's chart draws: month, median and the -3/-2/+2 SD curves, in kg.

	Computed from the same LMS parameters as the child's own point, so the line the child is plotted
	against and the z-score reported for them cannot disagree — which is what happens when a chart
	uses published rounded SD columns and the verdict uses the transform.
	"""
	assert sex in SEXES, f'WHO tabulates two sexes, not {sex!r}'
	out: list[dict[str, float]] = []
	for month, l, m, s in WEIGHT_FOR_AGE[sex]:
		out.append({
			'month': month, 'median': m,
			'minus_3': _value_at(-3.0, l, m, s), 'minus_2': _value_at(-2.0, l, m, s),
			'plus_2': _value_at(2.0, l, m, s),
		})
	return out


def height_reference(sex: str) -> list[dict[str, float]]:
	"""The height chart's lines, in cm, over 0-60 months from the two tables joined at 24.

	WHO's two tables both carry a 24-month row — the length-for-age table ends there and the
	height-for-age table begins there — because the two describe the same age measured two ways, and
	they do not agree: recumbent length reads about 0.7 cm longer than standing height. Concatenating
	them puts two rows on month 24, so a chart drawn from the result has a doubled month at the seam
	and two different medians for one age. The standing table wins at 24, which is the measurement a
	child of that age gets, and the boundary is stated here rather than left to the order of `+`.
	"""
	assert sex in SEXES, f'WHO tabulates two sexes, not {sex!r}'
	joined = ([r for r in LENGTH_FOR_AGE[sex] if r[0] < STANDING_FROM_MONTHS]
	          + list(HEIGHT_FOR_AGE[sex]))
	assert len({r[0] for r in joined}) == len(joined), 'the two WHO tables overlap at 24 months'
	out: list[dict[str, float]] = []
	for month, l, m, s in joined:
		out.append({
			'month': month, 'median': m,
			'minus_3': _value_at(-3.0, l, m, s), 'minus_2': _value_at(-2.0, l, m, s),
			'plus_2': _value_at(2.0, l, m, s),
		})
	return out


def _value_at(z: float, l: float, m: float, s: float) -> float:
	"""The measurement at a given z — the inverse of `zscore`, for drawing the reference line.

	`zscore` is the WHO transform; this is its inverse, `M * (1 + L*S*z) ** (1/L)`, so a chart line
	and a plotted point are the same function read in two directions. `L == 0` is the log-normal
	case and takes the exponential form.
	"""
	if abs(l) < 1e-9:
		return m * math.exp(s * z)
	return m * (1 + l * s * z) ** (1 / l)


MUAC_SAM_CM = 11.5
"""Kenya's IMAM cut-off for severe acute malnutrition by MUAC, for a child 6-59 months.

Below this the guideline is unconditional: "Any child older than six months and a MUAC <11.5cm must
be admitted to the nutrition programme for treatment of severe acute malnutrition". It is a
centimetre, not a z-score, because a tape measure is what a community health volunteer has.
"""

MUAC_MAM_CM = 12.5
"""The upper bound of the moderate band. `11.5` to `<12.5` is MAM; the guideline prints the band as
`11.5 to 12.4`, which is the same interval written to the tape's own resolution."""

MUAC_AT_RISK_CM = 13.5
"""The upper bound of the at-risk band, `12.5-13.4` cm. Above it the guideline states no category."""

MUAC_MIN_AGE_MONTHS = 6
"""The guideline's own floor for a MUAC admission decision: it applies to "children 6 to 59 months",
and an infant below that is referred to the inpatient section instead — `Table 3.1` admits them on
weight-for-length and clinical signs. The WHO arm-circumference standard starts at 3 months, so
between 3 and 6 months a z-score exists while an admission category does not, and the two are
reported separately rather than one standing in for the other.
"""


def classify_muac(muac_cm: float) -> str:
	"""Kenya's IMAM category for a MUAC, in the guideline's own four words.

	This is deliberately *not* `classify`. WHO's z-score bands and Kenya's MUAC cut-offs are two
	different instruments answering two different questions: the z-score says how far from the
	reference median the child is, and the MUAC cut-off says which programme the child is admitted
	to. A child can sit at -2.2 z and above 12.5 cm, or at -1.8 z and below 11.5 cm, and a service
	that collapsed the two would either admit a child the guideline does not or miss one it does.
	The category is what a health worker acts on, so it is stated in the guideline's vocabulary
	(`sam`, `mam`, `at_risk`, `normal`) rather than in WHO's.
	"""
	assert muac_cm > 0, 'a MUAC is positive'
	if muac_cm < MUAC_SAM_CM:
		return 'sam'
	if muac_cm < MUAC_MAM_CM:
		return 'mam'
	if muac_cm < MUAC_AT_RISK_CM:
		return 'at_risk'
	return 'normal'


MUAC_ALERTS: dict[str, str] = {
	'sam': (
		'This arm measurement is below the level at which a child needs treatment for severe acute '
		'malnutrition. Take the child to a health facility now — do not wait for the next visit. A '
		'health worker will check for swelling of both feet and start treatment.'
	),
	'mam': (
		'This arm measurement is in the range that needs nutrition support. Take the child to a '
		'health facility for an assessment and a feeding programme.'
	),
	'at_risk': (
		'This arm measurement is on the low side. Ask a health worker about feeding and bring the '
		'child back for another measurement.'
	),
}
"""The guideline's admission rule, in the words a parent is given.

`sams`, `mam` and `at_risk` carry an alert because the IMAM guideline acts on each of them: the
severe band admits unconditionally ("Any child older than six months and a MUAC <11.5cm must be
admitted"), and the moderate and at-risk bands route to support and to counselling. `normal` is
absent deliberately — a normal reading is not an alert, and a dictionary with an entry for it would
be a lookup that returns a message where the honest answer is none.
"""


def classify(z: float) -> str:
	"""WHO's z-score classification, as the four words §REC-003's alert can act on.

	The two-sided case is deliberate: a child at +3 is not "normal", they need a referral for the
	opposite reason, and a classifier that only looks downward reports a severely overweight child
	as healthy.
	"""
	if z < SEVERE_Z:
		return 'severe'
	if z < MODERATE_Z:
		return 'moderate'
	if z > 3.0:
		return 'above'
	return 'normal'
