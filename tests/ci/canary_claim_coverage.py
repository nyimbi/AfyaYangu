"""Canaries for the claim-side gate in tests/ci/test_content_audit.py.

The content side has had a canary file since it existed; the claim side had no gate at all, so
there was nothing to canary. It has one now, and it has three ways to fail open, each of which gets
a canary — because a gate whose exit 0 has never been watched turning to 1 is not evidence that it
ran anything.

* **The coverage gate** (`test_every_claim_label_a_section_prints_has_a_verdict_under_it`) — a
  claim passage the spec prints with no verdict under it. Its blind spot is the *set it compares*:
  it builds `printed` from `_CLAIM_LABELS` and `covered` from `CLAIM_CONTENT`, so deleting a label
  from `_CLAIM_LABELS` removes the requirement along with the coverage — the gate would then be
  silent about a passage nobody read, which is exactly the defect it was written for. Canary #1 is
  that deletion, and it must fail on the *vocabulary partition* rather than only here, because two
  gates noticing is the point.
* **The verbatim gate** (`test_every_claim_is_the_sections_claim_in_its_own_words`) — a reworded
  sentence. Canary #2 edits one claim in the table and the join stops reproducing the passage.
* **The pinned narrative set** (`test_the_narrative_claims_are_the_ones_no_code_can_carry`) — the
  one check that catches a capability moved into `narrative` to make a gap disappear. Canary #3
  moves §AI-003's carried early-warning claim into `narrative` with a plausible reason, which every
  other test in the file accepts: it has a note, it has no reference, and the verdict is legal. Only
  the pinned set and the named-closure test can see it, which is why both exist.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
T = ROOT / 'tests/ci/test_content_audit.py'
S = ROOT / 'src/afya/content_audit/service.py'
F = ROOT / 'tests/ci/test_feature_coverage.py'

CANARIES = [
	# 1. A claim label the spec prints leaves the vocabulary, so the coverage gate stops demanding a
	#    verdict for every passage under it. This is the defect that let §CHAN-2's Integration
	#    sentence sit unread: not a wrong verdict but a passage nobody had to give one to.
	('a claim label leaves the vocabulary', S,
	 "	'Capabilities', 'Critical requirement', 'Distribution', 'Feature ID', 'Language coverage',\n"
	 "	'Measurement', 'Objectives', 'Rationale', 'Role', 'Session limits',",
	 "	'Capabilities', 'Critical requirement', 'Distribution', 'Feature ID', 'Language coverage',\n"
	 "	'Measurement', 'Objectives', 'Rationale', 'Role',",
	 'test_every_claim_label_a_section_prints_has_a_verdict_under_it'),

	# 2. A claim is reworded in the table, so it is no longer the section's own sentence. The audit
	#    would then be measuring a paraphrase of the spec rather than the spec — the failure the
	#    content side's verbatim gate exists for, one level up.
	('a claim is reworded away from the spec', S,
	 "'Must complete within 2 USSD sessions (approx. 360 characters) to avoid timeouts.'",
	 "'Must complete within two USSD sessions to avoid timeouts.'",
	 'test_every_claim_is_the_sections_claim_in_its_own_words'),

	# 3. §AI-003's early-warning claim — carried by the channel report sink, and one of the two
	#    defects this whole gate was built for — is moved into `narrative` with a reason that reads
	#    like the others. Every other test in the file accepts it; the pinned set and the named
	#    closure are the two that do not.
	('a carried claim is filed as narrative to make it disappear', S,
	 "	('AI-003', 'Value', 'This is how the app contributes to detecting the *next* outbreak before it is clinically recognised.', 'carried', 'afya.ai.service:WARNING_Z', None),",
	 "	('AI-003', 'Value', 'This is how the app contributes to detecting the *next* outbreak before it is clinically recognised.', 'narrative', None, 'a statement about what the product is for, which is an argument rather than a capability'),",
	 'test_the_narrative_claims_are_the_ones_no_code_can_carry'),

	# 4. An `ON_DEVICE` reason goes back to citing a carrier that does not exist — the state INF-015
	#    was actually in. It names a harmony tag the seed corpus has never carried, which is a
	#    citation pointing at nothing: a reader who chases it finds no herbal tag and no herbal item,
	#    and the capability is one module over in `afya.info.myths`. The mutation restores the false
	#    reason rather than inventing a new one, so the canary is the real defect reproduced.
	('a corpus reason cites a tag the corpus does not have', F,
	 "	'INF-015': 'traditional and herbal safety is the `cure_claim` correction in afya.info.myths',",
	 "	'INF-015': 'herbal-safety items are in the health library corpus (harmony tag `herbal-safety`)',",
	 'test_the_corpus_reasons_name_a_tag_the_corpus_has'),
]

_FILES = ['tests/ci/test_content_audit.py', 'tests/ci/test_feature_coverage.py']


def _node(canary_node: str) -> str:
	"""Resolve a bare test name to `file::name` by asking pytest, so a renamed or moved test fails
	here rather than being reported as a canary that fired against nothing."""
	for f, names in _KNOWN.items():
		if canary_node in names:
			return f'{f}::{canary_node}'
	raise AssertionError(f'no test file declares {canary_node}')


_KNOWN: dict[str, set[str]] = {}
for _f in _FILES:
	_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only', _f],
		cwd=ROOT, capture_output=True, text=True)
	assert _collected.returncode == 0, _collected.stdout[-2000:]
	_KNOWN[_f] = {line.strip().split('::')[-1] for line in _collected.stdout.splitlines() if '::' in line}

_missing = sorted({c[-1] for c in CANARIES if not any(c[-1] in v for v in _KNOWN.values())})
assert not _missing, f'canaries name tests that do not exist: {_missing}'


failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_claim_coverage.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	# The node resolves to the file that declares it rather than to a fixed path. Canary #4 aims at
	# a test in `test_feature_coverage.py` while #1-#3 aim at `test_content_audit.py`, and a
	# hardcoded target would make #4 fail collection — which reads as CAUGHT while proving nothing.
	target = _node(node)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', target],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		# Caught for the *right* reason: the failure must name the node the canary aimed at, not a
		# collection error or a sibling's breakage from the same edit.
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	ok = caught and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
