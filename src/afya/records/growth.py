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
	HEIGHT_FOR_AGE, LENGTH_FOR_AGE, SEXES, STANDING_FROM_MONTHS, WEIGHT_FOR_AGE,
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
