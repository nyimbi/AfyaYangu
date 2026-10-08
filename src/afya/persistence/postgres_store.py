"""PostgreSQL store — production adapter of the persistence Protocol (spec §15.2), schema.sql-deployed."""
import json
from pathlib import Path

import asyncpg

from afya.facilities.views import Facility
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
				'''INSERT INTO afya.sync_ops (op_id, dataset, server_version, client_ts, server_ts, payload, attempt, synced)
				VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
				ON CONFLICT (op_id) DO UPDATE SET server_version=$3, server_ts=$5, payload=$6::jsonb, attempt=$7, synced=$8, updated_at=now()''',
				op.op_id, op.dataset, op.server_version, op.client_ts, op.server_ts, json.dumps(op.payload), op.attempt, op.synced,
			)

	async def sync_ops(self) -> list[SyncOp]:
		async with (await self.pool()).acquire() as c:
			rows = await c.fetch('SELECT op_id, dataset, server_version, client_ts, server_ts, payload, attempt, synced FROM afya.sync_ops ORDER BY client_ts')
		return [
			SyncOp(op_id=r['op_id'], dataset=r['dataset'], server_version=r['server_version'], client_ts=r['client_ts'], server_ts=r['server_ts'], payload=json.loads(r["payload"]), attempt=r['attempt'], synced=r['synced'])
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