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
				text = "Show a nurse your concern"
				setOnClickListener { ctx.startActivity(android.content.Intent(ctx, EvidenceActivity::class.java)) }
			}
			val root = LinearLayout(ctx).apply {
				orientation = LinearLayout.VERTICAL
				addView(evBtn)
				addView(section(ctx, "Find care near me", finderOut))
				addView(section(ctx, "Family health wallet", walletOut))
				addView(section(ctx, "My 21-day diary", diaryOut))
				addView(section(ctx, "Community health worker tasks", chwOut))
				addView(section(ctx, "Motion check-in", sensorOut))
				takeIf { true }?.let {
					val placesBtn = android.widget.Button(ctx).apply {
						text = "Maps & directions (OpenStreetMap)"
						setOnClickListener { ctx.startActivity(android.content.Intent(ctx, PlacesActivity::class.java)) }
					}
					addView(placesBtn)
				}
				addView(android.widget.Button(ctx).apply {
					text = "All services"
					setOnClickListener { ctx.startActivity(android.content.Intent(ctx, ActionsActivity::class.java)) }
				})
			}
			executor.execute {
				setOut(finderOut, runCatching { client.nearest(-1.29, 36.82, "ed", 3) }.recoverCatching { client.nearest(-1.29, 36.82, "pharmacy", 3) })
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