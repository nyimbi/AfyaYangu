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

	companion object { const val BASE = "http://localhost:8000/" }
}