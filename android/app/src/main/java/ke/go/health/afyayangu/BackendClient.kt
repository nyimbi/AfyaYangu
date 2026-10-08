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

// Offline-first: last good response cached in SharedPreferences (spec 16.1).
class BackendClient(private val context: Context) {

	private fun request(path: String, body: String?): String {
		val conn = URL(BASE + path).openConnection() as HttpURLConnection
		conn.connectTimeout = 8000
		conn.readTimeout = 8000
		if (body == null) {
			conn.requestMethod = "GET"
		} else {
			conn.requestMethod = "POST"
			conn.doOutput = true
			conn.setRequestProperty("content-type", "application/json")
			conn.outputStream.use { it.write(body.toByteArray()) }
		}
		return conn.inputStream.use { ins ->
			ByteArrayOutputStream().apply { ins.copyTo(this) }.toString()

		}
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

	fun features(): List<FeatureDTO> {
		val txt = cached("features") ?: JSONObject().let { throw IllegalStateException("offline and no cache") }
		val arr = JSONObject(txt).getJSONArray("features")
		return (0 until arr.length()).map { i ->
			val f = arr.getJSONObject(i)
			FeatureDTO(f.getString("id"), f.getString("name"))
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
		val txt = request("facilities/nearest?lat=$lat&lon=$lon&limit=$limit" + (kind?.let { "&kind=$it" } ?: ""), null)
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
		val body = JSONObject().put("kind", kind).put("subject_ref", "U1").put("value", value).put("county", county).toString()
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
		conn.setRequestProperty("content-type", "multipart/form-data; boundary=$boundary")
		conn.outputStream.use { os ->
			os.write(("--$boundary\r\nContent-Disposition: form-data; name=\"kind\"\r\n\r\n$kind\r\n").toByteArray())
			os.write(("--$boundary\r\nContent-Disposition: form-data; name=\"subject_ref\"\r\n\r\nU1\r\n").toByteArray())
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

	fun importOsmPlaces(lat: Double, lon: Double): String {
		val out = JSONObject(request("places/import-osm?county_lat=$lat&county_lon=$lon", null))
		return "OSM import: ${out.getInt("imported")} places (total ${out.getInt("total")})"
	}

	companion object { const val BASE = "http://localhost:8000/" }
}