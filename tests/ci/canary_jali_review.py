"""Canaries for §18.2's clinician-review wire, which was four defects in one route pair.

The route `GET /integrations/jali/assessments/{assessment_id}/review` is the app's half of the
section's fourth row — "Health worker review | JALI → App | Clinician response | On review" — and it
had no guard, no reachable id, and no failure branch; the push beside it enforced consent in one of
its two ports. Each is a way the wire can look present while being a disclosure, a dead end, or a
control at half the paths, and each gets a canary because a fix you have never watched revert is a
fix you have not tested.

* **#1 is the disclosure.** The route carried no dependency at all, so it answered 200 to a caller
  with no token. Reverting the guard is the defect exactly as it shipped.
* **#2 is the dead end.** The push returned a boolean and discarded JALI's response, so the app
  never learned the id the review is pulled by. Reverting the return to a boolean makes the wire
  unreachable *without* making any guard test fail — which is why the front-door test asserts the
  ref comes back rather than only that the route exists.
* **#3 is the surface gate's own blind spot.** `test_self_scope.py`'s app-wide gate keys on a route
  naming a *subject*; this one names an `assessment_id`, so it sat outside that gate's jurisdiction
  while serving exactly the data the gate exists for. The canary plants the unguarded route under
  that vendor-shaped name and asserts the §18-scoped gate refuses it — the app-wide gate cannot,
  which is the reason this one was written.
* **#4 is the half-applied control.** The consent rule lived only in `JaliClient`, and JALI has two
  ports: the client, and `InlineJaliPort`, which is what runs when no JALI key is configured. The
  offline port accepted an unconsented summary and answered 200 while the online one refused the
  identical call. Deleting the boundary check restores that split exactly.

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
G = ROOT / 'src/afya/service.py'
C = ROOT / 'src/afya/integrations/service.py'

CANARIES = [
	# 1. The review route loses its guard — the defect as it shipped. The front-door test fails on
	#    the 200-with-no-token assertion, and the surface gate fails naming the route.
	('the clinician review route serves a person with no guard', G,
	 """	async def jali_review(assessment_id: str, _subject: str = Depends(require_scope('assigned', purpose='case_management'))) -> dict[str, object]:""",
	 """	async def jali_review(assessment_id: str) -> dict[str, object]:""",
	 'test_the_clinician_review_route_refuses_a_caller_with_no_token'),

	# 2. The push discards the vendor's reference again, so no client can ever hold the id the review
	#    is pulled by. The route still exists and is still guarded, so only a test that drives the
	#    wire end to end can see it.
	('the assessment push stops returning the id the review needs', C,
	 """		return str(resp.json().get('assessment_ref', ''))""",
	 """		return ''""",
	 'test_jali_full_wire'),

	# 3. A new unguarded route joins the surface under a vendor-shaped name. The app-wide gate in
	#    `test_self_scope.py` keys on subject names and cannot see it; the §18-scoped gate must.
	('an unguarded route joins the surface under a vendor name', G,
	 """	@app.get('/integrations/jali/assessments/{assessment_id}/review')""",
	 """	@app.get('/integrations/jali/assessments/{assessment_id}/notes')
	async def jali_notes(assessment_id: str) -> dict[str, str]:
		return {'notes': assessment_id}

	@app.get('/integrations/jali/assessments/{assessment_id}/review')""",
	 'test_the_integration_surface_has_no_unguarded_person_route'),

	# 4. The consent check leaves the boundary and goes back to living only in `JaliClient`. The
	#    offline port — the default when no JALI key is configured — then accepts an unconsented
	#    summary and answers 200, which is the state this was found in. The mutation is the deletion
	#    of the boundary check, so the online path stays guarded and only the front-door test on the
	#    offline port can see it.
	('the consent rule goes back to living in one of two ports', G,
	 """		if summary.get('consented') is not True:
			raise HTTPException(status_code=403, detail='assessments are shared only with consent')
		try:
			ref = await jali.share_assessment(dict(summary))""",
	 """		try:
			ref = await jali.share_assessment(dict(summary))""",
	 'test_an_unconsented_assessment_is_refused_at_the_boundary_not_only_in_the_client'),
]

# Every canary node names a test in one of these files; a canary whose test does not exist would
# "pass" for the wrong reason, so collection is asserted before anything is mutated.
_FILES = ['tests/ci/test_integrations.py']


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
	backup = pathlib.Path(f'/tmp/canary_jali_review.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# A same-second write of the same size reuses the previous canary's bytecode, and the canary then
	# tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', _node(node)],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
		# Caught for the *right* reason: the failure must name the node the canary aimed at. A
		# collection error from a malformed patch also exits non-zero, and reading that as CAUGHT is
		# how a canary that never ran gets recorded as one that fired.
		aimed = node in proc.stdout
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
		for cache in path.parent.rglob('__pycache__'):
			shutil.rmtree(cache, ignore_errors=True)
	ok = caught and aimed
	print(f'{"CAUGHT " if ok else "MISSED "} {name}')
	if not ok:
		failures.append(name)
		print(f'  returncode={proc.returncode} aimed_at_node={aimed}')
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
