"""Surveillance Tier-4 models — dormant outbreak superpower (spec §11, §19.4).

`disease` is validated against §3.3 principle 12's vocabulary rather than a pattern written out
here. The pattern this module used to carry omitted `measles`, which principle 12 names as one of
the diseases Tier 4 activates for, so the county reporting measles was the county whose early-warning
signal the system refused to compute.
"""
from pydantic import BaseModel, ConfigDict, Field

from afya.registry.diseases import DISEASE_PATTERN

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class CountySignal(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	disease: str = Field(default='evd', pattern=DISEASE_PATTERN)
	week_isoyear: int = Field(ge=2024, le=2100)
	week: int = Field(ge=1, le=53)
	fever_reports: int = Field(ge=0)
	hotline_calls: int = Field(ge=0)
	confirmed_cases: int = Field(ge=0)


class SignalReading(BaseModel):
	model_config = MODEL_CONFIG
	county: str
	disease: str = Field(default='evd', pattern=DISEASE_PATTERN)
	z_score: float
	risk: str = Field(pattern=r'^(low|moderate|high)$')
	weeks_observed: int = Field(ge=1)


class ProximityToken(BaseModel):
	model_config = MODEL_CONFIG
	token: str = Field(min_length=32, max_length=64)
	seen_at_ms: int
	county: str
	exposure_risk: bool = False


class Geofence(BaseModel):
	model_config = MODEL_CONFIG
	geofence_id: str
	lat: float = Field(ge=-5, le=6)
	lon: float = Field(ge=33, le=43)
	radius_m: int = Field(gt=50, le=50_000)
	risk_type: str = Field(pattern=r'^(general|outbreak)$')
	alert_level: str = Field(pattern=r'^(low|medium|high)$')
	# §LOC-001's Alert content is "Avoid [specific location]", and the section's own bracket is the
	# load-bearing part: an alert that tells a person to avoid "the named location" names nothing, so
	# the one action it asks for is the one it does not make possible. The label is the county or
	# place the county health authority drew the zone around, and it is optional because a zone may
	# be registered before anyone has named it — in which case the alert says so rather than
	# inventing a place name a person would act on.
	place_label: str | None = Field(default=None, max_length=80)
	# §LOC-001's Tier 4 behaviour is "alert on entry **and exit**", and the two need telling apart:
	# a client that renders the same sentence for both has told someone leaving a zone the same thing
	# it told them entering, and the 21-day watch that started on entry is still running.
	county: str = ''