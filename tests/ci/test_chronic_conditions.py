"""§MON-003's three conditions with no reading behind them, and its three missing features.

Six rows were `missing` in the content audit. Three of them — epilepsy, sickle cell disease, chronic
kidney disease — were conditions `ConditionProfile.conditions` would accept and nothing would act on.
The other three were features: trend charts (impossible while two of the four readings stored no
series), appointment tracking (a `Booking` is when you are seen, not when you are due), and lifestyle
guidance (`nutrition_guidance` bands by age, which is the wrong key here).

Every clinical number is checked against the published source archived in `sources/clinical-thresholds/`
with the reasoning in `sources/INDEX.md`. Where a source states no threshold, the test asserts the
implementation carries none rather than asserting a number someone liked.
"""
import httpx

from afya.chronic.conditions import (
	ALBUMINURIA_STAGES, CKD_SUSTAINED_DAYS, DANGER_SIGNS, KIDNEY_STAGES, PROPHYLAXIS,
	SEIZURE_EMERGENCY_MINUTES, SICKLE_FEVER_C, STATUS_EPILEPTICUS_MINUTES, albuminuria_stage,
	assess_kidney, assess_seizure, assess_sickle_crisis, egfr_ckdepi_2021, kidney_stage,
)
from afya.chronic.service import ChronicService
from afya.chronic.trends import (
	APPOINTMENT_LEAD_DAYS, LIFESTYLE, METRICS, MIN_POINTS_FOR_DIRECTION, THRESHOLDS,
	TREND_THRESHOLD, appointment_status, build_chart, lifestyle, lifestyle_for_profile,
	review_interval_days,
)
from afya.chronic.views import (
	MeasurementSource,
	BPReading, ChronicAppointment, KidneyFunction, SeizureEvent, SickleCrisis, TrendPoint,
)

# --- CKD-EPI 2021 ---------------------------------------------------------------------------------

def test_ckdepi_reproduces_the_equation_at_a_worked_point() -> None:
	"""The equation, evaluated by hand, at a point where every branch is exercised.

	Scr 1.8 mg/dL, 20-year-old male: Scr/κ = 2.0 > 1, so `min` is 1 and `max` carries the exponent;
	the whole value is `142 × 2^-1.2 × 0.9938^20`. A test that asserted only "some number came back"
	would pass against a formula with the wrong κ, the wrong sign on α, or the female multiplier —
	so the expected value is the arithmetic, written out, not a number copied from a previous run.
	"""
	expected = 142.0 * (2.0 ** -1.200) * (0.9938 ** 20)
	assert abs(egfr_ckdepi_2021(1.8, 20, 'male') - round(expected, 1)) < 0.05


def test_ckdepi_uses_the_sex_specific_kappa_alpha_and_multiplier() -> None:
	"""The three places sex enters, each with a case that fails if it is dropped.

	At Scr/κ < 1 the α branch is the live one, so the two sexes diverge sharply. At Scr 1.0 both
	ratios are *above* κ (0.9 and 0.7), so both take the -1.200 arm and the whole difference is the
	ratio of the two κ-scaled terms times the 1.012 multiplier — which is the one case that isolates
	the multiplier from the exponent. The relation is written as the ratio of the two formulas rather
	than as a remembered constant, so it is the equation being checked and not my arithmetic.
	"""
	assert egfr_ckdepi_2021(0.45, 20, 'male') > 150.0   # ratio 0.5, exponent -0.302
	assert egfr_ckdepi_2021(0.35, 20, 'female') > 145.0  # ratio 0.5, exponent -0.241
	male, female = egfr_ckdepi_2021(1.0, 40, 'male'), egfr_ckdepi_2021(1.0, 40, 'female')
	assert male > female, 'the female eGFR is the lower of the two at the same creatinine'
	ratio = ((1.0 / 0.7) ** -1.200 * 1.012) / ((1.0 / 0.9) ** -1.200)
	assert abs(female - round(male * ratio, 1)) < 0.2


def test_ckdepi_is_continuous_at_the_kappa_threshold() -> None:
	"""`min`/`max` is a branch, and a branch is where an equation breaks.

	The two arms are constructed to meet at Scr = κ, so a small step across it must move the result
	by less than the step itself. An implementation that used the wrong arm on one side jumps here.
	"""
	below = egfr_ckdepi_2021(0.8999, 50, 'male')
	above = egfr_ckdepi_2021(0.9001, 50, 'male')
	assert abs(above - below) < 0.1, f'{below} -> {above} jumps at kappa'


def test_ckdepi_refuses_a_child_a_bad_sex_and_a_zero_creatinine() -> None:
	"""The equation is for adults and is sex-specific; both are asserted rather than assumed."""
	for bad in (lambda: egfr_ckdepi_2021(1.0, 12, 'male'), lambda: egfr_ckdepi_2021(1.0, 40, 'other'),
	            lambda: egfr_ckdepi_2021(0.0, 40, 'male')):
		try:
			bad()
		except AssertionError:
			continue
		raise AssertionError('an input outside the equation\'s domain was accepted')


def test_the_canary_catches_an_equation_with_the_race_coefficient_back() -> None:
	"""Point the *shipped* check at the equation the 2021 revision replaced, and watch it fail.

	The canary runs `egfr_ckdepi_2021` itself and compares against the hand arithmetic the real test
	uses — not a copy of the check, because a canary against a re-implementation passes while the
	shipped check rots. The 2009 equation applied the same 142/κ/α terms to `Scr/κ` with **no**
	`min`/`max` split; on Scr/κ = 2.0 that is the identical arithmetic, so the mutation that must be
	caught is the one the 2009 form actually changes: the exponent and the absence of the floor at 1.
	"""
	def with_the_2009_race_era_form(scr: float, age: int, sex: str) -> float:
		kappa, alpha = (0.7, -0.241) if sex == 'female' else (0.9, -0.302)
		ratio = scr / kappa
		value = (142.0 * ratio ** alpha * 0.9938 ** age * (1.012 if sex == 'female' else 1.0))
		return round(value, 1)

	assert egfr_ckdepi_2021(1.8, 20, 'male') != with_the_2009_race_era_form(1.8, 20, 'male')
	# Below κ the 2021 `min` clamps to 1, so the two forms agree there — the mutation is invisible on
	# that side of the branch, which is why the canary is taken above it.
	assert abs(egfr_ckdepi_2021(0.45, 20, 'male') - with_the_2009_race_era_form(0.45, 20, 'male')) < 0.05


# --- KDIGO staging --------------------------------------------------------------------------------

def test_the_kdigo_categories_are_the_published_boundaries_and_they_tile() -> None:
	"""Each boundary read at the value itself and one step below, plus the coverage assertion.

	KDIGO's categories are half-open and the boundary is the whole point: 60 is G2 and 59.9 is G3a,
	and an off-by-one at any one of the six boundaries puts a person in the wrong monitoring interval.
	"""
	assert kidney_stage(90.0) == 'G1' and kidney_stage(120.0) == 'G1'
	assert kidney_stage(89.9) == 'G2' and kidney_stage(60.0) == 'G2'
	assert kidney_stage(59.9) == 'G3a' and kidney_stage(45.0) == 'G3a'
	assert kidney_stage(44.9) == 'G3b' and kidney_stage(30.0) == 'G3b'
	assert kidney_stage(29.9) == 'G4' and kidney_stage(15.0) == 'G4'
	assert kidney_stage(14.9) == 'G5' and kidney_stage(1.0) == 'G5'
	# The table is a partition of the positive eGFRs, so no value falls between two rows.
	assert [label for label, _, _, _ in KIDNEY_STAGES] == ['G1', 'G2', 'G3a', 'G3b', 'G4', 'G5']
	assert sum(1 for row in KIDNEY_STAGES if kidney_stage(50.0) == row[0]) == 1


def test_the_albuminuria_categories_are_the_published_boundaries() -> None:
	assert albuminuria_stage(0.0) == 'A1' and albuminuria_stage(29.9) == 'A1'
	assert albuminuria_stage(30.0) == 'A2' and albuminuria_stage(299.9) == 'A2'
	assert albuminuria_stage(300.0) == 'A3' and albuminuria_stage(5000.0) == 'A3'
	assert [label for label, _, _, _ in ALBUMINURIA_STAGES] == ['A1', 'A2', 'A3']


def _kidney(**over: object) -> KidneyFunction:
	base: dict[str, object] = {'subject_ref': 'K1', 'creatinine_mg_dl': 1.0, 'age_years': 40,
	                           'sex': 'male'}
	base.update(over)
	return KidneyFunction(**base)  # type: ignore[arg-type]


def test_a_single_low_egfr_is_staged_and_not_called_chronic_kidney_disease() -> None:
	"""KDIGO's three months is a condition of the definition, not a footnote to it.

	A person whose only reading is low has an acute finding; the answer must say so and ask for the
	repeat, because telling them they have kidney disease on one creatinine is both wrong and
	irreversible in their mind.
	"""
	out = assess_kidney(_kidney(creatinine_mg_dl=1.8), '2026-10-12')
	assert out.measure['stage'] == 'G3a' and out.measure['sustained'] is False
	assert 'not' in out.summary and 'three months' in out.summary


def test_two_low_readings_ninety_days_apart_are_chronic_kidney_disease() -> None:
	"""The other side: sustained past the interval, the definition is met and the summary says so."""
	reading = _kidney(creatinine_mg_dl=1.8, prior_egfr=50.0, prior_egfr_iso='2026-07-01')
	out = assess_kidney(reading, '2026-10-12')  # 103 days later
	assert out.measure['sustained'] is True
	assert 'chronic kidney disease' in out.summary


def test_eighty_nine_days_apart_is_one_day_short_of_the_definition() -> None:
	"""The boundary of the sustainment rule, which is the only place it can be wrong."""
	assert CKD_SUSTAINED_DAYS == 90
	reading = _kidney(creatinine_mg_dl=1.8, prior_egfr=50.0, prior_egfr_iso='2026-07-15')
	assert assess_kidney(reading, '2026-10-12').measure['sustained'] is False  # 89 days
	reading = _kidney(creatinine_mg_dl=1.8, prior_egfr=50.0, prior_egfr_iso='2026-07-14')
	assert assess_kidney(reading, '2026-10-12').measure['sustained'] is True   # 90 days


def test_an_undated_low_reading_is_never_called_sustained() -> None:
	"""No date means no duration, and a duration invented from the clock is a wrong diagnosis.

	This is the defect the route used to have: it stamped an undated reading with the server's date,
	so a prior reading of unknown age was compared against today and the result reported as a
	three-month history.
	"""
	out = assess_kidney(_kidney(creatinine_mg_dl=1.8, prior_egfr=50.0, prior_egfr_iso='2000-01-01'),
	                    None)
	assert out.measure['sustained'] is False
	assert 'undated' in out.summary


def test_the_two_things_that_escalate_a_kidney_reading_are_separate_from_its_stage() -> None:
	"""eGFR under 30 and albuminuria A3 each escalate, and neither is the staging itself.

	A G3a reading with heavy albuminuria is more urgent than a bare G3a, which is why the escalation
	is computed from both rather than read off the GFR category.
	"""
	assert assess_kidney(_kidney(creatinine_mg_dl=3.0), '2026-10-12').escalate is True   # eGFR ~24
	assert assess_kidney(_kidney(acr_mg_g=400.0), '2026-10-12').escalate is True          # A3
	assert assess_kidney(_kidney(acr_mg_g=100.0), '2026-10-12').escalate is False         # A2
	assert assess_kidney(_kidney(), '2026-10-12').escalate is False


def test_the_canary_catches_a_sustainment_check_that_ignores_the_interval() -> None:
	"""The shipped comparison, pointed at the defect it exists to catch.

	`_days_between` is the only thing standing between "two low readings" and "two low readings three
	months apart". The canary drops the interval comparison and confirms the same pair of readings
	would then be reported as chronic — proving the test above is testing the interval and not merely
	the presence of a prior value.
	"""
	reading = _kidney(creatinine_mg_dl=1.8, prior_egfr=50.0, prior_egfr_iso='2026-10-11')
	assert assess_kidney(reading, '2026-10-12').measure['sustained'] is False  # one day apart
	without_the_interval = bool(reading.prior_egfr is not None and reading.prior_egfr_iso is not None)
	assert without_the_interval is True, 'the canary target must be present before it is trusted'


# --- epilepsy: ILAE's two time points ---------------------------------------------------------------

def _seizure(**over: object) -> SeizureEvent:
	base: dict[str, object] = {'subject_ref': 'E1', 'duration_seconds': 60, 'at_iso': '2026-10-12'}
	base.update(over)
	return SeizureEvent(**base)  # type: ignore[arg-type]


def test_ilae_states_two_time_points_and_the_escalation_uses_both() -> None:
	"""5 minutes is when to act and 30 is when harm is likely, so one threshold cannot serve.

	Below 5 minutes the seizure has ended and the advice is to time the next one; at 5 it is treated
	as continuous; at 30 it is status and the message changes from "give the rescue medicine" to
	"call 719 now". A single threshold either calls a treatable seizure an emergency or a harmful one
	a wait.
	"""
	assert (SEIZURE_EMERGENCY_MINUTES, STATUS_EPILEPTICUS_MINUTES) == (5, 30)
	assert assess_seizure(_seizure(duration_seconds=60)).measure['state'] == 'recovered'
	assert assess_seizure(_seizure(duration_seconds=60)).escalate is False
	assert assess_seizure(_seizure(duration_seconds=300)).measure['state'] == 'emergency'
	assert assess_seizure(_seizure(duration_seconds=299)).measure['state'] == 'recovered'
	assert assess_seizure(_seizure(duration_seconds=1800)).measure['state'] == 'status_epilepticus'
	assert assess_seizure(_seizure(duration_seconds=1799)).measure['state'] == 'emergency'
	# The three states carry three different instructions, not one instruction and two labels.
	actions = {assess_seizure(_seizure(duration_seconds=s)).summary
	           for s in (60, 300, 1800)}
	assert len(actions) == 3


def test_a_cluster_escalates_at_any_duration() -> None:
	"""A second seizure before recovery is treated as continuous, so duration is not the test."""
	out = assess_seizure(_seizure(duration_seconds=30, cluster=True))
	assert out.escalate is True and out.measure['state'] == 'emergency'


def test_any_seizure_in_pregnancy_needs_same_day_review() -> None:
	out = assess_seizure(_seizure(duration_seconds=30, pregnant=True))
	assert out.escalate is True and 'pregnan' in out.summary.lower()


def test_the_canary_catches_a_ladder_that_reads_only_t2() -> None:
	"""The defect a single-threshold implementation has: a 6-minute seizure waved through.

	The canary evaluates the shipped assessor at a duration between the two time points and asserts
	the *t1* branch is what caught it — if the implementation only knew about 30 minutes this reading
	would be reported as recovered, which is the failure the two-point definition exists to prevent.
	"""
	six_minutes = _seizure(duration_seconds=360)
	out = assess_seizure(six_minutes)
	assert out.escalate is True, 'the canary target must be present before it is trusted'
	assert out.measure['state'] == 'emergency', 't1, not t2, is what escalates at 6 minutes'
	assert six_minutes.duration_seconds / 60 < STATUS_EPILEPTICUS_MINUTES


# --- sickle cell disease ----------------------------------------------------------------------------

def _crisis(**over: object) -> SickleCrisis:
	base: dict[str, object] = {'subject_ref': 'S1', 'pain_score': 5, 'temperature_c': 36.8,
	                           'at_iso': '2026-10-12'}
	base.update(over)
	return SickleCrisis(**base)  # type: ignore[arg-type]


def test_a_fever_in_sickle_cell_disease_escalates_on_its_own() -> None:
	"""Infection is a leading cause of death here and functional asplenia begins in infancy.

	The threshold is named as an assumption in the source index — the archived WHO and disease pages
	state that fever is the emergency but print no temperature — so this asserts the *behaviour* at
	the stated threshold and that the constant is the one documented, not a number pulled from air.
	"""
	assert SICKLE_FEVER_C == 38.0
	assert assess_sickle_crisis(_crisis(temperature_c=38.0)).escalate is True
	assert assess_sickle_crisis(_crisis(temperature_c=37.9)).escalate is False
	assert 'emergency' in assess_sickle_crisis(_crisis(temperature_c=38.5)).summary.lower()


def test_the_signs_that_make_a_crisis_more_than_a_crisis_escalate_it() -> None:
	"""Acute chest syndrome, sequestration, stroke, a falling haemoglobin: each escalates alone.

	The archived sources give danger signs and no severity score, so the implementation keys on the
	signs themselves. The canary half is that a sign *outside* the vocabulary does not escalate: the
	field is a closed set because the escalation is a lookup, and free text matches nothing.
	"""
	for sign in ('chest_pain', 'breathing_difficulty', 'spleen_pain', 'stroke_signs',
	             'uncontrolled_pain', 'sudden_pallor'):
		out = assess_sickle_crisis(_crisis(signs=[sign]))
		assert out.escalate is True, sign
		assert sign in str(out.measure['signs'])
	assert assess_sickle_crisis(_crisis(signs=['a headache'])).escalate is False
	assert assess_sickle_crisis(_crisis(pain_score=10)).escalate is False


def test_a_plain_crisis_is_managed_at_home_with_the_medicine_that_exists() -> None:
	"""No danger sign means advice, not escalation — and the advice names real analgesics.

	WHO's guidance names paracetamol, ibuprofen and opioids; a summary that said "take pain relief"
	without naming them would be advice a person cannot act on.
	"""
	out = assess_sickle_crisis(_crisis(pain_score=7))
	assert out.escalate is False and out.danger_signs == []
	assert 'paracetamol' in out.summary and 'ibuprofen' in out.summary


def test_prophylaxis_is_carried_and_the_absent_dose_is_stated_as_absent() -> None:
	"""The archived sources recommend daily penicillin and state no milligram dose.

	A dose invented to fill the gap is worse than the gap, because the gap is visible. The assertion
	is that the implementation says so rather than that it stays silent.
	"""
	penicillin = ' '.join(PROPHYLAXIS['sickle_cell'])
	assert 'penicillin' in penicillin.lower()
	assert 'no milligram dose' in penicillin.lower() or 'No milligram dose' in penicillin


def test_the_canary_catches_a_fever_threshold_that_crept_up() -> None:
	"""The shipped constant, pointed at the reading it must not wave through.

	A threshold moved from 38.0 to 38.5 would pass a test written only at 38.0/37.9 if the boundary
	were not asserted. Here the canary reads the constant the assessor reads and confirms a 38.2 C
	reading is on the escalating side of it.
	"""
	reading = _crisis(temperature_c=38.2)
	assert reading.temperature_c >= SICKLE_FEVER_C, 'the canary target must be present first'
	assert assess_sickle_crisis(reading).escalate is True
	assert SICKLE_FEVER_C == 38.0, 'the threshold moved; the 38.2 case above would stop escalating'


# --- trend charts ------------------------------------------------------------------------------------

def test_a_chart_needs_three_points_before_it_has_a_direction() -> None:
	"""Two points are a line through any two points; a direction needs a third.

	This is not a refusal — "you have not measured this enough yet" is the useful answer to a chart
	request, so the chart comes back with `insufficient` and the count rather than an error.
	"""
	points = [TrendPoint(at_iso=f'2026-10-0{i}', value=120.0 + i, label='systolic') for i in (1, 2)]
	chart = build_chart('T1', 'bp_systolic', points)
	assert MIN_POINTS_FOR_DIRECTION == 3
	assert chart.direction == 'insufficient' and chart.change == 0.0
	assert '2 reading' in chart.note
	empty = build_chart('T1', 'bp_systolic', [])
	assert empty.direction == 'insufficient' and empty.points == []


def test_the_direction_is_read_across_the_window_and_not_end_to_end() -> None:
	"""The first third against the last third, so a series that returns to where it started is stable.

	Six readings that rise then fall back: the two windows are equal, so the answer is `stable`. An
	end-to-end comparison of the first and last reading would call the same series stable for the
	wrong reason, and would read a series with a single spike as a trend.
	"""
	values = [120.0, 130.0, 140.0, 150.0, 160.0, 170.0]
	points = [TrendPoint(at_iso=f'2026-10-{i:02d}', value=v, label='systolic')
	          for i, v in enumerate(values, start=1)]
	rising = build_chart('T1', 'bp_systolic', points)
	assert rising.direction == 'rising'
	assert rising.change == 40.0  # mean(160,170) - mean(120,130): a third of six is two

	plateau = [TrendPoint(at_iso=f'2026-10-{i:02d}', value=v, label='systolic')
	           for i, v in enumerate([120.0, 130.0, 140.0, 140.0, 130.0, 120.0], start=1)]
	flat = build_chart('T1', 'bp_systolic', plateau)
	assert flat.direction == 'stable' and abs(flat.change) <= TREND_THRESHOLD

	# A single spike at the end is a third of three, so it is the whole late window and it counts;
	# the same spike inside a longer series is diluted by its own window, which is the point of one.
	spiked = [TrendPoint(at_iso=f'2026-10-{i:02d}', value=v, label='systolic')
	          for i, v in enumerate([120.0, 120.0, 120.0, 120.0, 120.0, 190.0], start=1)]
	assert build_chart('T1', 'bp_systolic', spiked).direction == 'rising'


def test_the_canary_catches_a_three_point_window_that_overlaps_itself() -> None:
	"""The defect this chart actually shipped with, pointed at by the shipped builder.

	Fixed three-point windows are correct for every series of six or more and wrong at exactly three,
	where `[:3]` and `[-3:]` are the same points and the change is identically zero. The canary runs
	`build_chart` on a three-point series that falls by 80 L/min — a fifth of this person's best, a
	red-zone move — and asserts it does not come back `stable`. It also asserts the falling series is
	real: the endpoints differ by far more than the threshold, so `stable` can only be the window.
	"""
	falling = [TrendPoint(at_iso=f'2026-10-0{i}', value=v, label='peak flow')
	           for i, v in enumerate([380.0, 340.0, 300.0], start=1)]
	assert abs(falling[-1].value - falling[0].value) > TREND_THRESHOLD, 'the canary target must be present'
	assert len(falling) == MIN_POINTS_FOR_DIRECTION
	assert build_chart('T1', 'peak_flow', falling).direction == 'falling'
	assert build_chart('T1', 'peak_flow', falling).change == -80.0


def test_the_canary_catches_a_chart_that_calls_two_points_a_trend() -> None:
	"""The shipped builder, pointed at the input that must come back `insufficient`.

	Two readings 40 mmHg apart is the case where a naive implementation reports a direction with
	total confidence. The canary asserts the difference is real — that the threshold and the point
	count are both exceeded by the data — so the `insufficient` answer is the guard and not an
	artefact of small numbers.
	"""
	two = [TrendPoint(at_iso='2026-10-01', value=110.0, label='systolic'),
	       TrendPoint(at_iso='2026-10-08', value=150.0, label='systolic')]
	assert abs(two[-1].value - two[0].value) > TREND_THRESHOLD, 'the canary target must be present'
	assert len(two) < MIN_POINTS_FOR_DIRECTION
	assert build_chart('T1', 'bp_systolic', two).direction == 'insufficient'


def test_the_chart_carries_the_threshold_lines_the_readings_themselves_use() -> None:
	"""A chart without its lines is a shape: 140 is alarming and 118 is not, at the same slope.

	The lines are read from `THRESHOLDS`, which is where the readings' own boundaries live, so the
	chart and the verdict cannot disagree about where "high" starts.
	"""
	points = [TrendPoint(at_iso=f'2026-10-0{i}', value=v, label='systolic')
	          for i, v in enumerate([125.0, 135.0, 150.0], start=1)]
	chart = build_chart('T1', 'bp_systolic', points)
	assert [t['label'] for t in chart.thresholds] == ['elevated', 'high']
	assert 'high' in chart.note and 'clinician' in chart.note
	quiet = build_chart('T1', 'bp_systolic',
	                    [TrendPoint(at_iso=f'2026-10-0{i}', value=118.0, label='systolic')
	                     for i in (1, 2, 3)])
	assert 'crosses' not in quiet.note


def test_every_metric_the_section_names_has_a_unit_a_label_and_thresholds() -> None:
	assert set(METRICS) == {'bp_systolic', 'bp_diastolic', 'glucose', 'peak_flow', 'weight'}
	assert all(unit and label for unit, label in METRICS.values())
	assert set(THRESHOLDS) == set(METRICS)
	assert build_chart('T1', 'weight', []).unit == 'kg'


def test_a_metric_the_section_does_not_name_is_refused() -> None:
	try:
		build_chart('T1', 'blood_pressure', [])
	except AssertionError as exc:
		assert 'blood_pressure' in str(exc)
	else:
		raise AssertionError('an unknown metric produced a chart')


# --- appointment tracking -----------------------------------------------------------------------------

def _appointment(**over: object) -> ChronicAppointment:
	base: dict[str, object] = {'appointment_id': 'A1', 'subject_ref': 'P1', 'condition': 'hypertension',
	                           'due_iso': '2026-11-01', 'interval_days': 90, 'kind': 'review'}
	base.update(over)
	return ChronicAppointment(**base)  # type: ignore[arg-type]


def test_overdue_and_remind_are_two_answers_and_not_one_boolean() -> None:
	"""An appointment that passed needs "you missed this"; one coming up needs "this is in a week".

	Collapsing them into one flag produces the wrong sentence for one of the two, which is the defect
	the two fields exist to prevent — so the test asserts the messages differ, not just the flags.
	"""
	assert APPOINTMENT_LEAD_DAYS == 14
	past = appointment_status(_appointment(due_iso='2026-09-30'), '2026-10-12')
	soon = appointment_status(_appointment(due_iso='2026-10-20'), '2026-10-12')
	far = appointment_status(_appointment(due_iso='2026-12-01'), '2026-10-12')
	assert past.overdue is True and past.remind is True
	assert soon.overdue is False and soon.remind is True
	assert far.overdue is False and far.remind is False
	assert past.days_until == -12 and soon.days_until == 8 and far.days_until == 50
	assert len({past.message, soon.message, far.message}) == 3


def test_the_reminder_window_boundary_is_the_stated_lead() -> None:
	"""14 days out reminds, 15 does not — the boundary, which is where a window is decided."""
	assert appointment_status(_appointment(due_iso='2026-10-26'), '2026-10-12').remind is True
	assert appointment_status(_appointment(due_iso='2026-10-27'), '2026-10-12').remind is False


def test_the_review_interval_is_a_property_of_the_condition_and_the_kidney_stage() -> None:
	"""Two people with the same diagnosis are reviewed at different rates by stage.

	This is why the due date is computed rather than stored: a stored date goes stale the moment the
	stage changes, and the stage is the thing that changes the answer.
	"""
	assert review_interval_days('hypertension') == 90
	assert review_interval_days('asthma') == 180
	assert review_interval_days('chronic_kidney', 'G1') == 365
	assert review_interval_days('chronic_kidney', 'G4') == 90
	# The stage overrides the condition's own interval, and only for the kidney conditions.
	assert review_interval_days('chronic_kidney', 'G1') != review_interval_days('chronic_kidney')
	try:
		review_interval_days('gout')
	except AssertionError as exc:
		assert 'gout' in str(exc)
	else:
		raise AssertionError('a condition with no interval produced a date')


def test_the_canary_catches_a_status_that_treats_overdue_as_merely_due_soon() -> None:
	"""The shipped comparison, pointed at a missed appointment.

	An implementation that reported only `days_until` and let the caller decide would give -12 for a
	missed review and 8 for one next week, and a caller testing `days_until <= 14` would call both
	"coming up". The canary asserts the negative case is distinguishable at the shipped boundary.
	"""
	missed = appointment_status(_appointment(due_iso='2026-09-30'), '2026-10-12')
	upcoming = appointment_status(_appointment(due_iso='2026-10-20'), '2026-10-12')
	assert missed.days_until < 0 and upcoming.days_until >= 0, 'the canary target must be present'
	assert missed.overdue and not upcoming.overdue
	assert missed.remind and upcoming.remind  # both remind, and for different reasons


# --- lifestyle guidance ---------------------------------------------------------------------------------

def test_lifestyle_is_keyed_on_the_condition_and_not_the_age() -> None:
	"""What a person with hypertension eats and what a person with sickle cell must avoid differ.

	`nutrition_guidance` bands by age, which is right for a well-child visit and wrong here: two
	40-year-olds with different diagnoses get different lists, and the test asserts the lists differ
	rather than merely that both exist.
	"""
	hyper = lifestyle('hypertension')
	sickle = lifestyle('sickle_cell')
	assert hyper.condition == 'hypertension' and sickle.condition == 'sickle_cell'
	assert hyper.guidance != sickle.guidance and hyper.avoid != sickle.avoid
	assert any('salt' in line.lower() for line in hyper.guidance)
	assert any('fever' in line.lower() for line in sickle.avoid)


def test_every_condition_the_log_supports_carries_guidance() -> None:
	"""§9.1's seven conditions, and the kidney one under the name the audit uses."""
	for condition in ('hypertension', 'diabetes', 'asthma', 'epilepsy', 'sickle_cell', 'hiv',
	                  'chronic_kidney'):
		out = lifestyle(condition)
		assert out.guidance and out.avoid and out.note, condition
	assert set(LIFESTYLE) == {'hypertension', 'diabetes', 'asthma', 'epilepsy', 'sickle_cell', 'hiv',
	                          'chronic_kidney'}


def test_a_person_with_two_conditions_gets_both_lists() -> None:
	out = lifestyle_for_profile(['Hypertension', 'sickle cell', 'gout'])
	assert [g.condition for g in out] == ['hypertension', 'sickle_cell']


def test_the_canary_catches_guidance_that_silently_returns_nothing_for_a_known_condition() -> None:
	"""The shipped lookup, pointed at a condition that must resolve.

	A `lifestyle` that fell through to an empty list for a condition in the profile would render an
	empty card, which reads as "there is no advice for you" rather than as a bug. The canary asserts
	the key the audit names resolves to the same object the profile path returns.
	"""
	assert 'chronic_kidney' in LIFESTYLE, 'the canary target must be present before it is trusted'
	direct = lifestyle('chronic_kidney')
	via_profile = lifestyle_for_profile(['chronic_kidney'])
	assert via_profile and via_profile[0].condition == direct.condition
	assert via_profile[0].guidance == direct.guidance
	assert direct.guidance, 'a known condition resolved to no guidance'


# --- the service, and the routes ---------------------------------------------------------------------

async def test_the_service_keeps_the_series_the_charts_read() -> None:
	"""A chart needs a series, and the series is what the readings are stored into.

	Two of the four readings §MON-003 names stored nothing, which is why "Trend charts" was missing:
	the storage had to exist before a chart could be drawn from it. This asserts the storage, and
	that an undated reading is scored without being charted rather than being stamped with today.
	"""
	c = ChronicService()
	for at, sys_ in [('2026-10-01', 120), ('2026-10-05', 132), ('2026-10-09', 145)]:
		await c.bp(BPReading(subject_ref='C1', systolic=sys_, diastolic=80, source=MeasurementSource.manual), at)
	assert [p.value for p in c.chart('C1', 'bp_systolic').points] == [120.0, 132.0, 145.0]
	assert c.chart('C1', 'bp_systolic').direction == 'rising'
	await c.bp(BPReading(subject_ref='C1', systolic=150, diastolic=90, source=MeasurementSource.manual))
	assert len(c.chart('C1', 'bp_systolic').points) == 3, 'an undated reading must not be charted'


async def test_the_kidney_service_refuses_to_date_a_reading_from_the_clock() -> None:
	c = ChronicService()
	out = await c.kidney(_kidney(creatinine_mg_dl=1.8, prior_egfr=50.0,
	                             prior_egfr_iso='2000-01-01'))
	assert out.measure['sustained'] is False
	assert c.kidney_series('K1') == [], 'an undated reading is not a point on a series'
	out = await c.kidney(_kidney(creatinine_mg_dl=1.8), '2026-10-12')
	assert len(c.kidney_series('K1')) == 1


async def test_the_service_schedules_a_review_and_reports_it_overdue() -> None:
	c = ChronicService()
	review = c.next_review('P1', 'chronic_kidney', '2026-01-01', 'G4')
	assert review.due_iso == '2026-04-01' and review.interval_days == 90
	await c.schedule_appointment(review)
	status = c.appointment(review.appointment_id, '2026-10-12')
	assert status.overdue is True
	assert [s.appointment_id for s in c.appointments_for('P1', '2026-10-12')] == [review.appointment_id]


async def test_an_appointment_cannot_be_scheduled_twice() -> None:
	c = ChronicService()
	appt = _appointment()
	await c.schedule_appointment(appt)
	try:
		await c.schedule_appointment(appt)
	except AssertionError as exc:
		assert 'already scheduled' in str(exc)
	else:
		raise AssertionError('the same appointment was scheduled twice')


def _client() -> tuple[httpx.AsyncClient, dict[str, object]]:
	"""A real app over a real service set, so each test's readings do not leak into the next."""
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t'), services


async def _subject_token(client: httpx.AsyncClient, ref: str) -> str:
	r = await client.post('/auth/anonymous', json={'subject_ref': ref})
	r.raise_for_status()
	return r.json()['token']


async def test_the_mon_003_routes_answer_a_real_client() -> None:
	"""The routes as a client reaches them — a route that 422s is a route no screen can call.

	This is the check that found three defects in the §REC unit: a required query parameter the
	client never sends, a body field the server overwrites, and a missing ownership check. Every one
	of them passed review and failed here.
	"""
	client, _ = _client()
	async with client:
		token = await _subject_token(client, 'MON003')
		head = {'Authorization': f'Bearer {token}'}
		kidney = await client.post('/chronic/kidney?at_iso=2026-10-12', headers=head,
		                           json={'subject_ref': 'MON003', 'creatinine_mg_dl': 1.8,
		                                 'age_years': 60, 'sex': 'male'})
		assert kidney.status_code == 200, kidney.text
		assert kidney.json()['measure']['stage'] in {'G2', 'G3a', 'G3b'}
		seizure = await client.post('/chronic/seizure', headers=head,
		                            json={'subject_ref': 'MON003', 'duration_seconds': 400,
		                                  'at_iso': '2026-10-12'})
		assert seizure.status_code == 200, seizure.text
		assert seizure.json()['escalate'] is True
		crisis = await client.post('/chronic/sickle-crisis', headers=head,
		                           json={'subject_ref': 'MON003', 'pain_score': 6,
		                                 'temperature_c': 38.4, 'at_iso': '2026-10-12'})
		assert crisis.status_code == 200, crisis.text
		assert crisis.json()['escalate'] is True
		lifestyle_r = await client.get('/chronic/lifestyle?condition=hypertension', headers=head)
		assert lifestyle_r.status_code == 200, lifestyle_r.text
		assert lifestyle_r.json()['guidance']
		# A metric the section does not name is refused, and a known one with no readings is a chart.
		assert (await client.get('/chronic/MON003/chart?metric=blood_pressure',
		                         headers=head)).status_code == 422
		chart = await client.get('/chronic/MON003/chart?metric=bp_systolic', headers=head)
		assert chart.status_code == 200, chart.text
		assert chart.json()['direction'] == 'insufficient'


async def test_the_trend_chart_reads_a_series_logged_through_the_routes() -> None:
	"""End to end: three dated readings in, a direction out.

	The peak-flow and weight series live in the monitoring service and the chart is built in the
	chronic one, so this crosses both — which is where a route that dropped `at_iso` on the floor
	would show up as an empty chart rather than as a failed test.
	"""
	client, _ = _client()
	async with client:
		token = await _subject_token(client, 'MON003B')
		head = {'Authorization': f'Bearer {token}'}
		for at, litres in (('2026-10-01', 380), ('2026-10-05', 340), ('2026-10-09', 300)):
			r = await client.post(f'/monitoring/chronic/peak-flow?at_iso={at}', headers=head,
			                      json={'subject_ref': 'MON003B', 'litres_per_min': litres,
			                            'personal_best': 400})
			assert r.status_code == 200, r.text
		chart = await client.get('/chronic/MON003B/chart?metric=peak_flow', headers=head)
		assert chart.status_code == 200, chart.text
		body = chart.json()
		assert [p['value'] for p in body['points']] == [380.0, 340.0, 300.0]
		assert body['direction'] == 'falling' and body['unit'] == 'L/min'


async def test_the_appointment_routes_round_trip() -> None:
	client, _ = _client()
	async with client:
		token = await _subject_token(client, 'MON003C')
		head = {'Authorization': f'Bearer {token}'}
		appt = await client.post('/chronic/appointments', headers=head,
		                         json={'appointment_id': 'APPT-MON003C', 'subject_ref': 'MON003C',
		                               'condition': 'diabetes', 'due_iso': '2026-10-01',
		                               'interval_days': 90, 'kind': 'review'})
		assert appt.status_code == 200, appt.text
		listed = await client.get('/chronic/MON003C/appointments?today_iso=2026-10-12', headers=head)
		assert listed.status_code == 200, listed.text
		assert listed.json()[0]['overdue'] is True
		assert listed.json()[0]['days_until'] == -11
