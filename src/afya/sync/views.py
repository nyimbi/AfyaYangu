"""Offline-first sync models (spec §16)."""
from enum import Enum
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class ConflictStrategy(str, Enum):
	lww = 'last_write_wins'
	server_auth = 'server_authoritative'
	append_only = 'append_only'


class ConflictRule(BaseModel):
	"""One §16.3 row: the dataset, its strategy, and the rationale the spec states for it.

	`appealable` carries §16.3's own qualifier on the immunisation row — "Server-authoritative on
	conflict, **user can appeal**". A strategy alone could not express it, so the row is the unit
	rather than the strategy, and a conflict the client lost is recoverable exactly where the spec
	says it is.
	"""
	model_config = MODEL_CONFIG
	dataset: str = Field(pattern=r'^[a-z][a-z0-9_]*$')
	strategy: ConflictStrategy
	rationale: str = Field(min_length=1)
	appealable: bool = False

	@model_validator(mode='after')
	def _an_appeal_only_makes_sense_against_a_server_decision(self) -> Self:
		"""An appeal is a person asking a server to reconsider. Under last-write-wins the newest
		write already won on the merits and there is nothing to reconsider; under append-only there
		is no conflict at all."""
		if self.appealable and self.strategy is not ConflictStrategy.server_auth:
			raise ValueError(f'{self.dataset} is {self.strategy.value}, so there is no decision to appeal')
		return self


# §16.3's matrix, in the spec's own order, with the spec's own rationale. One row per data type —
# the dict below is derived from this rather than stated beside it.
CONFLICT_RULES: tuple[ConflictRule, ...] = (
	ConflictRule(dataset='symptom_logs', strategy=ConflictStrategy.lww,
		rationale='Personal data, low conflict'),
	ConflictRule(dataset='temperature', strategy=ConflictStrategy.lww,
		rationale='Append-only in practice'),
	ConflictRule(dataset='case_reports', strategy=ConflictStrategy.server_auth,
		rationale='Clinical accuracy critical'),
	ConflictRule(dataset='immunisation', strategy=ConflictStrategy.server_auth, appealable=True,
		rationale='Safety-critical'),
	ConflictRule(dataset='medication', strategy=ConflictStrategy.lww, rationale='Personal'),
	ConflictRule(dataset='facility', strategy=ConflictStrategy.server_auth,
		rationale='Central source of truth'),
	ConflictRule(dataset='content', strategy=ConflictStrategy.server_auth,
		rationale='Must match official messaging'),
	ConflictRule(dataset='proximity_tokens', strategy=ConflictStrategy.append_only,
		rationale='No conflicts possible'),
)

RULE_BY_DATASET: dict[str, ConflictRule] = {r.dataset: r for r in CONFLICT_RULES}
STRATEGY_MATRIX: dict[str, ConflictStrategy] = {r.dataset: r.strategy for r in CONFLICT_RULES}


class AppealState(str, Enum):
	none = 'none'
	available = 'available'
	filed = 'filed'
	upheld = 'upheld'
	declined = 'declined'


class ConflictRecord(BaseModel):
	"""A conflict the client lost, kept rather than silently retried.

	Before this a losing op had its `attempt` incremented and stayed in the queue, so the client's
	version was discarded on every pass with nothing recording that it had been, and `SyncStatus`
	reported the count of *pending* ops under the name `conflicts`. Two different facts wore one
	name, and the one a person needed — my reading was overruled — was the one not carried.
	"""
	model_config = MODEL_CONFIG
	op_id: str
	dataset: str
	strategy: ConflictStrategy
	client_ts: int
	server_ts: int
	client_payload: dict[str, str] = Field(default_factory=dict)
	server_payload: dict[str, str] = Field(default_factory=dict)
	appealable: bool
	appeal: AppealState = AppealState.none
	appeal_note: str | None = None

	def resolved(self) -> bool:
		"""Whether this conflict has stopped needing anyone's attention. A conflict with no appeal
		path is resolved the moment it is recorded — the server decides and that is the end of it.
		An appealable one stays open until the appeal is decided."""
		return not self.appealable or self.appeal in (AppealState.upheld, AppealState.declined)


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


class SendOutcome(str, Enum):
	"""Which edge of §16.2's flow a send took. The diagram has three exits from "Batch & send", and
	they are not interchangeable: an ack marks the op synced, a missing ack earns a backoff, and no
	network earns none — the phone was offline, which is not the op's fault and not something to
	wait out once a network returns."""

	acked = 'acked'
	no_ack = 'no_ack'
	no_network = 'no_network'


class SyncOp(BaseModel):
	"""One queued write, with the retry schedule §16.2's diagram draws.

	`attempt` numbers the attempt about to be made — `enqueue` seeds it at 1 — and `retry_at_ms` is
	when the op may next be offered to the network. Both are needed: `attempt` alone was a write-only
	counter, so nothing could tell a first try from a fifth, and an op that could not be sent had
	nowhere to record when it should be tried again — so it was re-sent on every flush, which is the
	opposite of backoff.

	`retry_at_ms` is `None` for an op that has never failed, which means *due now*. That is what
	makes the offline case work: an op deferred because there was no network keeps its due-now
	status, so the moment a network appears it goes out on the next flush rather than waiting out a
	delay it earned during an outage it could not have avoided.
	"""

	model_config = MODEL_CONFIG
	op_id: str = Field(pattern=r'^OP-[A-Z0-9]{6,}$')
	dataset: str
	server_version: int = Field(default=0, ge=0)
	client_ts: int
	server_ts: int = 0
	payload: dict[str, str] = Field(default_factory=dict)
	attempt: int = Field(default=0, ge=0)
	synced: bool = False
	retry_at_ms: int | None = None

	def due(self, now_ms: int) -> bool:
		"""Whether the backoff window has elapsed. An op that has never failed is always due."""
		return self.retry_at_ms is None or now_ms >= self.retry_at_ms


class SyncQueue(Protocol):
	"""The one method a feature needs from the sync layer to be offline-capable.

	Declared here rather than in each service that takes one, because two declarations of one
	contract drift: `MonitoringService` and `CommunityService` both need exactly this, and a
	`Protocol` that lives beside the model it takes cannot disagree with it about the shape.

	Structural rather than an import of `SyncService` for two reasons. The dependency then runs one
	way — `sync` imports neither service, so neither can form a cycle through it — and a test can
	pass a queue that records what it was handed instead of standing up the whole sync service.
	"""

	async def enqueue(self, op: SyncOp) -> SyncOp: ...


class SyncBatch(BaseModel):
	"""One request's worth of queued writes (§16.4 batching), with what it will cost on the wire."""

	model_config = MODEL_CONFIG
	connection: ConnectionClass
	ops: list[SyncOp]
	encoding: str = Field(pattern=r'^(identity|gzip|br)$')
	wire_bytes: int = Field(ge=0)
	raw_bytes: int = Field(ge=0)
	deferred: int = Field(ge=0)  # ops left for the next batch, not dropped

	@property
	def saved_ratio(self) -> float:
		"""Fraction of the raw payload the encoding removed. 0.0 when nothing was compressed."""
		return 0.0 if self.raw_bytes == 0 else round(1.0 - (self.wire_bytes / self.raw_bytes), 4)


class SyncStatus(BaseModel):
	"""One flush's outcome.

	`pending` and `deferred` are different facts and were one number. `pending` is everything still
	queued; `deferred` is the subset §16.2's diagram routes to "Retry with exponential backoff" —
	due now but unsent because no network was available — as against `waiting`, which is queued but
	inside its backoff window and was not offered to the network at all. A client that conflated
	them would re-send an op the backoff had just scheduled to wait, which is the retry storm the
	backoff exists to prevent.
	"""

	model_config = MODEL_CONFIG
	pending: int
	synced: int
	conflicts: int
	deferred: int = 0
	waiting: int = 0
	next_retry_at_ms: int | None = None


class OfflineState(BaseModel):
	"""§16.1 principle 4 / ACC-003's "clear offline indicator in the UI", as the data behind it.

	The indicator is the one place a person learns whether their work is safe, so what it renders
	is computed from the queue rather than asserted: `durable` is False when no store is attached,
	which means §16.1's "every queued write survives app restart" does not hold in that deployment
	and the user should be told rather than reassured.
	"""
	model_config = MODEL_CONFIG
	connection: ConnectionClass
	label: str = Field(min_length=1)
	pending: int = Field(ge=0)
	conflicts: int = Field(ge=0)
	open_conflicts: int = Field(ge=0)
	durable: bool
	last_synced_at_ms: int | None = None
	detail: str = Field(min_length=1)
