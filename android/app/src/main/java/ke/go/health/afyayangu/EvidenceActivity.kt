package ke.go.health.afyayangu

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.io.ByteArrayOutputStream

private const val MATCH_PARENT = ViewGroup.LayoutParams.MATCH_PARENT

/** SENS-004 photo + textual evidence submission. */
class EvidenceActivity : Activity() {

	private val client = lazy { BackendClient(this) }
	private lateinit var out: TextView
	private var pending: ByteArray? = null

	override fun onCreate(savedInstanceState: Bundle?) {
		super.onCreate(savedInstanceState)
		out = TextView(this).apply { textSize = 14f; setPadding(16, 8, 16, 8) }
		val note = EditText(this).apply { hint = "What did you observe?"; setSingleLine(false); minLines = 2 }
		val kinds = arrayOf("rash", "red_eye", "pallor", "scene_photo")
		val kindBtn = Button(this).apply {
			var idx = 0; text = "Type: ${kinds[0]}"
			setOnClickListener { idx = (idx + 1) % kinds.size; text = "Type: ${kinds[idx]}" }
		}
		val pick = Button(this).apply {
			text = "Attach photo"
			setOnClickListener {
				val intent = Intent(Intent.ACTION_GET_CONTENT).apply { type = "image/*"; addCategory(Intent.CATEGORY_OPENABLE) }
				startActivityForResult(Intent.createChooser(intent, "Select evidence photo"), 42)
			}
		}
		val submit = Button(this).apply {
			text = "Submit photo + note"
			setOnClickListener {
				val data = pending ?: run { out.text = "Attach a photo first"; return@setOnClickListener }
				Thread {
					val res = runCatching { client.value.uploadEvidence(kinds[0].let { kindBtn.text.toString().removePrefix("Type: ") }, note.text.toString(), data) }
					post { out.text = res.fold({ "Stored ✓ $it" }, { "Rejected: ${it.message}" }) }
				}.start()
			}
		}
		setContentView(ScrollView(this).apply {
			addView(LinearLayout(this@EvidenceActivity).apply {
				orientation = LinearLayout.VERTICAL
				addView(kindBtn)
				addView(note)
				addView(pick)
				addView(submit)
				addView(out)
			})
		})
	}

	override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
		super.onActivityResult(requestCode, resultCode, data)
		if (requestCode != 42 || resultCode != RESULT_OK || data?.data == null) return
		val uri: Uri = data.data!!
		contentResolver.openInputStream(uri)?.use { ins ->
			pending = ins.readBytes()
			out.text = "Photo attached (${pending?.size ?: 0} bytes)"
		} ?: run { out.text = "Could not read photo" }
	}
}