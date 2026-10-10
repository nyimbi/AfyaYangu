package ke.go.health.afyayangu

import org.json.JSONArray
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The catalogue parse, tested off-device.
 *
 * The bug this guards: `JSONObject.optString` returns the four-character string "null" for a JSON
 * null, so a field with no placeholder rendered a literal `null` in the form. It reached a real
 * emulator before anyone noticed, because the parse had no test.
 */
class CatalogueParseTest {

	private val payload = """
		[{"id":"febrile_triage","title":"Check a fever","group":"Triage","method":"POST",
		  "path":"/triage/preliminary",
		  "fields":[
		    {"name":"symptoms","label":"Symptoms","type":"list","options":null,
		     "placeholder":"fever, headache","required":false},
		    {"name":"temperature_c","label":"Temperature °C","type":"decimal","options":null,
		     "placeholder":null,"required":false},
		    {"name":"ebola_contact","label":"Contact with an Ebola patient?","type":"bool",
		     "options":null,"placeholder":null,"required":true}
		  ]}]
	""".trimIndent()

	@Test fun aJsonNullPlaceholderStaysNull() {
		val fields = BackendClient.parseActions(JSONArray(payload)).single().fields
		assertNull("a null placeholder must not become the string \"null\"", fields[1].placeholder)
		assertNull(fields[2].placeholder)
	}

	/**
	 * The device bug, reproduced off-device.
	 *
	 * Android's `optString` coerces a JSON null to the literal string "null"; desktop `org.json`
	 * returns "". A JVM test therefore cannot observe the device behaviour through `optString` —
	 * but it can assert the guard that makes the device correct, which is that the four-character
	 * string "null" is never accepted as a placeholder. Without this case the suite would pass on
	 * a build that renders `null` in the form, which is what happened.
	 */
	@Test fun theLiteralStringNullIsNeverAPlaceholder() {
		val arr = JSONArray("""[{"id":"a","title":"t","group":"g","method":"GET","path":"/p",
			"fields":[{"name":"n","label":"l","type":"text","options":null,"placeholder":"null","required":false}]}]""")
		assertNull(
			"the string \"null\" must be rejected: Android's optString produces it for a JSON null",
			BackendClient.parseActions(arr).single().fields.single().placeholder,
		)
	}

	@Test fun aRealPlaceholderSurvives() {
		val fields = BackendClient.parseActions(JSONArray(payload)).single().fields
		assertEquals("fever, headache", fields[0].placeholder)
	}

	@Test fun anEmptyPlaceholderIsTreatedAsAbsent() {
		val arr = JSONArray("""[{"id":"a","title":"t","group":"g","method":"GET","path":"/p",
			"fields":[{"name":"n","label":"l","type":"text","options":null,"placeholder":"","required":false}]}]""")
		assertNull(BackendClient.parseActions(arr).single().fields.single().placeholder)
	}

	@Test fun actionAndFieldMetadataAreCarriedThrough() {
		val action = BackendClient.parseActions(JSONArray(payload)).single()
		assertEquals("febrile_triage", action.id)
		assertEquals("Check a fever", action.title)
		assertEquals("POST", action.method)
		assertEquals(3, action.fields.size)
		assertEquals(true, action.fields[2].required)
	}

	@Test fun aMissingFieldsArrayYieldsNoFields() {
		val arr = JSONArray("""[{"id":"a","title":"t","group":"g","method":"GET","path":"/p"}]""")
		assertEquals(0, BackendClient.parseActions(arr).single().fields.size)
	}
}
