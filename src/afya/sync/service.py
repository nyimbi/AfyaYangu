"""Sync service — local-write queue, exponential backoff, §16.3 conflict matrix, append-only proximity tokens."""
import gzip
import json

from afya.logmixin import LogMixin
from afya.sync.views import (
	POLICY_BY_CONNECTION, ConflictStrategy, ConnectionClass, STRATEGY_MATRIX, SyncBatch, SyncOp,
	SyncPolicy, SyncStatus,
)


def backoff_delay_s(attempt: int) -> float:
	assert attempt >= 1, 'attempt starts at 1'
	return min(600.0, 2.0 ** attempt)


def delta_payload(previous: dict[str, str], current: dict[str, str]) -> dict[str, str]:
	"""§16.4 delta sync: only the fields that changed, plus explicit removals.

	A field that disappeared has to be sent as an explicit removal, not omitted — omission means
	"unchanged", so a deletion the user made would otherwise never reach the server and the record
	would come back on the next pull.
	"""
	assert isinstance(previous, dict) and isinstance(current, dict), 'delta needs two mappings'
	out = {k: v for k, v in current.items() if previous.get(k) != v}
	for gone in previous:
		if gone not in current:
			out[f'-{gone}'] = ''
	return out


def apply_delta(previous: dict[str, str], delta: dict[str, str]) -> dict[str, str]:
	"""The server's side of `delta_payload`. Round-trips exactly, removals included."""
	merged = dict(previous)
	for k, v in delta.items():
		if k.startswith('-'):
			merged.pop(k[1:], None)
		else:
			merged[k] = v
	return merged


class SyncService(LogMixin):
	def __init__(self, store=None) -> None:
		self._queue: dict[str, SyncOp] = {}
		self._server_state: dict[str, dict[str, SyncOp]] = {}
		self._store = store
		self._loaded = False
		# dataset -> op_id -> the payload the server last acknowledged. Three levels, not two: the
		# op id alone is not unique across datasets.
		self._last_synced: dict[str, dict[str, dict[str, str]]] = {}
		assert self._queue == {} and self._server_state == {}

	async def load(self) -> int:
		"""Rehydrate the queue from the store. §16.1 promises a queued write survives a restart.

		Without this the queue is written to SQLite and never read back, so an op that was queued
		before a crash is durable on disk and invisible to `flush` — the promise was half kept, in
		the direction that looks like it works. Idempotent, so a second startup is a no-op.
		"""
		if self._loaded or self._store is None:
			self._loaded = True
			return 0
		rows = await self._store.sync_ops()
		for op in rows:
			if not op.synced:
				self._queue[op.op_id] = op
		self._loaded = True
		if self._queue:
			self._log_info('sync queue rehydrated', pending=len(self._queue))
		return len(self._queue)

	async def enqueue(self, op: SyncOp) -> SyncOp:
		assert op.dataset in STRATEGY_MATRIX, f'unknown dataset {op.dataset}'
		op.attempt = 1
		op.synced = False
		self._queue[op.op_id] = op
		if self._store is not None:
			await self._store.save_sync_op(op)
		return op

	def strategy_for(self, dataset: str) -> ConflictStrategy:
		return STRATEGY_MATRIX[dataset]

	# --- §16.4 bandwidth minimisation ---------------------------------------------------------

	def policy_for(self, connection: ConnectionClass) -> SyncPolicy:
		"""The policy a connection class is entitled to. Not a caller-supplied number: a client that
		could ask for the wifi batch size on a metered link would defeat the point."""
		return POLICY_BY_CONNECTION[connection]

	def encode(self, ops: list[SyncOp], connection: ConnectionClass) -> SyncBatch:
		"""Assemble one request's batch: delta payloads, then gzip when it pays for itself.

		Compression is applied only above the policy's threshold *and* only when the compressed form
		is actually smaller — gzip on a 200-byte body adds framing overhead and makes the request
		bigger, which is a real cost on a metered link.
		"""
		policy = self.policy_for(connection)
		batch = ops[: policy.batch_max_ops]
		wire_ops: list[SyncOp] = []
		for op in batch:
			if not policy.delta_only:
				wire_ops.append(op)
				continue
			previous = self._last_synced.get(op.dataset, {}).get(op.op_id)
			if previous is None:
				wire_ops.append(op)
			else:
				delta = delta_payload(previous, op.payload)
				# An op with no changed field is a no-op on the wire; sending an empty delta would
				# spend a request to say nothing.
				if delta:
					wire_ops.append(op.model_copy(update={'payload': delta}))

		raw = json.dumps([o.model_dump(mode='json') for o in wire_ops], separators=(',', ':')).encode()
		encoding = 'identity'
		wire = raw
		if policy.compress and len(raw) >= policy.compress_threshold_bytes:
			packed = gzip.compress(raw, compresslevel=6)
			if len(packed) < len(raw):
				wire, encoding = packed, 'gzip'
		out = SyncBatch(
			connection=connection, ops=wire_ops, encoding=encoding,
			wire_bytes=len(wire), raw_bytes=len(raw), deferred=len(ops) - len(batch),
		)
		self._log_info('sync batch encoded', connection=connection.value, ops=len(wire_ops),
		               wire_bytes=out.wire_bytes, ratio=out.saved_ratio, deferred=out.deferred)
		assert out.wire_bytes <= out.raw_bytes or encoding == 'identity', 'compression must not grow a batch'
		return out

	def next_poll_interval_s(self, connection: ConnectionClass) -> int:
		"""§16.4 adaptive sync: how long to wait before asking again on this connection."""
		return self.policy_for(connection).poll_interval_s

	def image_budget(self, connection: ConnectionClass) -> tuple[int, int]:
		"""§16.4 image compression: (max edge px, quality) for an upload on this connection."""
		p = self.policy_for(connection)
		return (p.image_max_edge_px, p.image_quality)

	def remember_synced(self, op: SyncOp) -> None:
		"""Record what the server now holds for this op, so the next edit can be sent as a delta.

		Called after a successful flush. Without it every write re-sends the whole payload and
		§16.4's delta sync is a claim rather than a behaviour.
		"""
		self._last_synced.setdefault(op.dataset, {})[op.op_id] = dict(op.payload)

	async def resolve(self, op: SyncOp, server: SyncOp) -> tuple[SyncOp, bool]:
		strategy = self.strategy_for(op.dataset)
		if strategy is ConflictStrategy.lww:
			winner = op if op.client_ts > server.server_ts else server
			return (winner, winner is op)
		if strategy is ConflictStrategy.append_only:
			return (server, False)
		return (server, False)

	async def flush(self, now_ms: int) -> SyncStatus:
		await self.load()
		synced = 0
		for op in list(self._queue.values()):
			if op.synced:
				continue
			srv = self._server_state.get(op.dataset, {}).get(op.op_id)
			if srv is None:
				op.synced = True
				self._server_state.setdefault(op.dataset, {})[op.op_id] = op
				synced += 1
				self.remember_synced(op)
				if self._store is not None:
					await self._store.save_sync_op(op)
			else:
				winner, client_won = await self.resolve(op, srv)
				if client_won:
					op.synced = True
					self._server_state[op.dataset][op.op_id] = op
					synced += 1
					self.remember_synced(op)
					if self._store is not None:
						await self._store.save_sync_op(op)
				else:
					op.attempt += 1
					assert backoff_delay_s(op.attempt) > backoff_delay_s(op.attempt - 1), 'backoff monotonic'
		pending = len([o for o in self._queue.values() if not o.synced])
		self._log_info('flush done', synced=synced, pending=pending)
		return SyncStatus(pending=pending, synced=synced, conflicts=pending)