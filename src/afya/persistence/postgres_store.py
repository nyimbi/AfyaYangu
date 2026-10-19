"""PostgreSQL store — production adapter of the persistence Protocol (spec §15.2), schema.sql-deployed."""
import json
from pathlib import Path

import asyncpg

from afya.facilities.views import Facility
from afya.ids import uuid7str
from afya.logmixin import LogMixin
from afya.privacy.views import ConsentRecord, LegalBasis
from afya.sync.views import SyncOp
from afya.persistence.views import StoreStats

_SCHEMA_SQL = (Path(__file__).parent / 'schema.sql').read_text()


class PostgresStore(LogMixin):
	def __init__(self, dsn: str) -> None:
		assert dsn.startswith('postgres'), 'valid postgres DSN'
		self._dsn = dsn
		self._pool: asyncpg.Pool | None = None

	async def pool(self) -> asyncpg.Pool:
		if self._pool is None:
			self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=6)
		assert self._pool is not None, 'pool established'
		return self._pool

	async def deploy(self) -> int:
		"""Deploy schema.sql idempotently; returns statement count."""
		count = 0
		no_comments = '\n'.join(line for line in _SCHEMA_SQL.splitlines() if not line.lstrip().startswith('--'))
		async with (await self.pool()).acquire() as conn:
			for stmt in no_comments.split(';'):
				sql = stmt.strip()
				if sql:
					await conn.execute(sql + ';')
					count += 1
		self._log_info('schema deployed', statements=count)
		return count

	async def close(self) -> None:
		if self._pool is not None:
			await self._pool.close()
			self._pool = None

	async def save_sync_op(self, op: SyncOp) -> None:
		async with (await self.pool()).acquire() as c:
			await c.execute(
				'''INSERT INTO afya.sync_ops (op_id, dataset, server_version, client_ts, server_ts, payload, attempt, synced, retry_at_ms)
				VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9)
				ON CONFLICT (op_id) DO UPDATE SET server_version=$3, server_ts=$5, payload=$6::jsonb, attempt=$7, synced=$8, retry_at_ms=$9, updated_at=now()''',
				op.op_id, op.dataset, op.server_version, op.client_ts, op.server_ts, json.dumps(op.payload), op.attempt, op.synced, op.retry_at_ms,
			)
			# Written once, in its own table: the upsert above rewrites the op on every flush, and
			# a rehydrated queue has no subject to re-supply, so an owner carried on the op row
			# would be blanked at the flush — the moment `GET /sync/conflicts` needs it.
			if op.subject_ref is not None:
				await c.execute(
					'INSERT INTO afya.sync_op_owners (op_id, subject_ref) VALUES ($1, $2) '
					'ON CONFLICT (op_id) DO NOTHING',
					op.op_id, op.subject_ref,
				)

	async def sync_ops(self) -> list[SyncOp]:
		async with (await self.pool()).acquire() as c:
			rows = await c.fetch(
				'SELECT s.op_id, s.dataset, s.server_version, s.client_ts, s.server_ts, s.payload, '
				's.attempt, s.synced, s.retry_at_ms, o.subject_ref '
				'FROM afya.sync_ops s LEFT JOIN afya.sync_op_owners o ON o.op_id = s.op_id '
				'ORDER BY s.client_ts')
		return [
			SyncOp(op_id=r['op_id'], dataset=r['dataset'], server_version=r['server_version'], client_ts=r['client_ts'], server_ts=r['server_ts'], payload=json.loads(r["payload"]), attempt=r['attempt'], synced=r['synced'], retry_at_ms=r['retry_at_ms'], subject_ref=r['subject_ref'])
			for r in rows
		]

	async def save_consent(self, rec: ConsentRecord) -> None:
		async with (await self.pool()).acquire() as c:
			await c.execute(
				'''INSERT INTO afya.consents (consent_id, subject_ref, purpose, data_types, retention_days, legal_basis, withdrawn)
				VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
				ON CONFLICT (consent_id) DO UPDATE SET data_types=$4::jsonb, retention_days=$5, withdrawn=$7, updated_at=now()''',
				rec.consent_id, rec.subject_ref, rec.purpose, json.dumps(rec.data_types), rec.retention_days, rec.legal_basis.value, rec.withdrawn,
			)

	async def consents(self) -> list[ConsentRecord]:
		async with (await self.pool()).acquire() as c:
			rows = await c.fetch('SELECT consent_id, subject_ref, purpose, data_types, retention_days, legal_basis, withdrawn FROM afya.consents ORDER BY created_at')
		return [
			ConsentRecord(consent_id=r['consent_id'], subject_ref=r['subject_ref'], purpose=r['purpose'], data_types=json.loads(r["data_types"]), retention_days=r['retention_days'], legal_basis=LegalBasis(r['legal_basis']), withdrawn=r['withdrawn'])
			for r in rows
		]

	async def save_facility(self, fac: Facility) -> None:
		async with (await self.pool()).acquire() as c:
			await c.execute(
				'''INSERT INTO afya.facilities (facility_id, name, kind, county, lat, lon, open_now, ed_status, crowdload, payload)
				VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
				ON CONFLICT (facility_id) DO UPDATE SET name=$2, kind=$3, county=$4, lat=$5, lon=$6, open_now=$7, ed_status=$8, crowdload=$9, payload=$10::jsonb, updated_at=now()''',
				fac.facility_id, fac.name, fac.kind.value, fac.county, fac.lat, fac.lon, fac.open_now, fac.ed_status, fac.crowdload, fac.model_dump_json(),
			)

	async def facilities(self) -> list[Facility]:
		async with (await self.pool()).acquire() as c:
			rows = await c.fetch('SELECT payload FROM afya.facilities ORDER BY facility_id')
		return [Facility.model_validate_json(r["payload"]) for r in rows]

	async def stats(self) -> StoreStats:
		async with (await self.pool()).acquire() as c:
			return StoreStats(
				sync_ops=await c.fetchval('SELECT count(*) FROM afya.sync_ops'),
				consents=await c.fetchval('SELECT count(*) FROM afya.consents'),
				facilities=await c.fetchval('SELECT count(*) FROM afya.facilities'),
			)

	async def append_audit(self, role: str, dataset: str, allowed: bool, at_ms: int,
	                       purpose: str | None = None) -> None:
		"""Append one §17.4 access decision. Insert-only, as the SQLite adapter is.

		The table and the `ref` column already existed here and had **no writer at all** — the
		durable §17.4 record was carried only by the SQLite adapter, so a deployment on Postgres
		kept the log in memory and lost it on restart. `purpose` goes in the `ref` column rather
		than a new one, because `ref` was declared for exactly this: the detail about an entry that
		is not the role, the dataset or the decision. `entry_id` and `at` take their defaults.
		"""
		assert role and dataset, 'an audit entry must name the role and the dataset'
		async with (await self.pool()).acquire() as c:
			await c.execute(
				'''INSERT INTO afya.audit_log (entry_id, role, dataset, allowed, ref, purpose)
				VALUES ($1, $2, $3, $4, $5::jsonb, $6)''',
				uuid7str(), role, dataset, allowed, json.dumps({'at_ms': at_ms}), purpose,
			)

	async def audit_entries(self, limit: int = 1000) -> list[tuple[str, str, bool, int, str | None]]:
		"""Most recent first, in the shape `SqliteStore.audit_entries` returns."""
		assert limit > 0, 'limit must be positive'
		async with (await self.pool()).acquire() as c:
			rows = await c.fetch(
				'SELECT role, dataset, allowed, ref, purpose FROM afya.audit_log ORDER BY at DESC LIMIT $1', limit,
			)
		return [(r['role'], r['dataset'], bool(r['allowed']),
		         int(json.loads(r['ref']).get('at_ms', 0)), r['purpose']) for r in rows]