import Foundation

/// §ACC-003's "local-first data storage (SQLite / Room / Core Data)", as the SQL the device runs.
///
/// §15.2 names Core Data for iOS and SQLite + Room for Android, and §16.1 principle 1 says every
/// user action is written to the local database first. What the client had instead was
/// `UserDefaults` holding the last good response and a JSON array of queued ops — a cache, with no
/// transactions, no schema and no key. Two writes racing lost one; a half-written batch could not
/// be rolled back; and nothing recorded an attempt or a backoff, so a failing send was retried on
/// every resume forever.
///
/// The statements live here rather than inline so the test bundle can run the *same* strings, and
/// so both clients run the same vectors (`proto/local_store/contract.json`).
enum LocalStoreSchema {

	static let name = "afya.db"
	static let version = 1

	static let ddl: [String] = [
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
		"CREATE INDEX IF NOT EXISTS sync_ops_due ON sync_ops (synced, client_ts)",
	]

	/// Columns a newer build needs on a table an older one created. `CREATE TABLE IF NOT EXISTS` is
	/// a no-op against an existing file, so without this a handset upgrading from the cache-only
	/// build keeps its old schema and the first insert naming the column fails — losing the queue
	/// the column was added to protect.
	static func migrations(existingColumns: Set<String>) -> [String] {
		var out: [String] = []
		if !existingColumns.contains("retry_at_ms") {
			out.append("ALTER TABLE sync_ops ADD COLUMN retry_at_ms INTEGER")
		}
		return out
	}

	/// `INSERT OR REPLACE` and not `INSERT`: a replay is the normal case offline, not the exception,
	/// so the primary key is what stops one op becoming two rows.
	static let insertOp =
		"INSERT OR REPLACE INTO sync_ops " +
		"(op_id, dataset, server_version, client_ts, server_ts, payload, attempt, synced, retry_at_ms) " +
		"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"

	/// Ops waiting for a network, oldest first, so the queue replays in the order it was written.
	static let pendingOps =
		"SELECT op_id, dataset, client_ts, payload, attempt, retry_at_ms FROM sync_ops " +
		"WHERE synced = 0 ORDER BY client_ts"

	static let pendingCount = "SELECT COUNT(*) FROM sync_ops WHERE synced = 0"
	static let markSynced = "UPDATE sync_ops SET synced = 1, server_ts = ? WHERE op_id = ?"
	static let dropOp = "DELETE FROM sync_ops WHERE op_id = ?"
	static let deferOp = "UPDATE sync_ops SET attempt = ?, retry_at_ms = ? WHERE op_id = ?"
}
