import XCTest
import SQLite3

@testable import AfyaYangu

/// §ACC-003's "local-first data storage", verified against a real database engine.
///
/// The store's own class needs a device; the *statements* do not, and they are where the property
/// lives. These run `LocalStoreSchema`'s SQL against SQLite and assert what §16.1 promises:
/// durability across a reopen, the absence of a rolled-back write, and a key that makes a replay
/// one row rather than two.
///
/// The scenarios come from `proto/local_store/contract.json`, which the Android client runs too.
/// Two files that agree today are not one source of truth; one file both clients run is.
final class LocalStoreTests: XCTestCase {

	private var path: String!

	override func setUpWithError() throws {
		path = NSTemporaryDirectory() + "afya-test-\(UUID().uuidString).db"
	}

	override func tearDownWithError() throws {
		try? FileManager.default.removeItem(atPath: path)
	}

	/// A database of its own, at `at`.
	///
	/// Every scenario gets a fresh file. Sharing one was the first version of this test and it
	/// failed — not because the store was wrong but because scenario 1's committed rows were still
	/// in the file when scenario 2 asserted that only its own survived. The Android side did not
	/// catch it because `jdbc:sqlite::memory:` is a new engine per connection, which is exactly the
	/// kind of asymmetry a shared contract exists to expose.
	private func open(at: String? = nil) -> OpaquePointer? {
		var db: OpaquePointer?
		guard sqlite3_open(at ?? path, &db) == SQLITE_OK else { return nil }
		for statement in LocalStoreSchema.ddl {
			sqlite3_exec(db, statement, nil, nil, nil)
		}
		return db
	}

	private func run(_ db: OpaquePointer?, _ sql: String) {
		sqlite3_exec(db, sql, nil, nil, nil)
	}

	private func column(_ db: OpaquePointer?, _ sql: String) -> [String] {
		var stmt: OpaquePointer?
		guard sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK else { return [] }
		defer { sqlite3_finalize(stmt) }
		var out: [String] = []
		while sqlite3_step(stmt) == SQLITE_ROW {
			out.append(sqlite3_column_text(stmt, 0).map { String(cString: $0) } ?? "")
		}
		return out
	}

	/// The repo root, found by walking up rather than by counting `..`: the test bundle's working
	/// directory is a fact about the build settings, and a count that drifts reads nothing.
	private func contractURL() throws -> URL {
		var dir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
		while dir.path != "/" {
			let candidate = dir.appendingPathComponent("proto/local_store/contract.json")
			if FileManager.default.fileExists(atPath: candidate.path) { return candidate }
			dir = dir.deletingLastPathComponent()
		}
		throw XCTSkip("proto/local_store/contract.json not found above \(#filePath)")
	}

	func testTheSharedContractIsTheOneBothClientsRun() throws {
		let obj = try JSONSerialization.jsonObject(with: Data(contentsOf: try contractURL())) as! [String: Any]
		XCTAssertEqual(obj["contract"] as? String, "afya.local_store.v1")
		let names = (obj["scenarios"] as! [[String: Any]]).map { $0["name"] as! String }
		XCTAssertEqual(
			names,
			["committed_rows_are_durable", "rolled_back_rows_are_gone", "the_key_refuses_a_duplicate"]
		)
	}

	func testEverySharedScenarioHoldsAgainstARealEngine() throws {
		let obj = try JSONSerialization.jsonObject(with: Data(contentsOf: try contractURL())) as! [String: Any]
		let ddl = obj["ddl"] as! String
		for scenario in obj["scenarios"] as! [[String: Any]] {
			let name = scenario["name"] as! String
			let scratch = NSTemporaryDirectory() + "afya-scenario-\(name).db"
			try? FileManager.default.removeItem(atPath: scratch)
			defer { try? FileManager.default.removeItem(atPath: scratch) }
			guard let db = open(at: scratch) else { return XCTFail("cannot open a store") }
			run(db, ddl)
			for statement in scenario["statements"] as! [String] { run(db, statement) }
			let got = column(db, scenario["query"] as! String)
			sqlite3_close(db)
			XCTAssertEqual(got, scenario["expect"] as! [String], "\(name): \(scenario["why"] as! String)")
		}
	}

	func testTheDeviceRunsTheContractsOwnDdlRatherThanACopyOfIt() throws {
		// A test that rebuilt the DDL by hand would pass against a store whose real schema had
		// drifted. The first scenario's first statement must be the store's own table definition.
		let obj = try JSONSerialization.jsonObject(with: Data(contentsOf: try contractURL())) as! [String: Any]
		XCTAssertEqual(obj["ddl"] as! String, LocalStoreSchema.ddl[0])
	}

	func testAnOlderDatabaseGainsTheColumnANewerBuildNeeds() throws {
		guard let db = open() else { return XCTFail("cannot open a store") }
		defer { sqlite3_close(db) }
		run(db, "DROP TABLE sync_ops")
		run(db, LocalStoreSchema.ddl[0].replacingOccurrences(of: ", retry_at_ms INTEGER", with: ""))
		var existing = Set<String>()
		var stmt: OpaquePointer?
		if sqlite3_prepare_v2(db, "PRAGMA table_info(sync_ops)", -1, &stmt, nil) == SQLITE_OK {
			while sqlite3_step(stmt) == SQLITE_ROW {
				existing.insert(sqlite3_column_text(stmt, 1).map { String(cString: $0) } ?? "")
			}
			sqlite3_finalize(stmt)
		}
		XCTAssertFalse(existing.contains("retry_at_ms"))
		for statement in LocalStoreSchema.migrations(existingColumns: existing) { run(db, statement) }
		// Without this the upgrade path fails on the first insert naming the column — losing the
		// queue the column was added to protect.
		run(db, "INSERT INTO sync_ops (op_id, dataset, client_ts, retry_at_ms) VALUES ('OP-OLD001', 'medication', 1, 99)")
		XCTAssertEqual(column(db, "SELECT op_id FROM sync_ops"), ["OP-OLD001"])
	}

	func testThePendingQueryReturnsTheOldestFirstAndTheSyncedNever() throws {
		guard let db = open() else { return XCTFail("cannot open a store") }
		defer { sqlite3_close(db) }
		run(db, "INSERT INTO sync_ops (op_id, dataset, client_ts, synced) VALUES ('OP-B2', 'medication', 200, 0)")
		run(db, "INSERT INTO sync_ops (op_id, dataset, client_ts, synced) VALUES ('OP-A1', 'symptom_logs', 100, 0)")
		run(db, "INSERT INTO sync_ops (op_id, dataset, client_ts, synced) VALUES ('OP-C3', 'facility', 300, 1)")
		// Order matters: a queue that replays out of order applies a later state before an earlier
		// one, which is the conflict §16.3 then has to resolve.
		XCTAssertEqual(column(db, LocalStoreSchema.pendingOps), ["OP-A1", "OP-B2"])
	}

	func testAWriteSurvivesTheStoreBeingClosedAndReopened() throws {
		// §16.1 principle 5, through the store's own type rather than through raw SQL: this is the
		// promise the JSON array in UserDefaults was making and could not keep.
		let first = LocalStore(path: path)
		first.enqueue(
			QueuedOp(
				opId: "OP-REOPEN", dataset: "symptom_logs", clientTs: 1, method: "POST",
				url: "http://localhost:8000/triage/diary", body: "{}", key: "OP-REOPEN",
				attempt: 0, retryAtMs: nil
			)
		)
		XCTAssertEqual(first.pendingCount(), 1)

		let second = LocalStore(path: path)
		XCTAssertEqual(second.pendingCount(), 1)
		XCTAssertEqual(second.pending().first?.url, "http://localhost:8000/triage/diary")
		second.markSynced("OP-REOPEN", serverTs: 42)
		XCTAssertEqual(second.pendingCount(), 0)
	}
}
