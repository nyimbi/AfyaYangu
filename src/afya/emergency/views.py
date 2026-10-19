"""Emergency domain models (EMG-001..003)."""
from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.ids import ref8

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


def _parse_named_contacts(data: object, *keys: str) -> object:
	"""Accept `"Jane:0722000111"` where the model holds named contacts.

	A generic mobile form can only offer one text box per field, so the catalogue hands a
	comma-separated list of `name:number` strings and the model wants `EmergencyContact` objects.
	Without this the form and the model disagree on both the name and the shape, and every
	submission from a client rendering the catalogue is refused.

	`keys` is the spellings the caller's payload may use, most specific first; the last is the field
	the parsed list is written back under. `relationship` stays absent rather than guessed: the
	string carries a name and a number, and inventing a third fact would be worse than the gap.
	Only strings are parsed — a caller that sends `EmergencyContact` objects, or dicts, has already
	said what it means, and treating a model instance as a string is how the first version of this
	turned every well-formed card into a blank number.
	"""
	if not isinstance(data, dict):
		return data
	raw = next((data[k] for k in keys if data.get(k) is not None), None)
	if raw is None:
		return data
	contacts = raw if isinstance(raw, list) else [raw]
	if not any(isinstance(c, str) for c in contacts):
		return data
	parsed: list[object] = []
	for item in contacts:
		if not isinstance(item, str):
			parsed.append(item)
			continue
		# `name:number`, or the `name,number` a person is as likely to type. A string with no
		# separator is a name with no number, which the contact model refuses by pattern rather
		# than this function inventing a placeholder number for it.
		parts = [p.strip() for p in str(item).replace(',', ':').split(':') if p.strip()]
		parsed.append({'name': parts[0], 'number': parts[1] if len(parts) >= 2 else ''})
	return {k: v for k, v in data.items() if k not in keys} | {keys[-1]: parsed}


class EmergencyContact(BaseModel):
	"""§EMG-003's "emergency contacts" — plural, and each one has a *name*.

	The section lists the card's contents and writes "emergency contacts"; the model carried one
	phone string, so the plural collapsed. A name is not decoration: the card is read by a clinician
	looking at an unconscious patient, and a bare number tells them neither who to ring nor what the
	person is to the patient. `relationship` is optional because a card can be filled in without it.

	§EMG-001's SOS sends to the same list — the section's "up to three emergency contacts" and
	§EMG-003's Contents are one set of people, and a second contact model would be two answers to
	"who do I ring".
	"""

	model_config = MODEL_CONFIG
	name: str = Field(min_length=1)
	number: str = Field(pattern=r'^\+?\d{7,15}$')
	relationship: str | None = None


class MedicalProfile(BaseModel):
	"""§EMG-001's "optional medical profile attachment (blood group, allergies, conditions,
	medications)" — the four the section names, every one optional.

	Not `EmergencyCard`. The card is §EMG-003's lock-screen payload and requires a name, a blood
	group and at least one contact; an SOS attaches what the person happens to have, and somebody
	who never filled the card in can still send the one fact a responder needs. All four default
	empty because "nothing attached" and "attached and blank" are the same answer here — unlike the
	card's `organ_donor`, where the difference is a clinical fact.
	"""

	model_config = MODEL_CONFIG
	blood_group: str | None = Field(default=None, max_length=8)
	allergies: list[str] = []
	conditions: list[str] = []
	medications: list[str] = []

	def is_empty(self) -> bool:
		return not (self.blood_group or self.allergies or self.conditions or self.medications)


class SOSEvent(BaseModel):
	"""§EMG-001's alert: the tap, where the person is, who to tell, and how it gets out.

	The section's fan-out is "location and a preset message to up to three emergency contacts", and
	the model carried neither the contacts nor the message: `sos` notified the hotline and returned
	the string `sms-contacts` inside a list, which is a label for a message nobody composed.

	`contacts` is `max_length=3` because the section says "up to three" — a fourth is refused rather
	than silently dropped, since a dropped contact is a person who was never told.

	`channel` is the client's own answer to §EMG-001's bolded "**Works over SMS when data is
	unavailable**". It is on the event rather than inferred because only the client knows whether it
	has data, and it is not a switch over which leg is used: the contacts are reached by SMS either
	way, because SMS is the leg the claim rests on.
	"""

	model_config = MODEL_CONFIG
	sos_id: str = Field(default_factory=lambda: 'SOS-' + ref8())
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	symptoms: list[str] = []
	severity: str = Field(pattern=r'^(low|medium|high)$')
	contacts: list[EmergencyContact] = Field(default=[], max_length=3)
	channel: str = Field(default='native', pattern=r'^(native|sms)$')
	# §EMG-001's "optional medical profile attachment". Flat here rather than nested, because the
	# catalogue renders one control per field and a generic form cannot build an object.
	blood_group: str | None = Field(default=None, max_length=8)
	allergies: list[str] = []
	conditions: list[str] = []
	medications: list[str] = []

	@model_validator(mode='before')
	@classmethod
	def _typed_contacts_are_contacts(cls, data: object) -> object:
		return _parse_named_contacts(data, 'contacts')


class SOSAlert(BaseModel):
	"""§EMG-001's countdown, as state rather than as a client's animation.

	Arming returns the deadline; `cancel` is refused past it. That is the whole of what "countdown
	with cancel option (prevents accidental activation)" needs from the server — the device owns the
	timer, because §ACC-004 wants no server-side polling and §EMG-001's Offline note wants the alert
	to work with no data at all, and a server-held timer would make both false. What the server owns
	is the window: how long it is, when it closes, whether a cancel arrived in time, and that a
	cancelled alert never goes out.

	`countdown_s` travels on the alert because the duration is a deployment parameter — the section
	prints no figure, and a constant invented here would read as one the spec states.
	"""

	model_config = MODEL_CONFIG
	sos_id: str
	message: str = Field(min_length=1)
	countdown_s: int = Field(ge=0, le=60)
	armed_at_ms: int
	cancel_deadline_ms: int
	event: SOSEvent
	cancelled: bool = False
	fired: bool = False
	# The subject whose token armed this alert, when one was presented. `None` is the deliberate
	# anonymous case: §EMG-001's tap must work with no login, so an alert armed without a token has
	# no owner and is refused to nobody. When it *does* have an owner, cancel, fire and the state
	# read are bound to that token — `sos_id` is a 20-bit counter, so the id alone is not a secret.
	owner_ref: str | None = None


class SOSDispatch(BaseModel):
	"""The receipt: who was told, by which leg, and who could not be reached.

	The three legs are separate fields because they fail separately. `notified` is the standing
	services §18.4 names; `contacts_notified` and `contacts_unreachable` split the section's "up to
	three emergency contacts" into the ones a message actually reached and the ones it did not —
	a person who pressed SOS needs to know that their sister's number was a landline, and a fan-out
	that reports "3 contacts" for two deliveries is the failure this split exists to prevent.
	"""

	model_config = MODEL_CONFIG
	sos_id: str
	message: str
	notified: list[str]
	contacts_notified: list[str]
	contacts_unreachable: list[str]
	ambulance_dispatch: str | None
	sms_sent: int = Field(ge=0)
	profile: MedicalProfile | None
	actions: list[str]


class IMUSample(BaseModel):
	model_config = MODEL_CONFIG
	x: float
	y: float
	z: float
	timestamp_ms: int


class FallResult(BaseModel):
	model_config = MODEL_CONFIG
	fall_detected: bool
	peak_g: float
	auto_alert: bool


class EmergencyCard(BaseModel):
	"""§EMG-003's offline card: the contents the section prints, and the Access clause as a field.

	Seven Contents, and four were absent. `emergency_contact` was one string where the section says
	"emergency contacts"; there was no medications list, no organ-donor status and no SHA number.

	`organ_donor` is `bool | None` rather than a defaulted `False`, and that is the one field where
	the difference is a safety property: a hospital reading the card of an unconscious patient must
	be able to tell "this person declined" from "this person never said", and a boolean with a
	default answers the second as the first.

	`sha_number` is carried on the *payload* and never persisted — the hash-only rule
	(`insurance.views.sha_of_member_no`) is about storage, and §EMG-003 asks for the number a hospital
	can read off the card. There is no method here that stores a card, which is what keeps the two
	compatible rather than in tension.
	"""

	model_config = MODEL_CONFIG
	name: str
	blood_group: str
	allergies: list[str]
	conditions: list[str]
	emergency_contacts: list[EmergencyContact] = Field(min_length=1)
	medications: list[str] = []
	organ_donor: bool | None = None
	sha_number: str | None = Field(default=None, pattern=r'^[A-Z0-9]{6,20}$')
	# §EMG-003's Access: "Available from the lock screen without unlocking the phone (opt-in)." The
	# opt-in is the gate, so it is a field with a false default — a card is not lock-screen readable
	# because it exists, and a client that renders one without this flag is showing medical data on a
	# locked screen for someone who never asked for it.
	lock_screen_opt_in: bool = False

	@model_validator(mode='before')
	@classmethod
	def _typed_contacts_are_contacts(cls, data: object) -> object:
		"""Accept `"Jane:0722000111"` where the model holds a named contact.

		The card's Contents say "emergency contacts" and the model carries them named, because a bare
		number tells a clinician looking at an unconscious patient neither who to ring nor what they
		are to them. A generic form can only offer one text box per field, and the catalogue offered
		`emergency_contact` — so the form and the model disagreed on both the name and the shape, and
		every submission from a client rendering the catalogue was refused.

		Both spellings arrive: the singular `emergency_contact` a one-box form produced, and the
		`emergency_contacts` list of `name:number` strings the catalogue now offers. Either becomes
		the list of named contacts the card holds; a caller that already sends that list is untouched.
		`relationship` stays absent rather than guessed: the string carries a name and a number, and
		inventing a third fact would be worse than the gap.
		"""
		if not isinstance(data, dict):
			return data
		raw = data.get('emergency_contact', data.get('emergency_contacts'))
		if raw is None:
			return data
		contacts = raw if isinstance(raw, list) else [raw]
		# Only strings are parsed. A caller that sends `EmergencyContact` objects, or dicts, has
		# already said what it means and this leaves the payload alone — treating a model instance as
		# a string is how the first version of this turned every well-formed card into a blank number.
		if not any(isinstance(c, str) for c in contacts):
			return data
		parsed: list[object] = []
		for item in contacts:
			if not isinstance(item, str):
				parsed.append(item)
				continue
			# `name:number`, or the `name,number` a person is as likely to type. A string with no
			# separator is a name with no number, which the contact model refuses by pattern rather
			# than this function inventing a placeholder number for it.
			parts = [p.strip() for p in str(item).replace(',', ':').split(':') if p.strip()]
			parsed.append({'name': parts[0], 'number': parts[1] if len(parts) >= 2 else ''})
		return {k: v for k, v in data.items() if k not in ('emergency_contact', 'emergency_contacts')} | {'emergency_contacts': parsed}