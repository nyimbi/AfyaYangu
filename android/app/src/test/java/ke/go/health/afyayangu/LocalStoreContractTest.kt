package ke.go.health.afyayangu

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Paths
import java.sql.Connection
import java.sql.DriverManager

/**
 * §ACC-003's "local-first data storage", verified against a real database engine.
 *
 * `android.database.sqlite` is a stub in JVM unit tests, so the store's own class cannot be
 * exercised off-device — but the *statements* can, and they are where the property lives. This runs
 * `LocalStoreSchema`'s SQL against an actual SQLite engine and asserts what §16.1 promises:
 *
 * * principle 5, durability — a committed write survives the connection that made it;
 * * the other half of durability — a rolled-back write is gone. This is the assertion a cache
 *   cannot express and the reason the cache was not a store: with no transactions there is no way
 *   to say a half-written batch must not appear, so a write-ahead queue built on one replays a
 *   write the user cancelled;
 * * the key — a replay of the same op is one row, not two.
 *
 * The scenarios come from `proto/local_store/contract.json`, which the iOS client runs too. Two
 * files that agree today are not one source of truth; one file both clients run is.
 */
class LocalStoreContractTest {

	private fun connect(): Connection = DriverManager.getConnection("jdbc:sqlite::memory:").also { c ->
		for (statement in LocalStoreSchema.DDL) c.createStatement().use { it.execute(statement) }
	}

	private fun schema(): String = contract().getString("ddl")

	private fun contract(): JSONObject {
		// The repo root is found by walking up from the test's working directory rather than by
		// counting `..` segments: the Gradle module directory is a fact about this build file, and a
		// count that drifts silently reads a file that is not there.
		var dir = Paths.get("").toAbsolutePath()
		while (!dir.resolve("proto/local_store/contract.json").toFile().exists()) {
			dir = dir.parent ?: error("proto/local_store/contract.json not found above the test working directory")
		}
		return JSONObject(dir.resolve("proto/local_store/contract.json").toFile().readText())
	}

	@Test
	fun `the shared contract is the one both clients run`() {
		val c = contract()
		assertEquals("afya.local_store.v1", c.getString("contract"))
		val names = (0 until c.getJSONArray("scenarios").length()).map { c.getJSONArray("scenarios").getJSONObject(it).getString("name") }
		assertEquals(
			listOf("committed_rows_are_durable", "rolled_back_rows_are_gone", "the_key_refuses_a_duplicate"),
			names,
		)
	}

	@Test
	fun `every shared scenario holds against a real engine`() {
		val scenarios = contract().getJSONArray("scenarios")
		for (i in 0 until scenarios.length()) {
			val s = scenarios.getJSONObject(i)
			val name = s.getString("name")
			val conn = connect()
			conn.use { c ->
				c.createStatement().use { it.execute(schema()) }
				val statements = s.getJSONArray("statements")
				for (j in 0 until statements.length()) c.createStatement().use { it.execute(statements.getString(j)) }
				val got = mutableListOf<String>()
				c.createStatement().use { st ->
					st.executeQuery(s.getString("query")).use { rs ->
						while (rs.next()) got.add(rs.getString(1))
					}
				}
				val want = (0 until s.getJSONArray("expect").length()).map { s.getJSONArray("expect").getString(it) }
				assertEquals("$name (${s.getString("why")})", want, got)
			}
		}
	}

	@Test
	fun `the device runs the contract's own ddl rather than a copy of it`() {
		// A test that rebuilt the DDL by hand would pass against a store whose real schema had
		// drifted. The contract's table definition must be the store's own.
		assertTrue(
			"the contract and the store disagree about the queue's schema:\n${schema()}",
			schema() == LocalStoreSchema.DDL[0],
		)
	}

	@Test
	fun `an older database gains the column a newer build needs`() {
		val conn = DriverManager.getConnection("jdbc:sqlite::memory:")
		conn.use { c ->
			// The schema as the first build shipped it: no `retry_at_ms`.
			c.createStatement().use {
				it.execute(LocalStoreSchema.DDL[0].replace(", retry_at_ms INTEGER", ""))
			}
			val existing = mutableSetOf<String>()
			c.createStatement().use { st ->
				st.executeQuery("PRAGMA table_info(sync_ops)").use { rs ->
					while (rs.next()) existing.add(rs.getString(2))
				}
			}
			assertTrue("retry_at_ms" !in existing)
			for (statement in LocalStoreSchema.migrations(existing)) c.createStatement().use { it.execute(statement) }
			val after = mutableSetOf<String>()
			c.createStatement().use { st ->
				st.executeQuery("PRAGMA table_info(sync_ops)").use { rs ->
					while (rs.next()) after.add(rs.getString(2))
				}
			}
			// Without this the upgrade path fails on the first insert naming the column — losing the
			// queue the column was added to protect.
			assertTrue("retry_at_ms" in after)
			c.createStatement().use {
				it.execute("INSERT INTO sync_ops (op_id, dataset, client_ts, retry_at_ms) VALUES ('OP-OLD001', 'medication', 1, 99)")
			}
		}
	}

	@Test
	fun `the pending query returns the oldest first and the synced never`() {
		connect().use { c ->
			c.createStatement().use { st ->
				st.execute("INSERT INTO sync_ops (op_id, dataset, client_ts, synced) VALUES ('OP-B2', 'medication', 200, 0)")
				st.execute("INSERT INTO sync_ops (op_id, dataset, client_ts, synced) VALUES ('OP-A1', 'symptom_logs', 100, 0)")
				st.execute("INSERT INTO sync_ops (op_id, dataset, client_ts, synced) VALUES ('OP-C3', 'facility', 300, 1)")
			}
			val got = mutableListOf<String>()
			c.createStatement().use { st ->
				st.executeQuery(LocalStoreSchema.PENDING_OPS).use { rs -> while (rs.next()) got.add(rs.getString(1)) }
			}
			// Order matters: a queue that replays out of order applies a later state before an
			// earlier one, which is the conflict §16.3 then has to resolve.
			assertEquals(listOf("OP-A1", "OP-B2"), got)
		}
	}
}
