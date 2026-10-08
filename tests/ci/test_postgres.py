import asyncio
import os

import pytest

from afya.facilities.views import Facility, FacilityKind
from afya.persistence.postgres_store import PostgresStore
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentRecord, LegalBasis
from afya.sync.views import SyncOp

DSN = os.environ.get('AFYA_PG_DSN', 'postgresql://localhost/afya')


@pytest.fixture
async def pg():
	try:
		store = PostgresStore(DSN)
		await _probe(store)
		await store.deploy()
		await _clean(store)
		return store
	except (OSError, AttributeError):
		pytest.skip(f'local postgres not reachable at {DSN}')
	except Exception as exc:
		if 'connect' in str(exc).lower() or 'Connection refused' in str(exc):
			pytest.skip(f'postgres not reachable: {exc}')
		raise


async def _probe(store: PostgresStore) -> None:
	await store.pool()
	await store.close()
	await store.pool()  # reopen works


async def _clean(store: PostgresStore) -> None:
	async with (await store.pool()).acquire() as c:
		await c.execute('DELETE FROM afya.sync_ops')
		await c.execute('DELETE FROM afya.consents')
		await c.execute('DELETE FROM afya.facilities')


async def test_deploy_idempotent(pg: PostgresStore) -> None:
	assert (await pg.deploy()) >= 8
	assert (await pg.deploy()) >= 8


async def test_sync_ops_survive_reopen(pg: PostgresStore) -> None:
	svc1 = PostgresStore(DSN)
	await svc1.save_sync_op(SyncOp(op_id='OP-PG111AAA', dataset='symptom_logs', client_ts=100, payload={'f': '1'}))
	await pg.close()
	rows = await pg.sync_ops()
	assert len(rows) == 1 and rows[0].payload == {'f': '1'} and rows[0].dataset == 'symptom_logs'


async def test_dataset_check_constraint(pg: PostgresStore) -> None:
	import asyncpg
	with pytest.raises(asyncpg.exceptions.CheckViolationError):
		await pg.save_sync_op(SyncOp.model_construct(op_id='OP-BAD', dataset='nope', client_ts=1, server_version=0, server_ts=0, payload={}, attempt=0, synced=False))


async def test_consent_ledger_roundtrip(pg: PostgresStore) -> None:
	svc = PrivacyService(pg)
	rec = await svc.record_consent(ConsentRecord(
		subject_ref='U1', purpose='health_companion', data_types=['demographic', 'location'],
		retention_days=730, legal_basis=LegalBasis.legitimate_interest,
	))
	await svc.withdraw(rec.consent_id)
	rows = (await pg.consents())
	assert any(r.withdrawn and r.legal_basis is LegalBasis.legitimate_interest and r.data_types == ['demographic', 'location'] for r in rows)


async def test_facility_cache_roundtrip(pg: PostgresStore) -> None:
	await pg.save_facility(Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed, county='Nairobi', lat=-1.3, lon=36.8, ed_status='operational', crowdload=10))
	rows = await pg.facilities()
	assert len(rows) == 1 and rows[0].name == 'KNH' and rows[0].ed_status == 'operational'
	stats = await pg.stats()
	assert stats.facilities == 1


async def test_geo_bounds_enforced_by_db(pg: PostgresStore) -> None:
	import asyncpg
	fac = Facility.model_construct(facility_id='F9', name='X', kind=FacilityKind.ed, county='X', lat=50.0, lon=36.0, open_now=True, ed_status=None, crowdload=0)
	with pytest.raises(asyncpg.exceptions.CheckViolationError):
		await pg.save_facility(fac)