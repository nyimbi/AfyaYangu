"""§MON-003's "Trend charts", "Appointment tracking" and "Lifestyle guidance".

Three bullets with three different reasons for being absent.

**Trend charts.** `ChronicService.bp_trend` returned a one-line direction from the systolic series
and there was no series for anything else, because `log_peak_flow` and `log_weight` returned a dict
and stored nothing — so two of the four readings §MON-003 names had no history at all. A chart needs
a series, and the series had to be kept before a chart could be drawn from it. This module builds the
chart from whatever series a service holds, so a metric with no storage has no chart rather than an
empty one.

**Appointment tracking.** `Booking` is a facility slot with a queue position: it is when a person is
being seen, not when they are due to be seen. A chronic condition's review interval is a property of
the condition — a stable hypertensive is reviewed in months and a person in stage G4 kidney disease
sooner — so the due date is computed from the condition and the last visit rather than stored.

**Lifestyle guidance.** `MonitoringService.nutrition_guidance` bands by the child's age, which is
right for a well-child visit and wrong here: what a person with hypertension eats and what a person
with sickle cell disease must avoid are different lists at the same age.
"""
from afya.chronic.views import (
	AppointmentStatus, ChronicAppointment, LifestyleGuidance, TrendChart, TrendPoint,
)

# metric -> (unit, human label)
METRICS: dict[str, tuple[str, str]] = {
	'bp_systolic': ('mmHg', 'systolic blood pressure'),
	'bp_diastolic': ('mmHg', 'diastolic blood pressure'),
	'glucose': ('mmol/L', 'blood sugar'),
	'peak_flow': ('L/min', 'peak flow'),
	'weight': ('kg', 'weight'),
}

TREND_THRESHOLD = 5.0
"""The change across the window that counts as a direction rather than noise. Five units is about
one BP cuff reading's variability, 0.5 mmol/L of glucose and 5% of a peak flow — a single number
because a per-metric one would be five numbers nothing distinguishes."""

MIN_POINTS_FOR_DIRECTION = 3
"""Two points are a line through any two points; a direction needs a third to mean anything."""

# The lines the chart draws, per metric: the value and what crossing it means. Taken from the
# thresholds the readings themselves use, so the chart and the verdict cannot disagree.
THRESHOLDS: dict[str, list[dict[str, object]]] = {
	'bp_systolic': [
		{'value': 130.0, 'label': 'elevated', 'advise': 'elevated — reduce salt, recheck in a week'},
		{'value': 140.0, 'label': 'high', 'advise': 'high — see a clinician; this needs treatment'},
	],
	'bp_diastolic': [
		{'value': 85.0, 'label': 'elevated', 'advise': 'elevated'},
		{'value': 90.0, 'label': 'high', 'advise': 'high — see a clinician'},
	],
	'glucose': [
		{'value': 6.1, 'label': 'impaired fasting', 'advise': 'impaired fasting glucose — diet and review'},
		{'value': 7.0, 'label': 'diabetes range', 'advise': 'diabetes range — confirm with a clinician'},
	],
	'peak_flow': [
		{'value': 80.0, 'label': 'green zone', 'advise': '80% of personal best — well controlled'},
		{'value': 50.0, 'label': 'yellow zone', 'advise': '50-79% of personal best — act on your plan'},
	],
	'weight': [],
}

REVIEW_INTERVAL_DAYS: dict[str, int] = {
	# condition -> the interval a stable patient is reviewed at
	'hypertension': 90,
	'diabetes': 90,
	'asthma': 180,
	'epilepsy': 180,
	'sickle_cell': 180,
	'hiv': 90,
	'chronic_kidney': 90,
}

STAGE_INTERVALS: dict[str, int] = {
	# §MON-003's kidney stages: KDIGO's monitoring frequency, which is the "1-4 times a year" the
	# archived classification table carries in its cells.
	'G1': 365, 'G2': 365, 'G3a': 180, 'G3b': 180, 'G4': 90, 'G5': 90,
}

APPOINTMENT_LEAD_DAYS = 14
"""How long before a review the reminder starts. Long enough to book transport, short enough that the
reminder is still about the appointment."""


def build_chart(subject_ref: str, metric: str, points: list[TrendPoint],
                thresholds: list[dict[str, object]] | None = None) -> TrendChart:
	"""The chart for one metric, with its direction and the lines it is read against.

	`insufficient` is a direction rather than an empty chart: two readings are a line through any two
	points, and a chart that drew a trend from them would tell a person their blood pressure is rising
	on the strength of one measurement and its follow-up.

	The window is the first third against the last third, as a partition. Fixed three-point windows
	were the obvious spelling and they are wrong at the smallest series this accepts: with exactly
	three readings `[:3]` and `[-3:]` are the same three points, so the change is always zero and a
	peak flow falling from 380 to 300 comes back "stable" — which is the one thing that series has to
	say. A third of the series at each end cannot overlap itself.
	"""
	assert metric in METRICS, f'{metric} is not a metric §MON-003 names'
	unit, label = METRICS[metric]
	ordered = sorted(points, key=lambda p: p.at_iso)
	if len(ordered) < MIN_POINTS_FOR_DIRECTION:
		direction, change = 'insufficient', 0.0
		note = (f'{len(ordered)} reading(s) for {label}. A trend needs at least '
		        f'{MIN_POINTS_FOR_DIRECTION} — until then this is a number, not a direction.')
	else:
		window = max(1, (len(ordered) + 2) // 3)
		early = sum(p.value for p in ordered[:window]) / window
		late = sum(p.value for p in ordered[-window:]) / window
		change = round(late - early, 1)
		if change > TREND_THRESHOLD:
			direction = 'rising'
		elif change < -TREND_THRESHOLD:
			direction = 'falling'
		else:
			direction = 'stable'
		note = f'{label} is {direction} ({change:+.1f} {unit} across {len(ordered)} readings).'
	lines = THRESHOLDS[metric] if thresholds is None else thresholds
	worst = max((p.value for p in ordered), default=None)
	if worst is not None:
		crossed = [t for t in lines if isinstance(t['value'], float) and worst >= t['value']]
		if crossed:
			top = crossed[-1]
			note += f' The highest reading crosses the {top["label"]} line ({top["advise"]}).'
	return TrendChart(
		subject_ref=subject_ref, metric=metric, points=ordered, direction=direction,
		change=change, unit=unit, thresholds=lines, note=note,
	)


def review_interval_days(condition: str, stage: str | None = None) -> int:
	"""How often a stable patient with this condition is reviewed.

	A kidney stage overrides the condition's interval, because the stage is the thing that changes
	the answer: two people with the same diagnosis are reviewed at different frequencies depending on
	how much function they have left.
	"""
	if condition == 'chronic_kidney' and stage in STAGE_INTERVALS:
		return STAGE_INTERVALS[stage]
	assert condition in REVIEW_INTERVAL_DAYS, f'{condition} has no review interval'
	return REVIEW_INTERVAL_DAYS[condition]


def appointment_status(appointment: ChronicAppointment, today_iso: str) -> AppointmentStatus:
	"""§MON-003's "Appointment tracking": how long until the review, and whether to remind.

	`overdue` and `remind` are separate because they are different messages: an appointment that
	passed needs "you missed this" and one coming up needs "this is in a week", and collapsing them
	into one boolean produces the wrong sentence for one of the two.
	"""
	days = _days_between(today_iso, appointment.due_iso)
	overdue = days < 0
	remind = overdue or days <= APPOINTMENT_LEAD_DAYS
	if overdue:
		message = (f'Your {appointment.kind} for {appointment.condition.replace("_", " ")} was due '
		           f'{-days} day(s) ago. Book it — a review that slips is how a controlled condition '
		           f'stops being controlled.')
	elif remind:
		message = (f'Your {appointment.kind} for {appointment.condition.replace("_", " ")} is due in '
		           f'{days} day(s), on {appointment.due_iso}.')
	else:
		message = (f'Next {appointment.kind} for {appointment.condition.replace("_", " ")}: '
		           f'{appointment.due_iso}.')
	return AppointmentStatus(
		appointment_id=appointment.appointment_id, subject_ref=appointment.subject_ref,
		condition=appointment.condition, due_iso=appointment.due_iso, kind=appointment.kind,
		days_until=days, overdue=overdue, remind=remind, message=message,
	)


def _days_between(iso_a: str, iso_b: str) -> int:
	from datetime import date
	a = date(*(int(p) for p in iso_a[:10].split('-')))
	b = date(*(int(p) for p in iso_b[:10].split('-')))
	return (b - a).days


# --- lifestyle guidance -------------------------------------------------------------------------

LIFESTYLE: dict[str, tuple[list[str], list[str], str]] = {
	'hypertension': (
		['Cut salt: cook with herbs and spices instead, and keep the salt shaker off the table.',
		 'Walk briskly for 30 minutes on most days — the cheapest blood pressure treatment there is.',
		 'Lose weight if you carry it around the middle; 5 kg is worth several mmHg.',
		 'Limit alcohol and stop smoking: both raise pressure and both blunt the medicines.'],
		['Do not stop the tablets when the readings look normal — the tablets are why they do.',
		 'Avoid painkillers like ibuprofen and diclofenac; they raise blood pressure and strain kidneys.',
		 'Avoid licorice and heavily salted traditional preparations.'],
		'Take the medicine at the same time daily and bring your card to every review.',
	),
	'diabetes': (
		['Eat at fixed times and keep the starchy portion the same at each meal.',
		 'Choose whole grains, beans and vegetables over white bread, soda and sweets.',
		 'Walk after meals — 15 minutes after each of the day\'s main meals lowers the sugar spike.',
		 'Check your feet daily for cuts or numbness; a foot ulcer starts small.',
		 'Have your eyes and kidneys checked yearly even when you feel well.'],
		['Avoid sugary drinks, including fruit juice in quantity.',
		 'Do not skip meals when taking insulin or a sulfonylurea — that is how hypoglycaemia happens.',
		 'Avoid alcohol on an empty stomach.'],
		'Know the signs of low sugar — sweating, shaking, confusion — and carry something sweet.',
	),
	'asthma': (
		['Take the preventer inhaler every day, even when breathing is easy.',
		 'Keep the reliever with you and check the dose counter.',
		 'Rinse your mouth after a steroid inhaler to prevent thrush.',
		 'Dust the bedroom, wash bedding hot, and keep animals out of it if they trigger you.',
		 'Use your written action plan when the peak flow drops into yellow.'],
		['Avoid smoke, including cooking smoke and second-hand smoke.',
		 'Avoid cold air and strong perfumes if they set off a cough.',
		 'Do not use the reliever as your only treatment — it does not control the disease.'],
		'A peak flow below half your personal best is an emergency: use the reliever and go now.',
	),
	'epilepsy': (
		['Take the medicine every day at the same time.',
		 'Sleep regular hours — missed sleep is the commonest trigger people can name.',
		 'Tell the people around you what to do: cushion the head, turn on the side, time it, do not '
		 'put anything in the mouth.',
		 'Keep a seizure diary with the date, duration and what happened before it.'],
		['Avoid alcohol and recreational drugs.',
		 'Avoid swimming alone, bathing in a full tub unattended, or working at heights.',
		 'Avoid flickering light and long screen sessions if they trigger you.',
		 'Do not drive until a clinician says the seizures are controlled.'],
		'Never stop the medicine abruptly — it can trigger status epilepticus.',
	),
	'sickle_cell': (
		['Drink plenty of water every day — dehydration makes the cells sickle.',
		 'Keep warm: cold hands, feet and baths set off crises.',
		 'Take folic acid daily and penicillin daily through early childhood.',
		 'Keep vaccinations up to date, especially pneumococcal, Hib and hepatitis B.',
		 'Rest and treat pain early; a crisis caught early needs less medicine.'],
		['Avoid getting cold, and avoid sudden temperature change.',
		 'Avoid strenuous exercise to exhaustion and high altitudes.',
		 'Avoid infection where you can — a fever is an emergency in this condition.',
		 'Avoid anything that reduces blood flow: tight clothing, prolonged pressure on one spot.'],
		'Fever of 38 C or above means go to a facility now, not in the morning.',
	),
	'chronic_kidney': (
		['Control blood pressure and blood sugar — the two commonest causes of kidney damage.',
		 'Drink to thirst unless a clinician has set a limit.',
		 'Keep salt low and eat less processed food.',
		 'Take the medicines for pressure and sugar exactly as prescribed.',
		 'Keep every appointment for creatinine and urine albumin.'],
		['Avoid NSAID painkillers: ibuprofen, diclofenac, naproxen.',
		 'Avoid herbal and traditional preparations that have not been cleared by a clinician.',
		 'Avoid contrast dye studies unless the radiology team knows about your kidneys.',
		 'Avoid smoking.'],
		'Stage G4 and G5 need a clinician\'s diet plan, not general advice — ask at your next review.',
	),
	'hiv': (
		['Take antiretroviral treatment every day at the same time — adherence is what keeps it '
		 'undetectable.',
		 'Keep every clinic appointment; the viral load result decides whether the regimen still works.',
		 'Eat well and treat infections early.',
		 'Tell only who you choose to tell — the record is protected by a separate PIN.'],
		['Do not share razors or toothbrushes.',
		 'Do not stop or switch the regimen without the clinic.'],
		'This guidance is offered with the condition; the HIV record is withheld from any share '
		'without separate consent.',
	),
}


def lifestyle(condition: str, subject_ref: str | None = None) -> LifestyleGuidance:
	"""§MON-003's "Lifestyle guidance", for one condition.

	Keyed on the condition and not the age, because the two lists that matter here — what helps and
	what to avoid — differ by diagnosis at the same age, and `nutrition_guidance` bands by age.
	"""
	key = condition.lower().replace(' ', '_')
	assert key in LIFESTYLE, f'{condition} has no lifestyle guidance'
	guidance, avoid, note = LIFESTYLE[key]
	return LifestyleGuidance(condition=key, subject_ref=subject_ref,
	                         guidance=list(guidance), avoid=list(avoid), note=note)


def lifestyle_for_profile(conditions: list[str]) -> list[LifestyleGuidance]:
	"""Every condition in a profile that has guidance, so a person with two gets both lists."""
	known = [c.lower().replace(' ', '_') for c in conditions]
	return [lifestyle(c) for c in known if c in LIFESTYLE]
