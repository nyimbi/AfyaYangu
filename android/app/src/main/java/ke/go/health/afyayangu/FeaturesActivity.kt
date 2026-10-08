package ke.go.health.afyayangu

import android.app.Activity
import android.os.Bundle
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.util.concurrent.Executors

private const val MATCH_PARENT = ViewGroup.LayoutParams.MATCH_PARENT

/** Feature surfaces: FND-001 finder, REC-001 wallet, TRI-002 diary, CHAN-005 CHW, sensor ingest. */
class FeaturesActivity : Activity() {

	private val executor = Executors.newSingleThreadExecutor()
	private lateinit var client: BackendClient

	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		client = BackendClient(this)
		setContentView(Sections.build(this, executor, client))
	}

	private object Sections {
		fun section(ctx: Activity, title: String, body: TextView): LinearLayout {
			val ll = LinearLayout(ctx).apply {
				orientation = LinearLayout.VERTICAL
				addView(TextView(ctx).apply { text = title; textSize = 16f; setPadding(8, 24, 8, 4) })
				addView(body.apply { textSize = 14f; setPadding(16, 4, 16, 12) })
			}
			return ll
		}

		fun build(ctx: Activity, executor: java.util.concurrent.ExecutorService, client: BackendClient): ScrollView {
			val finderOut = TextView(ctx).apply { text = "loading..." }
			val walletOut = TextView(ctx).apply { text = "loading..." }
			val diaryOut = TextView(ctx).apply { text = "loading..." }
			val chwOut = TextView(ctx).apply { text = "loading..." }
			val sensorOut = TextView(ctx).apply { text = "loading..." }
			val evBtn = android.widget.Button(ctx).apply {
				text = "SENS-004 Evidence submission"
				setOnClickListener { ctx.startActivity(android.content.Intent(ctx, EvidenceActivity::class.java)) }
			}
			val root = LinearLayout(ctx).apply {
				orientation = LinearLayout.VERTICAL
				addView(evBtn)
				addView(section(ctx, "FND-001 Facility Finder", finderOut))
				addView(section(ctx, "REC-001 Family Health Wallet", walletOut))
				addView(section(ctx, "TRI-002 Symptom Diary", diaryOut))
				addView(section(ctx, "CHAN-005 CHW tasks", chwOut))
				addView(section(ctx, "Sensors ingest (fall, 5.5 g demo)", sensorOut))
				takeIf { true }?.let {
					val placesBtn = android.widget.Button(ctx).apply {
						text = "Maps: pharmacies / hospitals / schools (OpenStreetMap)"
						setOnClickListener { ctx.startActivity(android.content.Intent(ctx, PlacesActivity::class.java)) }
					}
					addView(placesBtn)
				}
			}
			executor.execute {
				setOut(finderOut, runCatching { client.nearest(-1.29, 36.82, "treatment_unit", 3) }
					.recover { runCatching { client.nearest(-1.29, 36.82, "ed", 3) }.getOrThrow() })
				setOut(walletOut, runCatching { client.wallet("GUARD1") })
				setOut(diaryOut, runCatching { client.diary("U1") })
				setOut(chwOut, runCatching { client.chwTasks("CHW1") })
				setOut(sensorOut, runCatching { client.ingest("fall", 5.5, "Nairobi") })
			}
			return ScrollView(ctx).apply { addView(root) }
		}

		private fun setOut(out: TextView, result: Result<*>) {
			val text = result.fold({ it.toString() }, { "Offline — ${result.exceptionOrNull()?.message ?: "unavailable"}" })
			out.post { out.text = text }
		}
	}
}