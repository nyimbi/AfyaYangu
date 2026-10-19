"""Canaries for tests/ci/test_client_upload.py — each gate pointed at a planted defect.

Every mutation is disjoint from what its predicate reads: the gate for "the mark is the server's"
is broken by un-marking a field, not by changing the string it looks for; the picker gate is broken
by restoring the path guess, not by deleting the `accept` read.

Backups are read back before the mutation and the restore is verified, because the mutation and the
real fix live in one uncommitted tree and `git checkout --` would take the real work with it.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
ACTIONS = ROOT / 'src/afya/mobile/actions.py'
KOTLIN = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'
ACTIVITY = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/ActionsActivity.kt'
STORE = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/LocalStore.kt'
SWIFT = ROOT / 'ios/AfyaYangu/Endpoints.swift'
SWIFT_CLIENT = ROOT / 'ios/AfyaYangu/BackendClient.swift'
SWIFT_UI = ROOT / 'ios/AfyaYangu/Features.swift'

GATE = 'tests/ci/test_client_upload.py'

CANARIES = [
	('a form action loses its mark', ACTIONS,
	 "_f('purpose', 'Symptoms or a note?', 'select', VOICE_PURPOSES, form=True)",
	 "_f('purpose', 'Symptoms or a note?', 'select', VOICE_PURPOSES)",
	 'test_the_catalogue_marks_exactly_the_actions_whose_route_takes_a_form_body'),

	('a JSON action is marked as a form', ACTIONS,
	 "_a('maternity_facilities', 'Where can I deliver?', 'Maternity', 'GET', '/maternal/facilities', [_f('lat', 'My latitude', 'decimal')",
	 "_a('maternity_facilities', 'Where can I deliver?', 'Maternity', 'GET', '/maternal/facilities', [_f('lat', 'My latitude', 'decimal', form=True)",
	 'test_the_catalogue_marks_exactly_the_actions_whose_route_takes_a_form_body'),

	('a file field loses its accept', ACTIONS,
	 "_f('file', 'Photo', 'file', form=True, accept='image/*')",
	 "_f('file', 'Photo', 'file', form=True)",
	 'test_the_catalogue_says_what_the_picker_may_offer'),

	('Android infers the transport from the file field', KOTLIN,
	 '		if (form || upload != null) {',
	 '		if (upload != null) {',
	 'test_both_clients_choose_the_transport_from_the_catalogues_mark'),

	('iOS infers the transport from the file field', SWIFT,
	 '		let encodedAsForm = action.fields.contains(where: { $0.form == true })',
	 '		let encodedAsForm = false',
	 'test_both_clients_choose_the_transport_from_the_catalogues_mark'),

	('Android guesses the picker type from the path', ACTIVITY,
	 '	private fun mimeFor(a: CatalogueAction): String = acceptOf(a)',
	 '	private fun mimeFor(a: CatalogueAction): String =\n\t\tif (a.path.startsWith("/evidence")) "image/*" else "audio/*"',
	 'test_the_picker_offers_what_the_route_accepts'),

	('iOS offers a PhotosPicker for every file field', SWIFT_UI,
	 '			if (field.accept ?? "").hasPrefix("image") {',
	 '			if true {',
	 'test_the_picker_offers_what_the_route_accepts'),

	('Android queues an upload without its bytes', STORE,
	 '						put("base64", android.util.Base64.encodeToString(u.bytes, android.util.Base64.NO_WRAP))',
	 '						put("base64", "")',
	 'test_a_queued_upload_keeps_its_bytes_and_its_transport'),

	('iOS queues a multipart op with no body', SWIFT,
	 '			bodyText = encoded.base64EncodedString()',
	 '			bodyText = ""',
	 'test_a_queued_upload_keeps_its_bytes_and_its_transport'),

	('iOS digests a binary body through String(decoding:)', SWIFT_CLIENT,
	 '		let material = "\\(method) \\(url) " + body.base64EncodedString()',
	 '		let material = "\\(method) \\(url) " + String(decoding: body, as: UTF8.self)',
	 'test_a_queued_upload_keeps_its_bytes_and_its_transport'),

	('iOS gives the boundary a random value', SWIFT,
	 '			let boundary = "afya-" + String(Self.opKey(method: action.method, url: action.path, body: canonical).dropFirst(3))',
	 '			let boundary = "afya-" + UUID().uuidString',
	 'test_the_multipart_boundary_is_the_same_on_every_attempt'),

	('iOS builds the boundary from an unordered dictionary', SWIFT,
	 '			let canonical = values.sorted { $0.key < $1.key }.map { "\\($0.key)=\\($0.value)" }.joined(separator: "&")',
	 '			let canonical = "\\(values)"',
	 'test_the_multipart_boundary_is_the_same_on_every_attempt'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_upload.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	assert s == backup.read_text(), f'{name}: the backup is not this file'
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', f'{GATE}::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
