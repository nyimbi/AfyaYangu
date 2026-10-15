"""Canaries for §17.6's last line: "Extra protections for adolescent reproductive health data".

The unit adds a filter to the wallet's read paths, and every canary here is about a way that filter
can be *absent while the tests still pass*. The class this repo keeps meeting: a control fitted to
one door while the same data is served through another.

The five worth reading as a set:

* **#1** removes the filter from `documents()`, which is the chokepoint every reader passes through.
  The service-level test and the front-door test both fail, which is the point — the protection is
  not a claim on one route.
* **#2** is the second door. `_lab_document` files a lab as a wallet document, so filtering the
  envelope alone withholds a pregnancy test there and serves the same result through
  `/records/{ref}/labs` as a typed row. The mutation removes the filter from `labs()` only, and the
  front-door test catches it while the service-level test would not — which is why both exist.
* **#3** makes the classifier read a caller-supplied flag instead of the document's own fields. This
  is the failure the whole design is arranged against: the person filing the record is the person
  the protection is *from*.
* **#4** drops the lower bound of the adolescent band, so every minor's record is withheld from
  their parent — §17.6's third line taken away by the last line, which is the protection widening
  itself past the sentence it implements.
* **#5** is the argument a new route forgets. `documents()` and `labs()` take a *member* first, so
  nothing in the call says who is reading and the filter is opt-in — a route that omits `reader=`
  serves the guardian everything and every behavioural test still passes. Only the call-site gate in
  `test_wallet.py` catches it, which is the evidence that gate is load-bearing rather than
  decorative.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line is a failure of this script. `__pycache__` is purged
after each write, for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
R = ROOT / 'src/afya/records/service.py'
C = ROOT / 'src/afya/women/content.py'
G = ROOT / 'src/afya/service.py'

CANARIES = [
	# 1. The chokepoint stops filtering. `reader` is still accepted and still threaded through every
	#    caller, so nothing else changes — the guardian simply sees everything again.
	('the wallet stops withholding anything from the guardian', R,
	 """		if reader is not None:
			held = [d for d in held if self.readable(reader, d, today)]""",
	 """		if reader is not None and False:
			held = [d for d in held if self.readable(reader, d, today)]""",
	 'test_a_guardian_cannot_read_an_adolescents_reproductive_documents'),

	# 2. The second door. Only `labs()` stops filtering; the envelope still does. The service-level
	#    test passes and the front-door test fails, which is exactly why the front-door test exists.
	('the typed lab route serves what the envelope withholds', R,
	 """		if reader is not None and reader != member_ref:
			from afya.women.content import is_reproductive_health_data
			held = [l for l in held
			        if not is_reproductive_health_data(kind='lab', **_lab_text(l))]""",
	 """		if reader is not None and reader != member_ref and False:
			from afya.women.content import is_reproductive_health_data
			held = [l for l in held
			        if not is_reproductive_health_data(kind='lab', **_lab_text(l))]""",
	 'test_the_protection_holds_at_the_front_door_and_on_both_doors'),

	# 3. The classifier trusts the caller. A `sensitive` flag on the request would be a value the
	#    person filing the record attests about itself, and the case this exists for — a guardian
	#    filing their daughter's contraceptive under a benign title — is the case it would be set
	#    False on. The mutation reads that flag instead of the document.
	('the classifier trusts a caller-supplied flag instead of the document', C,
	 """	haystack = f'{kind} {title} {detail}'.lower()""",
	 """	haystack = ''  # a caller-supplied flag would be read here
	_ = (kind, title, detail)""",
	 'test_the_classifier_reads_the_document_and_not_a_caller_supplied_flag'),

	# 4. The band loses its lower bound, so a six-year-old's record is withheld from their parent.
	#    §17.6's third line gives the guardian that record; the last line must not take it away.
	('every minor is treated as an adolescent', R,
	 """		if not (ADOLESCENT_YEARS[0] <= age <= ADOLESCENT_YEARS[1]):
			return True""",
	 """		if not (0 <= age <= ADOLESCENT_YEARS[1]):
			return True""",
	 'test_an_adult_guardian_reads_everything_and_so_does_a_young_childs'),

	# 5. A route stops saying who is reading. `documents()`/`labs()` still filter for every caller
	#    that passes a reader, and every behavioural test still passes — the route simply omits the
	#    argument, so the guardian sees everything through that one door. This is the mutation the
	#    call-site gate exists for. It is on the *labs* route rather than `/documents` deliberately:
	#    the front-door test names the documents route, so a canary there would be caught by that
	#    test and would prove nothing about the gate.
	('a route serves a member without saying who is reading', G,
	 """		return [l.model_dump(mode='json') for l in records.labs(ref, reader=_subject)]""",
	 """		return [l.model_dump(mode='json') for l in records.labs(ref)]""",
	 'test_every_route_that_serves_a_member_says_who_is_reading'),
]

# Every canary node names a test in one of these files; a canary whose test does not exist would
# "pass" for the wrong reason, so collection is asserted before anything is mutated.
_FILES = ['tests/ci/test_records.py', 'tests/ci/test_wallet.py']


def _node(canary_node: str) -> str:
	"""Resolve a bare test name to `file::name` by asking pytest, so a renamed test is caught."""
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
	backup = pathlib.Path(f'/tmp/canary_children_176.{path.name}.bak')
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
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
