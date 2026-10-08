package ke.go.health.afyayangu

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.net.Uri
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject

/** OSM places (pharmacy/clinic/hospital/school/water) + turn-by-turn handoff to the maps app. */
class PlacesActivity : Activity(), LocationListener {

	private val executor = java.util.concurrent.Executors.newSingleThreadExecutor()
	private var pendingKind: String? = null
	private lateinit var out: TextView
	private lateinit var client: BackendClient

	private companion object {
		var LAST_CALLBACK: ((Location) -> Unit)? = null
		const val PERMISSION_REQ = 7
	}

	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		client = BackendClient(this)
		out = TextView(this).apply { textSize = 13f; setPadding(16, 8, 16, 24); text = "Pick a place type (uses your GPS)" }
		val kinds = LinearLayout(this).apply {
			orientation = LinearLayout.VERTICAL
			for (k in listOf("pharmacy", "hospital", "clinic", "school", "water_point")) {
				addView(Button(this@PlacesActivity).apply {
					text = "Nearest $k"
					setOnClickListener { pendingKind = k; locate() }
				})
			}
			addView(Button(this@PlacesActivity).apply {
				text = "Import OpenStreetMap places here"; setOnClickListener { pendingKind = null; locate() }
			})
		}
		setContentView(ScrollView(this).apply {
			addView(LinearLayout(this@PlacesActivity).apply {
				orientation = LinearLayout.VERTICAL
				addView(kinds)
				addView(out)
			})
		})
	}

	private fun locate() {
		if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
			requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION), PERMISSION_REQ)
			return
		}
		val lm = getSystemService(LOCATION_SERVICE) as LocationManager
		val last = runCatching { lm.getLastKnownLocation(LocationManager.GPS_PROVIDER) }
			.recover { runCatching { lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER) }.getOrNull() }.getOrNull()
		if (last != null) onLocationReady(last) else {
			runCatching { lm.requestSingleUpdate(LocationManager.GPS_PROVIDER, this, null) }
			out.text = "Locating via GPS… (allow location + be outdoors for a fix)"
		}
	}

	override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
		if (requestCode == PERMISSION_REQ && grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) locate()
		else out.text = "Location permission declined — typed coordinates only."
	}

	override fun onLocationChanged(location: Location) {
		onLocationReady(location)
	}

	private fun onLocationReady(loc: Location) {
		val kind = pendingKind
		if (kind == null) {
			out.text = "Importing OpenStreetMap places…"
			executor.execute {
				val res = runCatching { client.importOsmPlaces(loc.latitude, loc.longitude) }
				runOnUiThread { res.fold({ out.text = it }, { out.text = "Import failed: ${it.message}" }) }
			}
			return
		}
		out.text = "Nearest $kind…"
		executor.execute {
			val res = runCatching { client.nearestPlaces(loc.latitude, loc.longitude, kind) }
			runOnUiThread {
				res.fold({ rows ->
					val box = out.parent as LinearLayout
					box.removeAllViews()
					box.addView(kindButton(kind))
					if (rows.isEmpty()) box.addView(TextView(this@PlacesActivity).apply { text = "None imported yet — tap 'Import OpenStreetMap places here' first." })
					for (r in rows) box.addView(placeButton(r))
					box.addView(out)
				}, { out.text = "Offline: ${it.message}" })
			}
		}
	}

	private fun kindButton(kind: String): Button =
		Button(this).apply { text = "Nearest $kind"; setOnClickListener { pendingKind = kind; locate() } }

	private fun placeButton(r: BackendClient.PlaceRow): Button = Button(this).apply {
		text = "${r.name}\n${r.kind} · ${"%.2f".format(r.km)} km · ~${r.walkMin} min walk${if (r.hours == null) "" else "\n" + r.hours}"
		setOnClickListener { openMaps(r.lat, r.lon) }
	}

	private fun openMaps(lat: Double, lon: Double) {
		startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com/maps/dir/?api=1&destination=$lat,$lon&travelmode=walking")))
	}
}