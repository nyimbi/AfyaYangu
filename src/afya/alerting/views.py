"""Alerting models (spec §9.6 ALT-003, §10.3 ALT-001/002, §11.8 ALT-004)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


# --- ALT-001 community alert feed --------------------------------------------------------

# The public hazard types a feed item can carry.
FEED_CATEGORIES: tuple[str, ...] = (
	'outbreak', 'weather', 'flood', 'fire', 'road', 'security', 'drug_recall', 'water',
	'food_recall', 'service',
)

# Which preference governs each feed category. A feed item and a preference are not the same
# vocabulary — a person switches off "water quality", they do not switch off "flood" — so the
# link between them has to be stated rather than assumed. Without it a subscriber naming a
# preference could never match an item, and the socket would silently deliver nothing.
FEED_PREFERENCE: dict[str, str] = {
	'outbreak': 'disease_alerts', 'weather': 'county_alerts', 'flood': 'county_alerts',
	'fire': 'county_alerts', 'road': 'county_alerts', 'security': 'county_alerts',
	'drug_recall': 'facility_alerts', 'water': 'water_quality', 'food_recall': 'nutrition',
	'service': 'facility_alerts',
}


def governing_preference(feed_category: str) -> str:
	"""The preference category that decides whether `feed_category` is delivered."""
	assert feed_category in FEED_PREFERENCE, f'unknown feed category {feed_category}'
	return FEED_PREFERENCE[feed_category]


class FeedItem(BaseModel):
	model_config = MODEL_CONFIG
	item_id: str
	category: str = Field(pattern=r'^(' + '|'.join(FEED_CATEGORIES) + r')$')
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

# A preference can only govern a feed category if the person is able to switch it off, so every
# value in FEED_PREFERENCE must be toggleable. Asserted here rather than discovered in production.
assert set(FEED_PREFERENCE.values()) <= set(TOGGLEABLE), 'a feed category is governed by a preference nobody can set'

# The preferences that govern at least one feed category — the ones a subscriber may name.
FEED_SCOPED_PREFERENCES: frozenset[str] = frozenset(FEED_PREFERENCE.values())


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
