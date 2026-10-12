"""Triage domain models (spec TRI-001/002/003, §6.3 malaria trap, §8.1)."""
from enum import Enum

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from afya.ids import uuid7str

from afya.derived import DerivedFields

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class RiskLevel(str, Enum):
	"""§8.1's risk classification, which is a *clinical ladder* and not a severity score.

	The section prints five outputs — Emergency / High (Ebola suspicion) / High (other cause) /
	Moderate / Low — and the enum had four members, none of which separated Ebola suspicion from
	other high-risk fever. That is not a naming gap: the two send a person to different places. An
	Ebola suspect is isolated and notified to the county under IDSR; a severe malaria or typhoid
	case goes to a treatment unit. Collapsing them means the triage answer cannot say which.

	`emergency` is the fifth and it is the bleeding branch. §8.1 lists unexplained bleeding first
	among its red flags and the algorithm already treated it as the top rung, but it returned
	`high` — the same value as a contact-history fever, so a client could not tell a haemorrhagic
	case from an exposure risk.
	"""

	low = 'low'
	medium = 'medium'
	malaria_suspect = 'malaria_suspect'
	high_other = 'high_other'
	high_ebola_suspicion = 'high_ebola_suspicion'
	emergency = 'emergency'


EBOLA_SYMPTOMS: frozenset[str] = frozenset({'fever', 'headache', 'muscle_pain', 'sore_throat', 'vomiting', 'diarrhoea', 'rash', 'bleeding'})

# §8.1's red flags, verbatim: "unexplained bleeding, bleeding gums, blood in stool or vomit,
# bruising without cause, confusion, difficulty breathing, inability to drink, convulsions". They
# are the inputs the section prints as a separate list from the symptom multi-select, and
# `TriageInput.red_flags` carries them under those own names rather than folded into `symptoms` —
# a client rendering the two lists cannot do it from one merged list.
RED_FLAGS: tuple[str, ...] = (
	'unexplained_bleeding', 'bleeding_gums', 'blood_in_stool_or_vomit', 'bruising_without_cause',
	'confusion', 'difficulty_breathing', 'inability_to_drink', 'convulsions',
)

# The red flags that mean the person cannot wait for a call back. §8.1 lists them under the same
# heading, but "confusion" and "convulsions" are the ones where the answer is an ambulance rather
# than advice, and the section's first output rung is named Emergency for exactly this.
EMERGENCY_FLAGS: frozenset[str] = frozenset({'unexplained_bleeding', 'blood_in_stool_or_vomit', 'convulsions', 'inability_to_drink'})

# The watch-for list §8.1's third output asks for, "for the next 24–48 hours". Written as the
# deterioration signs a person can actually check on themselves at home, because a watch-for list
# that names clinical findings is a list nobody can use. Each entry is (sign, what to do).
WATCH_FOR: tuple[tuple[str, str], ...] = (
	('bleeding that will not stop, or blood in vomit or stool', 'call 719 now'),
	('vomiting everything, or unable to drink', 'call 719 now'),
	('confusion or drowsiness', 'call 719 now'),
	('difficulty breathing', 'call 719 now'),
	('fever still above 38 °C after 48 hours', 'go to a facility and ask for a malaria test'),
	('no urine for a day, or sunken eyes', 'go to a facility now — this is dehydration'),
	('rash, or bleeding gums', 'call 719 and mention the rash or bleeding'),
)

# §11.2 TRI-003's four exposure routes, each with the fact that makes it one. The strings are the
# section's own names, snake_cased, and they are a closed vocabulary validated on the model for the
# reason `RED_FLAGS` is: an exposure list a client can extend is an exposure list the classifier
# cannot reason about.
#
# The evidence is `sources/ebola-transmission/` — WHO's Ebola disease fact sheet (24 April 2025) and
# CDC's About Ebola Disease page — and each entry is the source's own mechanism rather than a
# restatement of it:
#
# - `funeral_attendance` and `case_contact` are the two the WHO fact sheet states outright —
#   "close contact with patients when infection control precautions are not strictly practiced" and
#   "burial ceremonies that involve direct contact with the body of a person who has died".
# - `healthcare_work` is the same sentence from the other side: the source's qualifier is *without
#   precautions*, so the exposure is unprotected clinical contact, not the occupation.
# - `bushmeat_consumption` is the animal-source route. The fact sheet's wording is contact with "the
#   blood, secretions, organs or other bodily fluids of infected animals such as fruit bats,
#   chimpanzees, gorillas, monkeys, forest antelope or porcupines found ill or dead" — it does not
#   say that eating cooked bushmeat transmits Ebola, and neither does this code. What the field
#   records is the exposure a triage clinician asks about, and `EXPOSURE_NOTE` says what it means.
EBOLA_EXPOSURES: tuple[str, ...] = (
	'funeral_attendance', 'healthcare_work', 'case_contact', 'bushmeat_consumption',
)

# What each exposure means for the person reading the answer. Written as the *action*, because an
# exposure is not a diagnosis and a list of routes with no instruction is a frightening fact with no
# use. Every one of the four ends at the same place — the 21-day window — because the WHO fact sheet
# gives one incubation range for the disease, not one per route.
EXPOSURE_NOTE: dict[str, str] = {
	'funeral_attendance': 'You were near the body of someone who had died. That is the contact Ebola spreads through, so the next 21 days are the window to watch.',
	'healthcare_work': 'You cared for a sick person without full protective equipment. Watch yourself for 21 days and tell 719 that you had unprotected contact.',
	'case_contact': 'You were in close contact with someone who may have had Ebola. Watch yourself for 21 days and call 719 if any fever or symptom starts.',
	'bushmeat_consumption': 'You handled or ate meat from a wild animal found sick or dead. Watch yourself for 21 days and call 719 if a fever starts.',
}

# §11.2 TRI-003's isolation status, as the states a person can actually be in rather than a boolean.
# `not_isolated` is a member and it is the one that matters: "isolate now" is advice, and advice
# given to someone already isolating is a different message from advice given to someone who is not.
ISOLATION_STATES: tuple[str, ...] = ('not_isolated', 'isolated_at_home', 'isolated_at_facility')

# §11.2 TRI-003's "Isolation guidance for the household". The mechanism is the source's — Ebola
# spreads by direct contact with blood and body fluids — and the arrangements are the standard
# treatment-unit ones. The first line says which is which, because the WHO fact sheet states the
# mechanism and gives no home-care procedure, and a guidance block that implies otherwise is a
# citation the source does not carry. See `sources/INDEX.md`, "Ebola transmission".
HOUSEHOLD_ISOLATION_GUIDANCE: tuple[str, ...] = (
	'The virus passes through direct contact with blood or body fluids, so the aim is that nobody else touches them.',
	'One room for the sick person, and one caregiver who is the only person who goes in. No visitors.',
	'If there is no separate room, keep at least two metres away and sleep in a different room.',
	'A separate latrine or bucket for the sick person, emptied by the caregiver only.',
	'The caregiver covers hands and face before going in, and washes with soap and running water after every visit.',
	'Bedding, clothes and anything with blood or fluid on it stays in the room and is not washed by hand — ask 719 who collects it.',
	'No one else prepares or shares food with the sick person. Use separate plates and cutlery and wash them separately.',
	'If the person dies, do not wash, touch or kiss the body. Call 719 for a safe and dignified burial team.',
)

# §11.2 TRI-003's third Output, "Immediate action (call 719, do not travel by public transport, await
# instructions)". Three instructions and the section prints them in this order. Rendered as a model
# rather than as a sentence appended to `recommendation`, because the recommendation is a *clinical*
# string with a translation table behind it (§ACC-002) and this is an operational instruction set a
# client renders as a checklist — folding it into the sentence would put it in a language table's
# scope and behind a translator who never saw it.
IMMEDIATE_ACTIONS: tuple[tuple[str, str, str], ...] = (
	('call', 'Call 719 now and say you may have Ebola',
	 'Tell them where you are, that you have symptoms, and whether you had contact with a case or attended a funeral.'),
	('do_not_travel', 'Do not travel by public transport',
	 'Do not take a matatu, bus or boda. You would be sitting close to other people for the whole journey.'),
	('await_instructions', 'Stay where you are and wait to be told what to do',
	 'The county team will tell you which facility to go to and will send transport if you need it. Do not go to a clinic unannounced.'),
)


class TriageInput(DerivedFields, BaseModel):
	model_config = MODEL_CONFIG
	symptoms: list[str] = []
	temperature_c: float = Field(default=36.5, ge=30, le=45)
	ebola_contact: bool = False
	affected_area_travel: bool = False
	# §8.1's two remaining Inputs lists. `red_flags` is its own list in the spec, distinct from the
	# symptom multi-select, and `exposure_site` is the third epidemiological criterion — "attendance
	# at a known exposure site" — which had no field at all, so a person who attended a funeral of a
	# known case could only be triaged by claiming contact.
	red_flags: list[str] = []
	exposure_site: bool = False
	# §11.2 TRI-003's "Additional inputs", which are TRI-001's epidemiological criteria asked in more
	# detail. The section names four routes and the input had one boolean, so a funeral and a
	# bushmeat exposure read identically to the classifier — and they are not the same exposure:
	# a funeral is contact with a body, bushmeat is contact with an animal source. `EBOLA_EXPOSURES`
	# is the closed list; `exposure_note` says what each one means to the person who reported it.
	exposures: list[str] = []
	# §11.2 TRI-003's isolation status. Optional, because a triage is still a triage without it, and
	# `None` is a third answer: the person was not asked. "Not asked" and "not isolated" produce
	# different guidance — the first has to say what isolation means, the second only where to do it.
	isolation: str | None = Field(default=None, pattern=r'^(not_isolated|isolated_at_home|isolated_at_facility)$')
	age_band: str | None = Field(default=None, pattern=r'^(under_5|5_17|18_49|50_64|65_plus)$')
	pregnant: bool | None = None
	# §11.7 AI-003's first bullet is "sudden increase in fever triage *in a locality*", and a
	# locality is a county. Without it the early-warning collector counts a national number against a
	# county baseline, which is a signal that cannot mean anything. Optional because a triage is
	# still a triage without it — it is the surveillance dimension, not a clinical input.
	county: str | None = None

	def model_post_init(self, _context: object) -> None:
		assert all(f in RED_FLAGS for f in self.red_flags), \
			f'unknown red flag: {[f for f in self.red_flags if f not in RED_FLAGS]}'
		assert all(e in EBOLA_EXPOSURES for e in self.exposures), \
			f'unknown exposure: {[e for e in self.exposures if e not in EBOLA_EXPOSURES]}'

	@computed_field
	@property
	def exposure_history(self) -> bool:
		"""§8.1's epidemiological criteria, as one fact.

		All three — travel to an affected area within 21 days, contact with a known or suspected
		case, attendance at a known exposure site — are the same clinical question: has this person
		been where the virus is? Three booleans that must be OR-ed at each use site is the shape that
		drifts, and the `or` was already written twice in the algorithm. Derived rather than passed so
		the two spellings cannot disagree.

		§11.2's four named exposures feed it too, and that is the whole point of the field: the
		section's own three criteria *are* the general form of the four, so a person who reports
		healthcare work without precautions has contact history whether or not they also ticked the
		boolean. `case_contact` maps onto `ebola_contact` and `funeral_attendance` onto
		`exposure_site`, but the mapping is done here rather than left to the caller — a client that
		had to know which of the four implies which of the three would be the second place the two
		lists are related.
		"""
		return (self.ebola_contact or self.affected_area_travel or self.exposure_site
			or bool(self.exposures))

	@computed_field
	@property
	def exposure_notes(self) -> list[str]:
		"""What each reported exposure means, in the order the source lists them.

		Ordered by `EBOLA_EXPOSURES` rather than by the order the client sent them, so the same set
		of exposures renders the same way twice — a list that reshuffles with the request is a list
		the reader has to re-read.
		"""
		return [EXPOSURE_NOTE[e] for e in EBOLA_EXPOSURES if e in self.exposures]


class TriageAction(BaseModel):
	"""§8.1's second Output, "recommended action with one-tap execution".

	The three the section names are "call 719, find facility, request CHW visit". `recommendation`
	is prose and `escalate_719` is a boolean, so a client had a sentence and a flag and no way to
	execute either — the same gap §INF-006's directory had, and the same fix: the server renders
	what the client opens. `href` is a URI the device already knows how to handle (`tel:`, or this
	API's own path), and `kind` says which, so a client dispatches without parsing the label.

	`find_facility` and `request_chw` point at API paths rather than device schemes because they
	are the app's own screens: the search is `/places/facilities/nearest` and the CHW request is a
	task the CHW service already accepts. Rendering them as `kind` values keeps the client from
	having to know which of the three is a phone call and which is a screen.
	"""

	model_config = MODEL_CONFIG
	kind: str = Field(pattern=r'^(call|find_facility|request_chw)$')
	label: str = Field(min_length=1)
	href: str = Field(min_length=1)


class WatchForItem(BaseModel):
	model_config = MODEL_CONFIG
	sign: str = Field(min_length=1)
	action: str = Field(min_length=1)


class ImmediateAction(BaseModel):
	"""§11.2 TRI-003's second Output, "Immediate action (call 719, do not travel by public transport,
	await instructions)".

	Three instructions, each with what it means in practice. `step` is the section's own name for the
	instruction and is a closed vocabulary (`IMMEDIATE_ACTIONS`), so a client can lay the three out in
	order and a test can assert all three are present — the audit's finding was that the high-risk
	recommendation named 719 and isolation and the transport instruction was simply absent, which is
	a missing instruction no client could recover.
	"""

	model_config = MODEL_CONFIG
	step: str = Field(pattern=r'^(call|do_not_travel|await_instructions)$')
	instruction: str = Field(min_length=1)
	detail: str = Field(min_length=1)


class HouseholdIsolation(BaseModel):
	"""§11.2 TRI-003's third Output, "Isolation guidance for the household".

	`already_isolating` is carried because the same eight lines read differently to a person who has
	already moved out of the shared room and one who has not: the first needs the lines confirmed,
	the second needs them as instructions. `guidance` is the list either way — the section asks for
	guidance, not for a filtered subset of it — and the flag is what a client uses to decide whether
	to lead with "keep doing this" or with "start now".
	"""

	model_config = MODEL_CONFIG
	already_isolating: bool = False
	guidance: list[str] = Field(min_length=1)
	# The source's own distinction, carried so the block does not read as a citation it cannot
	# support: the mechanism is WHO's, the home arrangements are standard treatment-unit practice.
	provenance: str = Field(min_length=1)


class TriageResult(BaseModel):
	model_config = MODEL_CONFIG
	risk_level: RiskLevel
	recommendation: str
	treated_as_malaria_first: bool
	escalate_719: bool
	# The language the recommendation is actually in. §ACC-002 names six voice languages and only two
	# have string tables, so a request for Dholuo is answered in English — and this field is what
	# keeps that from being invisible. A client that renders `recommendation` without reading this
	# would present English to a Dholuo speaker as if it were her language.
	served_in: str = 'en'
	# True when `served_in` is not the language that was asked for, so a channel can add its own
	# "this is in English" preamble rather than silently substituting.
	language_fallback: bool = False
	# §8.1's remaining three Outputs. `actions` is the one-tap execution, `watch_for` is the
	# 24–48 hour list, and the summary card is derived below rather than stored — see `summary_card`.
	actions: list[TriageAction] = []
	watch_for: list[WatchForItem] = []
	# True when the classification came from a red flag rather than from the fever ladder, so a
	# clinician reading the card can see which branch produced it. A person who arrived with
	# convulsions and no fever is `emergency` by a different path than one with bleeding.
	red_flag_triggered: bool = False
	# §11.2 TRI-003's second and third Outputs. Both are empty on every rung except Ebola suspicion,
	# and the validator below is what keeps that true — see `_ebola_branch_carries_its_outputs`.
	immediate_actions: list[ImmediateAction] = []
	household_isolation: HouseholdIsolation | None = None
	# §11.2 TRI-003's Escalation: "an automatic, consented notification to the county rapid response
	# team if the user opts in". The opt-in is the caller's, because the consent lives in §SEC-001's
	# ledger and is read by the service that holds it; this field is what the *answer* says about
	# whether the notification went. `county_rrt_notified` is false both when the person declined
	# and when the branch is not the Ebola one, and `county_rrt_note` says which — a client cannot
	# tell a decline from a non-event, and a person who declined must not be told a team was told.
	county_rrt_notified: bool = False
	county_rrt_note: str = ''

	@model_validator(mode='after')
	def _ebola_branch_carries_its_outputs(self) -> Self:
		"""§11.2 prints the transport instruction and the household guidance as Outputs of the Ebola
		branch, and an Output that is present on the wrong rung is as wrong as one missing from the
		right rung.

		"Await instructions" is not a sentence for a person with a mild fever, and a household
		isolation block served to someone whose triage said "monitor; hydrate" would tell a family to
		separate over a headache. So the two travel together and only on `high_ebola_suspicion`: the
		branch is the gate, the validator is the gate's enforcement, and a caller constructing a
		`TriageResult` by hand cannot produce the pair without the classification that earns it.
		"""
		ebola = self.risk_level is RiskLevel.high_ebola_suspicion
		assert bool(self.immediate_actions) is ebola, (
			'the immediate-action list belongs to the Ebola suspicion branch and to no other'
		)
		assert (self.household_isolation is not None) is ebola, (
			'household isolation guidance belongs to the Ebola suspicion branch and to no other'
		)
		if ebola:
			assert {a.step for a in self.immediate_actions} == {s for s, _, _ in IMMEDIATE_ACTIONS}, (
				'§11.2 prints three immediate actions; all three must travel'
			)
		assert not (self.county_rrt_notified and not ebola), (
			'the county team is notified of an Ebola suspicion, and of nothing else'
		)
		# Only the direction the model can know. The note is written by the route, which holds the
		# consent ledger — so "every Ebola branch carries a note" is a property of the *route*, not
		# of the model, and asserting it here would fail for `assess`, which answers the clinical
		# question and has no business knowing whether the caller had a token.
		assert not (self.county_rrt_notified and not self.county_rrt_note), (
			'a notification is reported with the sentence that explains it'
		)
		return self

	@computed_field
	@property
	def summary_card(self) -> str:
		"""§8.1's fourth Output, "forwardable summary card".

		§3.3 principle 10 requires every output be shareable as a WhatsApp card, and a triage result
		is the one a person forwards to a relative or a CHW. Rendered here rather than composed by
		the client for the reason `HotlineActions.vcard` is: the card is clinical content, and two
		clients composing it from the fields would eventually disagree about what it says.

		It carries no symptom list and no contact history. The card is forwardable, which means it
		leaves the person's phone, and §8.1's own Privacy clause says triage data stays on-device
		unless the user consents to share — so what travels is the classification and what to do
		about it, which is what the recipient needs, and not the exposure history, which is what
		would identify the person as a suspected case to whoever reads the forward.
		"""
		lines = [f'Afya Yangu triage: {self.risk_level.value.replace("_", " ")}', self.recommendation]
		if self.actions:
			lines.append('Next: ' + '; '.join(a.label for a in self.actions))
		if self.watch_for:
			lines.append('Watch for: ' + '; '.join(w.sign for w in self.watch_for[:4]))
		return '\n'.join(lines)


class DiaryEntry(DerivedFields, BaseModel):
	model_config = MODEL_CONFIG
	entry_id: str = Field(default_factory=lambda: 'DIARY-' + uuid7str().replace('-', '').upper()[:10])
	subject_ref: str
	day: int = Field(ge=1, le=21)
	symptoms: list[str]
	temperature_c: float = Field(ge=30, le=45)
	# §TRI-002's "log symptoms with timestamp". The day index is the observation window; the
	# timestamp is what a clinician reading the export needs, and the two are not the same fact —
	# two entries on day 3 are a different history from one.
	logged_at_iso: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}')
	# §8.1's red flags, carried on the diary entry because §TRI-002's own second Feature is
	# "automatic escalation if new red flags are logged" — which needs the flags on the entry.
	red_flags: list[str] = []
	synced: bool = False

	def model_post_init(self, _context: object) -> None:
		assert all(f in RED_FLAGS for f in self.red_flags), \
			f'unknown red flag: {[f for f in self.red_flags if f not in RED_FLAGS]}'

	@computed_field
	@property
	def worst_red_flag(self) -> str | None:
		"""The flag that decides the escalation, in §8.1's own order of urgency.

		Returned rather than a boolean because the escalation message differs: convulsions and
		bleeding get an ambulance, confusion gets a call. A `bool` here would collapse the four
		emergency flags into one answer and lose which one fired.
		"""
		for flag in RED_FLAGS:
			if flag in self.red_flags:
				return flag
		return None


class DiaryPrompt(BaseModel):
	"""§TRI-002's daily "how are you feeling?" prompt (opt-in).

	The section writes the opt-in into the Feature itself, so the gate is the feature: a person who
	has not asked to be prompted is not prompted, and the server returns nothing rather than a
	prompt marked "disabled" — a client that renders whatever it is handed would otherwise show the
	prompt to someone who declined it.

	What the server owns is the opt-in, the cadence and the words. What the device owns is the
	notification. That split is the same one `HotlineActions` and `Directions` use: the server
	renders what the client cannot decide, and the client does the thing only a device can do. A
	server that "sends" the prompt would need a push channel the product does not have, and claiming
	to have sent one is worse than returning the text and the due flag.

	`due` is derived rather than stored because the two spellings that matter — "answered today" and
	"not yet answered today" — are a comparison against the diary, and a stored boolean would be one
	more thing to keep in step with it.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	day: int = Field(ge=1, le=21)
	question: str = Field(min_length=1)
	# The last day an entry was logged. `None` means nothing has been logged at all.
	last_logged_day: int | None = None

	@computed_field
	@property
	def due(self) -> bool:
		return self.last_logged_day != self.day


class TrendDirection(str, Enum):
	"""§TRI-002's "trend view: is this getting better or worse?".

	`unknown` is a member and it is not padding: a first entry has no trend, and "no change yet" is
	a different answer from "stable over four days". A two-member enum forces the first entry to
	claim one of them.
	"""

	improving = 'improving'
	worsening = 'worsening'
	stable = 'stable'
	unknown = 'unknown'


class DiaryTrend(BaseModel):
	model_config = MODEL_CONFIG
	direction: TrendDirection
	days_logged: int = Field(ge=0)
	# What moved, in the person's own terms. A trend view that says "worsening" without saying what
	# worsened is a verdict rather than a reading.
	changed: list[str]
	note: str = Field(min_length=1)


class DiaryExport(BaseModel):
	"""§TRI-002's "exportable summary for a clinician".

	A rendered text block rather than the entry list, because what the section asks for is an
	*export*: the person hands this to a clinician, and a clinician reading JSON is not the use
	case. `text` is what a client shares; `entries` stays available so the app can render its own
	view without re-deriving the summary.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str
	days_logged: int = Field(ge=0)
	trend: DiaryTrend
	text: str = Field(min_length=1)
	entries: list[DiaryEntry]


RECOMMENDATIONS: dict[RiskLevel, str] = {
	RiskLevel.low: 'Monitor; standard hygiene; hydrate; call 719 if worsening.',
	RiskLevel.malaria_suspect: 'A fever in Kenya is most often malaria. Test and treat for malaria first; call 719 if there is no improvement in 48 hours.',
	RiskLevel.medium: 'Contact hotline 719; self-monitor; isolate from household if symptoms progress.',
	RiskLevel.high_other: 'Seek care today at the nearest facility; call 719 if you cannot get there.',
	RiskLevel.high_ebola_suspicion: 'Isolate yourself now, away from the household. Call 719 and say you may have had contact with Ebola. Do not travel by public transport.',
	RiskLevel.emergency: 'Emergency. Call 719 now and stay where you are. Do not travel alone. If there is bleeding, press firmly on it and keep the person still.',
}

# --- Multi-disease differential (all common illnesses, not only EVD) ---

DISEASE_PROFILES: dict[str, frozenset[str]] = {
	'malaria': frozenset({'fever', 'headache', 'body_aches', 'chills', 'fatigue', 'nausea'}),
	'typhoid': frozenset({'fever', 'abdominal_pain', 'headache', 'constipation', 'diarrhoea', 'fatigue'}),
	'flu': frozenset({'fever', 'cough', 'sore_throat', 'runny_nose', 'body_aches', 'headache'}),
	'cholera': frozenset({'diarrhoea', 'vomiting', 'dehydration', 'muscle_cramps'}),
	'covid': frozenset({'fever', 'cough', 'sore_throat', 'loss_of_smell', 'fatigue', 'shortness_of_breath'}),
	'evd': EBOLA_SYMPTOMS,
}


class DiagnosisItem(BaseModel):
	model_config = MODEL_CONFIG
	disease: str
	score: float = Field(ge=0, le=1)
	note: str


class Differential(BaseModel):
	model_config = MODEL_CONFIG
	entries: list[DiagnosisItem]
	lead: str
	advise: str
	malaria_trap_applied: bool
