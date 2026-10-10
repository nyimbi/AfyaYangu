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


class ConnectionClass(str, Enum):
	"""How the handset is connected. §16.4's adaptive sync turns on this, not on a guess."""

	wifi = 'wifi'
	metered = 'metered'
	offline = 'offline'


class SyncPolicy(BaseModel):
	"""What one connection class is allowed to spend (§16.4 bandwidth minimisation).

	The numbers are the policy, not a measurement: they encode "on a metered connection, send less
	and less often". `poll_interval_s` is what makes the sync adaptive — a phone on mobile data
	asking every 30 seconds costs the user money for nothing, while on wifi there is no reason to
	wait.
	"""

	model_config = MODEL_CONFIG
	connection: ConnectionClass
	batch_max_ops: int = Field(ge=1)
	delta_only: bool
	compress: bool
	compress_threshold_bytes: int = Field(ge=0)
	poll_interval_s: int = Field(ge=0)
	image_max_edge_px: int = Field(ge=64)
	image_quality: int = Field(ge=1, le=100)


POLICY_BY_CONNECTION: dict[ConnectionClass, SyncPolicy] = {
	ConnectionClass.wifi: SyncPolicy(
		connection=ConnectionClass.wifi, batch_max_ops=500, delta_only=True, compress=True,
		compress_threshold_bytes=1024, poll_interval_s=30, image_max_edge_px=2048, image_quality=85,
	),
	ConnectionClass.metered: SyncPolicy(
		connection=ConnectionClass.metered, batch_max_ops=50, delta_only=True, compress=True,
		compress_threshold_bytes=512, poll_interval_s=300, image_max_edge_px=1280, image_quality=60,
	),
	ConnectionClass.offline: SyncPolicy(
		# Nothing is sent, and nothing is polled. The queue is the whole story until a network
		# appears, which is why the offline policy is not merely "metered but slower".
		connection=ConnectionClass.offline, batch_max_ops=1, delta_only=True, compress=True,
		compress_threshold_bytes=512, poll_interval_s=0, image_max_edge_px=1280, image_quality=60,
	),
}

assert set(POLICY_BY_CONNECTION) == set(ConnectionClass), 'every connection class needs a policy'


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


class SyncBatch(BaseModel):
	"""One request's worth of queued writes (§16.4 batching), with what it will cost on the wire."""

	model_config = MODEL_CONFIG
	connection: ConnectionClass
	ops: list[SyncOp]
	encoding: str = Field(pattern=r'^(identity|gzip)$')
	wire_bytes: int = Field(ge=0)
	raw_bytes: int = Field(ge=0)
	deferred: int = Field(ge=0)  # ops left for the next batch, not dropped

	@property
	def saved_ratio(self) -> float:
		"""Fraction of the raw payload the encoding removed. 0.0 when nothing was compressed."""
		return 0.0 if self.raw_bytes == 0 else round(1.0 - (self.wire_bytes / self.raw_bytes), 4)


class SyncStatus(BaseModel):
	model_config = MODEL_CONFIG
	pending: int
	synced: int
	conflicts: int
