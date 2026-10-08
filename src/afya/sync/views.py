"""Offline-first sync models (spec §16)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class ConflictStrategy(str, Enum):
	lww = 'last_write_wins'
	server_auth = 'server_authoritative'
	append_only = 'append_only'


STRATEGY_MATRIX: dict[str, ConflictStrategy] = {
	'symptom_logs': ConflictStrategy.lww,
	'temperature': ConflictStrategy.lww,
	'case_reports': ConflictStrategy.server_auth,
	'immunisation': ConflictStrategy.server_auth,
	'medication': ConflictStrategy.lww,
	'facility': ConflictStrategy.server_auth,
	'content': ConflictStrategy.server_auth,
	'proximity_tokens': ConflictStrategy.append_only,
}


class SyncOp(BaseModel):
	model_config = MODEL_CONFIG
	op_id: str = Field(pattern=r'^OP-[A-Z0-9]{6,}$')
	dataset: str
	server_version: int = Field(default=0, ge=0)
	client_ts: int
	server_ts: int = 0
	payload: dict[str, str] = Field(default_factory=dict)
	attempt: int = 0
	synced: bool = False


class SyncStatus(BaseModel):
	model_config = MODEL_CONFIG
	pending: int
	synced: int
	conflicts: int