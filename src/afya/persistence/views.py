"""Persistence models — SQLite store adapters (Postgres per §15.2 is production swap of same Protocol)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class StoreStats(BaseModel):
	model_config = MODEL_CONFIG
	sync_ops: int = 0
	consents: int = 0
	facilities: int = 0