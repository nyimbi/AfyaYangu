"""Canaries for tests/ci/test_com104.py.

§COM-104's two missing bullets failed in the two shapes this codebase keeps finding, so the
canaries come in the same two halves.

The first half is the medium. The pattern was there and the payload was not, so a canary here is
any way to keep the pattern and still have nothing behind it.

The second half is the notification, and it is the harder half because a notice is trivially easy
to *report* as sent. The audit row's own defect was a correction drafted for a flagger nobody could
identify — so most of these canaries are ways to make `sent` true while nothing was delivered, or
to make a refusal look like a delivery.

* **A medium that names a payload carries none** (#1) — the audit row's own gap, restored.
* **The per-item consent gate is dropped** (#2) — §SEC-002's words for this data become a default.
* **`flagger_ref` is not read again** (#3) — the join removed, which is the defect itself.
* **The notice is sent before a correction exists** (#4) — "under verification" pushed to the
  person who reported the rumour, which tells them nothing they did not already know.
* **The fallback topic is treated as drafted** (#5) — the case that matters most: an unclassified
  report resolves to `unknown`, which *has* a library entry, so the naive membership test pushes
  the one answer the tracker gives when it has nothing to say.
* **The subscription check is skipped** (#6) — §ALT-003's toggle becomes decoration, and the
  person who switched community alerts off is pushed to anyway.
* **`sent` is set without a transport** (#7) — the §COM-103 ending: a control that reports success
  with nothing wired.
* **A failed transport is reported as sent** (#8) — the same lie reached through the exception path.
* **The notice is keyed on the topic alone** (#9) — twenty people who reported one rumour get one
  notice between them.
* **The notice is keyed on nothing** (#10) — a re-flag pushes the same correction again, so the
  person who reported a rumour three times is told three times.
* **The push payload loses its category** (#11) — the toggle that governs delivery stops travelling
  with the notice, and the subscription check reads a category the sender never named.

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
V = ROOT / 'src/afya/community/views.py'
S = ROOT / 'src/afya/community/service.py'

CANARIES = [
	# 1. A medium that names a recording or an image carries none — the audit row's own gap, with
	#    the `medium` pattern still looking filled in.
	('a screenshot report carries no image', V,
	 "		if self.medium in ('voice', 'screenshot', 'whatsapp_forward') and not (\n				self.evidence_ref or self.transcript):",
	 "		if False and not (\n				self.evidence_ref or self.transcript):",
	 'test_a_screenshot_report_must_carry_the_image'),

	# 2. The per-item consent gate is dropped, so §SEC-002's "only shared with explicit per-item
	#    consent" becomes a default rather than a gate.
	('the per-item consent gate is dropped', V,
	 "		if self.evidence_ref and not self.evidence_consent:",
	 "		if False and not self.evidence_consent:",
	 'test_the_recording_is_shared_only_with_per_item_consent'),

	# 3. `flagger_ref` is not read again. This is the defect verbatim: the correction exists, the
	#    person is named on the report, and nothing joins them.
	('the flagger is never resolved', S,
	 "			if (s.topic or 'unknown') != topic or not s.flagger_ref:\n				continue",
	 "			if (s.topic or 'unknown') != topic or True:\n				continue",
	 'test_the_flagger_is_told_when_the_correction_is_ready'),

	# 4. The notice is sent before a correction exists, so "under verification" is pushed to the one
	#    person who already knows it is under verification.
	('an undrafted rumour is answered with the fallback', S,
	 "		drafted = topic in CORRECTION_LIBRARY and topic != FALLBACK_TOPIC",
	 "		drafted = True",
	 'test_the_notice_carries_the_correction_not_the_fallback'),

	# 5. The fallback topic counts as drafted. Same line, the other direction, and the case that
	#    matters most: a report filed with no topic resolves to `unknown`.
	('the fallback topic counts as drafted', S,
	 "		drafted = topic in CORRECTION_LIBRARY and topic != FALLBACK_TOPIC",
	 "		drafted = topic in CORRECTION_LIBRARY",
	 'test_an_unclassified_rumour_is_not_answered_with_the_fallback'),

	# 6. The subscription check is skipped, so §ALT-003's toggle governs nothing.
	('the alert subscription is not consulted', S,
	 "			if self._alerts is not None:\n				subscribed = bool(self._alerts.should_deliver(flagger, CORRECTION_NOTICE_CATEGORY))",
	 "			if False:\n				subscribed = bool(self._alerts.should_deliver(flagger, CORRECTION_NOTICE_CATEGORY))",
	 'test_a_person_who_switched_community_alerts_off_is_not_pushed'),

	# 7. `sent` is set with no transport wired — a control reporting success with nothing behind it,
	#    which is the §COM-103 defect in this section's clothes.
	('sent is set without a transport', S,
	 "			if subscribed and self._notifier is not None:",
	 "			if subscribed:",
	 'test_a_deployment_with_no_transport_says_so_rather_than_claiming_delivery'),

	# 8. A failed transport is reported as sent. The same lie, through the exception path — and this
	#    is the shape the dict-payload bug actually produced.
	('a failed transport is reported as sent', S,
	 "					notice.withheld = NOTICE_WITHHELD_TRANSPORT_FAILED",
	 "					notice.sent = True",
	 'test_a_transport_that_fails_does_not_lose_the_correction'),

	# 9. The notice is keyed on the topic alone, so twenty people who reported one rumour get one
	#    notice between them.
	('the notice is keyed on the topic alone', S,
	 "			notice = self._notices.get((topic, flagger))",
	 "			notice = self._notices.get((topic, ''))",
	 'test_the_notice_is_keyed_on_the_person_and_the_rumour'),

	# 10. The notice is never stored, so a re-flag pushes the same correction again and the person
	#     who reported a rumour three times is told three times.
	('a re-flag pushes the correction again', S,
	 "			self._notices[(topic, flagger)] = notice",
	 "			pass",
	 'test_the_notice_is_keyed_on_the_person_and_the_rumour'),

	# 11. The push payload loses its category, so the toggle that governs delivery stops travelling
	#     with the notice.
	('the push payload loses its category', S,
	 "						category=CORRECTION_NOTICE_CATEGORY,",
	 "						category='health_tips',",
	 'test_the_flagger_is_told_when_the_correction_is_ready'),
]

failures = []


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_com104.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_com104.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_com104.{path.name}.bak')
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
