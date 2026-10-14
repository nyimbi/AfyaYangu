package ke.go.health.afyayangu

/**
 * §ACC-003's "local-first data storage (SQLite / Room / Core Data)", as the SQL both the device and
 * its test run.
 *
 * §15.2 names SQLite + Room for Android and Core Data for iOS, and §16.1 principle 1 says every user
 * action is written to the local database first. What the client had instead was
 * `SharedPreferences` holding the last good response — a cache, with no transactions, no schema and
 * no key — so a queued write could be half-written, duplicated on replay, or lost to a race with the
 * next `apply()`. This is the schema that replaces it.
 *
 * The statements live in their own file with no Android imports so the JVM unit test can run the
 * *same* strings against a real SQLite engine. A test that rebuilt the DDL by hand would be testing
 * a copy, and two files that agree today are not one source of truth.
 *
 * The table mirrors the server's `sync_ops` (`afya/persistence/service.py`): a queue is only
 * replayable if the row it holds is the row the server expects.
 */
object LocalStoreSchema {

	const val NAME = "afya.db"
	const val VERSION = 1

	val DDL: List<String> = listOf(
		"CREATE TABLE IF NOT EXISTS sync_ops (" +
			"op_id TEXT PRIMARY KEY, " +
			"dataset TEXT NOT NULL, " +
			"server_version INTEGER NOT NULL DEFAULT 0, " +
			"client_ts INTEGER NOT NULL, " +
			"server_ts INTEGER NOT NULL DEFAULT 0, " +
			"payload TEXT NOT NULL DEFAULT '{}', " +
			"attempt INTEGER NOT NULL DEFAULT 0, " +
			"synced INTEGER NOT NULL DEFAULT 0, " +
			"retry_at_ms INTEGER)",
		// The flush reads the queue in client_ts order and skips what is not due, which is the one
		// query that runs on every resume.
		"CREATE INDEX IF NOT EXISTS sync_ops_due ON sync_ops (synced, client_ts)",
	)

	/**
	 * Columns a newer build needs on a table an older one created.
	 *
	 * `CREATE TABLE IF NOT EXISTS` is a no-op against a file that already has the table, so a handset
	 * that queued writes under the old build would keep its old schema and the first insert naming a
	 * new column would fail — losing the queue the column was added to protect. The column list is
	 * read first because SQLite has no `ADD COLUMN IF NOT EXISTS`.
	 */
	fun migrations(existingColumns: Set<String>): List<String> = buildList {
		if ("retry_at_ms" !in existingColumns) add("ALTER TABLE sync_ops ADD COLUMN retry_at_ms INTEGER")
	}

	// `INSERT OR REPLACE` and not `INSERT`: a replay is the normal case offline, not the exception,
	// so the primary key is what stops one op becoming two rows.
	const val INSERT_OP: String =
		"INSERT OR REPLACE INTO sync_ops " +
			"(op_id, dataset, server_version, client_ts, server_ts, payload, attempt, synced, retry_at_ms) " +
			"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"

	/** Ops waiting for a network, oldest first, so the queue replays in the order it was written. */
	const val PENDING_OPS: String =
		"SELECT op_id, dataset, client_ts, payload, attempt, retry_at_ms FROM sync_ops " +
			"WHERE synced = 0 ORDER BY client_ts"

	const val PENDING_COUNT: String = "SELECT COUNT(*) FROM sync_ops WHERE synced = 0"

	/** Mark an op sent. `server_ts` comes from the ack, so the row records when the server took it. */
	const val MARK_SYNCED: String = "UPDATE sync_ops SET synced = 1, server_ts = ? WHERE op_id = ?"

	/** A write the server refused outright. Retrying a 4xx forever blocks the queue behind it. */
	const val DROP_OP: String = "DELETE FROM sync_ops WHERE op_id = ?"

	/** Record a failed attempt and when the op may be offered again — §16.2's exponential backoff. */
	const val DEFER_OP: String = "UPDATE sync_ops SET attempt = ?, retry_at_ms = ? WHERE op_id = ?"
}
