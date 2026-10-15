"""Canaries for the audit-note / gate-citation class: a note that reads as evidence and is not.

Three instances, found by widening one check rather than by any single finding:

1. **§LOC-004** cited `` `SENS-010` `` as a member of the coverage gate's `ON_DEVICE` set. It is not
   one, and had not been since §SENS-010's four applications got their own routes — the gate's own
   comment records the removal. The note rotted against a set nothing compared it to.
2. **§FND-001** named the gate as corroborating its deferral while citing no member at all, so the
   claim could not be checked even in principle — the weaker form of the same defect.
3. The test docstring for the deferral list made the same claim at scale: "the fifteen ... the
   coverage gate's `ON_DEVICE` set already lists", when one of the fifteen is.

Canary 4 is different in kind: it mutates the *gate* rather than the note, and is the one that says
whether the gate is pointed at anything. Canaries 1-3 mutate a note back to a false citation and
expect the gate to fail; canary 4 removes §EMG-002 — the single true citation — from the set the
gate compares against, and expects the gate to fail on it. A gate that only ever sees false notes is
a gate nobody has watched reject a true one.

Every mutation is the *pre-fix* text, so it is disjoint from the fixed text by construction. The
`__pycache__` purge after each write is load-bearing for the reason `canary_inf001.py` documents:
`service.py` is large and the patches are similar in length, so a same-second same-size write could
reuse the previous canary's bytecode.

Reverted from a `cp` backup, never with `git checkout --`: the mutation and the real change live in
the same uncommitted tree.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
AUDIT = ROOT / 'src/afya/content_audit/service.py'
GATE = ROOT / 'tests/ci/test_feature_coverage.py'

NODE = 'tests/ci/test_content_audit.py::test_a_note_that_cites_the_on_device_gate_names_a_member_of_it'

CANARIES = [
	# 1. §LOC-004's note goes back to citing SENS-010 as an on-device member. The gate must catch it.
	('the LOC-004 note cites a feature the ON_DEVICE set does not hold', AUDIT,
		"each of §SENS-010's four applications has its own route\"),",
		"§SENS-010's four applications each have a route, which is why §SENS-010 is in the coverage gate's `ON_DEVICE` set\"),",
		NODE),

	# 2. §FND-001's note goes back to naming the gate with no member in it — the uncheckable form.
	('the FND-001 note names the gate and no member of it', AUDIT,
		"'opening a maps app is a client action with no server call, like the other device-side capabilities this audit defers'",
		"'opening a maps app is a client action with no server call, like the other device-side capabilities the coverage gate lists in ON_DEVICE'",
		NODE),

	# 3. §EMG-002's note cites a member the set does not hold, which is the citation-shaped falsehood
	#    rather than the missing-citation one. The replacement must be a feature id *outside* the set —
	#    MON-006 is inside it and would leave the note true, which is the mutation-that-did-not-mutate
	#    failure the canary convention warns about.
	('the EMG-002 note cites a feature the ON_DEVICE set does not hold', AUDIT,
		"and §EMG-002 sits in the coverage gate's `ON_DEVICE` set",
		"and §LOC-004 sits in the coverage gate's `ON_DEVICE` set",
		NODE),

	# 4. The set itself drops §EMG-002, so the one true citation becomes false. This canaries the
	#    gate's *comparison*, not just its parse: a gate that reads the set but never checks against
	#    it would pass 1-3 and fail only here.
	('the ON_DEVICE set drops the member a note truly cites', GATE,
		"\t'EMG-002': 'fall auto-alert is the device arming the SOS it already has an action for',\n",
		'',
		NODE),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_audit_notes.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', node],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
