"""Emergency domain models (EMG-001..003)."""
from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.ids import uuid7str

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class SOSEvent(BaseModel):
	model_config = MODEL_CONFIG
	sos_id: str = Field(default_factory=lambda: 'SOS-' + uuid7str().replace('-', '').upper()[:6])
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	symptoms: list[str] = []
	severity: str = Field(pattern=r'^(low|medium|high)$')


class SOSDispatch(BaseModel):
	model_config = MODEL_CONFIG
	sos_id: str
	notified: list[str]
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


class EmergencyContact(BaseModel):
	"""§EMG-003's "emergency contacts" — plural, and each one has a *name*.

	The section lists the card's contents and writes "emergency contacts"; the model carried one
	phone string, so the plural collapsed. A name is not decoration: the card is read by a clinician
	looking at an unconscious patient, and a bare number tells them neither who to ring nor what the
	person is to the patient. `relationship` is optional because a card can be filled in without it.
	"""

	model_config = MODEL_CONFIG
	name: str = Field(min_length=1)
	number: str = Field(pattern=r'^\+?\d{7,15}$')
	relationship: str | None = None


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