package ke.go.health.afyayangu

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView
import java.util.concurrent.Executors

private const val MATCH_PARENT = ViewGroup.LayoutParams.MATCH_PARENT

class MainActivity : Activity() {

	private val executor = Executors.newSingleThreadExecutor()
	private lateinit var client: BackendClient
	private lateinit var statusText: TextView
	private lateinit var resultText: TextView
	private var ebolaContact = false

	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		client = BackendClient(this)
		setContentView(buildUi())
		refresh()
	}

	private fun buildUi(): View {
		val ctx = this
		statusText = TextView(ctx).apply { textSize = 16f; setPadding(16, 24, 16, 8) }
		resultText = TextView(ctx).apply { textSize = 14f; setPadding(16, 8, 16, 24) }
		val contactSwitch = Switch(ctx).apply {
			text = "Contact with an Ebola patient or affected area?"
			setPadding(16, 8, 16, 8)
			setOnCheckedChangeListener { _, v -> ebolaContact = v }
		}
		val chips = LinearLayout(ctx).apply {
			orientation = LinearLayout.HORIZONTAL
			for (t in listOf(37.5, 38.3, 38.9)) {
				addView(Button(ctx).apply {
					text = "$t °C"
					setOnClickListener { assess(t) }
				})
			}
		}
		val sos = Button(ctx).apply { text = "Call 719 now (free, 24/7)" }
		val features = Button(ctx).apply { text = "Features" ; setOnClickListener { startActivity(android.content.Intent(ctx, FeaturesActivity::class.java)) } }
		val allActions = Button(ctx).apply { text = "All services" ; setOnClickListener { startActivity(android.content.Intent(ctx, ActionsActivity::class.java)) } }
		val root = LinearLayout(ctx).apply {
			orientation = LinearLayout.VERTICAL
			addView(statusText)
			addView(contactSwitch)
			addView(chips, ViewGroup.LayoutParams(MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT))
			addView(resultText)
			addView(sos)
			addView(features)
			addView(allActions)
			setGravity(Gravity.TOP)
		}
		return ScrollView(ctx).apply { addView(root) }
	}

	private fun refresh() = executor.execute {
		val h = runCatching { client.health() }
		val features = runCatching { client.features() }
		runOnUiThread {
			h.fold({
				statusText.text = "backend ${it.version} · tier4 ${if (it.tier4) "active" else "dormant"}"
			}, {
				statusText.text = "Offline — cached state shown"
			})
			features.fold({ list ->
				resultText.text = "Active features (${list.size}): " + list.joinToString { it.id }
			}, {})
		}
	}

	private fun assess(tempC: Double) = executor.execute {
		val r = runCatching { client.triagePreliminary(listOf("fever", "headache"), tempC, ebolaContact) }
		runOnUiThread {
			r.fold({ triage ->
				triage?.let {
					resultText.text = "${it.riskLevel}: ${it.recommendation}"
				} ?: run { resultText.text = "Offline — try again when connected" }
			}, {
				resultText.text = "Offline — try again when connected"
			})
		}
	}
}