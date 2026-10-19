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

# §SEC-003: "Contact lists and location history: additional application-layer encryption". These are
# the datasets that get the *second* key, so a reader holding the at-rest key — a database dump, a
# stolen backup bucket — still cannot read where a person has been or who they were near. The set is
# named here rather than inferred from a prefix, because a dataset that quietly stopped qualifying
# would silently lose its layer.
APP_LAYER_DATASETS: frozenset[str] = frozenset({
	'contact_lists', 'location_history', 'proximity_tokens', 'exposure_declarations',
})

_SCHEMA = (
	'CREATE TABLE IF NOT EXISTS sync_ops (op_id TEXT PRIMARY KEY, dataset TEXT NOT NULL, server_version INTEGER NOT NULL DEFAULT 0, client_ts INTEGER NOT NULL, server_ts INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL DEFAULT "{}", attempt INTEGER NOT NULL DEFAULT 0, synced INTEGER NOT NULL DEFAULT 0, retry_at_ms INTEGER)',
	# Whose queued write each op is. A table of its own rather than a column on `sync_ops` because
	# that statement is the *shared* contract with both device clients (`proto/local_store/contract.json`,
	# held equal by `tests/ci/test_acc003.py`) and the clients have no subject to put in it — the token
	# travels per request, not per row. The owner is server-side knowledge.
	#
	# `INSERT OR REPLACE` on `sync_ops` deletes and re-inserts the row, so a foreign key here would
	# cascade the owner away on every flush. The binding is written once and never overwritten:
	# a row rehydrated with no owner must not blank the owner a live enqueue recorded.
	'CREATE TABLE IF NOT EXISTS sync_op_owners (op_id TEXT PRIMARY KEY, subject_ref TEXT NOT NULL)',
	'CREATE TABLE IF NOT EXISTS consents (consent_id TEXT PRIMARY KEY, subject_ref TEXT NOT NULL, purpose TEXT NOT NULL, data_types TEXT NOT NULL, retention_days INTEGER NOT NULL, legal_basis TEXT NOT NULL, withdrawn INTEGER NOT NULL DEFAULT 0)',
	'CREATE TABLE IF NOT EXISTS facilities (facility_id TEXT PRIMARY KEY, json TEXT NOT NULL)',
	# §17.4: "All access is logged." Append-only by construction — there is no UPDATE or DELETE
	# path to this table anywhere in the store, so an entry can only be added, never rewritten.
	# `purpose` is the section's second sentence; nullable because a row written before this build
	# has none, and a backfilled value would be a purpose nobody declared.
	'CREATE TABLE IF NOT EXISTS access_audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT NOT NULL, dataset TEXT NOT NULL, allowed INTEGER NOT NULL, at_ms INTEGER NOT NULL, purpose TEXT)',
)


class SqliteStore(LogMixin):
	"""§16.1/§17.2's local store, with §SEC-003's encryption applied to the sensitive columns.

	`crypto` is injected rather than imported, and it is optional — a unit test that only wants the
	queue to survive a reopen must not have to mint a key. What is *not* optional is the
	consequence: when no crypto service is wired, `sealed` columns are written as plaintext, and
	`encrypted` reports False so §SEC-003's posture says so instead of asserting AES-256 over a
	file anyone can read. A store that silently fell back to plaintext while a posture boolean
	claimed otherwise is precisely the finding the audit row named.
	"""

	def __init__(self, path: str, crypto: object | None = None) -> None:
		assert path, 'path required'
		self._path = path
		self._crypto = crypto
		self._ready = False
		assert not self._ready, 'store starts unready'

	@property
	def encrypted(self) -> bool:
		"""Whether this store seals its sensitive columns. Reported, never assumed."""
		return self._crypto is not None

	def _seal(self, plaintext: str, app_layer: bool = False) -> str:
		"""Seal one column value, or pass it through when no crypto service is wired."""
		assert plaintext is not None, 'a column value is required'
		if self._crypto is None:
			return plaintext
		sealed = self._crypto.seal(plaintext.encode('utf-8'), app_layer=app_layer)  # type: ignore[attr-defined]
		return sealed.to_blob()  # type: ignore[attr-defined]

	def _open(self, stored: str) -> str:
		"""Reverse `_seal`. A v1-tagged value is opened; anything else is legacy plaintext.

		Rows written before the store was encrypted stay readable, which is the only way an
		existing handset's queue survives the upgrade. The version tag is what makes that
		distinguishable from a value that failed to open — and a failed open raises rather than
		returning the ciphertext, because a corrupt record and an encrypted one must not look alike.
		"""
		assert stored is not None, 'a column value is required'
		if self._crypto is None or not stored.startswith('v1.'):
			return stored
		from afya.crypto.service import Sealed
		return self._crypto.open(Sealed.from_blob(stored)).decode('utf-8')  # type: ignore[attr-defined]

	@asynccontextmanager
	async def _conn(self) -> AsyncIterator[aiosqlite.Connection]:
		async with aiosqlite.connect(self._path) as c:
			if not self._ready:
				for ddl in _SCHEMA:
					await c.execute(ddl)
				await self._migrate(c)
				await c.commit()
				self._ready = True
			yield c

	async def _migrate(self, c: aiosqlite.Connection) -> None:
		"""Add columns a newer build needs to a table an older one created.

		`CREATE TABLE IF NOT EXISTS` is a no-op against a file that already has the table, so a
		handset that queued writes under the old build would keep its old schema and the first
		insert naming `retry_at_ms` would fail — losing the queue the column was added to protect.
		SQLite has no `ADD COLUMN IF NOT EXISTS`, so the column list is read first.

		`access_audit` needs the same treatment for the same reason: a deployed handset's audit table
		has four columns, and the first insert naming `purpose` would fail — on the *audit* path,
		where a failure is silent and the consequence is a §17.4 record that stops being written.
		The entry is added rather than the table rewritten, because the rows already in it are the
		record and `CREATE TABLE IF NOT EXISTS` would leave them behind.
		"""
		rows = await (await c.execute('PRAGMA table_info(sync_ops)')).fetchall()
		existing = {r[1] for r in rows}
		if 'retry_at_ms' not in existing:
			await c.execute('ALTER TABLE sync_ops ADD COLUMN retry_at_ms INTEGER')
			self._log_info('sync_ops migrated', added='retry_at_ms')
		# The queue's owner lives in `sync_op_owners`, so there is no `subject_ref` column to add
		# here — the shared contract with both device clients fixes `sync_ops`'s column list, and
		# a server-only column would have to be written into that contract as a column neither
		# client can fill.

		audit_cols = {r[1] for r in await (await c.execute('PRAGMA table_info(access_audit)')).fetchall()}
		if audit_cols and 'purpose' not in audit_cols:
			await c.execute('ALTER TABLE access_audit ADD COLUMN purpose TEXT')
			self._log_info('access_audit migrated', added='purpose')

	async def save_sync_op(self, op: SyncOp) -> None:
		async with self._conn() as c:
			await c.execute(
				'REPLACE INTO sync_ops VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
				(op.op_id, op.dataset, op.server_version, op.client_ts, op.server_ts,
				 self._seal(json.dumps(op.payload), app_layer=op.dataset in APP_LAYER_DATASETS),
				 op.attempt, int(op.synced), op.retry_at_ms),
			)
			# The owner, written once. `REPLACE INTO sync_ops` deletes and re-inserts the row on
			# every flush, so a binding that travelled with it would have to be re-supplied from a
			# `SyncOp` that a rehydrated queue has no subject for — and the flush would blank the
			# owner exactly when it matters, at the conflict. `DO NOTHING` keeps the first one.
			if op.subject_ref is not None:
				await c.execute(
					'INSERT INTO sync_op_owners (op_id, subject_ref) VALUES (?, ?) '
					'ON CONFLICT(op_id) DO NOTHING',
					(op.op_id, op.subject_ref),
				)
			await c.commit()

	async def sync_ops(self) -> list[SyncOp]:
		async with self._conn() as c:
			rows = await (await c.execute(
				'SELECT s.*, o.subject_ref FROM sync_ops s LEFT JOIN sync_op_owners o ON o.op_id = s.op_id'
			)).fetchall()
		return [
			SyncOp(op_id=r[0], dataset=r[1], server_version=r[2], client_ts=r[3], server_ts=r[4], payload=json.loads(self._open(r[5])), attempt=r[6], synced=bool(r[7]), retry_at_ms=r[8], subject_ref=r[9])
			for r in rows
		]

	async def save_consent(self, rec: ConsentRecord) -> None:
		async with self._conn() as c:
			await c.execute(
				'REPLACE INTO consents VALUES (?, ?, ?, ?, ?, ?, ?)',
				(rec.consent_id, rec.subject_ref, rec.purpose, self._seal(json.dumps(rec.data_types)), rec.retention_days, rec.legal_basis.value, int(rec.withdrawn)),
			)
			await c.commit()

	async def consents(self) -> list[ConsentRecord]:
		async with self._conn() as c:
			rows = await (await c.execute('SELECT * FROM consents')).fetchall()
		return [
			ConsentRecord(consent_id=r[0], subject_ref=r[1], purpose=r[2], data_types=json.loads(self._open(r[3])), retention_days=r[4], legal_basis=LegalBasis(r[5]), withdrawn=bool(r[6]))
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

	async def append_audit(self, role: str, dataset: str, allowed: bool, at_ms: int,
	                       purpose: str | None = None) -> None:
		"""Append one access decision. Insert-only; the table has no update path.

		`purpose` is §17.4's "documented purpose" for a read of another person's data. It is
		nullable because a row written before this build has none and a backfilled value would be a
		purpose nobody declared — the ledger's job is to record what was declared, and inventing a
		declaration is the one thing it must not do.
		"""
		assert role and dataset, 'an audit entry must name the role and the dataset'
		async with self._conn() as c:
			await c.execute(
				'INSERT INTO access_audit (role, dataset, allowed, at_ms, purpose) VALUES (?, ?, ?, ?, ?)',
				(role, dataset, int(allowed), at_ms, purpose),
			)
			await c.commit()

	async def audit_entries(self, limit: int = 1000) -> list[tuple[str, str, bool, int, str | None]]:
		"""Most recent first. Read-only; nothing here can mutate an entry."""
		assert limit > 0, 'limit must be positive'
		async with self._conn() as c:
			rows = await (await c.execute(
				'SELECT role, dataset, allowed, at_ms, purpose FROM access_audit ORDER BY seq DESC LIMIT ?', (limit,),
			)).fetchall()
		return [(r[0], r[1], bool(r[2]), r[3], r[4]) for r in rows]