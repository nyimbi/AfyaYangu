package ke.go.health.afyayangu

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL

data class HealthDTO(val status: String, val version: String, val tier4: Boolean)
data class FeatureDTO(val id: String, val name: String)
data class TriageResultDTO(val riskLevel: String, val recommendation: String, val escalate719: Boolean)
data class ActionField(val name: String, val label: String, val type: String, val options: List<String>?, val placeholder: String?, val required: Boolean, val clientSupplied: Boolean, val serverAssigned: Boolean)
data class CatalogueAction(val id: String, val title: String, val group: String, val method: String, val path: String, val fields: List<ActionField>)

// Offline-first: last good response cached in SharedPreferences (spec 16.1).
class BackendClient(private val context: Context) {

	/**
	 * The citizen's session: an anonymous bearer token and the subject it was issued for.
	 *
	 * The personal-data routes bind the subject they name to the token that named it (§17), so a
	 * client that presents no token gets a 401 and a client that names a subject other than its
	 * own gets a 403. The subject is therefore the *device's*, obtained once and reused — never
	 * whatever a form field happens to contain.
	 */
	private val prefs get() = context.getSharedPreferences("afya", Context.MODE_PRIVATE)

	/**
	 * §ACC-003's local-first store. The session credentials and the response cache stay in
	 * `SharedPreferences` — a token and a last-good response are a cache, and calling them a database
	 * would be the same overstatement in the other direction. What moves here is the *queue*, because
	 * §16.1 principles 1 and 5 are promises about durability, and a cache cannot keep them.
	 */
	private val store = LocalStore(context.applicationContext)

	@Volatile private var token: String? = null
	@Volatile private var subject: String? = null

	fun subjectRef(): String = subject ?: prefs.getString("session.subject", null) ?: ensureSession().first

	/** Returns (subject, token), obtaining one if the device has none or the token expired. */
	private fun ensureSession(): Pair<String, String> {
		subject?.let { s -> token?.let { t -> return s to t } }
		val known = prefs.getString("session.subject", null)
		val body = if (known == null) "{}" else JSONObject().put("subject_ref", known).toString()
		val out = JSONObject(request("auth/anonymous", body, authorize = false))
		val s = out.getString("subject_ref")
		val t = out.getString("token")
		subject = s
		token = t
		prefs.edit().putString("session.subject", s).putString("session.token", t).apply()
		return s to t
	}

	/** A non-2xx response, carrying the code so a caller can tell "refused" from "try again later". */
	class HttpError(val code: Int, val body: String) : Exception("HTTP $code")

	private fun request(
		path: String,
		body: String?,
		authorize: Boolean = true,
		method: String? = null,
		idempotencyKey: String? = null,
	): String {
		val conn = URL(BASE + path).openConnection() as HttpURLConnection
		conn.connectTimeout = 8000
		conn.readTimeout = 8000
		if (authorize) conn.setRequestProperty("authorization", "Bearer ${ensureSession().second}")
		// The server replays the first response for a repeated key whose body is byte-identical
		// (§15.5), which is what makes replaying a queued write safe: the retry cannot double-write.
		idempotencyKey?.let { conn.setRequestProperty("idempotency-key", it) }
		// The verb is explicit when given. Inferring it from a non-null body is what sent every
		// DELETE as a POST, since the caller had to pass *something* to avoid a GET.
		val verb = method ?: if (body == null) "GET" else "POST"
		conn.requestMethod = verb
		if (body != null && verb != "GET") {
			conn.doOutput = true
			conn.setRequestProperty("content-type", "application/json")
			conn.outputStream.use { it.write(body.toByteArray()) }
		}
		val code = conn.responseCode
		val stream = if (code in 200..299) conn.inputStream else conn.errorStream
		val text = stream?.use { ins -> ByteArrayOutputStream().apply { ins.copyTo(this) }.toString() } ?: ""
		if (code !in 200..299) throw HttpError(code, text)
		return text
	}

	/** Whether the backend is reachable right now. A short probe, so a submit does not hang. */
	fun online(): Boolean = try {
		val conn = URL(BASE + "health").openConnection() as HttpURLConnection
		conn.connectTimeout = 1500
		conn.readTimeout = 1500
		conn.responseCode in 200..299
	} catch (e: Exception) {
		false
	}

	private fun cached(key: String): String? =
		context.getSharedPreferences("afya", Context.MODE_PRIVATE).getString("cache.$key", null)

	private fun send(key: String, body: String?): JSONObject? = try {
		val txt = request(key, body)
		val obj = JSONObject(txt)
		context.getSharedPreferences("afya", Context.MODE_PRIVATE).edit().putString("cache.$key", txt).apply()
		obj
	} catch (e: Exception) {
		cached(key)?.let { JSONObject(it) }
	}

	fun health(): HealthDTO {
		val h = send("health", null)
		if (h == null) throw IllegalStateException("offline and no cache")
		return HealthDTO(h.getString("status"), h.getString("version"), h.getBoolean("tier4"))
	}

	/**
	 * What the app can do, in plain language.
	 *
	 * This reads `/mobile/features`, whose ids are slugs. `/features` is the ops registry and its id
	 * is the spec code (`CHAN-000`); reading it here is what put those codes on screen.
	 */
	fun features(): List<FeatureDTO> {
		val arr = JSONArray(request("mobile/features", null))
		return (0 until arr.length()).map { i ->
			val f = arr.getJSONObject(i)
			FeatureDTO(f.getString("id"), f.getString("title"))
		}
	}

	fun triagePreliminary(symptoms: List<String>, temperatureC: Double, ebolaContact: Boolean): TriageResultDTO? {
		val body = JSONObject().apply {
			put("symptoms", JSONArray(symptoms))
			put("temperature_c", temperatureC)
			put("ebola_contact", ebolaContact)
		}.toString()
		val r = send("triage/preliminary", body) ?: return null
		return TriageResultDTO(r.getString("risk_level"), r.getString("recommendation"), r.getBoolean("escalate_719"))
	}

	fun saveEmergencyCard(card: String) =
		context.getSharedPreferences("afya", Context.MODE_PRIVATE).edit().putString("emergency.card", card).apply()

	fun emergencyCard(): String =
		context.getSharedPreferences("afya", Context.MODE_PRIVATE).getString("emergency.card", "AFYA|set name|blood group|contact")!!


	// --- Tier-1/2 feature surfaces (FND-001, REC-001, TRI-002, CHAN-005, sensors) ---

	fun nearest(lat: Double, lon: Double, kind: String?, limit: Int = 3): String {
		val body = JSONObject().put("lat", lat).put("lon", lon).apply { kind?.let { put("kind", it) } }.put("limit", limit)
		val txt = request("facilities/nearest", body.toString())
		val arr = JSONArray(txt)
		val out = StringBuilder()
		for (i in 0 until arr.length()) {
			val row = arr.getJSONObject(i)
			val f = row.getJSONObject("facility")
			out.append(f.getString("name")).append(" | ").append(f.getString("county"))
				.append(" (").append(row.getDouble("km")).append(" km)\n")
		}
		return out.toString()
	}

	fun wallet(guardianRef: String): String {
		val w = JSONObject(request("records/$guardianRef/wallet", null))
		val sb = StringBuilder("Guardian: ").append(w.getJSONObject("guardian").getString("member_ref")).append('\n')
		val members = w.getJSONArray("members")
		for (i in 0 until members.length()) sb.append("* ").append(members.getJSONObject(i).getString("member_ref")).append('\n')
		val gaps = w.getJSONObject("gaps")
		val idx = gaps.keys()
		while (idx.hasNext()) {
			val k = idx.next()
			sb.append(k).append(": ").append(gaps.getJSONArray(k).join(", ")).append('\n')
		}
		return sb.toString()
	}

	fun diary(subjectRef: String): String {
		val arr = JSONArray(request("triage/$subjectRef/diary", null))
		val sb = StringBuilder()
		for (i in 0 until arr.length()) {
			val e = arr.getJSONObject(i)
			sb.append("Day ").append(e.getInt("day")).append(" - ").append(e.getJSONArray("symptoms").join(", "))
				.append(if (e.getBoolean("synced")) " synced" else " pending").append('\n')
		}
		return sb.ifEmpty { "No diary entries yet." }.toString()
	}

	fun chwTasks(chwRef: String): String {
		val arr = JSONArray(request("channels/chw/tasks/$chwRef", null))
		val sb = StringBuilder()
		for (i in 0 until arr.length()) {
			val t = arr.getJSONObject(i)
			sb.append(t.getString("task_id")).append(" | ").append(t.getString("kind")).append(" | ").append(t.getString("community")).append('\n')
		}
		return sb.ifEmpty { "No open tasks." }.toString()
	}

	fun completeTask(taskId: String): Boolean {
		request("channels/chw/tasks/$taskId/done", "{}")
		return true
	}

	fun ingest(kind: String, value: Double, county: String): String {
		val body = JSONObject().put("kind", kind).put("subject_ref", subjectRef()).put("value", value).put("county", county).toString()
		val v = JSONObject(request("sensors/ingest", body))
		return v.getString("band") + ": " + v.getString("detail")
	}
	fun uploadEvidence(kind: String, note: String, blob: ByteArray, consent: Boolean): String {
		val boundary = "afya-" + System.currentTimeMillis()
		val conn = URL(BASE + "evidence").openConnection() as HttpURLConnection
		conn.requestMethod = "POST"
		conn.doOutput = true
		conn.connectTimeout = 10000
		conn.readTimeout = 15000
		conn.setRequestProperty("authorization", "Bearer ${ensureSession().second}")
		conn.setRequestProperty("content-type", "multipart/form-data; boundary=$boundary")
		conn.outputStream.use { os ->
			os.write(("--$boundary\r\nContent-Disposition: form-data; name=\"kind\"\r\n\r\n$kind\r\n").toByteArray())
			os.write(("--$boundary\r\nContent-Disposition: form-data; name=\"subject_ref\"\r\n\r\n${subjectRef()}\r\n").toByteArray())
			os.write(("--$boundary\r\nContent-Disposition: form-data; name=\"county\"\r\n\r\nNairobi\r\n").toByteArray())
			os.write(("--$boundary\r\nContent-Disposition: form-data; name=\"note\"\r\n\r\n$note\r\n").toByteArray())
			// §SEC-002's per-item consent. The server refuses the photo without it, so a client
			// that left this out would draw a button that always fails.
			os.write(("--$boundary\r\nContent-Disposition: form-data; name=\"consent\"\r\n\r\n$consent\r\n").toByteArray())
			os.write("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"photo.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".toByteArray())
			os.write(blob)
			os.write("\r\n--$boundary--\r\n".toByteArray())
		}
		val code = conn.responseCode
		val text = (if (code in 200..299) conn.inputStream else conn.errorStream)?.use { it.readBytes().decodeToString() }
		if (code !in 200..299) throw IllegalStateException("upload failed: $code $text")
		return text.orEmpty()
	}

	/**
	 * §16.4's resumable upload: send a photo in chunks so a dropped connection costs one chunk
	 * rather than the whole picture.
	 *
	 * Chunks are addressed by byte offset and not by index, so the resume is a question rather than
	 * a guess: the client asks the server what it holds and continues from the answer. That is why
	 * this can be called again after a failure with no state carried in — the position comes back
	 * from the server each time, which is the only thing that survives a process restart.
	 *
	 * Returns the server's receipt as the single-shot path does, so a caller cannot tell which
	 * transport was used, and neither can the controls: the assembled bytes go through the same
	 * consent, seal and store on the server.
	 */
	fun uploadEvidenceResumable(
		kind: String,
		note: String,
		blob: ByteArray,
		consent: Boolean,
		chunkBytes: Int = 512 * 1024,
	): String {
		val digest = java.security.MessageDigest.getInstance("SHA-256")
		val sha = digest.digest(blob).joinToString("") { "%02x".format(it) }
		val opened = JSONObject(
			request(
				"evidence/upload",
				JSONObject()
					.put("kind", kind)
					.put("subject_ref", subjectRef())
					.put("county", "Nairobi")
					.put("note", note)
					.put("consent", consent)
					.put("declared_bytes", blob.size)
					.put("image_sha256", sha)
					.put("mime", "image/jpeg")
					.put("chunk_bytes", chunkBytes)
					.toString(),
			),
		)
		val sessionId = opened.getString("session_id")
		var offset = opened.getInt("next_offset")
		val encoder = android.util.Base64.URL_SAFE or android.util.Base64.NO_PADDING or android.util.Base64.NO_WRAP
		while (offset < blob.size) {
			val end = minOf(offset + chunkBytes, blob.size)
			val chunk = blob.copyOfRange(offset, end)
			val chunkSha = java.security.MessageDigest.getInstance("SHA-256")
				.digest(chunk).joinToString("") { "%02x".format(it) }
			val out = JSONObject(
				request(
					"evidence/upload/$sessionId/chunk",
					JSONObject()
						.put("offset", offset)
						.put("chunk_sha256", chunkSha)
						.put("data", android.util.Base64.encodeToString(chunk, encoder))
						.toString(),
				),
			)
			// The server's answer is the position, not the client's arithmetic. A retry after an
			// unacknowledged chunk comes back with the offset it already holds, and reading it here
			// is what makes the loop safe to re-enter rather than something that must be tracked.
			offset = out.getInt("next_offset")
		}
		return request("evidence/upload/$sessionId/finish", "{}")
	}
	data class PlaceRow(val name: String, val kind: String, val lat: Double, val lon: Double, val km: Double, val walkMin: Int, val guidance: String, val hours: String?)

	fun nearestPlaces(lat: Double, lon: Double, kind: String, limit: Int = 5): List<PlaceRow> {
		val arr = JSONArray(request("places/nearest?lat=$lat&lon=$lon&kinds=$kind&limit=$limit", null))
		return (0 until arr.length()).map { i ->
			val row = arr.getJSONObject(i)
			val p = row.getJSONObject("place")
			val d = row.getJSONObject("directions")
			PlaceRow(
				p.getString("name"), p.getString("kind"), p.getDouble("lat"), p.getDouble("lon"),
				row.getDouble("km"), d.getInt("walk_minutes"), d.getString("guidance"),
				p.optString("opening_hours", null),
			)
		}
	}

	// --- Server-driven action catalogue (GET /mobile/actions) ---
	// The server withholds dormant outbreak capabilities, so the list is rendered as-is.

	fun actions(): List<CatalogueAction> = parseActions(JSONArray(request("mobile/actions", null)))

	/** Calls one catalogue action. `pathValues` fills {placeholders}; `params` carries the rest. */
	fun perform(method: String, path: String, pathValues: Map<String, String>, params: JSONObject, idempotencyKey: String? = null): String {
		// The subject is the device's, not a form field: a personal-data route binds the subject it
		// is given to the token, so anything else is a 403 by construction. Overwriting whatever the
		// form collected is what keeps the client unable to name a stranger.
		val mine = subjectRef()
		val filled = HashMap(pathValues)
		if (path.contains("{subject_ref}")) filled["subject_ref"] = mine
		// Overwrite unconditionally: the caller has already decided this action takes a subject, so
		// whatever the form held must not survive.
		if (params.has("subject_ref") || path.contains("{subject_ref}") || pathValues.containsKey("subject_ref")) {
			params.put("subject_ref", mine)
		}
		var resolved = path
		for ((k, v) in filled) resolved = resolved.replace("{$k}", v)
		return when (method) {
			"GET" -> {
				val q = params.keys().asSequence().joinToString("&") { k ->
					"${java.net.URLEncoder.encode(k, "UTF-8")}=${java.net.URLEncoder.encode(params.get(k).toString(), "UTF-8")}"
				}
				request(resolved + if (q.isEmpty()) "" else "?$q", null)
			}
			"DELETE" -> request(resolved, null, method = "DELETE", idempotencyKey = idempotencyKey)
			else -> request(resolved, params.toString(), method = "POST", idempotencyKey = idempotencyKey)
		}
	}

	// --- §16.1 offline queue: a write made with no network is kept, not lost -----------------

	/**
	 * Perform a write, or queue it if the network is down.
	 *
	 * §16.1 promises the client works offline; a write that threw while offline was simply lost,
	 * which is the promise broken in the direction that looks like it works. A queued op carries an
	 * idempotency key derived from its content, so replaying it after a restart cannot double-write:
	 * the server returns the first response for a repeated key with an identical body (§15.5).
	 */
	fun performOrQueue(actionId: String, method: String, path: String, pathValues: Map<String, String>, params: JSONObject): String {
		if (method == "GET") return perform(method, path, pathValues, params)
		if (!online()) {
			queue(actionId, method, path, pathValues, params)
			return "{\"queued\":true}"
		}
		return try {
			perform(method, path, pathValues, params)
		} catch (e: HttpError) {
			// A 5xx is the server failing, which a retry may fix; a 4xx is the server refusing this
			// request, which a retry will not. Only the first is queued.
			if (e.code in 500..599) {
				queue(actionId, method, path, pathValues, params)
				return "{\"queued\":true}"
			}
			throw e
		}
	}

	/**
	 * §ACC-003: the queued write goes into the device's own database, in one transaction.
	 *
	 * This was a JSON array in `SharedPreferences`, read whole, mutated and written back whole. Two
	 * writes racing lost one; a process killed between the mutation and the `apply()` lost the batch;
	 * and nothing could be rolled back, because there was no transaction to roll back to. A queue
	 * that can lose the entry it exists to keep is not §16.1's queue.
	 */
	private fun queue(actionId: String, method: String, path: String, pathValues: Map<String, String>, params: JSONObject) {
		// The key is derived from the op's own content, so the same op always carries the same key
		// and a replay after a restart is recognised as a repeat rather than a second write. It is
		// also the row's primary key, which is what makes the deduplication a constraint rather than
		// a convention.
		val material = "$method $path $pathValues ${params}"
		val key = "OP-" + Integer.toHexString(material.hashCode()).uppercase()
		store.enqueue(
			QueuedOp(
				opId = key,
				dataset = actionId,
				clientTs = System.currentTimeMillis(),
				method = method,
				path = path,
				pathValues = JSONObject(pathValues as Map<*, *>),
				params = params,
				key = key,
				attempt = 0,
				retryAtMs = null,
			),
		)
	}

	fun queuedCount(): Int = store.pendingCount()

	/**
	 * Replay the queue. Stops at the first op that is still unreachable so ordering is preserved;
	 * an op the server *refuses* (4xx) is dropped rather than blocking the queue behind it forever,
	 * and an op that failed for a reason a retry may fix is deferred to its backoff window rather
	 * than re-sent on every resume.
	 */
	fun flushQueue(): Int {
		val ops = store.pending()
		var sent = 0
		for (op in ops) {
			val now = System.currentTimeMillis()
			op.retryAtMs?.let { if (now < it) return sent }  // inside its backoff window: nothing after it is due either
			val pathValues = op.pathValues.keys().asSequence().associateWith { op.pathValues.getString(it) }
			try {
				perform(op.method, op.path, pathValues, op.params, op.key)
				store.markSynced(op.opId, now)
				sent++
			} catch (err: HttpError) {
				if (err.code in 400..499) {
					store.drop(op.opId)  // refused: dropping it is honest, retrying it is not
					continue
				}
				// §16.2's "retry with exponential backoff". The delay is the server's own function
				// (`afya.sync.service:backoff_delay_s`), reproduced here because the device is the
				// side that has to wait: 2^attempt seconds, capped, so a failing server is not hit
				// once per resume forever.
				val attempt = op.attempt + 1
				store.defer(op.opId, attempt, now + backoffDelayMs(attempt))
				return sent  // ordering holds: the queue stops at the first op that did not go
			} catch (err: Exception) {
				val attempt = op.attempt + 1
				store.defer(op.opId, attempt, now + backoffDelayMs(attempt))
				return sent
			}
		}
		return sent
	}

	private fun backoffDelayMs(attempt: Int): Long {
		val seconds = (1L shl attempt.coerceIn(0, 10)).coerceAtMost(600L)
		return seconds * 1000L
	}

	fun importOsmPlaces(lat: Double, lon: Double): String {
		val out = JSONObject(request("places/import-osm?county_lat=$lat&county_lon=$lon", null))
		return "OSM import: ${out.getInt("imported")} places (total ${out.getInt("total")})"
	}

	companion object {
		const val BASE = "http://localhost:8000/"

		/** Catalogue JSON -> models. Pure, so the parse can be tested without a device or network. */
		fun parseActions(arr: JSONArray): List<CatalogueAction> = (0 until arr.length()).map { i ->
			val a = arr.getJSONObject(i)
			val fArr = a.optJSONArray("fields") ?: JSONArray()
			val fields = (0 until fArr.length()).map { j ->
				val f = fArr.getJSONObject(j)
				// A JSON null must stay null. Android's `optString` coerces one to the literal
				// string "null" (desktop org.json returns ""), and either would render as a hint.
				// Both are rejected here so the parse is correct whichever implementation is
				// underneath, and so the rule can be tested off-device.
				val ph = if (f.isNull("placeholder")) null else f.optString("placeholder").takeIf { it.isNotEmpty() && it != "null" }
				ActionField(
					f.getString("name"), f.getString("label"), f.getString("type"),
					f.optJSONArray("options")?.let { o -> (0 until o.length()).map { o.getString(it) } },
					ph,
					f.optBoolean("required", false),
					f.optBoolean("client_supplied", false),
					f.optBoolean("server_assigned", false),
				)
			}
			CatalogueAction(a.getString("id"), a.getString("title"), a.getString("group"), a.getString("method"), a.getString("path"), fields)
		}
	}
}