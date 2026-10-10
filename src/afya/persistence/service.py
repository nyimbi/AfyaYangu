"""SQLite persistence adapters — durability for sync queue + consent ledger (spec §16.1/§17.2).

Postgres adapter (asyncpg) implements the same Protocol in production; SQLite keeps
local/CI runs dependency-light while exercising identical contracts.
"""
import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite
from pydantic import ValidationError

from afya.facilities.views import Facility
from afya.logmixin import LogMixin
from afya.privacy.views import ConsentRecord, LegalBasis
from afya.sync.views import SyncOp
from afya.persistence.views import StoreStats

_SCHEMA = (
	'CREATE TABLE IF NOT EXISTS sync_ops (op_id TEXT PRIMARY KEY, dataset TEXT NOT NULL, server_version INTEGER NOT NULL DEFAULT 0, client_ts INTEGER NOT NULL, server_ts INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL DEFAULT "{}", attempt INTEGER NOT NULL DEFAULT 0, synced INTEGER NOT NULL DEFAULT 0)',
	'CREATE TABLE IF NOT EXISTS consents (consent_id TEXT PRIMARY KEY, subject_ref TEXT NOT NULL, purpose TEXT NOT NULL, data_types TEXT NOT NULL, retention_days INTEGER NOT NULL, legal_basis TEXT NOT NULL, withdrawn INTEGER NOT NULL DEFAULT 0)',
	'CREATE TABLE IF NOT EXISTS facilities (facility_id TEXT PRIMARY KEY, json TEXT NOT NULL)',
	# §17.4: "All access is logged." Append-only by construction — there is no UPDATE or DELETE
	# path to this table anywhere in the store, so an entry can only be added, never rewritten.
	'CREATE TABLE IF NOT EXISTS access_audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, dataset TEXT NOT NULL, allowed INTEGER NOT NULL, at_ms INTEGER NOT NULL)',
)


class SqliteStore(LogMixin):
	def __init__(self, path: str) -> None:
		assert path, 'path required'
		self._path = path
		self._ready = False
		assert not self._ready, 'store starts unready'

	@asynccontextmanager
	async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
		async with aiosqlite.connect(self._path) as c:
			if not self._ready:
				for ddl in _SCHEMA:
					await c.execute(ddl)
				await c.commit()
				self._ready = True
			yield c

	async def save_sync_op(self, op: SyncOp) -> None:
		async with self._conn() as c:
			await c.execute(
				'REPLACE INTO sync_ops VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
				(op.op_id, op.dataset, op.server_version, op.client_ts, op.server_ts, json.dumps(op.payload), op.attempt, int(op.synced)),
			)
			await c.commit()

	async def sync_ops(self) -> list[SyncOp]:
		async with self._conn() as c:
			rows = await (await c.execute('SELECT * FROM sync_ops')).fetchall()
		return [
			SyncOp(op_id=r[0], dataset=r[1], server_version=r[2], client_ts=r[3], server_ts=r[4], payload=json.loads(r[5]), attempt=r[6], synced=bool(r[7]))
			for r in rows
		]

	async def save_consent(self, rec: ConsentRecord) -> None:
		async with self._conn() as c:
			await c.execute(
				'REPLACE INTO consents VALUES (?, ?, ?, ?, ?, ?, ?)',
				(rec.consent_id, rec.subject_ref, rec.purpose, json.dumps(rec.data_types), rec.retention_days, rec.legal_basis.value, int(rec.withdrawn)),
			)
			await c.commit()

	async def consents(self) -> list[ConsentRecord]:
		async with self._conn() as c:
			rows = await (await c.execute('SELECT * FROM consents')).fetchall()
		return [
			ConsentRecord(consent_id=r[0], subject_ref=r[1], purpose=r[2], data_types=json.loads(r[3]), retention_days=r[4], legal_basis=LegalBasis(r[5]), withdrawn=bool(r[6]))
			for r in rows
		]

	async def save_facility(self, fac: Facility) -> None:
		async with self._conn() as c:
			await c.execute('REPLACE INTO facilities VALUES (?, ?)', (fac.facility_id, fac.model_dump_json()))
			await c.commit()

	async def facilities(self) -> list[Facility]:
		async with self._conn() as c:
			rows = await (await c.execute('SELECT facility_id, json FROM facilities')).fetchall()
		out = []
		for _, blob in rows:
			try:
				out.append(Facility.model_validate_json(blob))
			except ValidationError:
				self._log_warn('skipping corrupt facility row')
		return out

	async def stats(self) -> StoreStats:
		return StoreStats(sync_ops=len(await self.sync_ops()), consents=len(await self.consents()), facilities=len(await self.facilities()))

	async def append_audit(self, role: str, dataset: str, allowed: bool, at_ms: int) -> None:
		"""Append one access decision. Insert-only; the table has no update path."""
		assert role and dataset, 'an audit entry must name the role and the dataset'
		async with self._conn() as c:
			await c.execute(
				'INSERT INTO access_audit (role, dataset, allowed, at_ms) VALUES (?, ?, ?, ?)',
				(role, dataset, int(allowed), at_ms),
			)
			await c.commit()

	async def audit_entries(self, limit: int = 1000) -> list[tuple[str, str, bool, int]]:
		"""Most recent first. Read-only; nothing here can mutate an entry."""
		assert limit > 0, 'limit must be positive'
		async with self._conn() as c:
			rows = await (await c.execute(
				'SELECT role, dataset, allowed, at_ms FROM access_audit ORDER BY seq DESC LIMIT ?', (limit,),
			)).fetchall()
		return [(r[0], r[1], bool(r[2]), r[3]) for r in rows]