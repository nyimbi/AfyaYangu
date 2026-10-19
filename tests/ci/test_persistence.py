import asyncio

import pytest

from afya.facilities.views import Facility, FacilityKind
from afya.persistence.service import SqliteStore
from afya.privacy.views import ConsentRecord, LegalBasis
from afya.sync.views import SyncOp
from afya.sync.service import SyncService
from afya.privacy.service import PrivacyService


@pytest.fixture
def db(tmp_path) -> str:
	return str(tmp_path / 'afya.db')


async def test_sync_ops_survive_reopen(db: str) -> None:
	store = SqliteStore(db)
	svc = SyncService(store)
	await svc.enqueue(SyncOp(op_id='OP-AAA111222', dataset='symptom_logs', client_ts=100, payload={'f': '1'}))
	await svc.enqueue(SyncOp(op_id='OP-BBB222333', dataset='proximity_tokens', client_ts=200, payload={'token': 'x' * 40}))
	assert (await store.sync_ops())[0].payload == {'f': '1'}
	# Reopen file: §16.1 nothing is lost.
	store2 = SqliteStore(db)
	ops = await store2.sync_ops()
	assert len(ops) == 2 and ops[0].dataset == 'symptom_logs'


async def test_flush_persists_synced(db: str) -> None:
	store = SqliteStore(db)
	svc = SyncService(store)
	await svc.enqueue(SyncOp(op_id='OP-AAA111222', dataset='symptom_logs', client_ts=5, payload={}))
	await svc.flush(0)
	persisted = (await SqliteStore(db).sync_ops())[0]
	assert persisted.synced is True


async def test_consent_ledger_roundtrip(db: str) -> None:
	store = SqliteStore(db)
	svc = PrivacyService(store)
	rec = await svc.record_consent(ConsentRecord(
		subject_ref='U1', purpose='health_companion', data_types=['demographic', 'location'],
		retention_days=730, legal_basis=LegalBasis.legitimate_interest,
	))
	await svc.withdraw(rec.consent_id)
	reloaded = SqliteStore(db)
	rows = await reloaded.consents()
	assert rows[0].withdrawn and rows[0].legal_basis is LegalBasis.legitimate_interest
	assert rows[0].data_types == ['demographic', 'location']


async def test_facility_cache_roundtrip(db: str) -> None:
	store = SqliteStore(db)
	fac = Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed, county='Nairobi', lat=-1.3, lon=36.8)
	await store.save_facility(fac)
	await store.save_facility(Facility(facility_id='F2', name='P', kind=FacilityKind.pharmacy, county='N', lat=-1.0, lon=36.0))
	rows = await SqliteStore(db).facilities()
	assert {f.facility_id for f in rows} == {'F1', 'F2'}


async def test_stats(db: str) -> None:
	store = SqliteStore(db)
	await store.save_sync_op(SyncOp(op_id='OP-AAA111222', dataset='temperature', client_ts=1, payload={}))
	stats = await store.stats()
	assert stats.sync_ops == 1 and stats.consents == 0


async def test_persisted_services_rehydrate(db: str) -> None:
	store = SqliteStore(db)
	await SqliteStore(db).save_consent(ConsentRecord(
		subject_ref='U9', purpose='p', data_types=[], retention_days=30, legal_basis=LegalBasis.consent,
	))
	# New service instance over same file must be wired from the store in prod; here verify store reads:
	rows = await store.consents()
	assert rows[0].subject_ref == 'U9'


async def test_queued_write_survives_restart_and_is_flushed(db: str) -> None:
	"""§16.1(5): a write queued offline is not lost when the process dies.

	The op was durable in SQLite all along, but nothing read it back, so `flush` iterated an empty
	in-memory queue and reported success while the write sat on disk forever. Durability that is
	only half-wired fails in the direction that looks like it works.
	"""
	first = SyncService(SqliteStore(db))
	await first.enqueue(SyncOp(op_id='OP-RESTART01', dataset='symptom_logs', client_ts=42, payload={'fever': '1'}))

	# New process, same file.
	second = SyncService(SqliteStore(db))
	status = await second.flush(0)
	assert status.synced == 1, 'the queued write must be replayed after a restart'
	assert status.pending == 0
	assert (await SqliteStore(db).sync_ops())[0].synced is True


async def test_already_synced_ops_are_not_replayed(db: str) -> None:
	"""Rehydration must not resurrect work that already reached the server, or every restart
	would re-upload the whole history."""
	first = SyncService(SqliteStore(db))
	await first.enqueue(SyncOp(op_id='OP-DONE00001', dataset='symptom_logs', client_ts=7, payload={}))
	await first.flush(0)

	second = SyncService(SqliteStore(db))
	assert await second.load() == 0, 'synced ops must not return to the queue'
	assert (await second.flush(0)).synced == 0


async def test_a_queued_writes_owner_survives_the_restart_and_the_flush(db: str) -> None:
	"""§16.3's appeal surface filters on the op's owner, and the owner has to outlive the process.

	Two ways it was lost. The op row is written with `REPLACE INTO`, which deletes and re-inserts,
	so an owner stored *on* that row is blanked by the next flush — and a flush is exactly what
	precedes a conflict. And a queue rehydrated after a restart is built from the stored row, which
	carries no token, so an owner kept only in memory is gone at the restart. Either way the write
	survives and the record of whose it was does not, and the conflict it loses is then withheld
	from every caller by the filter that was added to protect it.
	"""
	first = SyncService(SqliteStore(db))
	await first.enqueue(SyncOp(op_id='OP-OWNER0001', dataset='immunisation', client_ts=1,
	                          payload={'dose': '1'}, subject_ref='U-OWNER'))
	# The flush rewrites the row. The owner must not be a casualty of that.
	await first.flush(0)
	assert (await SqliteStore(db).sync_ops())[0].subject_ref == 'U-OWNER', 'the flush blanked the owner'

	# And a fresh process, which has no token to re-supply it from.
	restored = (await SqliteStore(db).sync_ops())[0]
	assert restored.subject_ref == 'U-OWNER', 'the restart lost the owner'
	assert restored.op_id == 'OP-OWNER0001'

	# The owner is written *once*. A later flush of the same op — the retry path, which re-enqueues
	# a row the queue rehydrated and therefore carries no subject — must not blank it, and must not
	# transfer it either: the op belongs to whoever queued it, and a re-enqueue is the same write.
	second = SyncService(SqliteStore(db))
	await second.enqueue(SyncOp(op_id='OP-OWNER0001', dataset='immunisation', client_ts=1,
	                           payload={'dose': '2'}, subject_ref=None))
	await second.flush(0)
	after = (await SqliteStore(db).sync_ops())[0]
	assert after.subject_ref == 'U-OWNER', 'a rehydrated re-enqueue blanked the owner'
	await second.enqueue(SyncOp(op_id='OP-OWNER0001', dataset='immunisation', client_ts=1,
	                           payload={'dose': '3'}, subject_ref='U-IMPOSTOR'))
	assert (await SqliteStore(db).sync_ops())[0].subject_ref == 'U-OWNER', \
		'a second enqueue transferred the op to a different caller'