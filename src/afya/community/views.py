"""Community models (spec §10.4 COM-005, §11.4 COM-101..104)."""
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from afya.derived import DerivedFields
from afya.ids import ref8
from afya.location.views import ALERT_ZONE_RADII_M

from afya.registry.diseases import DISEASE_PATTERN

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


# --- COM-005 community reporting ---------------------------------------------------------

class IssueKind(str, Enum):
	broken_water_point = 'broken_water_point'
	open_sewage = 'open_sewage'
	illegal_dumping = 'illegal_dumping'
	mosquito_breeding = 'mosquito_breeding'
	dead_animal = 'dead_animal'
	unsafe_food_vendor = 'unsafe_food_vendor'
	counterfeit_medicine = 'counterfeit_medicine'
	facility_stockout = 'facility_stockout'
	facility_staff_absence = 'facility_staff_absence'


# county authority routing table — who actually fixes this (§10.4 "routed to relevant authority")
ISSUE_ROUTING: dict[IssueKind, str] = {
	IssueKind.broken_water_point: 'County Water Services',
	IssueKind.open_sewage: 'County Public Health Office',
	IssueKind.illegal_dumping: 'County Environment Office',
	IssueKind.mosquito_breeding: 'County Public Health Office',
	IssueKind.dead_animal: 'County Veterinary Services',
	IssueKind.unsafe_food_vendor: 'County Public Health Office',
	IssueKind.counterfeit_medicine: 'Pharmacy and Poisons Board',
	IssueKind.facility_stockout: 'County Health Management Team',
	IssueKind.facility_staff_absence: 'County Health Management Team',
}


class CommunityIssue(BaseModel):
	model_config = MODEL_CONFIG
	issue_id: str = Field(default_factory=lambda: 'CIS-' + ref8())
	kind: IssueKind
	county: str
	description: str = Field(min_length=5, max_length=300)
	lat: float | None = Field(default=None, ge=-5, le=6)
	lon: float | None = Field(default=None, ge=33, le=43)


class IssueStatus(str, Enum):
	reported = 'reported'
	routed = 'routed'
	in_progress = 'in_progress'
	resolved = 'resolved'


class IssueReceipt(BaseModel):
	model_config = MODEL_CONFIG
	issue_id: str
	routed_to: str
	status: IssueStatus
	message: str


# --- COM-101 CHW case reporting ----------------------------------------------------------

class CaseStatus(str, Enum):
	reported = 'reported'
	investigated = 'investigated'
	lab_result = 'lab_result'
	closed = 'closed'


class CaseReport(BaseModel):
	"""WHO IDSR / Kenya MoH structured report. Patient name optional — anonymous is a first-class path."""
	model_config = MODEL_CONFIG
	report_id: str = Field(default_factory=lambda: 'CR-' + ref8())
	chw_ref: str
	county: str
	community: str
	patient_ref: str | None = None
	age_years: int | None = Field(default=None, ge=0, le=120)
	sex: str | None = Field(default=None, pattern=r'^(male|female|other)$')
	symptoms: list[str] = Field(min_length=1)
	exposure_history: str | None = Field(default=None, max_length=500)
	temperature_c: float | None = Field(default=None, ge=30, le=45)
	geotagged: bool = False
	photo_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
	# §COM-101's "voice-to-text notes in local languages" and §ACC-002's "voice-to-text for CHW
	# notes and case descriptions" are the same bullet seen from two sections. `voice_note_lang`
	# named a language and nothing recorded a note: the field was there, the audio had nowhere to
	# go, and a CHW who dictated an observation had to type it afterwards or lose it. The note is
	# carried as the transcript the recogniser produced, beside the language it was recognised in —
	# never as audio, because §17.2 keeps the waveform on the handset.
	voice_note_lang: str | None = None
	voice_note: str | None = Field(default=None, max_length=2000)
	suspected_disease: str = Field(default='evd', pattern=DISEASE_PATTERN)
	reported_offline: bool = False
	# §5.4's "deduplicated by phone number" needs the number the report came from, and the model had
	# no field for it — so a case filed over USSD and the same case filed in the app were two cases
	# and the count PHEOC reads was inflated by exactly the duplicates the section promises are gone.
	# Optional because a CHW logging offline carries no MSISDN: the phone is a channel's identity, and
	# a report that did not come over a channel has none. Absent means "cannot be deduplicated", which
	# `CommunityService.submit_case` reports rather than treats as "no duplicate".
	reporter_msisdn: str | None = Field(default=None, pattern=r'^\+[1-9]\d{6,14}$')

	@model_validator(mode='after')
	def _a_note_is_kept_in_the_language_it_was_said_in(self) -> Self:
		"""A transcript with no language, or a language with no transcript, is half a record.

		`voice_note_lang` used to be settable on its own, which is how the field came to look
		implemented while nothing recorded a note. The two move together now: a note is a transcript
		*and* the language the recogniser was pointed at, and a report that carries one without the
		other is refused rather than stored as a claim about a recording nobody made.
		"""
		assert (self.voice_note is None) == (self.voice_note_lang is None), (
			'a voice note was given a language with no transcript, or a transcript with no language'
		)
		return self


class CaseReportView(BaseModel):
	model_config = MODEL_CONFIG
	report_id: str
	status: CaseStatus
	surveillance_officer: str
	alerts_sent: int = Field(ge=0)
	next_step: str
	# True when §5.4's dedup recognised this report as one already open. The caller is told rather
	# than silently given the first report's id: a person who reports twice because the first
	# acknowledgement never arrived must not be left believing a second case was opened.
	deduplicated: bool = False


# --- COM-102 peer alert network ----------------------------------------------------------

# §COM-102's alert body, as a template with two slots rather than as a string a caller writes.
#
# The section prints the sentence the alert carries — "A suspected case has been reported in your
# area. Avoid [specific location]. Monitor for symptoms for 21 days. Call 719 if you feel unwell." —
# and `PeerAlert` had a caller-supplied `headline`/`body` and nothing that drafted it. A template is
# the whole point of the bullet: the section's wording is the calm, factual, actionable one it says
# it tested with community representatives, and a free-text body is a body that can be alarmist,
# that can name a person, and that cannot be reviewed before it goes to a whole village.
#
# `{location}` is the "[specific location]" the section leaves open, and it is the *only* slot.
# There is no slot for a case reference, a name, a house number or a patient — §COM-102's own "No
# personally identifiable information about the case" is enforced by there being nowhere to put one,
# not by a reviewer noticing. `alert_body` refuses a location that looks like an identifier.
ALERT_TEMPLATE: str = (
	'A suspected case has been reported in your area. Avoid {location}. '
	'Monitor for symptoms for 21 days. Call 719 if you feel unwell.'
)

# What a `location` may not contain. A place name is a place name; a person is not a place. The
# check is about *identifier shapes* — a dwelling followed by a number, or a determiner followed by a
# person-noun — because the words a stigmatising alert uses are §6.2.9's business and the tone judge
# already reads this string. What the judge cannot see is that "House 14, next to Mama Otieno's" is
# a person, and that is what this refuses.
#
# "the case" is deliberately *not* on the list. It names nobody — it is the section's own anonymised
# phrasing, the one its template uses — and a rule that refused it would refuse "The Case Hotel" and
# teach a CHW to write around the check rather than to use it.
_ALERT_LOCATION_FORBIDDEN: tuple[str, ...] = (
	'the patient', 'the victim', 'the deceased', 'the body',
	'house ', 'plot ', 'door ', 'apartment ', 'flat ', 'room ',
)

# §COM-102's follow-up prompts, on the section's own days. Four, and they are a module constant
# because two features now read them: the alert carries them and §TRI-002's diary escalates on a
# red flag within the same window. A list written twice is a list that drifts.
FOLLOWUP_DAYS: tuple[int, ...] = (3, 7, 14, 21)

# §11.2 TRI-003's escalation window, which is also the symptom window §COM-102's alert names. The
# alert says "monitor for symptoms for 21 days" and the follow-up prompts end on day 21, so the two
# facts are one fact and the day count is read from the source's range rather than written again.
ALERT_WINDOW_DAYS: int = 21


class PeerAlert(DerivedFields, BaseModel):
	"""§COM-102's alert. The body is drafted from `ALERT_TEMPLATE`, not supplied.

	`verified_by` is required because the section's Verification clause is "Alerts are only sent
	after verification by county health authorities"; a model that defaulted it would make the
	clause a field nobody fills.
	"""

	model_config = MODEL_CONFIG
	alert_id: str
	county: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	# §COM-102's geofenced zones are 500 m, 1 km and 5 km, and §LOC-001's `ALLOWED_RADII_M` is the
	# same three. `radius_m` was bounded 500–5000, which admits 3000 — a radius the section does not
	# offer and no county can configure, since the set is the set of zones.
	radius_m: int
	headline: str = Field(max_length=120)
	# The "[specific location]" slot. Named for what it is: a place, not a case.
	location: str = Field(min_length=2, max_length=80)
	verified_by: str
	# When the alert was issued, which is when §COM-102's 21-day window opens — not when a recipient
	# happens to read it. Required rather than defaulted to today: an alert filed after the fact is
	# filed with the date it was issued, and a server that stamped `now` would silently move the
	# window for everyone who reads it late.
	issued_iso: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2}))?$')
	followup_days: list[int] = Field(default_factory=lambda: list(FOLLOWUP_DAYS))

	def model_post_init(self, _context: object) -> None:
		assert self.radius_m in ALERT_ZONE_RADII_M, (
			f'{self.radius_m} m is not a §COM-102 alert zone; '
			f'the section offers {list(ALERT_ZONE_RADII_M)}'
		)
		assert self.followup_days == list(FOLLOWUP_DAYS), (
			f'§COM-102 prints follow-up prompts on days {list(FOLLOWUP_DAYS)}'
		)
		low = self.location.lower()
		leaked = [w for w in _ALERT_LOCATION_FORBIDDEN if w in low]
		assert not leaked, (
			f'the alert location names something that is not a place: {leaked} — §COM-102 forbids '
			f'personally identifiable information about the case'
		)

	@computed_field
	@property
	def body(self) -> str:
		"""The section's sentence, with the location in it. Derived, so there is no free-text body."""
		return ALERT_TEMPLATE.format(location=self.location)


class PeerAlertReceipt(BaseModel):
	model_config = MODEL_CONFIG
	alert_id: str
	recipients: int = Field(ge=0)
	verification: str
	tone_check: str
	body: str
	# The acknowledgement §COM-102's fourth bullet asks for, and the guidance returned with it.
	# Both are on the receipt rather than on a second model because they are what the sender gets
	# back: a CHW who dispatched an alert reads whether anyone answered it.
	acknowledged: int = Field(default=0, ge=0)
	followup_days: list[int] = Field(default_factory=lambda: list(FOLLOWUP_DAYS))


class PeerAlertAck(BaseModel):
	"""§COM-102's "Users acknowledge alerts and receive follow-up guidance".

	The acknowledgement is a *recipient's* act, so it carries the person who read the alert and the
	alert they read. No case reference travels with it, for the same reason none travels with the
	alert.
	"""

	model_config = MODEL_CONFIG
	alert_id: str
	subject_ref: str
	acknowledged_iso: str
	# §COM-102's Tone clause is "calm, factual, actionable", so the guidance a person gets back is
	# the four things to do, not a restatement of the alert.
	concerned: bool = False


class PeerAlertGuidance(BaseModel):
	"""What an acknowledgement returns. The follow-up prompt for the day it was read, and the steps."""

	model_config = MODEL_CONFIG
	alert_id: str
	subject_ref: str
	day: int = Field(ge=1, le=ALERT_WINDOW_DAYS)
	guidance: list[str]
	next_followup_day: int | None = None
	message: str


# --- COM-103 contact tracing assistance --------------------------------------------------

class ContactEntry(BaseModel):
	model_config = MODEL_CONFIG
	description: str = Field(min_length=2, max_length=200)
	contact_ref: str | None = None
	setting: str = Field(pattern=r'^(home|work|transport|worship|market|social|other)$')
	approx_location: str | None = None
	name_unknown: bool = False


class ContactList(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	entries: list[ContactEntry] = Field(default_factory=list)
	share_consent: bool = False


class ContactTracingSummary(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	by_setting: dict[str, int]
	total: int = Field(ge=0)
	shared: bool
	progress_pct: float = Field(ge=0, le=100)
	message: str


class ContactShare(BaseModel):
	"""§COM-103's "secure, encrypted channel": the envelope a contact list travels in.

	`sealed` is a `Sealed.to_blob()` string, so the list is ciphertext before it leaves the process
	and the wire carries nothing a reader can open. It is sealed under the *application-layer* key
	and not the at-rest key, which is §SEC-003's own standard for contact lists and also the only
	choice that makes the transport meaningful: the at-rest key is the one an operator holds, so a
	share sealed under it is a share the operator could read without being the recipient.

	The recipient is named in the clear and the payload is not. That is deliberate — a routing header
	has to be readable to be routed, and `with_who` names an office rather than a person, so it
	discloses nothing about the contacts inside.
	"""
	model_config = MODEL_CONFIG
	share_id: str = Field(default_factory=lambda: 'CSH-' + ref8())
	subject_ref: str
	with_who: str = Field(min_length=2, max_length=120)
	sealed: str = Field(min_length=1)
	entries: int = Field(ge=0)
	shared_at_ms: int
	algorithm: str = 'AES-256-GCM'
	expires_at_ms: int
	receipt: str


class ContactShareReceipt(BaseModel):
	"""What the sharer is told. The ciphertext is deliberately absent.

	A response that echoed `sealed` back would put the one value worth protecting into a log, a
	cache and a client's memory for no gain — the caller produced it.
	"""
	model_config = MODEL_CONFIG
	share_id: str
	with_who: str
	entries: int
	shared_at_ms: int
	expires_at_ms: int
	algorithm: str
	message: str


# --- COM-104 misinformation tracker ------------------------------------------------------

class MisinfoSubmission(BaseModel):
	"""§COM-104's report, in whichever medium the person has it.

	`medium` said `voice` or `screenshot` and carried no payload for either, so a person who had the
	rumour as a voice note had to retype it as a claim — and the two media that cannot be retyped
	are exactly the two a WhatsApp forward arrives in. `evidence_ref` is where the recording or the
	image lives: §SEC-002's own rule for this data is "Photos encrypted and only shared with
	explicit per-item consent", so the *bytes* never enter this model. What travels is a reference to
	an envelope the caller sealed, which is the same division `WalletDocument.media_ref` draws.

	`transcript` is the text path out of a voice note: §ACC-002's recogniser runs on the device and
	the words come up, which is what makes a spoken rumour findable by `classify()` at all. A voice
	report with neither a transcript nor an `evidence_ref` is refused, because it is a claim with no
	content in any medium — the audit row's own gap, wearing a `medium` value that looks filled in.
	"""
	model_config = MODEL_CONFIG
	submission_id: str = Field(default_factory=lambda: 'MIS-' + ref8())
	claim: str = Field(min_length=5, max_length=500)
	county: str
	medium: str = Field(pattern=r'^(text|voice|screenshot|whatsapp_forward)$')
	topic: str | None = None
	# §SEC-001: who to tell when the rumour they reported is addressed. Read by `notices_for`,
	# which is what makes §11.4's last bullet reachable at all.
	flagger_ref: str | None = None
	# A reference to the sealed recording or image, never the bytes. Sealed under §SEC-003's
	# application-layer key by the caller, for the reason §COM-103's contact list is: the operator
	# holding the at-rest key is not the audience for a rumour someone forwarded them.
	evidence_ref: str | None = Field(default=None, max_length=200)
	# What a voice note said, recognised on the device by §ACC-002's engine. Never a server-side
	# transcription of uploaded audio: §SEC-002 says audio is not transmitted.
	transcript: str | None = Field(default=None, max_length=500)
	# §SEC-002's "explicit per-item consent" for the photograph itself, given per report rather
	# than once at install. Defaults False: a submission that says nothing shares nothing.
	evidence_consent: bool = False

	@model_validator(mode='after')
	def _payload_matches_medium(self) -> 'MisinfoSubmission':
		"""A medium that names a recording or an image must carry one.

		Without this the four-value `medium` pattern was the whole feature: a `screenshot` submission
		with no image is indistinguishable from a `text` one, and PHEOC reading the cluster counts
		would see "12 screenshots" and have nothing to look at.
		"""
		if self.medium in ('voice', 'screenshot', 'whatsapp_forward') and not (
				self.evidence_ref or self.transcript):
			raise ValueError(
				f'a {self.medium} report must carry the recording, the image or its transcript — '
				'otherwise it is a text report with a different label')
		if self.evidence_ref and not self.evidence_consent:
			raise ValueError(
				'the recording or image is shared only with explicit per-item consent, and none '
				'was given for this report')
		return self


class MisinfoCluster(BaseModel):
	model_config = MODEL_CONFIG
	topic: str
	reports: int = Field(ge=1)
	velocity: str = Field(pattern=r'^(slow|rising|spiking)$')
	counties: list[str]
	correction: str | None = None
	status: str = Field(pattern=r'^(aggregating|verified|correction_published)$')
	# §6.4's clock, on the cluster rather than beside it. `reports` and `velocity` say how loud a
	# rumour is; neither says how long the response has been running, so a cluster could read
	# `spiking` for a week with nothing anywhere showing that the four-hour triage was never done.
	detected_at_ms: int | None = None
	next_due_at_ms: int | None = None
	response_overdue: bool = False


class ClaimAnswer(BaseModel):
	"""§INF-004's "Ask about a rumour", answered to the person who asked.

	`MisinfoCluster` is the wrong shape for this and the difference is the feature. A cluster is
	PHEOC's view of a rumour — how many reports, which counties, how fast it is moving — and it is
	what a *flagger* gets, because a flagger reports something they saw someone else spread. Someone
	who asks "is it true that salt water cures Ebola" is not flagging anything: they want the
	correction, and handing them a surveillance row instead answers a question they did not ask.

	So the correction travels with the claim it corrects and the authority behind it, which is
	§INF-004's Format — "Rumour: [claim]. Fact: [correction]. Source: [authority]." — as fields rather
	than as one rendered string. `recognised` is what makes the fallback honest: a claim matching no
	drafted rumour is answered "under verification" and says so, rather than being attached to the
	nearest correction with the confidence of a match.
	"""
	model_config = MODEL_CONFIG
	claim: str = Field(min_length=5)
	# None when no drafted rumour matched. The topic, not the category: a category is a pre-drafting
	# grouping for §6.4's brief and several topics answer one, so naming the category here would lose
	# which rumour was actually recognised.
	topic: str | None = None
	# The words that decided the match, so a reader can argue with the classification rather than
	# being told an answer with no evidence behind it.
	matched: list[str] = []
	correction: str = Field(min_length=1)
	fact: str = Field(min_length=1)
	source: str = ''
	# The library item this correction is, so a client can open the full myth card rather than
	# rendering the correction as a dead end. Empty when nothing matched — there is no card for a
	# claim the library has not drafted.
	slug: str = ''
	# The language the answer is actually in, which is not always the one asked for: `answerable()`
	# resolves a language with no table to English rather than refusing, and a person told which
	# language they got is not left reading English believing it is Dholuo.
	answered_in: str = Field(pattern=r'^(en|sw)$')
	recognised: bool
	# §6.2.3: an undated correction about a live rumour is one nobody can weigh.
	drafted_on_iso: str = Field(min_length=10)


class CorrectionNotice(BaseModel):
	"""§11.4's last bullet: the correction, addressed to the person who flagged the rumour.

	The flow is explicit — "Flag → aggregated → verified → correction drafted → published on all
	channels → flagger notified" — and the last arrow was the one with nothing behind it.
	`correction_for` drafted the text and `flagger_ref` was written on every submission and read
	nowhere, so the person who reported a rumour was never told it had been answered. `sent` is the
	fact the audit row was missing: the notice exists *and* it was handed to a delivery path.

	`withheld` says why a notice that exists was not handed over — the person switched community
	alerts off, or gave no `flagger_ref` to address it to. A refusal is an answer, as everywhere
	else in this module: a notice silently dropped reads the same as a person who was never told.
	"""
	model_config = MODEL_CONFIG
	topic: str
	subject_ref: str
	title: str = Field(min_length=1)
	body: str = Field(min_length=1)
	correction: str = Field(min_length=1)
	source: str = ''
	sent: bool
	withheld: str | None = None
	category: str = Field(default='community_alerts', min_length=1)
	issued_at_ms: int
