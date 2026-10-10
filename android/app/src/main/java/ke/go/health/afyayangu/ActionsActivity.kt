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

	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		client = BackendClient(this)
		out = TextView(this).apply { textSize = 14f; setPadding(16, 8, 16, 24); text = "Loading actions…" }
		setContentView(ScrollView(this).apply {
			addView(LinearLayout(this@ActionsActivity).apply {
				orientation = LinearLayout.VERTICAL
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
		box.addView(TextView(this).apply { text = a.title; textSize = 16f; setPadding(16, 12, 16, 4) })
		// A client-supplied field is the device's own subject, filled by the client. It is not drawn:
		// the catalogue marks it because the route binds it to the token, so a field asking "who is
		// this for?" would offer a control the server refuses by construction. The only honest thing
		// to show is nothing.
		for (f in a.fields) if (!f.clientSupplied) box.addView(fieldView(f, inputs))
		box.addView(Button(this).apply {
			text = if (a.method == "GET") "Run" else "Submit"
			setOnClickListener { submit(a, inputs) }
		})
		(out.parent as? ViewGroup)?.removeView(out)
		box.addView(out)
		out.text = "${a.method} ${a.path}"
		setContentView(ScrollView(this).apply { addView(box) })
	}

	private fun fieldView(f: ActionField, inputs: MutableMap<String, android.view.View>): LinearLayout {
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
		// person the worker named — a contact being notified — is left alone.
		if (a.fields.any { it.clientSupplied } && !params.has("subject_ref")) params.put("subject_ref", client.subjectRef())
		executor.execute {
			val res = runCatching { client.perform(a.method, a.path, pathValues, params) }
			runOnUiThread {
				out.text = res.fold({ pretty(it) }, { "Request failed: ${it.message}" })
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
