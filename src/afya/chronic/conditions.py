"""§MON-003's three conditions with no reading behind them, and the thresholds they hang on.

§9.1 lists seven conditions a chronic disease log supports. Four had a reading — a BP cuff, a
glucometer, a peak-flow meter, and HIV's separate PIN. Epilepsy, sickle cell disease and chronic
kidney disease had nothing: `ConditionProfile.conditions` would accept the string and no threshold,
guidance or danger sign keyed on it, so the log recorded a diagnosis it could not act on.

Every number here comes from a published source, archived in `sources/clinical-thresholds/` with
`INDEX.md` recording what each one does and does not support. Where a source states no threshold the
implementation carries no threshold rather than a plausible one — a dose invented to fill a table is
worse than a table with a gap, because the gap is visible and the invention is not.
"""
from afya.chronic.views import ConditionReading, KidneyFunction, SeizureEvent, SickleCrisis

# --- epilepsy (§MON-003 "Epilepsy") -----------------------------------------------------------

SEIZURE_EMERGENCY_MINUTES = 5
"""ILAE 2015's `t1` for generalised tonic-clonic seizures: the duration at which a seizure is treated
as continuous and treatment begins. Before this it is a seizure; after it, it is an emergency."""

STATUS_EPILEPTICUS_MINUTES = 30
"""ILAE 2015's `t2`: the duration past which the definition states long-term harm is likely. The
distinction matters because `t1` is when to act and `t2` is when the outcome is already worse."""

DANGER_SIGNS = {
	'epilepsy': (
		'a seizure lasting 5 minutes or longer',
		'a second seizure starting before the first has ended',
		'difficulty breathing or a blue tinge to the lips after a seizure',
		'a seizure in water, or a first-ever seizure',
		'pregnancy with any seizure',
	),
	'sickle_cell': (
		'fever of 38 C or above — infection is the leading cause of death in sickle cell disease',
		'chest pain, wheezing or difficulty breathing (acute chest syndrome)',
		'left-sided abdominal pain or a swollen, tender spleen (splenic sequestration)',
		'sudden weakness, slurred speech or one-sided numbness (stroke)',
		'pain not controlled by the medicines at home, or a headache with vomiting',
		'pale palms, dizziness or a racing heart (a falling haemoglobin)',
	),
	'chronic_kidney': (
		'passing much less urine than usual, or none',
		'swelling of the legs, face or whole body',
		'breathlessness at rest, or nausea and vomiting that will not stop',
		'confusion, drowsiness or a fit',
		'itching all over with muscle cramps and a metallic taste',
	),
}

PROPHYLAXIS = {
	'sickle_cell': (
		'Daily penicillin through early childhood (WHO: "recommended daily during the first 5 years '
		'of life"). No milligram dose is stated in the archived source, so none is given here.',
		'Routine pneumococcal, Haemophilus influenzae type b and hepatitis B vaccination.',
		'Folic acid supplements.',
		'Hydroxyurea where a clinician prescribes it — it reduces the frequency of painful crises.',
	),
	'epilepsy': (
		'Antiseizure medicine taken every day, not only when a seizure happens.',
		'Carbamazepine or lamotrigine are first-line for focal seizures; valproate for generalised.',
		'Do not stop the medicine without a clinician: stopping abruptly can trigger status.',
		'Avoid triggers you can name — sleep loss, missed doses, alcohol, flickering light.',
	),
	'chronic_kidney': (
		'Control blood pressure and blood sugar — the two commonest causes of kidney damage.',
		'Avoid NSAID painkillers (ibuprofen, diclofenac) and any herbal preparation not cleared.',
		'Keep salt low and drink to thirst rather than to a target.',
		'Have creatinine and urine albumin checked at the interval your stage requires.',
	),
}

# --- chronic kidney disease (§MON-003 "Chronic kidney disease") -------------------------------

KIDNEY_STAGES: tuple[tuple[str, float, float, str], ...] = (
	# label, eGFR low (inclusive), eGFR high (exclusive), the KDIGO description
	('G1', 90.0, float('inf'), 'normal or high'),
	('G2', 60.0, 90.0, 'mildly decreased'),
	('G3a', 45.0, 60.0, 'mildly to moderately decreased'),
	('G3b', 30.0, 45.0, 'moderately to severely decreased'),
	('G4', 15.0, 30.0, 'severely decreased'),
	('G5', 0.0, 15.0, 'kidney failure'),
)
"""KDIGO 2012's GFR categories, as the archived table gives them. `G3` is split into `G3a` and
`G3b` because the guideline splits it: the two carry different risks and different monitoring
intervals, and a single `G3` would put a person at 46 and a person at 31 in one bucket."""

ALBUMINURIA_STAGES: tuple[tuple[str, float, float, str], ...] = (
	('A1', 0.0, 30.0, 'normal to mildly increased'),
	('A2', 30.0, 300.0, 'moderately increased'),
	('A3', 300.0, float('inf'), 'severely increased'),
)
"""KDIGO's albuminuria categories, ACR in mg/g. The archived article prints the table's numbers
without units and elsewhere gives a referral threshold in mg/mmol; the mg/g reading is the one the
KDIGO table uses and the one stated in its own definition of kidney damage ("ACR >= 30")."""

CKD_SUSTAINED_DAYS = 90
"""KDIGO: "the abnormalities must be present for at least three months". A single low eGFR is an
acute finding and a different clinical problem; CKD is the sustained one, so the staging refuses to
be made from one reading."""


def egfr_ckdepi_2021(creatinine_mg_dl: float, age_years: int, sex: str) -> float:
	"""CKD-EPI 2021 eGFR in mL/min/1.73 m², from serum creatinine, age and sex.

	The 2021 revision of the equation the NKF recommends. It dropped the race coefficient the 2009
	version carried, which is the version to use everywhere and especially here: a coefficient fitted
	on one population's muscle mass applied to another is a systematic error wearing a correction's
	clothes, and the 2021 equation does not need it.

	`Scr` is in mg/dL standardised to IDMS. A lab reporting µmol/L is converted by the caller, since
	the conversion factor is a property of the assay and not of this formula.
	"""
	assert creatinine_mg_dl > 0, 'creatinine is a positive concentration'
	assert 18 <= age_years <= 120, f'{age_years} is not an adult age for this equation'
	assert sex in ('male', 'female'), f'the equation is sex-specific, not {sex!r}'
	kappa = 0.7 if sex == 'female' else 0.9
	alpha = -0.241 if sex == 'female' else -0.302
	ratio = creatinine_mg_dl / kappa
	egfr = (142.0 * min(ratio, 1.0) ** alpha * max(ratio, 1.0) ** -1.200
	        * 0.9938 ** age_years * (1.012 if sex == 'female' else 1.0))
	return round(egfr, 1)


def kidney_stage(egfr: float) -> str:
	"""The KDIGO GFR category for an eGFR, or a refusal if it is not a possible value."""
	assert 0 < egfr <= 250, f'{egfr} is not an eGFR'
	for label, low, high, _ in KIDNEY_STAGES:
		if low <= egfr < high:
			return label
	assert False, 'the categories cover every positive eGFR'


def albuminuria_stage(acr_mg_g: float) -> str:
	"""The KDIGO albuminuria category for an albumin-creatinine ratio in mg/g."""
	assert acr_mg_g >= 0, 'a ratio is not negative'
	for label, low, high, _ in ALBUMINURIA_STAGES:
		if low <= acr_mg_g < high:
			return label
	assert False, 'the categories cover every non-negative ratio'


def assess_kidney(reading: KidneyFunction, today_iso: str | None) -> ConditionReading:
	"""Stage one kidney reading, and say whether it is CKD or an isolated finding.

	A single eGFR below 60 is a finding, not a diagnosis. KDIGO requires three months, so this
	reports the stage for the reading and separately whether the *history* sustains it — a person
	whose only reading is low is told to repeat it, not told they have kidney disease.

	An undated reading is staged and never called sustained. Dating it from the clock would compare
	a prior reading of unknown age against today, and the answer to "how long has this been going
	on" would be whatever the server's date happened to be.
	"""
	egfr = egfr_ckdepi_2021(reading.creatinine_mg_dl, reading.age_years, reading.sex)
	stage = kidney_stage(egfr)
	albuminuria = albuminuria_stage(reading.acr_mg_g) if reading.acr_mg_g is not None else None
	sustained = bool(
		today_iso and reading.prior_egfr is not None and reading.prior_egfr_iso is not None
		and egfr < 60 and reading.prior_egfr < 60
		and _days_between(reading.prior_egfr_iso, today_iso) >= CKD_SUSTAINED_DAYS
	)
	if sustained:
		summary = (f'eGFR {egfr} ({stage}, {_describe(stage)}) confirmed on two readings at least '
		           f'three months apart — this meets the KDIGO definition of chronic kidney disease.')
	elif egfr < 60 and today_iso:
		summary = (f'eGFR {egfr} ({stage}, {_describe(stage)}) on this reading. One low value is not '
		           f'chronic kidney disease: repeat it in three months, because KDIGO requires the '
		           f'abnormality to persist that long.')
	elif egfr < 60:
		summary = (f'eGFR {egfr} ({stage}, {_describe(stage)}) on an undated reading. KDIGO needs the '
		           f'abnormality sustained for three months, so nothing here can say whether this is '
		           f'chronic: send the reading with its date and the prior one.')
	else:
		summary = f'eGFR {egfr} ({stage}, {_describe(stage)}).'
	if albuminuria and albuminuria != 'A1':
		summary += f' Urine albumin is raised ({albuminuria}).'
	escalate = egfr < 30 or (albuminuria == 'A3')
	return ConditionReading(
		condition='chronic_kidney', escalate=escalate, summary=summary,
		measure={'egfr': egfr, 'stage': stage, 'albuminuria': albuminuria or 'not measured',
		         'sustained': sustained},
		danger_signs=list(DANGER_SIGNS['chronic_kidney']) if escalate else [],
	)


def _describe(stage: str) -> str:
	return next(desc for label, _, _, desc in KIDNEY_STAGES if label == stage)


def _days_between(iso_a: str, iso_b: str) -> int:
	from datetime import date
	a = date(*(int(p) for p in iso_a[:10].split('-')))
	b = date(*(int(p) for p in iso_b[:10].split('-')))
	return (b - a).days


# --- epilepsy and sickle cell: the ladders ------------------------------------------------------

def assess_seizure(event: SeizureEvent) -> ConditionReading:
	"""§MON-003's escalation for a seizure, at ILAE's two time points rather than at one.

	Five minutes is when to act and thirty is when the outcome is already worse, so a single
	threshold would either call a treatable seizure an emergency or a harmful one a wait. A cluster
	(another seizure before recovery) escalates regardless of duration, because the definition treats
	it as continuous.
	"""
	minutes = event.duration_seconds / 60.0
	if minutes >= STATUS_EPILEPTICUS_MINUTES:
		state, escalate = 'status_epilepticus', True
		action = ('This has lasted 30 minutes or more: status epilepticus. Call 719 now — this is a '
		          'medical emergency and needs hospital treatment.')
	elif minutes >= SEIZURE_EMERGENCY_MINUTES or event.cluster:
		state, escalate = 'emergency', True
		action = ('A seizure at 5 minutes or more, or a cluster, is treated as continuous. Give the '
		          'rescue medicine from your plan if you have one, call 719, and do not leave the '
		          'person alone.')
	else:
		state, escalate = 'recovered', False
		action = ('A seizure under 5 minutes that has ended. Time the next one, note what happened, '
		          'and tell your clinician — two or more unprovoked seizures is epilepsy.')
	if event.pregnant:
		escalate = True
		action += ' Any seizure in pregnancy needs same-day clinical review.'
	return ConditionReading(
		condition='epilepsy', escalate=escalate,
		summary=f'{minutes:.1f} minute seizure: {state}. {action}',
		measure={'minutes': round(minutes, 1), 'state': state, 'cluster': event.cluster},
		danger_signs=list(DANGER_SIGNS['epilepsy']) if escalate else [],
	)


SICKLE_FEVER_C = 38.0
"""The threshold at which a fever in sickle cell disease is an emergency. The archived sources state
that infection is a leading cause of death in this condition and that pneumococcal and salmonella
infections are the severe ones, and that functional asplenia begins in infancy; they do not print a
temperature. 38 C is the standard definition of fever and the point at which the guidance to seek
care attaches, and it is named as an assumption rather than presented as a sourced figure."""

SICKLE_CRISIS_SIGNS = frozenset({'chest_pain', 'breathing_difficulty', 'spleen_pain', 'stroke_signs',
                                 'uncontrolled_pain', 'sudden_pallor'})


def assess_sickle_crisis(crisis: SickleCrisis) -> ConditionReading:
	"""A painful crisis, and the four things that make it more than one.

	The archived sources give the danger signs but no severity score, so this does not invent one: it
	escalates on the signs themselves — acute chest syndrome, splenic sequestration, stroke and a
	falling haemoglobin — and otherwise reports a crisis to be managed at home with the pain relief
	the person already has.
	"""
	flagged = sorted(set(crisis.signs) & SICKLE_CRISIS_SIGNS)
	fever = crisis.temperature_c >= SICKLE_FEVER_C
	escalate = fever or bool(flagged)
	if fever:
		action = ('Fever of 38 C or above in sickle cell disease is an emergency: the spleen stops '
		          'filtering bacteria early in life, so what is a mild infection in another child can '
		          'be blood poisoning here. Go to a facility now.')
	elif flagged:
		action = (f'{", ".join(s.replace("_", " ") for s in flagged)} — this is a complication of the '
		          f'crisis, not the crisis itself. Go to a facility now.')
	else:
		action = ('A painful crisis without any of the danger signs. Rest, warm the painful area, '
		          'drink plenty, and take the pain relief you have been given — the WHO guidance names '
		          'paracetamol, ibuprofen and opioids. Come back if fever or any danger sign appears.')
	return ConditionReading(
		condition='sickle_cell', escalate=escalate,
		summary=f'Pain score {crisis.pain_score}/10. {action}',
		measure={'pain_score': crisis.pain_score, 'temperature_c': crisis.temperature_c,
		         'signs': flagged or ['none of the danger signs']},
		danger_signs=list(DANGER_SIGNS['sickle_cell']) if escalate else [],
	)
