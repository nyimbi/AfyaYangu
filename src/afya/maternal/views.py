"""Maternal health: pregnancy, the 8-contact ANC schedule (Kenya WHO 2016+ model), the birth plan,
trimester guidance, postnatal care, and danger-sign escalation.

§MON-002 prints ten features and the module carried two of them — the schedule and a danger-sign
classifier that wrote a message. The nine below are the rest: a due-date calculator (the section
asks for one and the model took `edd_iso` as an input the caller had already computed), reminders
for the ANC and postnatal contacts, education and a one-tap action behind each danger sign, the
five-field birth plan, guidance that varies by trimester, newborn danger signs, the maternity
finder, and a PMTCT referral.

`CareAction` is §MON-002's "one-tap escalation": the same three-part shape §8.1's `TriageAction`
uses — a kind, a label and an href — with the finder pointed at the maternity one, because a
maternity screen that rendered the general facility search would send a pregnant woman to a list
that is not the list of places that deliver babies.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

ANC_CONTACTS_WEEKS = (12, 20, 26, 30, 34, 36, 38, 40)
DANGER_SIGNS = ('bleeding', 'severe_headache', 'blurred_vision', 'convulsions', 'severe_swelling', 'reduced_fetal_movement', 'fever', 'abdominal_pain', 'water_breaks')

# §MON-002's due-date calculator. Naegele's rule: 280 days from the first day of the last
# menstrual period. A constant rather than a literal in the arithmetic because the section's own
# "Estimated due date calculator" is a claim about which rule is used, and two spellings of 280
# are two rules.
GESTATION_DAYS = 280

# What each danger sign means and what to do about it, so the escalation is not the only thing the
# person is handed. Every key of `DANGER_SIGNS` has a row, asserted below.
DANGER_SIGN_EDUCATION: dict[str, str] = {
	'bleeding': 'Any bleeding in pregnancy is an emergency. Go to the nearest maternity unit now.',
	'severe_headache': 'A headache that will not go, or comes with blurred vision, can be a sign of high blood pressure.',
	'blurred_vision': 'Blurred vision with swelling can mean pre-eclampsia. It needs treatment today.',
	'convulsions': 'A fit in pregnancy is an emergency. Clear the space and call 719 at once.',
	'severe_swelling': 'Sudden swelling of the face and hands can mean pre-eclampsia. Get checked today.',
	'reduced_fetal_movement': 'If the baby moves less than usual, go to the clinic the same day.',
	'fever': 'A fever in pregnancy needs testing and treatment. Do not wait to see if it passes.',
	'abdominal_pain': 'Severe or constant stomach pain is not normal in pregnancy. Get seen now.',
	'water_breaks': 'If your waters break, go to the maternity unit even with no pain.',
}

# §MON-002's "Trimester-specific guidance". Keyed by the trimester the week falls in, because the
# section asks for guidance that varies by trimester and one paragraph served at week 12 and week
# 40 is the same guidance at two different points in a pregnancy.
TRIMESTER_GUIDANCE: dict[int, tuple[str, tuple[str, ...]]] = {
	1: (
		'The first three months: the baby\'s organs form now, so this is when alcohol and smoking do the most harm.',
		('Start antenatal visits', 'Take folic acid daily', 'Eat small meals if nausea is bad', 'Test for HIV, syphilis and malaria'),
	),
	2: (
		'The middle months are usually the easiest. The baby grows quickly and starts to move.',
		('Keep every ANC visit', 'Sleep under a net every night', 'Plan where you will deliver', 'Watch for swelling of the face or hands'),
	),
	3: (
		'The last months: prepare for delivery and know the danger signs by heart.',
		('Agree how you will reach the facility', 'Save money and arrange a blood donor', 'Go in at once if the waters break', 'Know that 719 is free'),
	),
}

# WHO's postnatal contacts: within 24 hours of birth, on day 3, between day 7 and 14, and at week 6.
# The section asks for postnatal visit reminders and `ANC_CONTACTS_WEEKS` stops at 40, so there was
# no contact after delivery to remind anyone about.
POSTNATAL_CONTACTS: tuple[tuple[int, str], ...] = (
	(1, 'Within 24 hours of birth'),
	(3, 'Day 3: check feeding, cord and weight'),
	(14, 'Between day 7 and day 14: check the mother and the baby'),
	(42, 'Week 6: family planning, immunisation start and a final check'),
)

# §MON-002's "Newborn danger signs". `DANGER_SIGNS` is nine signs of the mother; a newborn's are a
# different list, and a screen showing the mother's list to a parent with a sick baby shows the
# wrong thing.
NEWBORN_DANGER_SIGNS: tuple[tuple[str, str], ...] = (
	('not_feeding', 'The baby stops feeding or refuses the breast.'),
	('convulsions', 'The baby has a fit or shakes.'),
	('fast_breathing', 'The baby breathes fast, or the ribs pull in with each breath.'),
	('very_hot', 'The baby feels very hot, or has a temperature of 38 degrees or more.'),
	('very_cold', 'The baby feels cold to touch even when covered.'),
	('yellow_skin', 'The skin or the whites of the eyes turn yellow.'),
	('cord_infection', 'The cord stump is red, smells, or has pus.'),
	('no_movement', 'The baby is floppy, or does not wake to feed.'),
)

# §MON-002's "Referral to PMTCT where relevant". Relevance is the mother's HIV status, which is
# asked at the point of care and not stored here (§17, and §MON-003's separate-PIN rule for HIV).
PMTCT_PROGRAMME = 'Prevention of Mother-to-Child Transmission clinic'
PMTCT_RELEVANT = 'An HIV-positive result in pregnancy is a referral to PMTCT the same day. Treatment started early protects the baby.'


class Pregnancy(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	edd_iso: str  # estimated date of delivery
	delivery_plan_facility_id: str | None = None
	lmp_week: int = Field(default=8, ge=1, le=42)
	# §MON-002's "Estimated due date calculator" computes `edd_iso` from this. Optional because a
	# woman who arrives with a date from her clinic card has one and no LMP, and refusing her
	# registration over a date the app does not need would lose the record the section is for.
	lmp_iso: str | None = None


class BirthPlan(BaseModel):
	"""§MON-002's "Birth plan builder (facility, transport, birth companion, blood donor, funds)".

	Five named fields because the section names five, and each is optional so the plan can be built
	over several conversations rather than in one sitting. `gaps()` is what makes an incomplete plan
	useful: a plan with three of five filled is not a plan, and a screen that rendered it without
	saying which two are missing would look finished.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	facility_id: str | None = None
	transport: str | None = Field(default=None, max_length=120)
	birth_companion: str | None = Field(default=None, max_length=80)
	blood_donor: str | None = Field(default=None, max_length=80)
	funds_kes: int | None = Field(default=None, ge=0, le=1_000_000)

	def gaps(self) -> list[str]:
		"""The fields the section names that this plan has not answered, in the section's order."""
		fields = ('facility_id', 'transport', 'birth_companion', 'blood_donor', 'funds_kes')
		return [f for f in fields if getattr(self, f) in (None, '')]


class ANCVisit(BaseModel):
	"""One ANC contact with the date it falls on, which is what a reminder needs.

	`ANC_CONTACTS_WEEKS` is a week number and a reminder is a date, so the conversion has to happen
	somewhere: a client that had the week and the LMP would compute it, and one that had neither
	would show a person "contact 3" with no day to put it in a calendar.
	"""

	model_config = MODEL_CONFIG
	contact_no: int = Field(ge=1, le=8)
	gest_week: int = Field(ge=1, le=42)
	due_iso: str
	done: bool = False
	remind_days_before: list[int] = []


class PostnatalVisit(BaseModel):
	model_config = MODEL_CONFIG
	day_after_birth: int = Field(ge=1, le=60)
	due_iso: str
	what: str


class NewbornDangerSign(BaseModel):
	"""One §MON-002 newborn danger sign. A model rather than a dict because the route serves it and
	a dict is a shape nothing validates — the client reads `sign` and `means` off a named field."""

	model_config = MODEL_CONFIG
	sign: str
	means: str


class CareAction(BaseModel):
	"""§MON-002's "one-tap escalation", as the two ways the section's danger signs send someone.

	`TriageAction` carries the same shape for §8.1's three. Two here rather than three because a
	maternity emergency has two answers — call 719, or get to a facility that delivers — and a third
	kind nothing produces would be a pattern member that is a claim rather than a capability.
	"""

	model_config = MODEL_CONFIG
	kind: str = Field(pattern=r'^(call|find_maternity)$')
	label: str = Field(min_length=1)
	href: str = Field(min_length=1)


class PmtctReferral(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	relevant: bool
	programme: str | None = None
	advise: str


class DangerEducation(BaseModel):
	"""One danger sign, what it means, and what to do — §MON-002's "danger sign education" half.

	The sign list and the education are one payload rather than two, because the section joins them:
	a screen that named nine signs and explained none of them is a list a person cannot act on, and
	`action` is the same object for every sign so the client renders one button, not nine.
	"""

	model_config = MODEL_CONFIG
	sign: str
	means: str
	action: CareAction

# Every sign the section prints has education behind it, asserted at import rather than discovered
# when a screen renders a sign with no explanation under it.
assert set(DANGER_SIGN_EDUCATION) == set(DANGER_SIGNS), 'a danger sign with no education is a word on a screen'
assert set(TRIMESTER_GUIDANCE) == {1, 2, 3}, 'a trimester with no guidance is a gap in the pregnancy'
assert len(NEWBORN_DANGER_SIGNS) >= 8, 'the newborn list is the section\'s own'


class ANCRecord(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	contact_no: int = Field(ge=1, le=8)
	done_iso: str
	facility_id: str | None = None


class DangerAssessment(BaseModel):
	model_config = MODEL_CONFIG
	signs: list[str]
	escalate: bool
	message: str
	# §MON-002's "danger sign education": what each sign the person reported means.
	education: list[DangerEducation] = []
	# And its "one-tap escalation": the button, rendered by the server for the reason §8.1's is.
	action: CareAction | None = None