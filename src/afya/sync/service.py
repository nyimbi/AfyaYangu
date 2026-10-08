"""Sync service — local-write queue, exponential backoff, §16.3 conflict matrix, append-only proximity tokens."""
from afya.logmixin import LogMixin
from afya.sync.views import ConflictStrategy, STRATEGY_MATRIX, SyncOp, SyncStatus


def backoff_delay_s(attempt: int) -> float:
	assert attempt >= 1, 'attempt starts at 1'
	return min(600.0, 2.0 ** attempt)


class SyncService(LogMixin):
	def __init__(self, store=None) -> None:
		self._queue: dict[str, SyncOp] = {}
		self._server_state: dict[str, dict[str, SyncOp]] = {}
		self._store = store
		assert self._queue == {} and self._server_state == {}

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

	async def resolve(self, op: SyncOp, server: SyncOp) -> tuple[SyncOp, bool]:
		strategy = self.strategy_for(op.dataset)
		if strategy is ConflictStrategy.lww:
			winner = op if op.client_ts > server.server_ts else server
			return (winner, winner is op)
		if strategy is ConflictStrategy.append_only:
			return (server, False)
		return (server, False)

	async def flush(self, now_ms: int) -> SyncStatus:
		synced = 0
		for op in list(self._queue.values()):
			if op.synced:
				continue
			srv = self._server_state.get(op.dataset, {}).get(op.op_id)
			if srv is None:
				op.synced = True
				self._server_state.setdefault(op.dataset, {})[op.op_id] = op
				synced += 1
				if self._store is not None:
					await self._store.save_sync_op(op)
			else:
				winner, client_won = await self.resolve(op, srv)
				if client_won:
					op.synced = True
					self._server_state[op.dataset][op.op_id] = op
					synced += 1
					if self._store is not None:
						await self._store.save_sync_op(op)
				else:
					op.attempt += 1
					assert backoff_delay_s(op.attempt) > backoff_delay_s(op.attempt - 1), 'backoff monotonic'
		pending = len([o for o in self._queue.values() if not o.synced])
		self._log_info('flush done', synced=synced, pending=pending)
		return SyncStatus(pending=pending, synced=synced, conflicts=pending)