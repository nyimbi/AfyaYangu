"""Canaries for tests/ci/test_sec002.py.

§SEC-002's fourth bullet was `missing` while every visible part of it existed: a route, a model, an
object-storage port and a tier-4 gate. The two halves of the sentence — *encrypted* and *only shared
with explicit per-item consent* — were the join, and neither was there.

The canaries are the cheap ways to have the parts without the join:

* **#1** is the defect exactly as it was found: the service hands the store the bytes it was given.
  The route, the model and the receipt are all still there, and the picture is on disk in the clear.
* **#2** is the same defect one step subtler — a receipt that says `aes-256-gcm` over a store that
  holds the JPEG. The label is what a reader checks, which is why the test reads the file.
* **#4** is the shape the audit row itself described: a consent field that exists and is never
  enforced. It is the most dangerous of the set, because the field's presence is what makes the
  bullet look carried.
* **#9** defaults the consent to True, which is the difference between an opt-in and a checkbox.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
ES = ROOT / 'src/afya/evidence/service.py'
EV = ROOT / 'src/afya/evidence/views.py'
G = ROOT / 'src/afya/service.py'
M = ROOT / 'src/afya/mobile/actions.py'
IOS = ROOT / 'ios/AfyaYangu/Evidence.swift'
AND = ROOT / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'

CANARIES = [
	# 1. The defect as found: the store is handed the plaintext. Everything else is intact — the
	#    consent is checked, the receipt is built, the gate still fires — and the photograph is on
	#    disk exactly as it arrived.
	('the store is handed the plaintext', ES,
	 "		ref = await self._store.put(submission, sealed.ciphertext)",
	 "		ref = await self._store.put(submission, blob)",
	 'test_the_store_holds_ciphertext_and_not_the_photo'),

	# 2. The seal happens and its result is thrown away, so the receipt says aes-256-gcm while the
	#    store holds the picture. This is the audit row's own failure mode — a label asserting a
	#    control — and it is why the test opens the file rather than reading the field.
	('the seal is computed and discarded', ES,
	 "		sealed = self._crypto.seal(blob)",
	 "		sealed = self._crypto.seal(blob)\n		sealed = sealed.__class__(nonce=sealed.nonce, salt=None, ciphertext=blob, user_held=False, layer='at_rest')",
	 'test_the_store_holds_ciphertext_and_not_the_photo'),

	# 3. A deployment with no key writes anyway. The fallback is the failure mode: from every test
	#    that supplies a key this is invisible, and from the screen it says "Stored ✓".
	('a keyless deployment stores in the clear', ES,
	 "		if self._crypto is None or not self._crypto.available:",
	 "		if False:",
	 'test_a_deployment_with_no_key_refuses_rather_than_storing_in_the_clear'),

	# 4. The consent field stays and stops being enforced — the field exists, the bullet reads as
	#    carried, and a photo nobody agreed to share is stored. This is the most dangerous canary
	#    here, because the visible part is what a reader checks.
	('the consent is carried but not enforced', EV,
	 "		if not self.consent:\n			raise ValueError(",
	 "		if False:\n			raise ValueError(",
	 'test_a_photo_without_its_own_consent_does_not_validate'),

	# 5. The service's own lock goes, so the path that skips pydantic — `model_construct`, a queue
	#    replay — reaches the store. The model gate is still there, which is what makes this the
	#    *second* door rather than the first.
	('the service stops re-checking the consent', ES,
	 "		assert submission.consent, (\n			'the photo is shared only with the consent recorded for this submission')",
	 "		assert True, 'the photo is shared only with the consent recorded for this submission'",
	 'test_the_service_refuses_a_submission_that_never_passed_the_model'),

	# 6. The consent defaults to allowed. A submission that says nothing then shares a photograph,
	#    which is the opposite of an opt-in and is invisible to any test that always sends `true`.
	('consent defaults to allowed', EV,
	 "	consent: bool = False",
	 "	consent: bool = True",
	 'test_consent_defaults_to_false_so_silence_shares_nothing'),

	# 7. The receipt can say `none`. The pattern is the only thing making a label-on-plaintext
	#    unrepresentable, and loosening it is how the vocabulary comes back.
	('the receipt can name no cipher', EV,
	 "	cipher: str = Field(pattern=r'^aes-256-gcm$')",
	 "	cipher: str = Field(default='none')",
	 'test_the_receipt_names_the_cipher_and_cannot_say_none'),

	# 8. The posture reports the intent rather than the deployment — a hardcoded `True`, which is
	#    exactly the `EncryptionPosture` finding §SEC-003's row records for the same class of defect.
	('encrypted is a constant', ES,
	 "		return self._crypto is not None and self._crypto.available",
	 "		return True",
	 'test_encrypted_reports_the_key_rather_than_a_constant'),

	# 9. The route stops passing the form field through, so the control is drawn, answered and
	#    dropped — a form that asks a question whose answer is thrown away. The model then refuses
	#    every upload, and the field is decoration.
	('the route drops the consent field', G,
	 "				size_bytes=len(blob), note=note, consent=consent,",
	 "				size_bytes=len(blob), note=note, consent=True,",
	 'test_the_route_stores_a_photo_only_when_consent_was_sent'),

	# 10. The dark-feature gate runs *after* the consent check, so a symptom photo sent while the
	#     response is dormant is answered "you did not consent" — sending someone to a checkbox that
	#     changes nothing. §11.1's refused control, wearing a consent label.
	('a dormant feature is refused as a consent problem', ES,
	 "		self.gate(submission.kind)\n		# §SEC-002's consent",
	 "		# §SEC-002's consent",
	 'test_a_dormant_feature_is_refused_as_dormant_not_as_a_consent_problem'),

	# 11. A missing key becomes the caller's fault. 422 tells a person holding a phone that their
	#     request was wrong, when no request would have succeeded.
	('a deployment fault is reported as the caller\'s mistake', G,
	 "		except RuntimeError as exc:",
	 "		except ZeroDivisionError as exc:",
	 'test_the_route_answers_a_missing_key_with_503_and_not_422'),

	# 12. The catalogue stops offering the field the route requires, so the form cannot fill its own
	#     route and the button always answers 422 — the `report_stock` defect, one level down.
	('the catalogue drops the consent field', M,
	 "_f('note', 'What did you notice?', 'textarea'), _f('consent', 'I agree to share this photo', 'bool')",
	 "_f('note', 'What did you notice?', 'textarea')",
	 'test_the_catalogue_offers_the_consent_field_the_route_requires'),

	# 13. The iOS uploader stops sending the field. The button still works, the server refuses, and
	#     nothing in the Python tree notices — which is why the clients are asserted by name.
	('the iOS uploader drops the consent field', IOS,
	 '		field("consent", consent ? "true" : "false")',
	 '		field("kind", kind)',
	 'test_the_native_uploaders_send_the_consent_field'),

	# 14. The Android uploader stops sending it. Same shape, other platform: a body missing a field
	#     its route requires, written by hand in a language no other gate reads.
	('the Android uploader drops the consent field', AND,
	 '			os.write(("--$boundary\\r\\nContent-Disposition: form-data; name=\\"consent\\"\\r\\n\\r\\n$consent\\r\\n").toByteArray())',
	 '			os.write("".toByteArray())',
	 'test_the_native_uploaders_send_the_consent_field'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_sec002.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_sec002.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_sec002.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See the module docstring: a same-second write of the same size reuses the previous canary's
	# bytecode, and the canary then tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
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
