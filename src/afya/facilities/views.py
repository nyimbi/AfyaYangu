"""Facility domain models (spec §8.2 FND-001..006, §18.5 MoHF)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class FacilityKind(str, Enum):
	treatment_unit = 'treatment_unit'
	ed = 'ed'
	testing_site = 'testing_site'
	pharmacy = 'pharmacy'
	vaccination_point = 'vaccination_point'


class Facility(BaseModel):
	model_config = MODEL_CONFIG
	facility_id: str
	name: str
	kind: FacilityKind
	county: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	open_now: bool = True
	ed_status: str | None = None
	crowdload: int = Field(default=0, ge=0, le=100)


class NearestRequest(BaseModel):
	model_config = MODEL_CONFIG
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	kind: FacilityKind | None = None
	limit: int = Field(default=3, ge=1, le=20)


class Booking(BaseModel):
	model_config = MODEL_CONFIG
	booking_id: str = Field(pattern=r'^BOOK-[A-Z0-9]{6,}$')
	facility_id: str
	slot_iso: str
	queue_position: int = Field(ge=1, le=500)