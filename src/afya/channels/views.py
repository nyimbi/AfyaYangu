"""Channel domain models (spec §5, CHAN-000..006)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class SmsOut(BaseModel):
	model_config = MODEL_CONFIG
	to_msisdn: str = Field(pattern=r'^\+254\d{9}$')
	body: str = Field(max_length=1600)
	segments: int = Field(ge=1, le=10)
	zero_rated: bool = True


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