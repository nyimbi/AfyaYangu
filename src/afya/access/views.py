"""Accessibility models (spec §12.1 ACC-001..005)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §ACC-002 priority order for the voice interface. `tier` is 1 for languages that must ship at
# launch and 2 for those that follow; `asr` records whether on-device recognition exists yet.
LANGUAGE_MATRIX: dict[str, dict[str, object]] = {
	'Kiswahili': {'code': 'sw', 'tier': 1, 'asr': True, 'tts': True},
	'English': {'code': 'en', 'tier': 1, 'asr': True, 'tts': True},
	'Dholuo': {'code': 'luo', 'tier': 1, 'asr': False, 'tts': True},
	'Luhya (Bukusu)': {'code': 'bxk', 'tier': 1, 'asr': False, 'tts': True},
	'Luhya (Maragoli)': {'code': 'rag', 'tier': 2, 'asr': False, 'tts': False},
	'Kalenjin': {'code': 'kln', 'tier': 2, 'asr': False, 'tts': False},
	'Kikuyu': {'code': 'ki', 'tier': 1, 'asr': False, 'tts': True},
	'Kamba': {'code': 'kam', 'tier': 2, 'asr': False, 'tts': False},
	'Somali': {'code': 'so', 'tier': 2, 'asr': False, 'tts': False},
	'Maasai': {'code': 'mas', 'tier': 2, 'asr': False, 'tts': False},
	'Kisii': {'code': 'guz', 'tier': 2, 'asr': False, 'tts': False},
	'Meru': {'code': 'mer', 'tier': 2, 'asr': False, 'tts': False},
	'Taita': {'code': 'dav', 'tier': 2, 'asr': False, 'tts': False},
}

MIN_TOUCH_TARGET_DP = 48


class AccessProfile(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	simple_mode: bool = False
	large_text: bool = False
	high_contrast: bool = False
	read_aloud: bool = True
	voice_input: bool = False
	lang: str = 'en'


class UIAsset(BaseModel):
	"""One screen described the way a low-literacy interface needs it (§ACC-001)."""
	model_config = MODEL_CONFIG
	screen_id: str
	pictogram: str
	label: str
	risk_colour: str = Field(pattern=r'^(green|yellow|red|neutral)$')
	universal_symbol: str | None = None
	touch_target_dp: int = Field(ge=MIN_TOUCH_TARGET_DP)
	read_aloud_text: str
	simple_mode_visible: bool = True


class VoiceRequest(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	lang: str
	utterance: str = Field(min_length=1, max_length=1000)
	offline: bool = False
	# §ACC-002's "voice-to-text for CHW notes and case descriptions". The route already took any
	# `VoiceRequest` and returned an *intent* — which is a symptom-reporting path, not a
	# transcription: a CHW dictating "the patient's house is behind the market, three children, one
	# with a rash" got `intent=unknown` and their words discarded. `purpose` says which of the two
	# the caller is doing, because they are answered differently and only one of them is a triage.
	purpose: str = Field(default='symptoms', pattern=r'^(symptoms|note)$')


class VoiceAudioRequest(BaseModel):
	"""§ACC-002's actual input: audio, not text. The text models were the shape of the gap.

	`VoiceRequest` takes an `utterance`, which is a *transcript* — so every voice path in the tree
	began after the hard part was already done, and a person who cannot type had no way in. This is
	the model for the thing a handset actually produces, and `purpose` carries over unchanged
	because a note and a symptom report are still two different questions asked of the same audio.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	lang: str
	purpose: str = Field(default='symptoms', pattern=r'^(symptoms|note)$')


class VoiceResult(BaseModel):
	model_config = MODEL_CONFIG
	lang: str
	transcript: str
	intent: str
	confidence: float = Field(ge=0, le=1)
	spoken_reply: str
	on_device: bool
	# Which language the answer is actually in, on §ACC-002's `answerable` rule: a speaker of a
	# language with no table is served English *and told so*, rather than reading English believing
	# it is Dholuo. `lang` stays the language the caller asked for; this is the one they got.
	served_in: str = 'en'
	# The symptoms a free-text utterance names, read out of it rather than assumed. This is the
	# field that makes "voice-guided symptom reporting" a report and not a menu: the caller's own
	# words enter the engine, and the client shows which of them were understood.
	symptoms: list[str] = Field(default_factory=list)
	# Which recogniser produced the transcript, when the request arrived as audio. `None` means the
	# caller sent text and no recognition ran — the two are different claims and a client that
	# rendered "recognised on device" over a typed message would be reporting a step that did not
	# happen. `LANGUAGE_MATRIX`'s `asr` flag says which languages ship recognition at all.
	recogniser: str | None = None


class SamplingContext(BaseModel):
	"""§ACC-004's "context (charging, stationary, time of day)".

	The section names the contexts and prints no rate, so a context selects a **duty multiplier** on
	the device's own sampling baseline — not an absolute Hz, which would be a figure invented to fill
	a table. The device multiplies; the server decides by how much and says why.

	§14.2 names two further suppressions in its own words — "disabled when on a call, in a meeting,
	or when the user sets 'do not monitor'" — and they are contexts rather than settings, so they sit
	here beside the three §ACC-004 prints rather than in a separate model.
	"""
	model_config = MODEL_CONFIG
	charging: bool = False
	stationary: bool = False
	hour: int = Field(default=12, ge=0, le=23)
	on_call: bool = False
	do_not_monitor: bool = False


class BatteryProfile(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	intensity: str = Field(pattern=r'^(low|balanced|maximum)$')
	# §13.1 sensor slugs the intensity switches on. Derived from `INTENSITY_READINGS` through the
	# sensor-to-feature table, because the six entries this used to hold — `fall`, `cough`, `ppg`,
	# `respiration`, `sleep`, `ambient` — are `SenseKind` *reading* kinds, and not one of them was a
	# sensor §13.1 has a row for. A screen titled "sensors on" was listing six things the app cannot
	# measure with, and the client that switched hardware on by these names switched on nothing.
	sensors_enabled: list[str]
	# The reading kinds those sensors produce — what the client actually collects. Both lists travel
	# because they answer different questions: which hardware is on, and what comes back from it.
	readings_enabled: list[str]
	estimated_daily_pct: float = Field(ge=0, le=100)
	# True because the module demonstrably responds to the charging state: the duty and the drain
	# both move when `SamplingContext.charging` is set, and a test asserts the two rates differ. It
	# was a hardcoded `True` with nothing reading a charging state, which is a claim with no
	# referent.
	charging_adaptive: bool
	battery_saver: bool
	# Which context was applied and why, in words a person reads in settings.
	context: str
	context_reason: str
	# The multiplier on the device's sampling baseline. Unitless on purpose: §ACC-004 prints no
	# rate, so this is the part the server owns and the baseline is the handset's.
	sampling_duty: float = Field(ge=0, le=4)


class DeviceCompatibility(BaseModel):
	model_config = MODEL_CONFIG
	platform: str = Field(pattern=r'^(android|ios)$')
	os_min: str
	apk_base_mb: float = Field(ge=0, le=15)
	go_edition_supported: bool
	no_play_services: bool
	min_ram_mb: int
	on_demand_modules: dict[str, float]
	missing_sensor_fallbacks: dict[str, str]
