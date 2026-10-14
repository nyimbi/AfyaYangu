package ke.go.health.afyayangu

import android.app.Activity
import android.os.Bundle
import android.text.InputType
import android.view.ViewGroup
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.ArrayAdapter
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors

private const val MATCH_PARENT = ViewGroup.LayoutParams.MATCH_PARENT

/**
 * Generic catalogue renderer. Fetches GET /mobile/actions and draws one form per action, grouped
 * by `group`, so a new backend feature needs no client code and no app release. The server already
 * withholds dormant capabilities, so nothing is filtered here.
 */
class ActionsActivity : Activity() {

	private val executor = Executors.newSingleThreadExecutor()
	private lateinit var client: BackendClient
	private lateinit var out: TextView
	private lateinit var queueNote: TextView

	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		client = BackendClient(this)
		out = TextView(this).apply { textSize = 14f; setPadding(16, 8, 16, 24); text = "Loading actions…" }
		queueNote = TextView(this).apply { textSize = 13f; setPadding(16, 4, 16, 4) }
		setContentView(ScrollView(this).apply {
			addView(LinearLayout(this@ActionsActivity).apply {
				orientation = LinearLayout.VERTICAL
				addView(queueNote)
				addView(out)
			})
		})
		load()
	}

	private fun load() = executor.execute {
		val res = runCatching { client.actions() }
		runOnUiThread {
			res.fold({ actions -> render(actions) }, { out.text = "Offline — could not load actions: ${it.message}" })
		}
	}

	private fun render(actions: List<CatalogueAction>) {
		val box = out.parent as LinearLayout
		box.removeAllViews()
		if (actions.isEmpty()) {
			box.addView(TextView(this).apply { text = "No actions are available right now."; setPadding(16, 16, 16, 16) })
			return
		}
		for ((group, groupActions) in actions.groupBy { it.group }) {
			box.addView(TextView(this).apply { text = group; textSize = 18f; setPadding(8, 24, 8, 4) })
			for (a in groupActions) box.addView(Button(this).apply {
				text = a.title
				setOnClickListener { openForm(a) }
			})
		}
	}

	private fun openForm(a: CatalogueAction) {
		val inputs = LinkedHashMap<String, android.view.View>()
		val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
		// §ACC-005's "support for low-resolution screens". The layout is chosen from the device's own
		// smallest width, in dp, so a 320dp handset gets one column and a 56dp target while a tablet
		// gets two — the same numbers the server serves for the bucket, applied where they matter.
		// `smallestScreenWidthDp` is the shorter side and is the same in portrait and landscape,
		// which is why the choice does not flip when the phone is turned.
		val smallestWidthDp = resources.configuration.smallestScreenWidthDp
		val narrow = smallestWidthDp < 600
		val minTargetPx = ((if (narrow) 56 else 64) * resources.displayMetrics.density).toInt()  // dp -> px
		box.addView(TextView(this).apply { text = a.title; textSize = 16f; setPadding(16, 12, 16, 4) })
		// A client-supplied field is the device's own subject, filled by the client. It is not drawn:
		// the catalogue marks it because the route binds it to the token, so a field asking "who is
		// this for?" would offer a control the server refuses by construction. The only honest thing
		// to show is nothing.
		// Neither a subject the client holds nor a reference the server mints is a question.
		for (f in a.fields) if (!f.clientSupplied && !f.serverAssigned) box.addView(fieldView(f, inputs, minTargetPx))
		box.addView(Button(this).apply {
			text = if (a.method == "GET") "Run" else "Submit"
			// Never below §ACC-001's 48dp floor. A small screen is where a thumb misses, so the
			// control is the last thing to shrink, not the first.
			minHeight = minTargetPx
			setOnClickListener { submit(a, inputs) }
		})
		(out.parent as? ViewGroup)?.removeView(out)
		box.addView(out)
		out.text = "${a.method} ${a.path}"
		setContentView(ScrollView(this).apply { addView(box) })
	}

	private fun fieldView(f: ActionField, inputs: MutableMap<String, android.view.View>, minTargetPx: Int): LinearLayout {
		val row = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(16, 8, 16, 0) }
		if (f.type != "bool") {
			val label = f.label + if (f.required) " *" else ""
			row.addView(TextView(this).apply { text = label; textSize = 13f })
		}
		val view: android.view.View = when (f.type) {
			"bool" -> CheckBox(this).apply { text = f.label; textSize = 15f }
			"select" -> Spinner(this).apply {
				adapter = ArrayAdapter(this@ActionsActivity, android.R.layout.simple_spinner_dropdown_item, f.options ?: emptyList())
			}
			"textarea" -> EditText(this).apply { setSingleLine(false); minLines = 3; hint = f.placeholder }
			"int" -> EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_SIGNED; hint = f.placeholder }
			"decimal" -> EditText(this).apply { inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED; hint = f.placeholder }
			else -> EditText(this).apply { inputType = InputType.TYPE_CLASS_TEXT; hint = f.placeholder }
		}
		inputs[f.name] = view
		row.addView(view, ViewGroup.LayoutParams(MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
		// `minimumHeight` and not `minHeight`: `View` carries the first and `TextView` the second, and
		// the declared type here is `View`. `Spinner` is not a `TextView` at all, so the `TextView`
		// property would not reach it — which is how this line failed to compile while the button
		// above, whose receiver is a `Button`, compiled fine.
		if (view is EditText || view is Spinner) view.minimumHeight = minTargetPx
		return row
	}

	private fun submit(a: CatalogueAction, inputs: Map<String, android.view.View>) {
		val pathValues = HashMap<String, String>()
		val params = JSONObject()
		for (f in a.fields) {
			val v = inputs[f.name] ?: continue
			val raw = when (v) {
				is CheckBox -> if (v.isChecked) "true" else ""
				is Spinner -> v.selectedItem?.toString().orEmpty()
				is EditText -> v.text.toString().trim()
				else -> ""
			}
			if (raw.isEmpty()) continue // omit empty optional fields entirely
			if (f.type == "path") pathValues[f.name] = raw
			else params.put(f.name, typed(f.type, raw))
		}
		// A client-supplied subject is the device's, whatever the transport (query, path or body).
		// `perform` overwrites it in all three; a worker action's subject is not marked, so the
		// person the worker named — a contact being notified — is left alone. Keyed on the field
		// being a subject, not on *any* field being client-supplied: a server-assigned reference
		// carries its own flag, and injecting a subject for one would name a person into a request
		// that has no subject.
		if (a.fields.any { it.clientSupplied && it.name == "subject_ref" } && !params.has("subject_ref")) params.put("subject_ref", client.subjectRef())
		executor.execute {
			// §16.1: a write with no network is queued, not lost. `performOrQueue` keeps it and
			// replays it on the next successful submit or resume.
			val res = runCatching { client.performOrQueue(a.id, a.method, a.path, pathValues, params) }
			runOnUiThread {
				out.text = res.fold({ pretty(it) }, { "Request failed: ${it.message}" })
				refreshQueueNote()
			}
		}
	}

	/** §16.1: how many writes are waiting for a network, shown so a user knows nothing was lost. */
	private fun refreshQueueNote() {
		val n = client.queuedCount()
		queueNote.text = if (n == 0) "" else "$n change(s) saved on this phone, waiting to send"
	}

	/** Replay anything queued when the screen comes back, since that is when a network often does. */
	override fun onResume() {
		super.onResume()
		executor.execute {
			val sent = runCatching { client.flushQueue() }.getOrDefault(0)
			runOnUiThread {
				if (sent > 0) out.text = "Sent $sent saved change(s)."
				refreshQueueNote()
			}
		}
	}

	private fun typed(type: String, raw: String): Any = when (type) {
		"bool" -> raw.toBoolean()
		"int" -> raw.toLongOrNull() ?: raw
		"decimal" -> raw.toDoubleOrNull() ?: raw
		"list" -> JSONArray(raw.split(",").map { it.trim() }.filter { it.isNotEmpty() })
		else -> raw
	}

	private fun pretty(txt: String): String = runCatching {
		val t = txt.trim()
		if (t.startsWith("{")) JSONObject(t).toString(2)
		else if (t.startsWith("[")) JSONArray(t).toString(2)
		else t
	}.getOrDefault(txt)
}
