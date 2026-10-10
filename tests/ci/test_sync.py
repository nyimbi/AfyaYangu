import pytest

from afya.sync.service import SyncService, apply_delta, backoff_delay_s, delta_payload
from afya.sync.views import POLICY_BY_CONNECTION, ConnectionClass, SyncOp


async def test_enqueue_backoff_monotonic() -> None:
	assert backoff_delay_s(1) < backoff_delay_s(2) < backoff_delay_s(10)
	assert backoff_delay_s(99) == 600.0


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
	# A repeated payload, so gzip has something to find.
	await big.enqueue(SyncOp(op_id='OP-BIG0000001', dataset='symptom_logs', client_ts=1,
	                         payload={f'k{i}': 'cough fever headache' for i in range(80)}))
	batch = big.encode([o for o in big._queue.values()], ConnectionClass.wifi)  # noqa: SLF001
	assert batch.encoding == 'gzip', 'a large repetitive body should compress'
	assert batch.wire_bytes < batch.raw_bytes and batch.saved_ratio > 0.5


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

		empty = (await c.post('/sync/batch', params={'connection': 'wifi'})).json()
		# An empty queue is still a 2-byte `[]` on the wire — the claim is that no *op* is sent,
		# not that the request costs nothing.
		assert empty['ops'] == [] and empty['encoding'] == 'identity'
		assert (await c.post('/sync/batch', params={'connection': 'satellite'})).status_code == 422
