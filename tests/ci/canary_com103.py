"""Canaries for tests/ci/test_com103.py.

§COM-103's missing bullet failed in the shape this codebase keeps finding: the flag existed, the
summary read it, and nothing transmitted. A checkbox on a form said "Share with the health team?"
and the person was told the list had been shared. So every canary here is a plausible way to keep
that true while the form still looks finished — or a way to *fix* it in the direction that leaks.

The two directions are the two ways the bullet can be wrong: a share that never leaves, and a share
that leaves in the clear. The second is the more expensive mistake, so more canaries point at it.

* **Nothing transmits** (#1) — the bullet failing outright, with the summary still claiming delivery.
* **The consent gate is dropped** (#2) — §COM-103's "transmitted only with explicit consent"
  becomes a checkbox nobody checks, which is the shape the audit row named.
* **An empty list is sent** (#3) — the county reads it as "this person had no contacts", a claim
  about the outbreak the person never made.
* **The list is sealed under the at-rest key** (#4) — the dangerous one. The operator holds that key,
  so the "secure, encrypted channel" is a lock whose key the recipient's side already has, and
  §SEC-003's second layer is gone while the algorithm label still reads AES-256-GCM.
* **A deployment with no app key falls back instead of refusing** (#5) — the same leak, reached by
  the other road: the fallback is the failure mode a fallback always has.
* **The receipt echoes the ciphertext** (#6) — the one value worth protecting put into a response, a
  log and a client cache for no gain.
* **`shared` reads the consent flag again** (#7) — the audit row's own defect, restored.
* **The share is lost when the transport fails** (#8) — the outbox written after the send rather
  than before, so a person who shared with no bars has nothing and no record of trying.
* **The window is typed again rather than read** (#9) — a 30-day contact-list retention beside
  §COM-102's 21-day one, which is two answers to one question.
* **The envelope reaches ADaM unsealed** (#10) — the client's own guard, which is the last cheap
  place to catch a caller that skipped the seal.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. Every node is
collected first and asserted present, because a nonexistent node id makes pytest exit non-zero on a
*collection* error, which reads as CAUGHT.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/community/service.py'
A = ROOT / 'src/afya/integrations/adam.py'

CANARIES = [
	# 1. Nothing transmits. The bullet failing outright: the envelope is sealed and the transport is
	#    never consulted, so the county learns nothing while the person is told it was sent.
	('the share is never transmitted', S,
	 "		if self._authority is not None:\n			# A transport that exists but is unreachable is this section's *normal* case, not an edge",
	 "		if False:\n			# A transport that exists but is unreachable is this section's *normal* case, not an edge",
	 'test_a_delivered_share_says_so'),

	# 2. The consent gate is dropped. §COM-103's data handling says the list is transmitted "only
	#    with explicit consent"; without this the flag is decorative.
	('the consent gate is dropped', S,
	 "		assert bucket.share_consent, (",
	 "		assert True, (",
	 'test_a_share_needs_the_persons_consent'),

	# 3. An empty list is sent. The county reads a zero-contact share as a statement about the
	#    outbreak rather than about the form.
	('an empty list is sent anyway', S,
	 "		assert bucket.entries, 'there is nothing to share — an empty list is not a statement about contacts'",
	 "		assert True, 'an empty list is fine'",
	 'test_an_empty_list_is_refused_rather_than_sent'),

	# 4. The list is sealed under the at-rest key. The expensive direction: the operator holds that
	#    key, so the second layer §SEC-003 asks for is gone while the label still says AES-256-GCM.
	('the list is sealed under the at-rest key', S,
	 "		sealed = self._crypto.seal(payload, app_layer=True)",
	 "		sealed = self._crypto.seal(payload)",
	 'test_the_list_travels_as_ciphertext_and_opens_only_with_the_app_key'),

	# 5. A deployment with no application-layer key falls back rather than refusing. Same leak,
	#    other road — and this is the one a fallback always has.
	('a deployment with no app key falls back to the at-rest key', S,
	 "		assert self._crypto is not None and self._crypto.has_app_layer, (",
	 "		assert self._crypto is not None, (",
	 'test_a_deployment_with_no_application_layer_key_refuses_to_share'),

	# 6. The receipt echoes the ciphertext. Nothing is leaked by the ciphertext alone, but the value
	#    is put into a response, a log and a client cache for no gain.
	('the receipt echoes the ciphertext', S,
	 "			share_id=envelope.share_id, with_who=recipient, entries=envelope.entries,",
	 "			share_id=envelope.share_id, with_who=recipient, entries=envelope.entries, sealed=envelope.sealed,",
	 'test_the_receipt_does_not_echo_the_ciphertext_back'),

	# 7. `shared` reads the consent flag again. The audit row's own defect, restored: consent and
	#    delivery wear one name and the person is told something that is not true.
	('shared reads the consent flag again', S,
	 "		delivered = any(s.subject_ref == subject_ref for s in self._shares.values())",
	 "		delivered = bucket.share_consent",
	 'test_the_summary_offers_the_share_before_it_is_made'),

	# 8. The outbox is written after the send rather than before, so a transport failure loses the
	#    sealed list — and the person who shared with no bars has nothing and no record of trying.
	('the share is lost when the transport fails', S,
	 "			# Kept before it is sent, so a transport that fails does not lose the sealed list.\n			self._shares[f'{subject_ref}:{recipient}'] = envelope",
	 "			pass",
	 'test_the_share_is_kept_even_when_nothing_carried_it'),

	# 9. The window is typed again instead of read from the constant, so the contact-list retention
	#    and §COM-102's follow-up window become two answers to one question.
	('the window is typed again rather than read', S,
	 "CONTACT_SHARE_WINDOW_DAYS: int = ALERT_WINDOW_DAYS",
	 "CONTACT_SHARE_WINDOW_DAYS: int = 30",
	 'test_the_share_expires_when_the_tracing_window_closes'),

	# 10. The envelope reaches ADaM unsealed — the client's own guard, which is the last cheap place
	#     to catch a caller that skipped §SEC-003's application layer.
	('the envelope reaches adam unsealed', A,
	 "		assert envelope.get('sealed'), (",
	 "		assert True, (",
	 'test_adam_refuses_a_contact_list_that_was_not_sealed'),
]

failures = []


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_com103.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_com103.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_com103.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated.
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
