import Foundation
import SQLite3

/// One queued write as the device holds it. `key` is the idempotency key it replays under.
struct QueuedOp {
	let opId: String
	let dataset: String
	let clientTs: Int64
	let method: String
	let url: String
	let body: String
	let key: String
	let attempt: Int
	let retryAtMs: Int64?
}

/// §ACC-003's local-first store: a real SQLite database, so §16.1's promises are ones the device
/// can keep. See `LocalStoreSchema` for what the cache could not do.
///
/// The `sqlite3` C API is used directly rather than through a wrapper because the wrapper would be
/// a third-party dependency for one table, and because the point of the unit is that the store is
/// the device's own — a Swift package that re-implemented the schema would put the schema somewhere
/// the test bundle could not read it.
final class LocalStore {

	private var db: OpaquePointer?
	private let path: String

	/// `SQLITE_TRANSIENT` tells SQLite to copy the bound bytes, which is what makes a Swift `String`
	/// safe to bind: the default would keep the pointer and read freed memory at step time.
	private let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

	init(path: String? = nil) {
		self.path = path ?? LocalStore.defaultPath()
		open()
	}

	/// A path under Application Support rather than Documents: this is the app's own queue, not a
	/// file the user owns, and it should not appear in the Files browser or an iTunes backup.
	static func defaultPath() -> String {
		let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
		try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
		return dir.appendingPathComponent(LocalStoreSchema.name).path
	}

	private func open() {
		if sqlite3_open(path, &db) != SQLITE_OK {
			// A store that cannot open is not a store, and a queue that silently did not persist is
			// exactly the failure this unit exists to remove. The caller decides what to do; the
			// store does not pretend.
			NSLog("afya: cannot open the local store at \(path)")
			db = nil
			return
		}
		for statement in LocalStoreSchema.ddl { exec(statement) }
		let existing = columns(of: "sync_ops")
		for statement in LocalStoreSchema.migrations(existingColumns: existing) { exec(statement) }
	}

	deinit { if db != nil { sqlite3_close(db) } }

	private func exec(_ sql: String, _ bindings: [Any?] = []) {
		guard let db else { return }
		var stmt: OpaquePointer?
		guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return }
		defer { sqlite3_finalize(stmt) }
		bind(stmt, bindings)
		sqlite3_step(stmt)
	}

	private func bind(_ stmt: OpaquePointer?, _ bindings: [Any?]) {
		for (i, value) in bindings.enumerated() {
			let idx = Int32(i + 1)
			switch value {
			case nil: sqlite3_bind_null(stmt, idx)
			case let s as String: sqlite3_bind_text(stmt, idx, s, -1, transient)
			case let n as Int: sqlite3_bind_int64(stmt, idx, Int64(n))
			case let n as Int64: sqlite3_bind_int64(stmt, idx, n)
			default: sqlite3_bind_null(stmt, idx)
			}
		}
	}

	private func columns(of table: String) -> Set<String> {
		guard let db else { return [] }
		var stmt: OpaquePointer?
		guard sqlite3_prepare_v2(db, "PRAGMA table_info(\(table))", -1, &stmt, nil) == SQLITE_OK else { return [] }
		defer { sqlite3_finalize(stmt) }
		var out = Set<String>()
		while sqlite3_step(stmt) == SQLITE_ROW {
			if let c = sqlite3_column_text(stmt, 1) { out.insert(String(cString: c)) }
		}
		return out
	}

	private func text(_ stmt: OpaquePointer?, _ col: Int32) -> String {
		guard let c = sqlite3_column_text(stmt, col) else { return "" }
		return String(cString: c)
	}

	/// Queue a write. One statement, so the row and its key are committed together.
	func enqueue(_ op: QueuedOp) {
		let payload: [String: Any] = ["method": op.method, "url": op.url, "body": op.body, "key": op.key]
		let json = (try? JSONSerialization.data(withJSONObject: payload)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
		exec(
			LocalStoreSchema.insertOp,
			[op.opId, op.dataset, 0, op.clientTs, 0, json, op.attempt, 0, op.retryAtMs]
		)
	}

	/// Ops waiting for a network, oldest first.
	func pending() -> [QueuedOp] {
		guard let db else { return [] }
		var stmt: OpaquePointer?
		guard sqlite3_prepare_v2(db, LocalStoreSchema.pendingOps, -1, &stmt, nil) == SQLITE_OK else { return [] }
		defer { sqlite3_finalize(stmt) }
		var out: [QueuedOp] = []
		while sqlite3_step(stmt) == SQLITE_ROW {
			let raw = text(stmt, 3)
			let obj = (try? JSONSerialization.jsonObject(with: Data(raw.utf8))) as? [String: Any] ?? [:]
			out.append(
				QueuedOp(
					opId: text(stmt, 0),
					dataset: text(stmt, 1),
					clientTs: sqlite3_column_int64(stmt, 2),
					method: obj["method"] as? String ?? "POST",
					url: obj["url"] as? String ?? "",
					body: obj["body"] as? String ?? "",
					key: obj["key"] as? String ?? "",
					attempt: Int(sqlite3_column_int(stmt, 4)),
					retryAtMs: sqlite3_column_type(stmt, 5) == SQLITE_NULL ? nil : sqlite3_column_int64(stmt, 5)
				)
			)
		}
		return out
	}

	func pendingCount() -> Int {
		guard let db else { return 0 }
		var stmt: OpaquePointer?
		guard sqlite3_prepare_v2(db, LocalStoreSchema.pendingCount, -1, &stmt, nil) == SQLITE_OK else { return 0 }
		defer { sqlite3_finalize(stmt) }
		return sqlite3_step(stmt) == SQLITE_ROW ? Int(sqlite3_column_int(stmt, 0)) : 0
	}

	func markSynced(_ opId: String, serverTs: Int64) {
		exec(LocalStoreSchema.markSynced, [serverTs, opId])
	}

	/// The server refused this request; retrying it forever would block the queue behind it.
	func drop(_ opId: String) {
		exec(LocalStoreSchema.dropOp, [opId])
	}

	/// The send failed for a reason a retry may fix. Record the attempt and when to try again.
	func deferOp(_ opId: String, attempt: Int, retryAtMs: Int64?) {
		exec(LocalStoreSchema.deferOp, [attempt, retryAtMs, opId])
	}
}
