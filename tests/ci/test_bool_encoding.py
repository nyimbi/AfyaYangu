"""A checkbox that cannot say no, and the check that stopped asking.

Both native clients render the catalogue's `bool` fields as a toggle. Android's `raw()` returned
`"true"` when ticked and `""` when not, so:

* a **required** bool could never be submitted false — `monitoring_consent.granted`, `in_stock`,
  `sha_covered` and eight others could only ever be answered *yes*, and a person who meant no had
  no control that carried it;
* an **optional** bool was indistinguishable from an unanswered one, so a model default won. Nine
  drawn bools default to `True` in their models (`GlucoseReading.fasting`, `AccessProfile.read_aloud`,
  …) and every unticked box recorded the default: "Before eating?" was always yes.

Swift has always sent both states, and that is the other half of this gate: sending `"false"` makes
the string non-empty, so the *pre-request check* — which asked `(values[name] ?? "").isEmpty` — read
an unticked toggle as answered. `flag_misinformation.evidence_consent` is required exactly when
there is a recording to consent to, so on iOS the form would submit a report the route refuses, with
no message, because the check had already decided the field was filled.

So the contract has three parts, and a client is wrong if it drops any:

1. a toggle sends `"true"` **or** `"false"`, never nothing and never only `"true"`;
2. "answered" for a toggle means `"true"` — the request still carries `false`, which is what lets a
   required yes/no question be answered no;
3. the missing-field check and the either/or check both read (2), not string emptiness.

Parts 1–3 are read from the client sources, because they are the client's rule and no Python
execution can observe a Kotlin `when` branch. Part 4 reads the served catalogue, so the population
the rule is about is pinned: if a bool stops being demanded, the rule is still right and has less to
do, and this gate should say so rather than pass quietly.
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
KOTLIN = REPO / 'android/app/src/main/java/ke/go/health/afyayangu/ActionsActivity.kt'
SWIFT = REPO / 'ios/AfyaYangu/Features.swift'


def test_a_toggle_sends_both_states_on_both_clients() -> None:
	"""A control with no "empty" state must not be encoded as one.

	This is the defect as Android shipped it: `if (v.isChecked) "true" else ""`. The assertion is on
	the *encoding*, not on the word `bool`, because a source mentioning bools can still send one state
	— which is exactly what the old line did.
	"""
	kotlin = KOTLIN.read_text()
	assert 'is CheckBox -> if (v.isChecked) "true" else "false"' in kotlin, (
		'Android encodes an unticked checkbox as absent rather than as "false", so a required bool '
		'cannot be answered no and an optional bool falls back to its model default')

	swift = SWIFT.read_text()
	assert 'set: { values[field.name] = $0 ? "true" : "false" }' in swift, (
		'iOS does not send both states for a toggle')


def test_an_unticked_toggle_is_unanswered_for_the_pre_request_check() -> None:
	"""Sending `"false"` is right, and it makes string emptiness the wrong test for "answered".

	The two facts are one defect from opposite sides: Android omitted the value and could not say no;
	iOS sent `false` and the check stopped noticing that the person had not answered. A client needs
	both a two-state encoding *and* a bool-aware answered-predicate, and neither alone is enough.
	"""
	kotlin = KOTLIN.read_text()
	assert 'private fun answered(f: ActionField, raw: String): Boolean' in kotlin and \
		'if (f.type == "bool") raw == "true" else raw.isNotEmpty()' in kotlin, (
		'Android has no bool-aware answered-predicate, so "false" reads as an answer')
	assert 'needed(a, it, answers) && unanswered(it)' in kotlin, (
		'Android\'s missing-field check does not use the answered-predicate')
	assert '!answered(it, answers[it.name] ?: "")' in kotlin, (
		'Android\'s `unanswered` helper no longer reads the answered-predicate')
	assert 'return g.fields.none { n -> answered(' in kotlin, (
		'Android\'s either/or check does not use the answered-predicate, so an unticked toggle '
		'satisfies a group it should leave open')

	swift = SWIFT.read_text()
	assert 'private func answered(_ f: MobileFieldDTO) -> Bool' in swift and \
		'if f.type == "bool" { return (values[f.name] ?? "") == "true" }' in swift, (
		'iOS has no bool-aware answered-predicate, so "false" reads as an answer')
	assert '&& needed($0) && !answered($0) }' in swift, (
		'iOS\'s missing-field check does not use the answered-predicate')
	assert 'return answered(f)' in swift, (
		'iOS\'s either/or check does not use the answered-predicate')


def test_the_catalogue_still_demands_bools_a_toggle_has_to_answer() -> None:
	"""The population the encoding is about, pinned by name.

	A rule about how a bool is sent is only load-bearing while some bool is demanded. Eleven are
	required outright and one is conditional (`evidence_consent`, required once there is a recording),
	and that one is the case the pre-request check exists for: the route refuses it and the form has to
	say so before the round trip.
	"""
	from afya.access.forms import required_fields
	from afya.mobile.actions import catalogue, marked
	from afya.service import build_services, create_app

	app = create_app(build_services())
	served = {a.id: a for a in marked(catalogue(), required_fields(app))}

	required_bools = {f'{a.id}.{f.name}' for a in served.values() for f in a.fields
	                  if f.type == 'bool' and f.required}
	assert required_bools == {
		'set_zone_alerts.enabled', 'report_stock.in_stock', 'pmtct_referral.hiv_positive',
		'water_advisory.ecoli_detected', 'publish_feed_item.verified', 'set_alert_preference.enabled',
		'monitoring_consent.granted', 'register_border.screening_required',
		'provision_chw.registry_verified', 'assign_chw_case.ppe_reminder_due', 'file_price.sha_covered',
	}, f'the required bools drifted: {sorted(required_bools)}'

	conditional_bools = {f'{a.id}.{f.name}' for a in served.values() for f in a.fields
	                     if f.type == 'bool' and f.condition is not None}
	assert conditional_bools == {'flag_misinformation.evidence_consent'}, (
		f'the conditional bools drifted: {sorted(conditional_bools)} — the pre-request check has '
		'less to do than the gate assumes, or a new one was added without a gate')
