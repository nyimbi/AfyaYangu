"""Alerting models (spec §9.6 ALT-003, §10.3 ALT-001/002, §11.8 ALT-004)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


# --- ALT-001 community alert feed --------------------------------------------------------

class FeedItem(BaseModel):
	model_config = MODEL_CONFIG
	item_id: str
	category: str = Field(pattern=r'^(outbreak|weather|flood|fire|road|security|drug_recall|water|food_recall|service)$')
	headline: str = Field(max_length=120)
	body: str = Field(max_length=600)
	source: str
	verified: bool
	published_iso: str
	county: str | None = None


# --- ALT-003 personalised alert preferences ----------------------------------------------

# Categories a user may switch off. Critical categories are absent by construction — they are
# not disableable, so they have no toggle to flip (§9.6).
TOGGLEABLE: tuple[str, ...] = (
	'county_alerts', 'disease_alerts', 'facility_alerts', 'appointment_reminders',
	'medication_reminders', 'immunisation_reminders', 'community_alerts', 'air_quality',
	'water_quality', 'nutrition', 'health_tips',
)
CRITICAL: tuple[str, ...] = ('exposure_notification', 'immediate_danger')


class AlertPreferences(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	enabled: dict[str, bool] = Field(default_factory=dict)
	quiet_hours: tuple[int, int] | None = None
	channels: list[str] = Field(default_factory=lambda: ['native'])


class PreferenceUpdate(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	category: str
	enabled: bool


class PreferenceReceipt(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	category: str
	enabled: bool
	critical: bool
	message: str


# --- ALT-002 family safety check-in ------------------------------------------------------

class SafetyCheckIn(BaseModel):
	model_config = MODEL_CONFIG
	checkin_id: str = Field(pattern=r'^SAFE-[A-Z0-9]{8,}$')
	subject_ref: str
	at_iso: str
	note: str | None = Field(default=None, max_length=200)
	channel: str = Field(default='native', pattern=r'^(native|sms)$')


class FamilyStatus(BaseModel):
	model_config = MODEL_CONFIG
	family_ref: str
	members_safe: list[str]
	members_unknown: list[str]
	last_checkin_iso: str | None = None
	board: str


# --- ALT-004 exposure notification -------------------------------------------------------

class ExposureNotification(BaseModel):
	model_config = MODEL_CONFIG
	notification_id: str
	subject_ref: str
	contact_window_days: int = Field(default=21, ge=1, le=28)
	headline: str
	body: str
	delivery_channels: list[str]
	enrols_monitoring: bool
	callback_offered: bool
	acknowledged: bool = False


class ExposureAck(BaseModel):
	model_config = MODEL_CONFIG
	notification_id: str
	subject_ref: str
	acknowledged_iso: str
	request_callback: bool = False
