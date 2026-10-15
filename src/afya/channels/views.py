"""Channel domain models (spec §5, CHAN-000..006)."""
from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from afya.channels.outbound import PlainLanguageReading, plain_language
from afya.derived import DerivedFields
from afya.ids import uuid7str
from afya.strings import LANGUAGE_NAME_FOR

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class SmsOut(DerivedFields, BaseModel):
	"""One outbound SMS, with whether the person receiving it is charged and how plain it reads.

	`zero_rated` has no default. It used to default to `True`, which meant every message the system
	sent was stamped free whether or not any carrier agreement existed — a claim nothing could make
	false, checked only by an assert on the value it had just been handed. It is now resolved from
	§5.2's cost table and §18.8's pulled billing rules (`afya.channels.cost`), so a caller that does
	not know has to say so by omission rather than by inheriting "free".

	`plain` is §5.3 CHAN-1's Format bullet — "plain language" — carried on the message rather than
	measured in a report beside it, so the property travels with every body the channel sends. It is a
	computed field over `body` and cannot be set, which is why the model mixes in `DerivedFields`: a
	client that reads a message back and posts it would otherwise be refused for a key it never wrote.
	"""

	model_config = MODEL_CONFIG
	to_msisdn: str = Field(pattern=r'^\+254\d{9}$')
	body: str = Field(max_length=1600)
	segments: int = Field(ge=1, le=10)
	zero_rated: bool

	@computed_field  # type: ignore[prop-decorator]
	@property
	def plain(self) -> PlainLanguageReading:
		return plain_language(self.body)


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


# §CHAN-000's `300 chars/sec` bound, the one `schedule_bulletin` already asserts. It is the same
# number here rather than a second one, because a vignette and a bulletin are read at the same
# pace by the same presenter on the same station, and two bounds would drift the first time a
# script ran long.
VIGNETTE_CHARS_PER_SECOND = 300


class VignetteTheme(str, Enum):
	"""§CHAN-000's three themes, and only those three.

	The section prints "Pre-recorded drama vignettes on prevention, care-seeking, and stigma" — a
	closed list, so the enum is the list. A theme the section does not name is a segment somebody
	decided to write, and an open string field would let one into the tree under this feature's
	name.
	"""
	prevention = 'prevention'
	care_seeking = 'care-seeking'
	stigma = 'stigma'


class VignetteLine(BaseModel):
	"""One spoken line of a drama vignette, attributed to a character.

	`speaker` is free text here and is checked against the cast one level up, in `VignetteScene`
	and again on the whole `RadioVignette`. A line whose speaker is not in `roles` is the exact
	defect a vignette model exists to catch: a voice on the radio that belongs to no one in the
	story, which is a script that cannot be recorded without somebody improvising a character the
	writer never wrote.
	"""
	model_config = MODEL_CONFIG
	speaker: str = Field(min_length=1)
	text: str = Field(min_length=1)


class VignetteScene(BaseModel):
	"""One numbered scene: where it happens, and who says what.

	Scenes are numbered rather than ordered by list position because the recording session is run
	off a printed script — a director calls "scene 3" and a model whose only ordering is the index
	in a list cannot answer which scene that is.
	"""
	model_config = MODEL_CONFIG
	number: int = Field(ge=1)
	setting: str = Field(min_length=1)
	lines: list[VignetteLine] = Field(min_length=1)

	@model_validator(mode='after')
	def _every_line_names_a_speaker(self) -> Self:
		"""A line with a blank speaker is not an unattributed line, it is a corrupt one: an empty
		string would pass a `speaker in roles` check the moment somebody put `''` in the cast."""
		assert all(line.speaker.strip() for line in self.lines), (
			'a scene has a line with no speaker — an unattributed line is not a vignette'
		)
		return self


class RadioVignette(DerivedFields, BaseModel):
	"""§CHAN-000's "Pre-recorded drama vignettes on prevention, care-seeking, and stigma".

	**The recording is not in this model, and that is the point.** A vignette is a produced audio
	asset; what the tree can build and review is the *script*, and this model is the script. The
	audit row stays `deferred` rather than `carried` on exactly that distinction: `RadioBulletin`
	already carries a `script` and no recording, so claiming this row carried would be claiming to
	have produced audio with nothing to play. The RECORDING is the broadcaster's, and §ACC-001 and
	§ACC-002 both refuse synthetic narration in a local language no speaker has validated — the
	same reason the row one above them refuses a synthetic voice. The script, though, is buildable
	and reviewable before a station ever sees it, which is what makes the deferral honest rather
	than an excuse.

	**Why this is not a `RadioBulletin` with a longer script.** §CHAN-000 lists the drama vignette
	beside the situation update and the myth-busting segment as a *different* format, and the
	difference is structure: a bulletin is one voice reading a script, and a vignette is dialogue
	between named characters across numbered scenes. Collapsing the two would let a monologue be
	filed as a drama, and the checks below — a cast, numbered scenes, every line attributed to
	somebody in it — are the checks that tell the two apart.

	**The three asserts here are the format.** A vignette with no cast is a monologue; a vignette
	whose scenes are not numbered is a transcript; a vignette with a line spoken by someone not in
	the cast is a script that cannot be recorded as written. All three are runtime checks at
	construction, in the same spirit as `schedule_bulletin`'s slot bound, because a script is
	written once and read by a station that has no way to know the model would have refused it.

	`lang` is checked against §CHAN-000's own language coverage — the codes in
	`afya.access.views:LANGUAGE_MATRIX`, the same registry the SMS prefix and the voice matrix read
	— so a vignette cannot declare a language the section does not list.
	"""

	model_config = MODEL_CONFIG
	vignette_id: str = Field(default_factory=lambda: 'VIG-' + uuid7str().replace('-', '').upper()[:8])
	station: str = Field(min_length=1)
	air_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')
	duration_s: int = Field(ge=15, le=3600)
	theme: VignetteTheme
	# §CHAN-000's coverage list, by its own codes. The section names the languages in prose
	# ("Swahili, Dholuo, Luhya (Bukusu, Maragoli), Kalenjin, Kikuyu, Kamba, Somali, Maasai, Turkana,
	# Kisii, Taita, Pokomo, and others"); `LANGUAGE_NAME_FOR` is the code side of the registry the
	# rest of the tree reads, so the model refuses a code no surface can serve.
	lang: str
	# The cast. A set, so a character cannot be in it twice, and non-empty, because a vignette with
	# no cast is a monologue wearing a drama's name.
	roles: set[str] = Field(min_length=1)
	scenes: list[VignetteScene] = Field(min_length=1)
	script: str = Field(min_length=1)

	def model_post_init(self, _context: object) -> None:
		assert self.lang in LANGUAGE_NAME_FOR, (
			f'{self.lang!r} is not a language this station broadcasts in; the section lists '
			f'{sorted(LANGUAGE_NAME_FOR)}'
		)
		assert all(role.strip() for role in self.roles), 'a cast member has no name'
		# Numbered, and consecutive from 1: a script whose scenes skip a number is a script with a
		# missing scene, and the director reads the numbers off the page.
		assert [s.number for s in self.scenes] == list(range(1, len(self.scenes) + 1)), (
			'the scenes are numbered from 1 without gaps'
		)
		speakers = {line.speaker for scene in self.scenes for line in scene.lines}
		unknown = speakers - self.roles
		assert not unknown, (
			f'{sorted(unknown)} speak in this vignette but are not in its cast — a line attributed '
			f'to a character who is not in `roles` cannot be recorded as written'
		)
		assert len(self.script) <= VIGNETTE_CHARS_PER_SECOND * self.duration_s, (
			'script too long for slot'
		)

	@computed_field  # type: ignore[prop-decorator]
	@property
	def cast(self) -> list[str]:
		"""The cast in a stable order, for a printed script.

		`roles` is a set, and a set has no order a caller can print. This is the reading order, not
		a second source of truth — it is derived from `roles`, so the two cannot disagree.
		"""
		return sorted(self.roles)


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


class ChannelReport(BaseModel):
	"""§5.4's "single case-report backend" for the channels that have no CHW standing behind them.

	The dedup machinery §5.4 describes was real and unreachable. `CaseReport.reporter_msisdn` reaches
	`IdentityService.dedup_key`, which normalises `0712345678` and `+254712345678` onto one key — and
	`CommunityService.submit_case` has exactly one caller, `POST /community/cases`, guarded on the
	`assigned` scope. A USSD caller and a WhatsApp sender hold no token at all, and no channel code
	built a `CaseReport`. So §5.4's "deduplicated by phone number" held for the app and the CHW and
	for neither of the two channels §4.1 gives to people without smartphones, and §CHAN-2's
	Integration sentence ("Reports flow into the same backend as app and WhatsApp reports") was a
	sentence about a flow that did not exist.

	**It is not a `CaseReport`, and the reason is the same one `CallbackRequest` records.** A case
	report requires a `county` and a `community`; a person who presses `3` on a feature phone has
	given neither, and there is no phone-to-county mapping anywhere in the tree to supply one from.
	Building a `CaseReport` to carry their report would invent a location and file a suspected case
	nobody reported — the failure the callback model was split out to avoid, and the reason this is a
	second model rather than a second field.

	So what is stored is what was actually said, by the phone that said it: the symptom the engine
	heard, the menu item it was read from, and the phone number §5.4 keys the dedup on. `county` is
	optional and stays `None` on every USSD and SMS report today, because those channels carry no
	locality — and `None` here is load-bearing rather than empty, since it is what tells the signal
	ledger it cannot count this report into a baseline. A report the product cannot place is still a
	report the product holds.

	`consent_to_store` is the grant §5.4's consent crossing asks for, and it is *not* defaulted: a
	report stored without one would be the app keeping a person's health data on the strength of a
	wiring mistake, which is the direction `may_store_symptoms` was written to refuse.
	"""
	model_config = MODEL_CONFIG
	report_id: str = Field(default_factory=lambda: 'CHR-' + uuid7str().replace('-', '').upper()[:8])
	channel: str = Field(pattern=r'^(ussd|sms|whatsapp|app)$')
	msisdn: str = Field(pattern=r'^\+254\d{9}$')
	# What the engine heard, in its own vocabulary, in the order it was named. Empty is a real
	# answer: §CHAN-2's "Cough" and "Other" entries are offered and the engine has no word for
	# either, so a caller who picks one has reported something the engine cannot classify — which
	# `symptom_label` below preserves rather than the empty list discarding.
	symptoms: list[str] = []
	# §CHAN-2's menu item, in the section's own words, when the report came from a menu. This is the
	# half that survives an engine miss, and it is the reason a "Cough" report is not an empty one.
	symptom_label: str | None = None
	county: str | None = None
	lang: str = 'en'
	reported_at_ms: int
	# §5.4's dedup key for this phone, resolved through the one identity model rather than recomputed
	# — a second spelling of a number is a second person, which is the duplicate this key exists to
	# collapse.
	dedup_key: str
	consent_to_store: bool
	# The same state `CallbackRequest` carries and for the same reason: a queue that was read can be
	# told from one nothing ever looked at.
	handled: bool = False

	@model_validator(mode='after')
	def _a_report_names_something(self) -> Self:
		"""A report with neither an engine symptom nor a menu label is not a report.

		The empty-symptom case is legitimate and the empty-*report* case is not, and the difference is
		`symptom_label`: a caller who chose "Cough" said a word, and a WhatsApp body that named no
		symptom the engine knows said nothing it can act on. Refusing the second is what keeps a
		question ("what is Ebola?") from being filed as a symptom report and counted in a baseline.
		"""
		assert self.symptoms or self.symptom_label, (
			'a channel report names neither an engine symptom nor the menu item it was read from'
		)
		return self


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