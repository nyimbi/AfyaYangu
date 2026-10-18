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
		    {"name":"ebola_contact","label":"Contact with someone sick with Ebola?","type":"bool",
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

	/**
	 * A condition survives the parse, and an absent one stays absent.
	 *
	 * The bug this guards is the one the field exists for: a voice-note report needs the recording
	 * *only* because the medium is a voice note, and a client that dropped the condition would draw
	 * the field as an ordinary optional question and submit a form the route refuses. `equals_any`
	 * empty is a value the parser must be able to produce — it means "any answer fires this" — so it
	 * is asserted as an empty list rather than as null.
	 */
	@Test fun aConditionSurvivesTheParse() {
		val arr = JSONArray("""[{"id":"flag_misinformation","title":"t","group":"g","method":"POST","path":"/p",
			"fields":[
			  {"name":"medium","label":"How did you get it?","type":"select","options":["text","voice"],
			   "placeholder":null,"required":true},
			  {"name":"transcript","label":"What the voice note said","type":"textarea","options":null,
			   "placeholder":null,"required":false,
			   "condition":{"when":"medium","equals_any":["voice"]}}
			],
			"any_of":[{"fields":["a","b"],"when":"medium","equals_any":["voice"]}]}]""")
		val action = BackendClient.parseActions(arr).single()
		val cond = action.fields[1].condition
		assertEquals("medium", cond?.whenField)
		assertEquals(listOf("voice"), cond?.equalsAny)
		// A field with no condition carries none — not an empty one, which would read as "any answer".
		assertNull(action.fields[0].condition)
		assertEquals(listOf("a", "b"), action.anyOf.single().fields)
		assertEquals("medium", action.anyOf.single().whenField)
	}

	@Test fun anEmptyEqualsAnyIsAnEmptyListNotAnAbsentCondition() {
		val arr = JSONArray("""[{"id":"a","title":"t","group":"g","method":"POST","path":"/p",
			"fields":[{"name":"evidence_consent","label":"Share it","type":"bool","options":null,
			 "placeholder":null,"required":false,"condition":{"when":"evidence_ref","equals_any":[]}}]}]""")
		val cond = BackendClient.parseActions(arr).single().fields.single().condition
		assertEquals("evidence_ref", cond?.whenField)
		assertEquals(emptyList<String>(), cond?.equalsAny)
	}

	@Test fun aDistinctnessRuleSurvivesTheParse() {
		val arr = JSONArray("""[{"id":"a","title":"t","group":"g","method":"POST","path":"/p",
			"fields":[{"name":"back_translated_by","label":"Rendered back by","type":"text","options":null,
			 "placeholder":null,"required":true,"distinct_from":"translated_by"}]}]""")
		assertEquals("translated_by", BackendClient.parseActions(arr).single().fields.single().distinctFrom)
	}
}
