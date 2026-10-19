"""The four routes that read a `multipart/form-data` body, and what each client had to do to reach them.

The defect class is the same one `test_action_reachability.py` names, one layer down: **a form that
cannot be submitted**. There the crossing was *field → place a route reads it*. Here it is *field →
transport the route declares*, and the clients got it wrong in four separate ways:

1. **Neither client read the catalogue's transport.** Android and iOS both inferred multipart from
   "this action has a `file` field". That is a rule the client invented: `submit_evidence` also sends
   `kind`, `note` and `consent` as form parts, and an action could carry a form body with no file at
   all. The catalogue now marks `form`, and the mark is the server's — it is derived from the route's
   own OpenAPI content type, so it cannot drift from what the route accepts.

2. **Android offered the wrong file type.** The picker's MIME filter was guessed from the path
   (`/evidence` → images, everything else → audio), so the cough recording and the WhatsApp voice
   note were selectable only as images on that client, and the evidence photo only as audio on a
   route that wanted neither. The catalogue now carries `accept`, taken from the route.

3. **iOS could not select a recording at all.** Its only file control was `PhotosPicker`, which
   offers images. A voice-note action on iOS had a control that could not produce the part the route
   requires.

4. **iOS dropped a file upload instead of queueing it.** `submitOrQueue` short-circuited every action
   with a file field straight to `invoke`, so a person who photographed evidence with no signal got
   an exception and lost the photograph — the one payload that cannot be retyped. The queue now
   stores the exact multipart bytes, and the boundary is derived from the action's content rather
   than a UUID, so the replay is byte-identical and §15.5's replay table recognises it.

The server half — that these four routes really do take a form body — is read from the OpenAPI
document, which is the same source the clients are written against.
"""
import pathlib

from afya.mobile.actions import catalogue
from afya.service import build_services, create_app

REPO = pathlib.Path(__file__).resolve().parents[2]
KOTLIN = REPO / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'
ACTIVITY = REPO / 'android/app/src/main/java/ke/go/health/afyayangu/ActionsActivity.kt'
STORE = REPO / 'android/app/src/main/java/ke/go/health/afyayangu/LocalStore.kt'
SWIFT = REPO / 'ios/AfyaYangu/Endpoints.swift'
SWIFT_STORE = REPO / 'ios/AfyaYangu/LocalStore.swift'
SWIFT_CLIENT = REPO / 'ios/AfyaYangu/BackendClient.swift'
SWIFT_UI = REPO / 'ios/AfyaYangu/Features.swift'


def test_the_catalogue_marks_exactly_the_actions_whose_route_takes_a_form_body() -> None:
	"""Both directions: no form action unmarked, and no marked action whose route is JSON.

	One direction alone would pass on a catalogue that marked everything, and the other alone would
	pass on one that marked nothing.
	"""
	spec = create_app(build_services()).openapi()
	unmarked: list[str] = []
	overmarked: list[str] = []
	for act in catalogue():
		op = spec['paths'].get(act.path, {}).get(act.method.lower()) or {}
		content = ((op.get('requestBody') or {}).get('content') or {})
		takes_form = 'multipart/form-data' in content
		# Every body field, not just one: the transport belongs to the request, so a form action
		# whose `lang` is unmarked is a field a future client could route as JSON — and a gate that
		# accepted one marked field per action passed over exactly that.
		body_fields = [f for f in act.fields if f.type != 'path']
		unmarked_here = [f.name for f in body_fields if not f.form]
		marked_here = [f.name for f in body_fields if f.form]
		if takes_form and unmarked_here:
			unmarked.append(f'{act.id}: {unmarked_here}')
		if not takes_form and marked_here:
			overmarked.append(f'{act.id}: {marked_here}')
	assert unmarked == [], (
		f'actions whose route reads a form body but whose fields are not marked: {unmarked}. A client '
		'that cannot tell will send JSON, and the route refuses it before the handler runs.')
	assert overmarked == [], (
		f'actions marked as form but whose route takes JSON: {overmarked}. The mark is what a client '
		'uses to choose the transport, so a wrong one breaks a route that worked.')


def test_the_catalogue_says_what_the_picker_may_offer() -> None:
	"""`accept` on every file field, and it is a type the route can plausibly take."""
	spec = create_app(build_services()).openapi()
	missing: list[str] = []
	for act in catalogue():
		for field in act.fields:
			if field.type != 'file':
				continue
			if not field.accept:
				missing.append(f'{act.id}.{field.name}')
	assert missing == [], (
		f'file fields with no `accept`: {missing}. A client that guesses the picker type from the '
		'path offered audio for a photo route and images for a recording.')
	# And the OpenAPI document is the authority the catalogue must agree with: every form action's
	# file part is a binary string, which is what `accept` describes.
	for act in catalogue():
		if not any(f.type == 'file' for f in act.fields):
			continue
		op = spec['paths'].get(act.path, {}).get(act.method.lower()) or {}
		content = ((op.get('requestBody') or {}).get('content') or {})
		schema = (content.get('multipart/form-data') or {}).get('schema') or {}
		ref = schema.get('$ref')
		assert ref is not None, f'{act.id} has a file field but no form schema'
		name = ref.split('/')[-1]
		props = spec['components']['schemas'][name]['properties']
		assert props['file']['type'] == 'string', f'{act.id}: the file part is not a file'


def test_both_clients_choose_the_transport_from_the_catalogues_mark() -> None:
	"""Not from `type == "file"`: that is the client's own rule, and it was wrong for the fields."""
	kotlin = KOTLIN.read_text()
	assert 'form: Boolean = false' in kotlin, 'Android has no transport parameter'
	assert 'if (form || upload != null) {' in kotlin, (
		'Android still infers the form body from the presence of a file, so a form action without '
		'one is sent as JSON')
	activity = ACTIVITY.read_text()
	assert 'val form = a.fields.any { it.form }' in activity, (
		'Android\'s screen does not pass the catalogue\'s mark to the transport')

	swift = SWIFT.read_text()
	assert 'let encodedAsForm = action.fields.contains(where: { $0.form == true })' in swift, (
		'iOS still infers the form body from the presence of a file')
	assert 'let form: Bool?' in swift, 'iOS does not decode the catalogue\'s mark at all'


def test_the_picker_offers_what_the_route_accepts() -> None:
	"""Both pickers read `accept`, and iOS can reach a non-image file at all."""
	activity = ACTIVITY.read_text()
	assert 'a.fields.firstOrNull { it.type == "file" }?.accept ?: "*/*"' in activity, (
		'Android still guesses the picker type from the path')
	assert 'a.path.startsWith("/evidence")' not in activity, (
		'the path-based guess is still there beside the catalogue\'s answer')

	features = SWIFT_UI.read_text()
	assert '(field.accept ?? "").hasPrefix("image")' in features, (
		'iOS offers a PhotosPicker for every file field, so a recording cannot be selected')
	assert '.fileImporter(' in features, 'iOS has no control that can produce a non-image file'


def test_a_queued_upload_keeps_its_bytes_and_its_transport() -> None:
	"""§16.1's "never lost" is about the payload, and an upload's payload is the file."""
	kotlin = KOTLIN.read_text()
	store = STORE.read_text()
	assert 'form = form,' in kotlin, 'Android does not carry the transport into the queued op'
	assert 'put("form", op.form)' in store, 'the queued row forgets the transport'
	assert 'put("base64", android.util.Base64.encodeToString(u.bytes' in store, (
		'the queued row forgets the file, so a replay would send the fields and no part the route '
		'needs')

	swift = SWIFT.read_text()
	assert 'enqueue(method: action.method, url: req.url!.absoluteString, body: body,' in swift, (
		'iOS still queues only a text body, which for multipart is empty')
	assert 'bodyBytes: req.httpBody' in swift, 'iOS queues no bytes'
	assert 'bodyText = encoded.base64EncodedString()' in swift, (
		'iOS queues a multipart op with nothing to replay')
	client = SWIFT_CLIENT.read_text()
	assert 'let material = "\\(method) \\(url) " + body.base64EncodedString()' in client, (
		'iOS digests the bytes through `String(decoding:)`, which maps every non-UTF-8 byte to the '
		'same replacement character — two photographs would collide on one key')
	assert 'req.httpBody = op.bodyData' in client, 'the replay sends no bytes'
	assert 'req.setValue(op.contentType, forHTTPHeaderField: "content-type")' in client, (
		'the replay declares JSON for a body that is multipart')


def test_the_multipart_boundary_is_the_same_on_every_attempt() -> None:
	"""§15.5 compares bodies. A boundary that differs per attempt makes every replay a new write."""
	kotlin = KOTLIN.read_text()
	assert 'val boundary = "----afya" + (idempotencyKey ?: "adhoc")' in kotlin, (
		'Android derives the boundary from something other than the op key')
	assert 'let boundary = "afya-" + String(Self.opKey(' in SWIFT.read_text(), (
		'iOS derives the boundary from something other than the op content')
	# The material must be ordered, because a Swift dictionary's description is not: an unordered
	# boundary changes between launches even when the action does not.
	assert 'values.sorted { $0.key < $1.key }' in SWIFT.read_text(), (
		'iOS builds the boundary from an unordered dictionary, so it differs between launches')
