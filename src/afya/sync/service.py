"""Sync service — local-write queue, exponential backoff, §16.3 conflict matrix, append-only proximity tokens."""
import gzip
import json
from collections.abc import Awaitable, Callable

import brotli

from afya.logmixin import LogMixin
from afya.sync.views import (
	POLICY_BY_CONNECTION, RULE_BY_DATASET, AppealState, ConflictRecord, ConflictStrategy,
	ConflictRule, ConnectionClass, OfflineState, SendOutcome, STRATEGY_MATRIX, SyncBatch, SyncOp,
	SyncPolicy, SyncStatus,
)

# The transport seam. A deployment that reaches a real server supplies one; the local model is the
# server when it does not. It is the same shape as `store`, and it exists because §16.2's two "No"
# edges have no other way to fire: with no transport, an op that is written is an op the server
# has, so "Ack received?" could only ever answer Yes and the retry the diagram schedules below it
# was unreachable. The send returns *which* edge it took rather than a bool, because "the server
# did not ack" and "there was no network" lead to the same box on the diagram and to opposite
# behaviour in the queue.
SendFn = Callable[[SyncBatch], Awaitable[SendOutcome]]


def backoff_delay_s(attempt: int) -> float:
	"""§16.2's exponential backoff: the delay after `attempt` failed attempts, capped at ten minutes.

	The cap is what keeps a handset that has been offline overnight from waking to a delay measured
	in days — an op must still be offered again the same session it is queued in, and 2^n is
	unbounded. `attempt` numbers the attempt just made, so a first failure waits 2 s and the tenth
	waits the ceiling; `enqueue` seeds it at 1 for the first try, so it is never 0 when read here.
	"""
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
	def __init__(self, store=None, send: SendFn | None = None) -> None:
		self._queue: dict[str, SyncOp] = {}
		self._server_state: dict[str, dict[str, SyncOp]] = {}
		self._store = store
		self._loaded = False
		# dataset -> op_id -> the payload the server last acknowledged. Three levels, not two: the
		# op id alone is not unique across datasets.
		self._last_synced: dict[str, dict[str, dict[str, str]]] = {}
		# Conflicts the client lost, keyed by op id. §16.3's immunisation row promises a person can
		# appeal a server-authoritative overwrite, which is only possible if the overruled value is
		# still held somewhere after the queue drops it.
		self._conflicts: dict[str, ConflictRecord] = {}
		self._last_synced_at_ms: int | None = None
		# §16.2's transport. None means the local model *is* the server, which is the honest default
		# for a deployment with no upstream and the reason the "Ack received? → No" branch was
		# unreachable before: with no transport there is no answer but Yes.
		self._send = send
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

	def rule_for(self, dataset: str) -> ConflictRule:
		"""The whole §16.3 row, because the strategy alone loses the appeal qualifier."""
		return RULE_BY_DATASET[dataset]

	def conflicts(self, subject_ref: str | None = None) -> list[ConflictRecord]:
		"""The conflicts this caller may see, newest dataset first.

		`subject_ref` is the token's own and is *required* by the route: the conflict record holds
		the losing payload and the value the server kept, both of which are the person's health
		data, and the queue used to be returned whole. A conflict whose owner is unknown (a record
		rebuilt from a store written before the binding) is matched by nobody, which is the safe
		direction — it is withheld from every caller rather than shown to all of them.

		The default `None` keeps the in-process callers that hold no subject (`open_conflicts`, the
		offline indicator) reading the whole set: those are the server's own bookkeeping, not a
		response to a caller.
		"""
		rows = sorted(self._conflicts.values(), key=lambda c: (c.dataset, c.op_id))
		if subject_ref is None:
			return rows
		return [c for c in rows if c.subject_ref == subject_ref]

	def offline_state(self, connection: ConnectionClass, subject_ref: str | None = None) -> OfflineState:
		"""§16.1 principle 4, computed. `durable` reports whether the queue is actually backed by a
		store — a service with none keeps §16.1's promise only until the process exits, and saying
		so is the difference between an indicator and a reassurance.

		`subject_ref` scopes the counts to the caller's own queue. The indicator is drawn on one
		handset about that handset's work, so a count taken over every caller's ops would tell a
		person how many writes somebody else had pending. `None` keeps the whole-queue reading for
		the in-process callers that are the server's own bookkeeping.
		"""
		scope = list(self._queue.values()) if subject_ref is None else [
			o for o in self._queue.values() if o.subject_ref == subject_ref]
		pending = len([o for o in scope if not o.synced])
		open_conflicts = self.conflicts(subject_ref)
		if connection is ConnectionClass.offline:
			label = 'Offline'
			detail = (
				f'{pending} change{"" if pending == 1 else "s"} saved on this phone and will send '
				'when you have a connection.' if pending
				else 'You are offline. Everything you entered has been sent.'
			)
		elif pending:
			label = 'Not yet sent'
			detail = f'{pending} change{"" if pending == 1 else "s"} waiting to send.'
		elif open_conflicts:
			label = 'Needs your attention'
			detail = f'{len(open_conflicts)} change{"" if len(open_conflicts) == 1 else "s"} the health service kept instead of yours.'
		else:
			label = 'Up to date'
			detail = 'Everything you entered has been sent.'
		if not self._store:
			detail += ' This device is not keeping a copy, so unsent changes are lost if the app closes.'
		return OfflineState(
			connection=connection, label=label, pending=pending, conflicts=len(self._conflicts),
			open_conflicts=len(open_conflicts), durable=self._store is not None,
			last_synced_at_ms=self._last_synced_at_ms, detail=detail,
		)

	def open_conflicts(self) -> list[ConflictRecord]:
		"""Conflicts still needing someone's attention — §16.3's appeal surface."""
		return [c for c in self.conflicts() if not c.resolved()]

	def appeal(self, op_id: str, note: str, subject_ref: str | None = None) -> ConflictRecord:
		"""§16.3's immunisation row: "Server-authoritative on conflict, user can appeal."

		Only where the spec says so. Filing an appeal against a last-write-wins overwrite would be
		an appeal against arithmetic — the newest write already won — so it is refused rather than
		accepted and ignored.

		`subject_ref`, when given, must be the conflict's owner: the op id is the only thing the
		route has, so without this check any caller could file an appeal against a stranger's
		conflict by naming its id. A conflict with no recorded owner cannot be claimed by anyone,
		for the same reason `conflicts` withholds it.
		"""
		rec = self._conflicts[op_id]
		if subject_ref is not None and rec.subject_ref != subject_ref:
			raise LookupError('no such conflict')
		if not rec.appealable:
			raise PermissionError(
				f'a {rec.strategy.value} conflict is not appealable; the server decides {rec.dataset}')
		rec.appeal = AppealState.filed
		rec.appeal_note = note
		self._log_warn('conflict appealed', op_id=op_id, dataset=rec.dataset)
		return rec

	# --- §16.4 bandwidth minimisation ---------------------------------------------------------

	def policy_for(self, connection: ConnectionClass) -> SyncPolicy:
		"""The policy a connection class is entitled to. Not a caller-supplied number: a client that
		could ask for the wifi batch size on a metered link would defeat the point."""
		return POLICY_BY_CONNECTION[connection]

	def encode(self, ops: list[SyncOp], connection: ConnectionClass) -> SyncBatch:
		"""Assemble one request's batch: delta payloads, then the smaller of gzip and Brotli.

		§16.4 names two codecs — "Payload compression: gzip / Brotli" — and the slash is a set, not a
		choice: a client that ships both and sends gzip because it was written first is leaving
		bandwidth on a metered link for no reason. Both are tried and the smaller wins, which is the
		only rule that minimises what the person pays for; Brotli's static dictionary makes it
		usually the winner on JSON, and gzip wins on some small bodies where Brotli's header costs
		more than its dictionary saves. Neither is preferred by construction.

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
			# Both codecs §16.4 names, and the smaller one goes on the wire. `brotli.compress` with
			# quality 5 is the level whose ratio is worth its CPU on a handset; the default 11 is
			# seconds of work per batch for a few percent, which on a phone is the battery cost
			# §16.4's whole argument is about.
			candidates = {'gzip': gzip.compress(raw, compresslevel=6),
			              'br': brotli.compress(raw, quality=5)}
			best = min(candidates, key=lambda k: len(candidates[k]))
			if len(candidates[best]) < len(raw):
				wire, encoding = candidates[best], best
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

	def _schedule_retry(self, op: SyncOp, now_ms: int, acked: bool) -> None:
		"""§16.2's "Retry with exponential backoff" — the branch both "No" edges lead to.

		`acked` is the difference between the diagram's two failure edges. An op the network carried
		but the server did not acknowledge has failed a *send*, so it earns a backoff and waits it
		out: the transport is up and the server is unhappy, and asking again immediately is the
		hammering the backoff exists to prevent. An op that could not be sent because there was no
		network has failed nothing — the phone was offline — so it is deferred with its due-now
		status intact and goes out the instant a network appears. Both stay in the queue; §16.1's
		"nothing is lost" is not a promise that can be kept by dropping them.
		"""
		if acked:
			# `attempt` numbers the attempt *about to be made* — `enqueue` seeds it at 1 — so the
			# delay is read off the attempt that just failed, and the counter then advances to the
			# next one. Incrementing first would charge the op a doubling for an attempt it has not
			# made yet, which is how a queue walks to its ceiling twice as fast as the spec's curve.
			op.retry_at_ms = now_ms + int(backoff_delay_s(op.attempt) * 1000)
			op.attempt += 1
		else:
			op.retry_at_ms = None

	async def flush(self, now_ms: int, connection: ConnectionClass = ConnectionClass.wifi,
	                subject_ref: str | None = None) -> SyncStatus:
		"""Run the queue through §16.2's flow once.

		`connection` is the diagram's first diamond — "Network available?" — and is why it is a
		parameter rather than an assumption: an offline flush defers every due op without pretending
		it was sent, which is the difference between a queue that reports the truth and one that
		marks work done because nobody asked the network.

		`subject_ref` is whose queue this is. The route passes the token's subject and the flush
		touches only that caller's ops; `None` is the in-process caller (a test, the server's own
		bookkeeping) and keeps the whole queue. Without the filter, `POST /sync/flush` sent *every*
		queued op — one person's flush pushed another person's pending health write through the
		conflict matrix and marked it synced, which is both a cross-tenant write and a way to make
		another caller's unsent work disappear from their queue before they ever sent it.
		"""
		await self.load()
		synced = 0
		deferred = 0
		waiting = 0
		for op in list(self._queue.values()):
			if op.synced:
				continue
			if subject_ref is not None and op.subject_ref != subject_ref:
				continue
			# An op inside its backoff window is not offered to the network at all — offering it is
			# the retry storm the backoff was computed to prevent.
			if not op.due(now_ms):
				waiting += 1
				continue
			# §16.2's "Network available? → No". Nothing is sent and no backoff is earned: the phone
			# was offline, which the op had no part in, so it keeps its due-now status and goes out
			# the moment a network appears.
			if connection is ConnectionClass.offline:
				deferred += 1
				self._schedule_retry(op, now_ms, acked=False)
				if self._store is not None:
					await self._store.save_sync_op(op)
				continue
			# §16.2's transport, when one is configured: the second diamond, "Ack received?".
			if self._send is not None:
				outcome = await self._send(self.encode([op], connection))
				if outcome is not SendOutcome.acked:
					deferred += 1
					self._schedule_retry(op, now_ms, acked=outcome is SendOutcome.no_ack)
					if self._store is not None:
						await self._store.save_sync_op(op)
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
					# The client lost. Record it, and take the op out of the queue.
					#
					# Retrying it was the bug: a server-authoritative conflict is *decided*, so every
					# later flush re-sent a payload that had already been overruled, bumped `attempt`
					# toward the backoff ceiling, and would have gone on doing so forever — a silent
					# discard dressed as a transient failure. §16.1's "nothing is lost" is about writes
					# that have not been decided yet; a decided conflict is kept as a ConflictRecord,
					# which is where §16.3's appeal reads it from.
					rule = self.rule_for(op.dataset)
					self._conflicts[op.op_id] = ConflictRecord(
						op_id=op.op_id, dataset=op.dataset, strategy=rule.strategy,
						client_ts=op.client_ts, server_ts=srv.server_ts,
						client_payload=dict(op.payload), server_payload=dict(srv.payload),
						appealable=rule.appealable, subject_ref=op.subject_ref,
					)
					self._queue.pop(op.op_id, None)
					if self._store is not None:
						op.attempt += 1
						await self._store.save_sync_op(op)
		# Every count the status reports is the caller's own. A global `pending` told one person
		# how much work another person's phone was holding, which is a fact about somebody else's
		# health data however small the number.
		scope = list(self._queue.values()) if subject_ref is None else [
			o for o in self._queue.values() if o.subject_ref == subject_ref]
		pending = len([o for o in scope if not o.synced])
		if synced:
			self._last_synced_at_ms = now_ms
		# The soonest any waiting op becomes due again, so a client can schedule its next attempt
		# instead of polling on a fixed interval that is either too eager or too slow.
		due_times = [o.retry_at_ms for o in scope if not o.synced and o.retry_at_ms is not None]
		conflicts = len(self.conflicts(subject_ref))
		self._log_info('flush done', synced=synced, pending=pending, deferred=deferred, waiting=waiting,
		               conflicts=conflicts)
		return SyncStatus(pending=pending, synced=synced, conflicts=conflicts,
		                  deferred=deferred, waiting=waiting,
		                  next_retry_at_ms=min(due_times) if due_times else None)