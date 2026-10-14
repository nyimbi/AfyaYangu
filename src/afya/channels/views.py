"""Channel domain models (spec §5, CHAN-000..006)."""
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.ids import uuid7str

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class SmsOut(BaseModel):
	"""One outbound SMS, with whether the person receiving it is charged.

	`zero_rated` has no default. It used to default to `True`, which meant every message the system
	sent was stamped free whether or not any carrier agreement existed — a claim nothing could make
	false, checked only by an assert on the value it had just been handed. It is now resolved from
	§5.2's cost table and §18.8's pulled billing rules (`afya.channels.cost`), so a caller that does
	not know has to say so by omission rather than by inheriting "free".
	"""
	model_config = MODEL_CONFIG
	to_msisdn: str = Field(pattern=r'^\+254\d{9}$')
	body: str = Field(max_length=1600)
	segments: int = Field(ge=1, le=10)
	zero_rated: bool


class UssdRequest(BaseModel):
	model_config = MODEL_CONFIG
	session_id: str
	msisdn: str = Field(pattern=r'^\+254\d{9}$')
	text: str = ''


class UssdResponse(BaseModel):
	model_config = MODEL_CONFIG
	session_id: str
	menu: str | None = None
	end_text: str | None = None


class WhatsAppIn(BaseModel):
	model_config = MODEL_CONFIG
	from_msisdn: str = Field(pattern=r'^\+?\d{8,15}$')
	body: str = Field(min_length=1, max_length=4096)
	# §ACC-002's "voice note triage on WhatsApp". A WhatsApp voice note arrives as *media*, not as
	# text: the sender holds the button down, speaks, and what reaches the webhook is an audio
	# reference. The model had one text field, so the router read a note's media id as if it were
	# the message body — a voice note was answered at the low risk level because the id contained no
	# symptom word. `voice_note_lang` is what the sender's own keypad/profile says they speak; the
	# note itself has no language tag until it is transcribed.
	kind: str = Field(default='text', pattern=r'^(text|voice)$')
	voice_note_lang: str | None = None

	@model_validator(mode='after')
	def _a_voice_note_is_not_also_text(self) -> Self:
		"""A voice note carries no body to read: its `body` is the media reference, and a client that
		also sent text would be two messages in one. The two are separate arrivals.

		The second assert is the one that matters. §ACC-002's `LANGUAGE_MATRIX` ships recognition per
		language, so a note that declares none is a note no recogniser can be pointed at — and
		guessing the language is guessing which language to mis-hear the person in.
		"""
		assert self.kind == 'voice' or self.voice_note_lang is None, (
			'a language was given for a voice note that is not a voice note'
		)
		assert self.kind != 'voice' or self.voice_note_lang is not None, (
			'a voice note arrived with no language declared, and recognition ships per language'
		)
		return self


class WhatsAppOut(BaseModel):
	model_config = MODEL_CONFIG
	to_msisdn: str
	reply: str
	channel_ok: bool = True


class RadioBulletin(BaseModel):
	model_config = MODEL_CONFIG
	bulletin_id: str
	station: str
	air_date: str
	duration_s: int = Field(ge=15, le=3600)
	script: str


class ChwTask(BaseModel):
	model_config = MODEL_CONFIG
	task_id: str
	chw_ref: str
	community: str
	kind: str = Field(pattern=r'^(followup|referral|sensitisation)$')
	done: bool = False


class CallbackRequest(BaseModel):
	"""§CHAN-1's Inbound use case "Callback requests (`CALLBACK`)" and §CHAN-2's second `→` prompt.

	One record for the one request arriving on either channel, because §CHAN-2's Integration clause
	puts every channel's report into one backend — a callback asked for over USSD and the same
	callback asked for by SMS are one thing, and two stores would be the duplicate that clause's
	dedup exists to prevent.

	It is a record of its own rather than a field on `CaseReport`, which is where the first cut put
	it and why the field was written and never set. A case report requires a county and a community,
	and a person who presses `2` on a feature phone has given neither: building one to carry the
	callback would have invented a location and filed a suspected case that nobody reported. What
	the person did give is a phone and a consent to be called, and that is the whole of this model.

	`location_shared` is the *consent* §CHAN-2's first prompt asks for, not a position. The
	coordinates are §LOC-003's business and a USSD session carries none — recording a boolean as a
	location would be the invented data this model exists to avoid.
	"""
	model_config = MODEL_CONFIG
	request_id: str = Field(default_factory=lambda: 'CB-' + uuid7str().replace('-', '').upper()[:8])
	msisdn: str = Field(pattern=r'^\+254\d{9}$')
	session_id: str
	# The symptom the caller selected, by the engine's own key, or None when the request came from
	# the keyword path rather than the menu. Named rather than left off because a health worker
	# ringing someone back is owed the reason they are ringing.
	symptom: str | None = None
	location_shared: bool = False
	lang: str = 'en'
	requested_at_ms: int
	# Filled by the deployment that takes the request, so a queue that was read can be told from one
	# that was never looked at. §CHAN-1's bullet is that the request is *recorded*; a record with no
	# way to say it was answered is a record that fills up.
	handled: bool = False


class PushPayload(BaseModel):
	"""One notification on its way to a person.

	`subject_ref` is the person it is *for*, and it is required because a notification without one
	is a notification nobody receives: §11.4 COM-104's correction is addressed to the person who
	flagged the rumour, and a payload that named no recipient could be "sent" for a year while no
	one was ever told anything. `category` is §ALT-003's own preference vocabulary, so the
	subscription check has a value to read rather than a route to guess at — a category absent from
	the catalogue would make the toggle a decoration.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str = Field(min_length=1)
	title: str
	body: str
	category: str = 'community_alerts'
	tier_feature: str | None = None