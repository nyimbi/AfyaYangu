"""Channel domain models (spec §5, CHAN-000..006)."""
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class PushPayload(BaseModel):
	model_config = MODEL_CONFIG
	title: str
	body: str
	tier_feature: str | None = None