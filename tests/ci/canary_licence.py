"""Canaries for tests/ci/test_licence.py.

§LOC-002 and §SEC-006 both asked for an open-source client and both rows were `missing` for the same
reason. The owner chose MIT; these are the cheap ways to make the tree *look* licensed without
offering terms anyone can rely on.

The four worth reading as a set:

* **#2** keeps the `MIT` constant and empties the file. The repository then declares a licence in
  code and ships all-rights-reserved terms — the worst of both, and the exact failure a constant
  cannot catch. This is the canary that makes `licence_is_offered` read the file rather than return
  `True`, and the only node that can catch it is the one that calls the function.
* **#4** lets MIT read as verification: the note stops saying no independent audit has happened, so
  closing the row becomes a stronger claim than the fact behind it — the failure mode the whole
  `sources/` discipline exists to prevent, arriving through the licence instead of a table.
* **#6** removes the catalogue action. The licence stays served and no client can reach it, which is
  the same join §SEC-001's toggle screen was missing and which no service-level test can see.
* **#7** drops the licence from the quarterly publication, so the one surface a person who never
  opens the repository reads is the one that does not mention it.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
L = ROOT / 'src/afya/licensing.py'
LIC = ROOT / 'LICENSE'
G = ROOT / 'src/afya/service.py'
M = ROOT / 'src/afya/mobile/actions.py'
R = ROOT / 'src/afya/retention/service.py'

CANARIES = [
	# 1. The identifier stops being MIT, so the tree ships MIT terms and declares something else —
	#    a scanner reads the constant and a person reads the file, and they disagree.
	('the declared identifier is not the one the file carries', L,
	 "SPDX_ID = 'MIT'",
	 "SPDX_ID = 'Apache-2.0'",
	 'test_the_offer_reports_the_identifier_holder_and_file'),

	# 2. `licence_is_offered` returns the constant instead of reading the file. A repository that
	#    deleted its LICENSE, or shipped all-rights-reserved terms, would keep answering `true` —
	#    the constant with a function around it, which is what this gate exists to be instead.
	('offered is the constant rather than the file', L,
	 "\tif not LICENCE_FILE.is_file():\n\t\treturn False\n\ttext = LICENCE_FILE.read_text(encoding='utf-8')\n\treturn SPDX_ID in text and COPYRIGHT_HOLDER in text",
	 "\treturn True",
	 'test_a_declared_licence_with_no_file_is_reported_as_not_offered'),

	# 3. The copyright line loses its holder, so the terms name nobody — a licence with no holder is
	#    not a licence, and the file gate stops being able to tell one grant from another.
	('the copyright holder leaves the file', LIC,
	 "Copyright (c) 2026 Nyimbi Odero",
	 "Copyright (c) 2026",
	 'test_the_file_actually_says_mit_and_names_a_holder'),

	# 4. The note stops saying no audit has happened, so MIT reads as independent verification. The
	#    row's own words are "for independent verification" and a permissive licence makes that
	#    possible, not true — this mutation is how a licence becomes a claim stronger than its fact.
	('MIT is allowed to read as verified', L,
	 "\t'MIT permits anyone to read, build and test the clients in this tree. It does not mean any '\n\t'external party has done so: no independent audit of this repository has been performed.'",
	 "\t'MIT permits anyone to read, build and test the clients in this tree, so the client is '\n\t'independently verified.'",
	 'test_the_note_does_not_let_mit_read_as_verified'),

	# 5. The route stops reporting whether the file is present, so it asserts a licence it cannot
	#    show — the served payload claiming `offered` without having read anything.
	('the route asserts the licence instead of reading it', G,
	 "\t\tfrom afya.licensing import licence_offer\n\t\treturn licence_offer()",
	 "\t\treturn {'spdx_id': 'MIT', 'offered': True}",
	 'test_the_route_serves_the_licence_with_no_token'),

	# 6. The catalogue action is removed. The licence keeps being served and no client can reach it:
	#    a person deciding whether to trust the app has no screen for the question. No service-level
	#    test can see this, which is why the node reads the catalogue.
	('the licence has no screen', M,
	 "		_a('licence_terms', 'Is this app open source?', 'Privacy', 'GET', '/security/licence', []),",
	 "",
	 'test_the_licence_has_a_screen_and_its_slug_is_a_slug'),

	# 7. The publication drops the licence, so the one surface a person who never opens the
	#    repository reads is the one that does not mention the terms.
	('the publication drops the licence', R,
	 "			licence=licence_offer(),\n		)",
	 "			licence=None,\n		)",
	 'test_the_publication_carries_the_licence_for_a_reader_who_never_opens_the_repo'),

	# 8. The publication's offer loses the boundary, so the quarterly document claims a verification
	#    the note is careful not to claim — the same overclaim as #4 through the public surface.
	('the publication overclaims the verification', R,
	 "			licence=licence_offer(),",
	 "			licence={**licence_offer(), 'note': 'The client is open source and independently verified.'},",
	 'test_the_publication_carries_the_licence_for_a_reader_who_never_opens_the_repo'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_licence.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_licence.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_licence.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		mode = 'collect' if 'ERROR' in proc.stdout or 'errors' in proc.stdout else 'test'
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT" if caught else "MISSED"} [{mode}] {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
