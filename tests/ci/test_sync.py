import pytest

from afya.sync.service import SyncService, backoff_delay_s
from afya.sync.views import SyncOp


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