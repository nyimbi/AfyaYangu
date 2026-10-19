package ke.go.health.afyayangu

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import org.json.JSONObject

/** One queued write as the device holds it. `key` is the idempotency key it replays under. */
data class QueuedOp(
	val opId: String,
	val dataset: String,
	val clientTs: Long,
	val method: String,
	val path: String,
	val pathValues: JSONObject,
	val params: JSONObject,
	val key: String,
	val attempt: Int,
	val retryAtMs: Long?,
	/** A `multipart/form-data` upload's file part, base64 in the row. Null for a JSON op. */
	val upload: UploadPart? = null,
	/** The route reads a form body. Persisted because a replay that forgot it would send JSON. */
	val form: Boolean = false,
)

/**
 * §ACC-003's local-first store: a real SQLite database, so §16.1's promises are ones the device can
 * keep.
 *
 * The queue used to live in `SharedPreferences` as a JSON array that was read, mutated and written
 * back whole. That is not a store. Two writes racing lost one of them; a process killed between the
 * mutation and the `apply()` lost the batch; a replay had nothing to key on but a hash of the
 * request; and a half-written op could not be rolled back, because there were no transactions to
 * roll back to. §16.1 principle 1 — "every user action is written to the local database first" —
 * and principle 5 — "every queued write survives app restart and device reboot" — both describe a
 * database, and the cache could not satisfy either.
 *
 * The payload a queued write is *about* also lands here, not only in the response cache: a symptom
 * entry made offline is the person's own record of being ill, and it should not exist solely as
 * something that will be reconstructed if a later request happens to succeed.
 */
class LocalStore(context: Context) : SQLiteOpenHelper(context, LocalStoreSchema.NAME, null, LocalStoreSchema.VERSION) {

	override fun onCreate(db: SQLiteDatabase) {
		for (statement in LocalStoreSchema.DDL) db.execSQL(statement)
	}

	override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
		// `CREATE TABLE IF NOT EXISTS` is a no-op against an existing file, so a handset upgrading
		// from the cache-only build gets the new column through the same helper the fresh install
		// gets it from. The column list is read first because SQLite has no ADD COLUMN IF NOT EXISTS.
		for (statement in LocalStoreSchema.DDL) db.execSQL(statement)
		val columns = mutableSetOf<String>()
		db.rawQuery("PRAGMA table_info(sync_ops)", null).use { c ->
			while (c.moveToNext()) columns.add(c.getString(1))
		}
		for (statement in LocalStoreSchema.migrations(columns)) db.execSQL(statement)
	}

	/** Queue a write, or replace the row for an op already queued under the same key. */
	fun enqueue(op: QueuedOp) {
		val values = ContentValues().apply {
			put("op_id", op.opId)
			put("dataset", op.dataset)
			put("client_ts", op.clientTs)
			put("payload", JSONObject().apply {
				put("method", op.method)
				put("path", op.path)
				put("path_values", op.pathValues)
				put("params", op.params)
				put("key", op.key)
				put("form", op.form)
				// A queued upload is the recording or photo itself. Dropping it here would queue an
				// op that replays without the one part the route needs, and the replay would 422
				// forever — the write lost in the direction that looks like it was kept.
				op.upload?.let { u ->
					put("upload", JSONObject().apply {
						put("filename", u.filename)
						put("mime", u.mime)
						put("base64", android.util.Base64.encodeToString(u.bytes, android.util.Base64.NO_WRAP))
					})
				}
			}.toString())
			put("attempt", op.attempt)
			put("synced", 0)
		}
		// One transaction: the row and its key commit together or not at all, which is the property
		// the JSON array could not offer.
		writableDatabase.beginTransaction()
		try {
			writableDatabase.insertWithOnConflict(
				"sync_ops", null, values, SQLiteDatabase.CONFLICT_REPLACE,
			)
			writableDatabase.setTransactionSuccessful()
		} finally {
			writableDatabase.endTransaction()
		}
	}

	/** Ops waiting for a network, oldest first. */
	fun pending(): List<QueuedOp> {
		val out = mutableListOf<QueuedOp>()
		readableDatabase.rawQuery(LocalStoreSchema.PENDING_OPS, null).use { c ->
			while (c.moveToNext()) {
				val payload = JSONObject(c.getString(3))
				out.add(
					QueuedOp(
						opId = c.getString(0),
						dataset = c.getString(1),
						clientTs = c.getLong(2),
						method = payload.optString("method", "POST"),
						path = payload.getString("path"),
						pathValues = payload.optJSONObject("path_values") ?: JSONObject(),
						params = payload.optJSONObject("params") ?: JSONObject(),
						key = payload.getString("key"),
						attempt = c.getInt(4),
						retryAtMs = if (c.isNull(5)) null else c.getLong(5),
						form = payload.optBoolean("form", false),
						upload = payload.optJSONObject("upload")?.let { u ->
							UploadPart(
								android.util.Base64.decode(u.getString("base64"), android.util.Base64.NO_WRAP),
								u.getString("filename"), u.getString("mime"),
							)
						},
					),
				)
			}
		}
		return out
	}

	fun pendingCount(): Int = readableDatabase.rawQuery(LocalStoreSchema.PENDING_COUNT, null).use { c ->
		if (c.moveToFirst()) c.getInt(0) else 0
	}

	/** The op went out and the server took it. */
	fun markSynced(opId: String, serverTs: Long) {
		writableDatabase.execSQL(LocalStoreSchema.MARK_SYNCED, arrayOf<Any?>(serverTs, opId))
	}

	/** The server refused this request; retrying it forever would block the queue behind it. */
	fun drop(opId: String) {
		writableDatabase.execSQL(LocalStoreSchema.DROP_OP, arrayOf<Any?>(opId))
	}

	/** The send failed for a reason a retry may fix. Record the attempt and when to try again. */
	fun defer(opId: String, attempt: Int, retryAtMs: Long?) {
		writableDatabase.execSQL(LocalStoreSchema.DEFER_OP, arrayOf<Any?>(attempt, retryAtMs, opId))
	}
}
