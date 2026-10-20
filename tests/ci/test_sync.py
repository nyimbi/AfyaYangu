import pytest

from afya.sync.service import SendFn, SyncService, apply_delta, backoff_delay_s, delta_payload
import pytest
from pydantic import ValidationError

from afya.sync.views import (
	POLICY_BY_CONNECTION, ConflictRule, ConflictStrategy, ConnectionClass, SendOutcome, SyncBatch,
	SyncOp,
)


async def test_enqueue_backoff_monotonic() -> None:
	assert backoff_delay_s(1) < backoff_delay_s(2) < backoff_delay_s(10)
	assert backoff_delay_s(99) == 600.0


# --- §16.2 sync queue design: the two "No" edges ---------------------------------------------

def _failing(outcome: SendOutcome) -> SendFn:
	"""A transport that always reports `outcome`, so each edge of §16.2's diagram can be driven."""
	calls: list[SyncBatch] = []

	async def send(batch: SyncBatch) -> SendOutcome:
		calls.append(batch)
		return outcome

	return send


async def test_the_backoff_function_is_applied_and_not_merely_defined() -> None:
	"""`backoff_delay_s` was defined, tested for monotonicity, and called by nothing.

	§16.2's diagram names "Retry with exponential backoff" on both of its "No" edges, and a function
	beside the flow is not the flow: `flush` had one path and it was success. The canary is that a
	failing send must move `retry_at_ms` by exactly the function's own value.
	"""
	svc = SyncService(send=_failing(SendOutcome.no_ack))
	await svc.enqueue(SyncOp(op_id='OP-BACKOFF01', dataset='symptom_logs', client_ts=1, payload={'a': 'b'}))
	st = await svc.flush(now_ms=1000)
	assert st.deferred == 1 and st.synced == 0
	op = svc._queue['OP-BACKOFF01']  # noqa: SLF001
	assert op.synced is False, 'a deferred op is deferred, not discarded'
	# `attempt` numbers the attempt about to be made, so after one failure it reads 2, and the delay
	# is the one the attempt that just failed earned.
	assert op.attempt == 2
	assert op.retry_at_ms == 1000 + int(backoff_delay_s(1) * 1000) == 3000


async def test_an_op_inside_its_backoff_window_is_not_offered_to_the_network() -> None:
	"""Offering it again is the retry storm the backoff was computed to prevent — the send must not
	be called a second time before the delay elapses."""
	svc = SyncService(send=_failing(SendOutcome.no_ack))
	await svc.enqueue(SyncOp(op_id='OP-WINDOW001', dataset='symptom_logs', client_ts=1, payload={'a': 'b'}))
	await svc.flush(now_ms=1000)
	early = await svc.flush(now_ms=2999)
	assert early.waiting == 1 and early.deferred == 0, 'still inside the window'
	assert early.pending == 1, 'waiting is not dropping'
	# Past the window it is offered again, and the second failure doubles the delay.
	late = await svc.flush(now_ms=3000)
	assert late.deferred == 1
	op = svc._queue['OP-WINDOW001']  # noqa: SLF001
	assert op.attempt == 3 and op.retry_at_ms == 3000 + int(backoff_delay_s(2) * 1000) == 7000


async def test_an_op_that_could_not_be_sent_earns_no_backoff() -> None:
	"""§16.2's first "No": there was no network. The phone was offline, which is not the op's fault,
	so it keeps its due-now status and goes out the moment a network appears rather than waiting out
	a delay it did not cause."""
	svc = SyncService(send=_failing(SendOutcome.no_network))
	await svc.enqueue(SyncOp(op_id='OP-NONET0001', dataset='symptom_logs', client_ts=1, payload={'a': 'b'}))
	first = await svc.flush(now_ms=1000)
	assert first.deferred == 1
	op = svc._queue['OP-NONET0001']  # noqa: SLF001
	assert op.retry_at_ms is None and op.attempt == 1, 'no network is not a failed attempt'
	# Same instant: still due, because nothing was earned against it.
	assert (await svc.flush(now_ms=1000)).deferred == 1
	assert first.next_retry_at_ms is None, 'nothing is waiting on a clock'


async def test_an_offline_flush_defers_and_does_not_pretend_to_have_sent() -> None:
	"""The diagram's first diamond, answered from the connection rather than assumed. With no
	transport configured the local model is the server, so without this an offline flush would mark
	every op synced — reporting work done because nobody asked the network."""
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-OFFLINE01', dataset='symptom_logs', client_ts=1, payload={'a': 'b'}))
	st = await svc.flush(now_ms=1000, connection=ConnectionClass.offline)
	assert st.synced == 0 and st.deferred == 1 and st.pending == 1
	assert svc._queue['OP-OFFLINE01'].synced is False  # noqa: SLF001
	# Back on wifi, it goes.
	assert (await svc.flush(now_ms=1001)).synced == 1


async def test_a_deferred_op_is_never_dropped_and_survives_a_restart(tmp_path) -> None:
	"""§16.1(5). A scheduled retry has to outlive the process, or an op that failed once is lost by
	the restart that follows — and the retry that was scheduled is the thing that was supposed to
	save it."""
	from afya.persistence.service import SqliteStore
	db = str(tmp_path / 'q.db')
	svc = SyncService(SqliteStore(db), send=_failing(SendOutcome.no_ack))
	await svc.enqueue(SyncOp(op_id='OP-SURVIVE01', dataset='symptom_logs', client_ts=1, payload={'a': 'b'}))
	await svc.flush(now_ms=1000)

	second = SyncService(SqliteStore(db), send=_failing(SendOutcome.acked))
	await second.load()
	restored = second._queue['OP-SURVIVE01']  # noqa: SLF001
	assert restored.retry_at_ms == 3000, 'the schedule must survive the restart that follows the failure'
	assert restored.attempt == 2
	assert (await second.flush(now_ms=3000)).synced == 1, 'and it goes when the window elapses'


async def test_an_old_database_gains_the_retry_column() -> None:
	"""`CREATE TABLE IF NOT EXISTS` is a no-op against a file that already has the table, so a
	handset that queued writes under the old build would keep its old schema and the first insert
	naming the new column would fail — losing the very queue the column was added to protect."""
	import sqlite3
	import tempfile
	from afya.persistence.service import SqliteStore
	with tempfile.TemporaryDirectory() as d:
		path = f'{d}/old.db'
		old = sqlite3.connect(path)
		old.execute(
			'CREATE TABLE sync_ops (op_id TEXT PRIMARY KEY, dataset TEXT NOT NULL, '
			'server_version INTEGER NOT NULL DEFAULT 0, client_ts INTEGER NOT NULL, '
			'server_ts INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL DEFAULT "{}", '
			'attempt INTEGER NOT NULL DEFAULT 0, synced INTEGER NOT NULL DEFAULT 0)'
		)
		old.execute("INSERT INTO sync_ops VALUES ('OP-OLD0000001', 'symptom_logs', 0, 5, 0, '{}', 0, 0)")
		old.commit()
		old.close()

		svc = SyncService(SqliteStore(path))
		assert await svc.load() == 1, 'the pre-existing queue must still be readable'
		assert (await svc.flush(1000)).synced == 1, 'and writable under the new schema'


async def test_lww_client_wins() -> None:
	svc = SyncService()
	op = SyncOp(op_id='OP-AAA111222', dataset='symptom_logs', client_ts=200, payload={'d': 'x'})
	await svc.enqueue(op)
	status = await svc.flush(0)
	assert status.synced == 1


async def test_unknown_dataset_rejected() -> None:
	svc = SyncService()
	with pytest.raises(AssertionError):
		await svc.enqueue(SyncOp(op_id='OP-BBB222333', dataset='unknown_table', client_ts=1))


async def test_append_only_never_client_wins() -> None:
	svc = SyncService()
	op = SyncOp(op_id='OP-CCC333444', dataset='proximity_tokens', client_ts=999, payload={'token': 'a' * 32})
	await svc.enqueue(op)
	assert svc.strategy_for('proximity_tokens').value == 'append_only'

# --- §16.4 bandwidth minimisation -----------------------------------------------------------


def test_every_connection_class_has_a_policy() -> None:
	assert set(POLICY_BY_CONNECTION) == set(ConnectionClass)
	metered = SyncService().policy_for(ConnectionClass.metered)
	wifi = SyncService().policy_for(ConnectionClass.wifi)
	assert metered.batch_max_ops < wifi.batch_max_ops
	assert metered.poll_interval_s > wifi.poll_interval_s, 'metered sync must be less frequent, not just smaller'
	assert metered.image_max_edge_px <= wifi.image_max_edge_px
	assert metered.image_quality < wifi.image_quality


def test_delta_carries_only_changed_fields() -> None:
	"""§16.4 delta sync. Unchanged fields cost nothing on the wire."""
	previous = {'temp': '36.5', 'note': 'fine', 'cough': 'no'}
	current = {'temp': '38.1', 'note': 'fine', 'cough': 'no'}
	delta = delta_payload(previous, current)
	assert delta == {'temp': '38.1'}
	assert apply_delta(previous, delta) == current


def test_delta_records_a_removal_explicitly() -> None:
	"""A deleted field has to travel as `-field`. Omitting it means "unchanged", so the deletion
	would never reach the server and the field would come back on the next pull."""
	previous = {'temp': '36.5', 'note': 'fine'}
	current = {'temp': '36.5'}
	delta = delta_payload(previous, current)
	assert delta == {'-note': ''}
	assert apply_delta(previous, delta) == current, 'the delta must reconstruct the current state'


def test_delta_round_trips_including_removals_and_additions() -> None:
	for previous, current in (
		({}, {'a': '1'}),
		({'a': '1'}, {}),
		({'a': '1', 'b': '2'}, {'b': '3', 'c': '4'}),
		({'a': '1'}, {'a': '1'}),
	):
		assert apply_delta(previous, delta_payload(previous, current)) == current, (previous, current)


async def test_batch_respects_the_connection_budget() -> None:
	svc = SyncService()
	for i in range(120):
		await svc.enqueue(SyncOp(op_id=f'OP-{i:06d}AAA', dataset='symptom_logs', client_ts=i, payload={'v': str(i)}))
	metered = svc.encode([o for o in svc._queue.values()], ConnectionClass.metered)  # noqa: SLF001
	wifi = svc.encode([o for o in svc._queue.values()], ConnectionClass.wifi)  # noqa: SLF001
	assert len(metered.ops) == svc.policy_for(ConnectionClass.metered).batch_max_ops
	assert len(wifi.ops) == 120, 'wifi fits the whole queue'
	# Deferred ops are deferred, not dropped: they are still in the queue for the next batch.
	assert metered.deferred == 120 - len(metered.ops)


async def test_batch_compresses_only_when_it_pays() -> None:
	"""gzip on a small body adds framing overhead and makes the request bigger, which is a real cost
	on a metered link — so the threshold is a threshold, not decoration."""
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-SMALL00001', dataset='symptom_logs', client_ts=1, payload={'v': '1'}))
	small = svc.encode([o for o in svc._queue.values()], ConnectionClass.metered)  # noqa: SLF001
	assert small.encoding == 'identity' and small.saved_ratio == 0.0

	big = SyncService()
	# A repeated payload, so the codecs have something to find.
	await big.enqueue(SyncOp(op_id='OP-BIG0000001', dataset='symptom_logs', client_ts=1,
	                         payload={f'k{i}': 'cough fever headache' for i in range(80)}))
	batch = big.encode([o for o in big._queue.values()], ConnectionClass.wifi)  # noqa: SLF001
	assert batch.encoding in ('gzip', 'br'), 'the encoding is one of the two §16.4 names'
	assert batch.wire_bytes < batch.raw_bytes and batch.saved_ratio > 0.5


async def test_both_codecs_the_section_names_are_tried_and_the_smaller_wins() -> None:
	"""§16.4's "gzip / Brotli" is a set, not a choice.

	This test replaces one that asserted `batch.encoding == 'gzip'` — a check on *which codec the
	implementation happened to use* rather than on what the section asks for. It passed for as long
	as gzip was the only one tried, and it would have gone on passing if gzip were the only one
	*ever* tried: a client shipping one of the two codecs the section names is leaving bandwidth on
	a metered link for no reason, and no test could see it.

	So the assertion is now the property: both codecs are computed for the same body, and the one
	that goes on the wire is the smaller of the two. Brotli's static dictionary usually wins on
	JSON, which is why this asserts the *rule* rather than the winner — pinning `br` here would be
	the same mistake in the other direction, and it would fail on the small bodies where gzip's
	header is cheaper than Brotli's.
	"""
	import brotli
	import gzip as _gzip
	import json
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-BIG0000002', dataset='symptom_logs', client_ts=1,
	                         payload={f'k{i}': 'cough fever headache' for i in range(80)}))
	batch = svc.encode([o for o in svc._queue.values()], ConnectionClass.wifi)  # noqa: SLF001
	raw = json.dumps([o.model_dump(mode='json') for o in batch.ops], separators=(',', ':')).encode()
	candidates = {'gzip': _gzip.compress(raw, compresslevel=6), 'br': brotli.compress(raw, quality=5)}
	smallest = min(candidates, key=lambda k: len(candidates[k]))
	assert batch.encoding == smallest, 'the smaller of the two codecs goes on the wire'
	assert batch.wire_bytes == len(candidates[smallest])
	# And the rule is not vacuous: the two codecs genuinely differ on this body, so `smallest` is a
	# decision rather than a tie that any implementation would satisfy.
	assert len(candidates['gzip']) != len(candidates['br']), 'a tie would make this test vacuous'
	assert batch.saved_ratio > 0.5


async def test_delta_makes_a_repeat_write_cheaper_than_the_first() -> None:
	"""The behaviour delta sync exists for: editing one field of a record must not re-send the
	record. Asserted through `remember_synced`, which is what makes the second write a delta."""
	svc = SyncService()
	payload = {f'f{i}': 'x' * 40 for i in range(20)}
	op = SyncOp(op_id='OP-DELTA00001', dataset='symptom_logs', client_ts=1, payload=dict(payload))
	await svc.enqueue(op)
	first = svc.encode([op], ConnectionClass.wifi)
	assert len(first.ops[0].payload) == 20, 'the first write is the whole record'

	await svc.flush(now_ms=1000)
	op2 = SyncOp(op_id='OP-DELTA00001', dataset='symptom_logs', client_ts=2, payload={**payload, 'f0': 'changed'})
	await svc.enqueue(op2)
	second = svc.encode([op2], ConnectionClass.wifi)
	assert second.ops[0].payload == {'f0': 'changed'}, 'only the changed field goes on the wire'
	assert second.wire_bytes < first.wire_bytes


async def test_a_repeat_write_with_no_change_sends_nothing() -> None:
	"""An unchanged record is a no-op, not an empty request."""
	svc = SyncService()
	op = SyncOp(op_id='OP-NOOP000001', dataset='symptom_logs', client_ts=1, payload={'v': '1'})
	await svc.enqueue(op)
	await svc.flush(now_ms=1000)
	same = SyncOp(op_id='OP-NOOP000001', dataset='symptom_logs', client_ts=2, payload={'v': '1'})
	batch = svc.encode([same], ConnectionClass.wifi)
	assert batch.ops == [], 'nothing changed, so nothing is sent'


def test_adaptive_poll_interval_follows_the_connection() -> None:
	svc = SyncService()
	assert svc.next_poll_interval_s(ConnectionClass.wifi) == 30
	assert svc.next_poll_interval_s(ConnectionClass.metered) == 300
	assert svc.next_poll_interval_s(ConnectionClass.offline) == 0, 'offline polls nothing'
	assert svc.image_budget(ConnectionClass.metered)[1] < svc.image_budget(ConnectionClass.wifi)[1]


async def test_sync_policy_and_delta_over_http() -> None:
	"""The routes are the part that can break: the policy a client reads, and the delta it sends."""
	import httpx

	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		metered = (await c.get('/sync/policy', params={'connection': 'metered'})).json()
		wifi = (await c.get('/sync/policy', params={'connection': 'wifi'})).json()
		assert metered['batch_max_ops'] < wifi['batch_max_ops']
		assert metered['poll_interval_s'] > wifi['poll_interval_s']
		assert (await c.get('/sync/policy', params={'connection': 'satellite'})).status_code == 422

		delta = (await c.post('/sync/delta', json={
			'previous': {'temp': '36.5', 'note': 'fine'}, 'current': {'temp': '38.1'},
		})).json()
		assert delta['delta'] == {'temp': '38.1', '-note': ''}
		assert delta['changed_fields'] == 2 and delta['full_fields'] == 1

		# §16.2's first diamond over HTTP: an offline flush defers rather than reporting success,
		# and the op goes out on the next flush once the connection is back. The enqueue names the
		# token's subject, because the conflict the op may lose is read back by `/sync/conflicts`.
		token = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		h = {'authorization': f'Bearer {token}'}
		await c.post('/sync/ops', json={'op_id': 'OP-ROUTE00001', 'dataset': 'symptom_logs', 'client_ts': 1, 'payload': {'a': 'b'}}, headers=h)
		off = (await c.post('/sync/flush', json={'connection': 'offline'}, headers=h)).json()
		assert off['synced'] == 0 and off['deferred'] == 1 and off['pending'] == 1, off
		assert (await c.post('/sync/flush', json={'connection': 'satellite'}, headers=h)).status_code == 422
		back = (await c.post('/sync/flush', json={'connection': 'wifi'}, headers=h)).json()
		assert back['synced'] == 1 and back['deferred'] == 0, back

		empty = (await c.post('/sync/batch', params={'connection': 'wifi'}, headers=h)).json()
		# An empty queue is still a 2-byte `[]` on the wire — the claim is that no *op* is sent,
		# not that the request costs nothing.
		assert empty['ops'] == [] and empty['encoding'] == 'identity'
		assert (await c.post('/sync/batch', params={'connection': 'satellite'}, headers=h)).status_code == 422


# --- §16.3 conflict matrix, and the appeal the immunisation row promises ---------------------

async def test_the_matrix_is_the_specs_own_eight_rows() -> None:
	"""§16.3 lists eight data types. The dict is derived from the rows rather than stated beside
	them, so a row cannot lose its rationale or drift from the strategy it names."""
	from afya.sync.views import CONFLICT_RULES, STRATEGY_MATRIX
	assert len(CONFLICT_RULES) == 8
	assert STRATEGY_MATRIX == {r.dataset: r.strategy for r in CONFLICT_RULES}
	assert [r.dataset for r in CONFLICT_RULES] == [
		'symptom_logs', 'temperature', 'case_reports', 'immunisation', 'medication', 'facility',
		'content', 'proximity_tokens',
	]
	assert all(r.rationale for r in CONFLICT_RULES)


async def test_only_the_immunisation_row_is_appealable() -> None:
	"""§16.3's immunisation row is the one that reads "Server-authoritative on conflict, user can
	appeal". An appeal against last-write-wins is an appeal against arithmetic, and under
	append-only there is no conflict — so the model refuses both."""
	from afya.sync.views import CONFLICT_RULES
	assert [r.dataset for r in CONFLICT_RULES if r.appealable] == ['immunisation']
	with pytest.raises(ValidationError, match='no decision to appeal'):
		ConflictRule(dataset='facility', strategy=ConflictStrategy.lww, rationale='x', appealable=True)


async def test_a_lost_conflict_is_recorded_and_not_retried_forever() -> None:
	"""The bug this replaced: a losing op had `attempt` bumped and stayed queued, so every flush
	re-sent a payload the server had already overruled. A decided conflict is not a transient
	failure, and §16.1's "nothing is lost" is about writes that are not yet decided."""
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-LOST0001', dataset='immunisation', client_ts=100,
	                         payload={'dose': '1'}))
	svc._server_state['immunisation'] = {'OP-LOST0001': SyncOp(  # noqa: SLF001 - seeding the server side
		op_id='OP-LOST0001', dataset='immunisation', client_ts=100, server_ts=500, payload={'dose': '2'})}
	first = await svc.flush(0)
	assert first.synced == 0 and first.conflicts == 1 and first.pending == 0, first
	again = await svc.flush(0)
	assert again.conflicts == 1 and again.pending == 0, 'a decided conflict must not be re-sent'
	c = svc.conflicts()[0]
	assert c.client_payload == {'dose': '1'} and c.server_payload == {'dose': '2'}, 'both versions kept'
	assert c.appealable is True and c.appeal.value == 'none'


async def test_pending_and_conflicts_are_different_counts() -> None:
	"""They shared one field. A queued write waiting for a network and a write the server overruled
	are different facts, and the one a person needs is the second."""
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-PEND0001', dataset='symptom_logs', client_ts=1, payload={'a': 'b'}))
	await svc.enqueue(SyncOp(op_id='OP-LOST0002', dataset='case_reports', client_ts=1, payload={'a': 'b'}))
	svc._server_state['case_reports'] = {'OP-LOST0002': SyncOp(  # noqa: SLF001
		op_id='OP-LOST0002', dataset='case_reports', client_ts=1, server_ts=900, payload={'a': 'z'})}
	st = await svc.flush(0)
	assert st.synced == 1, 'the symptom log had no server side, so it synced'
	assert st.conflicts == 1 and st.pending == 0


async def test_an_appeal_opens_and_closes() -> None:
	from afya.sync.views import AppealState
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-APPEAL01', dataset='immunisation', client_ts=1, payload={'d': '1'}))
	svc._server_state['immunisation'] = {'OP-APPEAL01': SyncOp(  # noqa: SLF001
		op_id='OP-APPEAL01', dataset='immunisation', client_ts=1, server_ts=9, payload={'d': '2'})}
	await svc.flush(0)
	assert [c.op_id for c in svc.open_conflicts()] == ['OP-APPEAL01'], 'an undecided appeal is open'
	rec = svc.appeal('OP-APPEAL01', 'the clinic gave dose 2 in March')
	assert rec.appeal is AppealState.filed and rec.appeal_note == 'the clinic gave dose 2 in March'
	assert [c.op_id for c in svc.open_conflicts()] == ['OP-APPEAL01'], 'filing is not deciding'
	rec.appeal = AppealState.upheld
	assert svc.open_conflicts() == [], 'a decided appeal is closed'


async def test_a_non_appealable_conflict_cannot_be_appealed() -> None:
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-NOAPPEAL', dataset='facility', client_ts=1, payload={'d': '1'}))
	svc._server_state['facility'] = {'OP-NOAPPEAL': SyncOp(  # noqa: SLF001
		op_id='OP-NOAPPEAL', dataset='facility', client_ts=1, server_ts=9, payload={'d': '2'})}
	await svc.flush(0)
	assert svc.conflicts()[0].resolved() is True, 'the server decided; that is the end of it'
	with pytest.raises(PermissionError, match='not appealable'):
		svc.appeal('OP-NOAPPEAL', 'please')


async def test_the_appeal_surface_is_reachable_and_carries_no_spec_code() -> None:
	import httpx
	import re
	from afya.service import create_app
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		token = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		h = {'authorization': f'Bearer {token}'}
		out = (await c.get('/sync/conflicts', headers=h)).json()
		assert out['conflicts'] == [] and out['open'] == 0
		assert (await c.get('/sync/conflicts')).status_code == 401, 'the queue is the device’s, not the world’s'
		assert (await c.post('/sync/conflicts/OP-NOPE/appeal', json={'note': 'x'}, headers=h)).status_code == 404
		body = str(out)
		assert re.search(r'\b(?:SENS|SEC|ACC|REC|MON|LOC|COM|ALT|AI|CHAN|INF|TRI|FND|MED|EMG)-\d{3}\b', body) is None


# --- §16.1 principle 4 / ACC-003: the offline indicator --------------------------------------

async def test_the_indicator_counts_what_is_actually_queued() -> None:
	"""§16.1 principle 4 and ACC-003's "clear offline indicator in the UI". The numbers are read
	from the queue rather than passed in, so an indicator cannot disagree with the queue it shows."""
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-QUEUE001', dataset='symptom_logs', client_ts=1, payload={'a': 'b'}))
	await svc.enqueue(SyncOp(op_id='OP-QUEUE002', dataset='medication', client_ts=2, payload={'a': 'c'}))
	offline = svc.offline_state(ConnectionClass.offline)
	assert offline.connection is ConnectionClass.offline and offline.pending == 2
	assert 'saved on this phone' in offline.detail, offline.detail
	on_wifi = svc.offline_state(ConnectionClass.wifi)
	assert on_wifi.pending == 2 and on_wifi.label == 'Not yet sent'
	await svc.flush(5000)
	assert svc.offline_state(ConnectionClass.wifi).label == 'Up to date'
	assert svc.offline_state(ConnectionClass.wifi).last_synced_at_ms == 5000


async def test_the_indicator_says_when_a_write_was_overruled() -> None:
	"""A person whose reading the health service kept needs to be told, not shown "up to date"."""
	svc = SyncService()
	await svc.enqueue(SyncOp(op_id='OP-OVERRUL1', dataset='immunisation', client_ts=1, payload={'d': '1'}))
	svc._server_state['immunisation'] = {'OP-OVERRUL1': SyncOp(  # noqa: SLF001
		op_id='OP-OVERRUL1', dataset='immunisation', client_ts=1, server_ts=9, payload={'d': '2'})}
	await svc.flush(0)
	st = svc.offline_state(ConnectionClass.wifi)
	assert st.label == 'Needs your attention' and st.open_conflicts == 1
	assert 'kept instead of yours' in st.detail, st.detail


async def test_durability_is_computed_from_whether_a_store_exists() -> None:
	"""§16.1 principle 5 is "every queued write survives app restart and device reboot". A service
	with no store does not keep that promise, and the indicator must say so rather than reassure —
	`durable` is read off the store, not stated as a constant."""
	import tempfile
	from afya.persistence.service import SqliteStore
	bare = SyncService()
	assert bare.offline_state(ConnectionClass.offline).durable is False
	assert 'lost if the app closes' in bare.offline_state(ConnectionClass.offline).detail
	with tempfile.TemporaryDirectory() as d:
		backed = SyncService(SqliteStore(f'{d}/s.db'))
		st = backed.offline_state(ConnectionClass.offline)
		assert st.durable is True and 'lost if the app closes' not in st.detail


async def test_the_indicator_route_is_scoped_and_carries_no_spec_code() -> None:
	"""The banner is about the caller's own queue, so it takes a token — and the *counts* it draws
	are over that queue, not every caller's.

	It was public on the argument that it names no person. The argument held for the label and
	failed for the numbers: `pending` was counted over a queue every caller writes to, so the
	banner told one person how many writes somebody else's phone was holding. A count is a fact
	about the data however small it is.
	"""
	import httpx
	import re
	from afya.service import create_app
	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/sync/state')).status_code in (401, 403), \
			'the indicator counted a queue that is not the caller’s'
		token = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		h = {'authorization': f'Bearer {token}'}
		out = (await c.get('/sync/state', headers=h)).json()
		assert out['label'] == 'Offline' and out['durable'] is False
		assert (await c.get('/sync/state', params={'connection': 'nonsense'}, headers=h)).status_code == 422
		assert (await c.get('/sync/state', params={'connection': 'wifi'}, headers=h)).json()['label'] == 'Up to date'
		body = str(out)
		assert re.search(r'\b(?:SENS|SEC|ACC|REC|MON|LOC|COM|ALT|AI|CHAN|INF|TRI|FND|MED|EMG)-\d{3}\b', body) is None


async def test_one_callers_queue_is_not_readable_or_flushable_by_another() -> None:
	"""The sync queue is one store shared by every caller, and three routes read or advance it.

	Unguarded, `POST /sync/batch` with no token at all returned every pending op in the deployment
	— a stranger's symptom log, their temperature, their medication — and `POST /sync/flush` pushed
	every caller's ops through the conflict matrix, marking another person's unsent write synced
	and deciding it against the server's value. The offline indicator counted them too. The subject
	the enqueue records is the only thing that can scope any of it, so all three bind to it.

	Both directions are asserted: the stranger's payload does not appear, and the owner's does. A
	test that only checked the first would pass on a route that returned nothing to anybody.
	"""
	import httpx
	from afya.service import build_services, create_app
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		victim = (await c.post('/auth/anonymous', json={'subject_ref': 'VICTIM01'})).json()['token']
		other = (await c.post('/auth/anonymous', json={'subject_ref': 'OTHER001'})).json()['token']
		hv = {'authorization': f'Bearer {victim}'}
		ho = {'authorization': f'Bearer {other}'}
		op = {'op_id': 'OP-PRIVATE1', 'dataset': 'symptom_logs', 'client_ts': 1,
		      'payload': {'hiv_status': 'positive'}}
		assert (await c.post('/sync/ops', json=op, headers=hv)).status_code == 200

		# The payload must not cross to a different caller, nor to no caller at all.
		assert (await c.post('/sync/batch', params={'connection': 'wifi'})).status_code in (401, 403), \
			'an anonymous caller read the queue'
		assert (await c.post('/sync/batch', params={'connection': 'wifi'}, headers=ho)).json()['ops'] == [], \
			'another caller read the queue'
		# And the owner still sees their own.
		mine = (await c.post('/sync/batch', params={'connection': 'wifi'}, headers=hv)).json()
		assert [o['op_id'] for o in mine['ops']] == ['OP-PRIVATE1']

		# A flush by someone else must not advance it.
		await c.post('/sync/flush', json={'connection': 'wifi'}, headers=ho)
		assert (await c.get('/sync/state', headers=hv)).json()['pending'] == 1, \
			'another caller’s flush sent a write that was not theirs'
		# Their own flush does send it.
		assert (await c.post('/sync/flush', json={'connection': 'wifi'}, headers=hv)).json()['synced'] == 1
		assert (await c.get('/sync/state', headers=hv)).json()['pending'] == 0
