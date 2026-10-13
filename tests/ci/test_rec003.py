"""§REC-003's growth and development tracker, tested against its own sources.

The section's two missing rows were both the same shape of defect: a field or a table that exists
and that nothing reads. `GrowthRecord` carried `head_circumference_cm` and `muac_mm` from the day
it was written and no code path consulted either, and no milestone table existed at all. So the
tests here are mostly about *reading*: that a measurement reaches a standard, that the standard
reaches a classification, and that the classification reaches the sentence a caregiver is given.

The sources are archived and the tests recompute from them rather than from the constants, which is
the only way the constants can be wrong without the test agreeing:

* `sources/who-child-growth-standards/hcfa_*_zscores.txt` and `acfa_*_zscores.txt` — the WHO LMS
  parameters. WHO prints the measurement at -3, -2, -1, 0, +1, +2 and +3 SD on the same row, so the
  printed columns are a check on the extracted L, M and S that a transcription error cannot pass.
* `sources/kenya-imam-guidelines/imam-guidelines-2020.txt` — Table 1.5's MUAC cut-offs and Annex 9's
  milestone checklist, both read out of the archived text rather than retyped.
"""
import pathlib
import re

import httpx
import pytest

from afya.records.growth import (
	MUAC_ALERTS, MUAC_AT_RISK_CM, MUAC_MAM_CM, MUAC_MIN_AGE_MONTHS, MUAC_SAM_CM,
	classify_muac, head_circumference_z, muac_z,
)
from afya.records.growth_standards import ARM_CIRCUMFERENCE_FOR_AGE, HEAD_CIRCUMFERENCE_FOR_AGE, SEXES
from afya.records.service import MILESTONE_GUIDANCE, MILESTONES, RecordsService
from afya.records.views import GrowthRecord, MilestoneCheck, WalletMember

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCES = ROOT / 'sources'


def _client() -> 'httpx.AsyncClient':
	import httpx

	from afya.service import build_services, create_app
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(build_services())),
	                         base_url='http://t')


async def _family(c: 'httpx.AsyncClient') -> tuple[dict[str, str], str]:
	"""A citizen token and a child in their wallet — the shape §17.6's routes are guarded for.

	`citizen_identified` is deliberately absent from `ISSUABLE_ROLES`: the app flow issues staff
	roles, and a citizen token comes from `/auth/anonymous`, which is the only route that mints one.
	"""
	token = (await c.post('/auth/anonymous', json={'subject_ref': 'GUARD1'})).json()['token']
	head = {'Authorization': f'Bearer {token}'}
	for body in ({'member_ref': 'GUARD1', 'dob_iso': '1990-01-01'},
	             {'member_ref': 'KID', 'dob_iso': '2025-10-01', 'guardian_ref': 'GUARD1'}):
		res = await c.post('/records/member', json=body, headers=head)
		assert res.status_code == 200, res.text
	return head, 'KID'


# ---------------------------------------------------------------- the WHO tables

def _lms_rows(name: str) -> list[tuple[int, float, float, float, list[float]]]:
	"""(month, L, M, S, printed SD columns) for every row of an archived WHO table."""
	row = re.compile(r'^\s*\d+:\s*\d+\s+\d+\s')
	num = re.compile(r'-?\d+\.?\d*')
	out = []
	for line in (SOURCES / 'who-child-growth-standards' / name).read_text().splitlines():
		if not row.match(line):
			continue
		toks = num.findall(line)
		out.append((int(float(toks[2])), float(toks[3]), float(toks[4]), float(toks[5]),
		            [float(t) for t in toks[-7:]]))
	return out


def _value_at(z: float, l: float, m: float, s: float) -> float:
	import math
	if abs(l) < 1e-9:
		return m * math.exp(s * z)
	return m * (1 + l * s * z) ** (1 / l)


@pytest.mark.parametrize('name,table', (
	('hcfa_boys_0_5_zscores.txt', HEAD_CIRCUMFERENCE_FOR_AGE['boy']),
	('hcfa_girls_0_5_zscores.txt', HEAD_CIRCUMFERENCE_FOR_AGE['girl']),
	('acfa_boys_3_5_zscores.txt', ARM_CIRCUMFERENCE_FOR_AGE['boy']),
	('acfa_girls_3_5_zscores.txt', ARM_CIRCUMFERENCE_FOR_AGE['girl']),
))
def test_the_table_is_the_source_row_for_row(name: str, table: tuple[tuple[int, float, float, float], ...]) -> None:
	"""Every LMS row is the archived table's row, checked against the columns WHO prints beside it.

	Comparing the extracted numbers to the extracted numbers would agree whatever they say. The
	printed -3/-2/-1/0/+1/+2/+3 SD columns are on the same line in the PDF, so recomputing them from
	L, M and S is an independent check: a mis-read digit moves a column by more than its rounding.
	"""
	source = _lms_rows(name)
	assert [r[0] for r in source] == [r[0] for r in table], 'the months drifted'
	for (month, l, m, s, printed), (got_month, gl, gm, gs) in zip(source, table):
		assert got_month == month, f'month {month} moved'
		assert (gl, gm, gs) == (l, m, s), f'month {month}: extracted {(l, m, s)}, module holds {(gl, gm, gs)}'
		for z, shown in zip((-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0), printed):
			assert abs(_value_at(z, l, m, s) - shown) <= 0.05, (
				f'{name} month {month} at z={z:+}: WHO prints {shown}, L/M/S gives '
				f'{_value_at(z, l, m, s):.4f} — the row is wrong, not the rounding'
			)


def test_head_circumference_covers_the_first_year_and_arm_does_not() -> None:
	"""The two coverage differences, which are why one can be refused and the other cannot.

	Head circumference is the measurement a growth tracker takes in the first year, and WHO
	tabulates it from birth. Arm circumference starts at three months, so a MUAC under three months
	is a question the standard does not answer — and the code must refuse it rather than interpolate
	a value no table defines.
	"""
	for sex in SEXES:
		assert [r[0] for r in HEAD_CIRCUMFERENCE_FOR_AGE[sex]] == list(range(0, 61))
		assert [r[0] for r in ARM_CIRCUMFERENCE_FOR_AGE[sex]] == list(range(3, 61))
		with pytest.raises(AssertionError, match='not in this table'):
			muac_z(sex, 2, 13.0)


def test_head_circumference_is_normal_and_arm_is_not() -> None:
	"""`L == 1` on every head row and never on an arm row — and the two score differently because of it.

	The table half says the parameters differ; the arithmetic half says the *code* uses them. Using
	the normal form on arm circumference is the error the Box-Cox transform exists to avoid, and it
	is invisible at the median, so the check is at the low end where the screening decision is made.
	"""
	assert {r[1] for r in HEAD_CIRCUMFERENCE_FOR_AGE['boy']} == {1.0}
	assert {r[1] for r in HEAD_CIRCUMFERENCE_FOR_AGE['girl']} == {1.0}
	assert all(r[1] != 1.0 for r in ARM_CIRCUMFERENCE_FOR_AGE['boy'])
	assert all(r[1] != 1.0 for r in ARM_CIRCUMFERENCE_FOR_AGE['girl'])

	# 11 cm at 12 months: the arm z-score is the Box-Cox value, not the normal one. The two differ
	# by more than a hundredth here, which is the margin a classification boundary sits on.
	import math
	l, m, s = {r[0]: r for r in ARM_CIRCUMFERENCE_FOR_AGE['boy']}[12][1:]
	boxcox = ((11.0 / m) ** l - 1) / (l * s)
	normal = (11.0 - m) / (m * s)
	assert abs(boxcox - normal) > 0.01, 'the two forms agree here, so this checks nothing'
	assert abs(muac_z('boy', 12, 11.0) - boxcox) < 1e-9, 'muac_z is not using the Box-Cox form'
	assert abs(muac_z('boy', 12, 11.0) - normal) > 0.01, 'muac_z is using the normal form'
	assert math.isclose(head_circumference_z('boy', 12, 45.0), (45.0 - 46.0661) / (46.0661 * 0.02789), abs_tol=1e-9)


def test_the_median_measurement_scores_zero() -> None:
	"""A child at the tabulated median is at z = 0 — the one value the transform must hit exactly."""
	for sex in SEXES:
		for month, _l, m, _s in HEAD_CIRCUMFERENCE_FOR_AGE[sex][::7]:
			assert abs(head_circumference_z(sex, month, m)) < 1e-9
		for month, _l, m, _s in ARM_CIRCUMFERENCE_FOR_AGE[sex][::7]:
			assert abs(muac_z(sex, month, m)) < 1e-9


def test_a_smaller_measurement_scores_lower() -> None:
	"""Monotonic in the measurement, so the z-score orders children the way the tape does."""
	for sex in SEXES:
		assert head_circumference_z(sex, 6, 43.3) < head_circumference_z(sex, 6, 45.0)
		assert muac_z(sex, 12, 12.0) < muac_z(sex, 12, 15.0)


# ---------------------------------------------------------------- the IMAM cut-offs

def _imam_muac_row() -> str:
	"""The 6-59 month MUAC row of Table 1.5, read out of the archived guideline.

	Table 1.5 is a layout-preserving table: the row that carries the three bands is one physical
	line, `MUAC  <11.5cm  11.5 to 12.4cm  12.5-13.4cm`. Matching on that line rather than on the
	section heading is what makes the parse land in the body — the heading "Children 6 to 59 months"
	occurs three times in the document, twice in the contents.
	"""
	text = (SOURCES / 'kenya-imam-guidelines' / 'imam-guidelines-2020.txt').read_text()
	rows = [m.group(0) for m in re.finditer(r'^MUAC\s+<\d+\.\d+cm.*$', text, re.M)]
	assert rows, 'Table 1.5\'s MUAC row is not in the archived guideline'
	return rows[0]


def test_the_cut_offs_are_the_guidelines_own_numbers() -> None:
	"""The four bands are Table 1.5's, parsed from the source rather than retyped here.

	The guideline prints the severe band as `<11.5cm`, the moderate as `11.5 to 12.4cm` and the
	at-risk band as `12.5-13.4cm`. Reading those three out of the archived text and comparing to the
	module's constants is the check that the numbers did not drift — and it is the reason the module
	states `12.5` rather than `12.4`, since `11.5 to 12.4` and `12.5-13.4` are adjacent intervals
	written to the tape's own resolution.
	"""
	row = _imam_muac_row()
	assert f'<{MUAC_SAM_CM}cm' in row, f'the severe cut-off is not in the source row: {row!r}'
	assert f'{MUAC_SAM_CM} to {MUAC_MAM_CM - 0.1:.1f}cm' in row, 'the moderate band drifted'
	assert f'{MUAC_MAM_CM}-{MUAC_AT_RISK_CM - 0.1:.1f}cm' in row, 'the at-risk band drifted'


def test_the_bands_are_the_guidelines_and_meet_at_their_edges() -> None:
	"""Every boundary, on both sides, so a band cannot be off by a tenth in either direction."""
	assert classify_muac(11.4) == 'sam'
	assert classify_muac(MUAC_SAM_CM) == 'mam'
	assert classify_muac(12.4) == 'mam'
	assert classify_muac(MUAC_MAM_CM) == 'at_risk'
	assert classify_muac(13.4) == 'at_risk'
	assert classify_muac(MUAC_AT_RISK_CM) == 'normal'


def test_every_acting_band_carries_an_alert_and_normal_does_not() -> None:
	"""The guideline acts on three of the four categories; the fourth is not an alert.

	`normal` having no entry is the point: a lookup that returned a message for a healthy child
	would turn the absence of a finding into a finding.
	"""
	assert set(MUAC_ALERTS) == {'sam', 'mam', 'at_risk'}
	assert 'normal' not in MUAC_ALERTS
	assert all(MUAC_ALERTS[c].strip() for c in MUAC_ALERTS)


def test_the_severe_alert_says_what_the_guideline_says() -> None:
	"""The severe band's rule is unconditional in the source and the message must not soften it."""
	severe = MUAC_ALERTS['sam'].lower()
	assert 'health facility' in severe, 'the alert names no place to go'
	assert 'now' in severe, 'the guideline says "must be admitted"; the alert hedges'
	assert 'wait' in severe, 'the alert does not name the thing it is telling the parent not to do'


# ---------------------------------------------------------------- the assessment

def _svc() -> RecordsService:
	"""A service with one enrolled member. `_members` is the registry the routes populate."""
	svc = RecordsService()
	svc._members['CH1'] = WalletMember(member_ref='CH1', dob_iso='2025-10-01')
	return svc


def test_the_recorded_measurements_reach_the_assessment() -> None:
	"""The defect §REC-003's row names: two fields recorded and read by nothing.

	A record carrying a head circumference and a MUAC now produces a z-score and a category for
	each, so the fields are no longer write-only.
	"""
	svc = _svc()
	report = svc.assess_growth(GrowthRecord(
		member_ref='CH1', age_months=12, weight_kg=9.5, height_cm=74.5, sex='boy',
		head_circumference_cm=46.0, muac_mm=125.0,
	))
	assert report.head_circumference_z is not None
	assert report.head_circumference_status is not None
	assert report.muac_z is not None
	assert report.muac_category == 'at_risk'
	assert report.muac_alert == MUAC_ALERTS['at_risk']


def test_an_unmeasured_child_is_not_reported_as_average() -> None:
	"""Absent stays absent. A `None` defaulted to a z-score of 0 would read as exactly average.

	This is the one direction a screening field may never fail in: "not measured" and "measured and
	fine" are different answers, and only one of them is safe to give.
	"""
	svc = _svc()
	report = svc.assess_growth(GrowthRecord(
		member_ref='CH1', age_months=12, weight_kg=9.5, height_cm=74.5, sex='boy'))
	assert report.head_circumference_z is None
	assert report.head_circumference_status is None
	assert report.muac_z is None
	assert report.muac_category is None
	assert report.muac_alert is None


def test_a_muac_below_six_months_has_a_z_score_and_no_category() -> None:
	"""Between three and six months the standard answers and the admission rule does not.

	WHO tabulates arm circumference from three months; the IMAM guideline's MUAC admission applies
	to "children 6 to 59 months" and sends an infant below that to its inpatient section on
	weight-for-length and clinical signs. Collapsing the two would either withhold a z-score that
	exists or assert an admission category the guideline does not give.
	"""
	svc = _svc()
	report = svc.assess_growth(GrowthRecord(
		member_ref='CH1', age_months=4, weight_kg=6.5, height_cm=62.0, sex='girl', muac_mm=110.0))
	assert report.muac_z is not None, 'the WHO standard covers 3 months and up'
	assert report.muac_category is None, 'the IMAM admission rule starts at six months'
	assert report.muac_alert is None
	assert MUAC_MIN_AGE_MONTHS == 6


# ---------------------------------------------------------------- milestones

def _annex9_items() -> dict[str, list[str]]:
	"""Annex 9's checklist, parsed from the archived guideline's own text.

	The Annex prints each band as a heading followed by its bullets, so the parse is on that shape.
	Reading it back is what makes the module's table checkable: the guideline is the authority and a
	transcription that dropped a bullet would otherwise be invisible.
	"""
	text = (SOURCES / 'kenya-imam-guidelines' / 'imam-guidelines-2020.txt').read_text()
	# Annex 9's title appears in the contents and again at the Annex itself; the body is the last.
	annex = text[text.rindex('Annex 9 Developmental Milestones'):]
	annex = annex.split('Annex 10:', 1)[0]
	bands: dict[str, list[str]] = {}
	current = ''
	# Annex 9 is printed as a two-column chart. The ASSESS column — the headings and the milestones —
	# sits in the left 62 characters, and the CLASSIFY column that explains it starts beyond that.
	# Cutting on the column is what keeps a bullet's own text: on a line where both columns carry
	# something, the right column's sentence runs straight into the bullet's, and a regex on the gap
	# cannot tell them apart because the gap is one space at the seam.
	ASSESS_COLUMNS = 62
	heading = re.compile(r'^(\d+ ?- ?\d+ MONTHS|\d+ MONTHS AND OLDER)$')
	for raw in annex.splitlines():
		line = raw[:ASSESS_COLUMNS].strip()
		found = heading.match(line)
		if found:
			current = found.group(1)
			bands[current] = []
			continue
		item = re.match(r'^[•·]\s*(.+?)\s*$', line)
		if item and current and not item.group(1).startswith('Absence'):
			bands[current].append(item.group(1))
	return bands


def test_the_milestone_table_is_annex_nines_checklist() -> None:
	"""Every band and every bullet, matched against the archived Annex rather than retyped."""
	annex = _annex9_items()
	assert len(annex) == 8, f'Annex 9 prints eight bands, the parse found {len(annex)}: {list(annex)}'
	module_labels = [label for label, _lo, _hi, _items in MILESTONES]
	assert len(module_labels) == 8
	# The Annex writes two bands with a spaced dash — "12 - 18 MONTHS", "18 - 24 MONTHS" — and the
	# module writes them closed up. Compare on the months rather than the punctuation, so the check
	# is on the band and not on its typesetting.
	normalise = lambda s: re.sub(r'\s*-\s*', '-', s.strip().upper())  # noqa: E731
	for (label, _lo, _hi, items), (annex_label, annex_items) in zip(MILESTONES, annex.items()):
		assert normalise(label) == normalise(annex_label), f'{label} is not {annex_label}'
		assert [t for _s, t in items] == annex_items, f'{label}: the milestones drifted from Annex 9'


def test_the_milestone_labels_are_the_guidelines_own_wording() -> None:
	"""The label is the sentence a caregiver is read, so it is the guideline's, not a paraphrase."""
	labels = [t for _l, _a, _b, items in MILESTONES for _s, t in items]
	# Thirty, not thirty-two: Annex 9's 0-2 month band lists two milestones where every other band
	# lists four, which is what the source says and what the parse above confirms.
	assert len(labels) == 30, f'Annex 9 lists 30 milestones, the table has {len(labels)}'
	assert 'Social smile (baby smiles back)' in labels
	assert 'Says 2-3 words' in labels
	assert 'Interested in playing with other children' in labels
	# The slugs are this deployment's handles and must not be the labels.
	slugs = [s for _l, _a, _b, items in MILESTONES for s, _t in items]
	assert all(' ' not in s for s in slugs), 'a slug has a space in it'
	assert not set(slugs) & set(labels), 'a slug is being used as a label'


def test_the_bands_cover_every_month_of_the_standard_with_no_gap() -> None:
	"""0-60 months, and every month inside a band.

	The bands meet at their endpoints — Annex 9 prints "0-2 MONTHS" and "2-4 MONTHS" — so month 2 is
	in two bands and the later one is the operative screen. A month in no band at all would be a
	child the checklist refuses, which is why the coverage is asserted rather than assumed.
	"""
	for month in range(0, 61):
		covering = [label for label, lo, hi, _i in MILESTONES if lo <= month <= hi]
		assert covering, f'month {month} is in no band'


def test_a_child_with_every_current_milestone_is_normal() -> None:
	svc = _svc()
	items = [s for s, _t in MILESTONES[2][3]]
	report = svc.milestone_check(MilestoneCheck(
		member_ref='CH1', age_months=5, present=items))
	assert report.status == 'normal'
	assert report.band == '4-6 months'
	assert report.missing == []
	assert report.guidance == MILESTONE_GUIDANCE['normal']


def test_one_missing_milestone_in_the_current_band_alone_is_an_alert_not_a_delay() -> None:
	"""The branch order that is easy to collapse: current-band gap alone is ALERT.

	Annex 9's DELAY rule needs a gap in the current band **and** one in an earlier band, or a
	regression. Reading "any missing milestone is a delay" would refer a child who is merely late on
	one skill — and the fix is one branch away, so the distinction is tested rather than trusted.
	"""
	svc = _svc()
	items = [s for s, _t in MILESTONES[2][3]]
	report = svc.milestone_check(MilestoneCheck(
		member_ref='CH1', age_months=5, present=items[1:]))
	assert report.missing == [items[0]]
	assert report.status == 'alert', 'a single current-band gap is an alert, not a delay'


def test_a_gap_in_the_current_band_and_an_earlier_one_is_a_delay() -> None:
	"""Annex 9's DELAY rule, and the reason `checked_earlier` exists.

	The earlier bands are only counted when the caller says they were assessed. Without the flag the
	same submission is an alert, because a caregiver asked only about the child's own age group has
	supplied no evidence about the earlier ones — and reading that silence as absence would classify
	every child as delayed.
	"""
	svc = _svc()
	current = [s for s, _t in MILESTONES[2][3]]
	earlier = [s for s, _t in MILESTONES[0][3]]
	unchecked = svc.milestone_check(MilestoneCheck(
		member_ref='CH1', age_months=5, present=current[1:] + earlier[1:]))
	assert unchecked.missing_earlier == [], 'the earlier bands were counted without being asked'
	assert unchecked.status == 'alert'
	assert unchecked.earlier_checked is False

	checked = svc.milestone_check(MilestoneCheck(
		member_ref='CH1', age_months=5, present=current[1:] + earlier[1:], checked_earlier=True))
	assert checked.missing and checked.missing_earlier
	assert checked.status == 'delay'
	assert checked.earlier_checked is True


def test_a_lost_milestone_is_a_delay_on_its_own() -> None:
	"""Regression is the criterion the guideline names in its own right, with everything present.

	This is the case a series of checklists cannot catch — an earlier one recorded the milestone as
	present — which is why `lost` is an input rather than something inferred from history.
	"""
	svc = _svc()
	items = [s for s, _t in MILESTONES[2][3]]
	report = svc.milestone_check(MilestoneCheck(
		member_ref='CH1', age_months=5, present=items, lost=['rolls_over']))
	assert report.missing == []
	assert report.lost == ['rolls_over']
	assert report.status == 'delay', 'regression alone is a delay'


def test_the_earlier_milestones_counted_are_served() -> None:
	"""`expected_earlier` names what the DELAY rule looked at, so a caller can see the denominator.

	A client that wants the earlier bands assessed needs to know which milestones those are before
	it can ask. Serving the list is what makes `checked_earlier` usable rather than a flag a caller
	has to guess the meaning of.
	"""
	svc = _svc()
	current = [s for s, _t in MILESTONES[2][3]]
	report = svc.milestone_check(MilestoneCheck(member_ref='CH1', age_months=5, present=current))
	assert report.expected_earlier, 'the earlier bands are not served'
	assert {m['slug'] for m in report.expected_earlier} >= {s for s, _t in MILESTONES[0][3]}
	assert report.earlier_checked is False
	# The negative case, which is what makes the flag do anything: not asked means not counted. A
	# report that counted them anyway would pass every assertion above.
	assert report.missing_earlier == [], (
		'the earlier bands were counted although the caller did not say they were checked'
	)

	# And the served list is the one the rule actually counted: the same submission with
	# `checked_earlier` set must produce `missing_earlier` drawn from `expected_earlier`, not from
	# some other set. A flag that is served but not consulted would pass the assertions above.
	checked = svc.milestone_check(MilestoneCheck(
		member_ref='CH1', age_months=5, present=current, checked_earlier=True))
	assert set(checked.missing_earlier) <= {m['slug'] for m in checked.expected_earlier}
	assert checked.missing_earlier, 'the flag was set and no earlier gap was found'


def test_a_milestone_the_checklist_does_not_know_is_refused() -> None:
	"""An unknown slug is refused rather than counted as absent — the safe direction.

	Reading it as absent would turn a client's typo into a developmental delay.
	"""
	svc = _svc()
	with pytest.raises(AssertionError, match='not a milestone'):
		svc.milestone_check(MilestoneCheck(
			member_ref='CH1', age_months=5, present=['does_not_exist']))


def test_the_checklist_can_be_read_before_it_is_answered() -> None:
	"""The ASSESS half: the list for an age, with nothing reported, and no member named yet.

	A caregiver reads the list first. It is the same table the check classifies against, so the list
	shown and the list scored cannot diverge.
	"""
	svc = _svc()
	report = svc.milestones_for(5)
	assert report.band == '4-6 months'
	assert [e['slug'] for e in report.expected] == [s for s, _t in MILESTONES[2][3]]
	# The status is `unanswered`, not `alert`. Nothing reported is a gap in every current-band
	# milestone, so classifying the empty answer set returned ALERT — "one or more skills for this
	# age are not there yet" — about a child nobody had looked at. Annex 9's ALERT is the
	# instruction to go and assess; serving it as a result is the same false positive
	# `checked_earlier` guards against, one level up. The list is still served, because the list is
	# the checklist.
	assert report.status == 'unanswered', report.status
	assert report.missing == [s for s, _t in MILESTONES[2][3]], 'the checklist itself is the list'
	assert report.earlier_checked is False
	# And no answered check can return it: the read half's status is not one of Annex 9's three.
	assert report.status not in {'normal', 'alert', 'delay'}


def test_the_guidance_covers_the_three_classifications_and_names_an_action() -> None:
	"""The three texts are distinct, and the report serves the one its own status names.

	Checking the dictionary alone would pass whatever `milestone_check` does with it — a report that
	served the normal sentence under a `delay` status would leave every assertion on the constant
	true. So this drives the classification and reads the guidance back off the report.
	"""
	assert set(MILESTONE_GUIDANCE) == {'normal', 'alert', 'delay', 'unanswered'}
	for status, text in MILESTONE_GUIDANCE.items():
		assert text.strip(), f'{status} has no guidance'
		assert text[0].isupper() and text.endswith('.'), f'{status} is not a sentence'
	assert len({*MILESTONE_GUIDANCE.values()}) == 4, 'two classifications serve the same sentence'
	assert 'health facility' in MILESTONE_GUIDANCE['delay'].lower()
	assert 'stopped doing' in MILESTONE_GUIDANCE['delay'].lower(), (
		'the delay guidance does not name regression, which is the guideline\'s own criterion'
	)
	# The read half's sentence must not read as a finding, because there is none.
	assert 'no result' in MILESTONE_GUIDANCE['unanswered'].lower()

	svc = _svc()
	current = [s for s, _t in MILESTONES[2][3]]
	for expected_status, check in (
		('normal', MilestoneCheck(member_ref='CH1', age_months=5, present=current)),
		('alert', MilestoneCheck(member_ref='CH1', age_months=5, present=current[1:])),
		('delay', MilestoneCheck(member_ref='CH1', age_months=5, present=current, lost=[current[0]])),
	):
		report = svc.milestone_check(check)
		assert report.status == expected_status, report.status
		assert report.guidance == MILESTONE_GUIDANCE[expected_status], (
			f'a {expected_status} report is serving the wrong guidance'
		)


# ---------------------------------------------------------------- the served route

async def test_the_growth_route_serves_the_two_measurements() -> None:
	"""The front door, because a green unit test over the service says nothing about the payload."""
	async with _client() as c:
		head, kid = await _family(c)
		res = await c.post('/records/growth', json={
			'member_ref': kid, 'age_months': 12, 'weight_kg': 9.5, 'height_cm': 74.5,
			'sex': 'boy', 'head_circumference_cm': 46.0, 'muac_mm': 125.0,
		}, headers=head)
		assert res.status_code == 200, res.text
		body = res.json()
		assert body['muac_category'] == 'at_risk', body
		assert body['head_circumference_z'] is not None
		assert body['muac_alert']
		# The standing constraint: no spec feature code in a served payload.
		assert 'REC-003' not in res.text


async def test_a_reweigh_at_the_same_age_is_two_visits_and_not_a_retry() -> None:
	"""The front door again, and this one is a defect the live probe found rather than a test.

	`record_growth` files a wallet document, and `add_document` asserts its `doc_id` unique. The id
	was `growth-{member}-{age}`, so a second measurement at the same age — a child weighed at twelve
	months who comes back a fortnight later, still twelve months — was an AssertionError and a 500
	with the first visit already stored. Unreachable until this work, because the route called
	`growth_flag`, which files nothing; it started calling `record_growth` and the collision became
	the ordinary path. A re-weigh is not a retry: a retry sends the same measurement, and this sends
	a different one the chart has to plot.
	"""
	async with _client() as c:
		head, kid = await _family(c)
		first = await c.post('/records/growth', json={
			'member_ref': kid, 'age_months': 12, 'weight_kg': 9.5, 'height_cm': 74.5, 'sex': 'boy',
		}, headers=head)
		assert first.status_code == 200, first.text
		second = await c.post('/records/growth', json={
			'member_ref': kid, 'age_months': 12, 'weight_kg': 8.6, 'height_cm': 74.6, 'sex': 'boy',
		}, headers=head)
		assert second.status_code == 200, second.text
		# Two visits, and the chart plots both: the second reading is the one that shows a loss.
		assert second.json()['weight_z'] < first.json()['weight_z']


async def test_the_milestone_route_classifies_and_the_read_route_lists() -> None:
	async with _client() as c:
		head, kid = await _family(c)
		listed = await c.get(f'/records/{kid}/milestones', params={'age_months': 5}, headers=head)
		assert listed.status_code == 200, listed.text
		expected = listed.json()['expected']
		assert len(expected) == 4
		reported = await c.post('/records/milestones', json={
			'member_ref': kid, 'age_months': 5, 'present': [e['slug'] for e in expected],
		}, headers=head)
		assert reported.status_code == 200, reported.text
		assert reported.json()['status'] == 'normal'
		assert 'REC-003' not in reported.text
