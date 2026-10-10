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
data class ActionField(val name: String, val label: String, val type: String, val options: List<String>?, val placeholder: String?, val required: Boolean, val clientSupplied: Boolean)
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
	fun uploadEvidence(kind: String, note: String, blob: ByteArray): String {
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
			os.write("--$boundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"photo.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".toByteArray())
			os.write(blob)
			os.write("\r\n--$boundary--\r\n".toByteArray())
		}
		val code = conn.responseCode
		val text = (if (code in 200..299) conn.inputStream else conn.errorStream)?.use { it.readBytes().decodeToString() }
		if (code !in 200..299) throw IllegalStateException("upload failed: $code $text")
		return text.orEmpty()
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

	private fun queue(actionId: String, method: String, path: String, pathValues: Map<String, String>, params: JSONObject) {
		// The key is derived from the op's own content, so the same op always carries the same key
		// and a replay after a restart is recognised as a repeat rather than a second write.
		val material = "$method $path $pathValues ${params}"
		val key = "q-" + Integer.toHexString(material.hashCode())
		val entry = JSONObject()
			.put("action_id", actionId)
			.put("method", method)
			.put("path", path)
			.put("path_values", JSONObject(pathValues as Map<*, *>))
			.put("params", params)
			.put("key", key)
		val arr = JSONArray(prefs.getString("queue", "[]"))
		arr.put(entry)
		prefs.edit().putString("queue", arr.toString()).apply()
	}

	fun queuedCount(): Int = JSONArray(prefs.getString("queue", "[]")).length()

	/**
	 * Replay the queue. Stops at the first op that is still unreachable so ordering is preserved;
	 * an op the server *refuses* (4xx) is dropped rather than blocking the queue behind it forever.
	 */
	fun flushQueue(): Int {
		val arr = JSONArray(prefs.getString("queue", "[]"))
		if (arr.length() == 0) return 0
		val remaining = JSONArray()
		var sent = 0
		var stopped = false
		for (i in 0 until arr.length()) {
			val e = arr.getJSONObject(i)
			if (stopped) {
				remaining.put(e)
				continue
			}
			val pathValues = e.getJSONObject("path_values").let { pv ->
				pv.keys().asSequence().associateWith { pv.getString(it) }
			}
			try {
				perform(e.getString("method"), e.getString("path"), pathValues, e.getJSONObject("params"), e.getString("key"))
				sent++
			} catch (err: HttpError) {
				if (err.code in 400..499) continue // refused: dropping it is honest, retrying it is not
				remaining.put(e)
				stopped = true
			} catch (err: Exception) {
				remaining.put(e)
				stopped = true
			}
		}
		prefs.edit().putString("queue", remaining.toString()).apply()
		return sent
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
				)
			}
			CatalogueAction(a.getString("id"), a.getString("title"), a.getString("group"), a.getString("method"), a.getString("path"), fields)
		}
	}
}