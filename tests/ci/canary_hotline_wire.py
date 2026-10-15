"""Canaries for the §18.4–§18.5 sweep: two wires that acknowledged writes they never made.

§18's checkable claim is the **Direction** column of each table. §18.4's fifth row is inbound
("Call outcome | 719 → App | Outcome code (where consented) | On close") and §18.5's second row is
outbound to a national registry ("Facility status updates | App → MoHF | Crowdsourced corrections |
On report"). Both routes existed, both were reachable, and both were wrong in the one way a
code-exists check cannot see.

* **#1 is the write that never happened.** `POST /integrations/hotline/outcome` returned
  `{'recorded': True, 'outcome_code': code}` and stored nothing — `grep` found `outcome_code` read
  only at the line that took it off the payload and the line that echoed it back, so the section's
  inbound row was a wire reporting a write it never made. Reverting the call to
  `record_call_outcome` restores exactly that, and only a test that reads the code back off the
  ledger can see it.
* **#2 is the outcome landing on the wrong call.** The queue is ordered and a person who asks twice
  is rung twice, so the code has to settle the *oldest open* request. Taking the most recent one is
  the plausible-looking bug: every assertion about "an outcome was recorded" still passes, and the
  wrong call is closed.
* **#3 is the open proxy to the national registry.** §18.5's correction route carried no guard while
  both its siblings on the same block carried `infrastructure`. Probed through the front door it
  answered 502, which is the proof it reached the vendor code path — so a caller with no token could
  spend this deployment's MoHF credentials on a correction of their choosing. Reverting the guard is
  the defect as it shipped.
* **#4 is the row made unreachable for two of its own three calls.** The first cut of this fix hung
  the outcome on the callback queue and refused a code with no open request behind it. §18.4's rows 1
  and 2 — the one-tap call and the auto-call on fall detection — are dispatched from the SOS path and
  file no `CallbackRequest`, so that refusal dropped the section's last row for two of the three calls
  it closes. It is the strict-subset failure, and the full suite caught it through the pre-existing
  webhook fixture before this canary did; the canary is here so the *shape* stays caught.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line fails this script. `__pycache__` is purged
after each write, for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
G = ROOT / 'src/afya/service.py'
C = ROOT / 'src/afya/channels/service.py'

CANARIES = [
	# 1. The outcome code is received and dropped again — the defect as it shipped. The route still
	#    answers `recorded: True`, so every assertion about the acknowledgement passes; only the read
	#    back off the ledger fails.
	('the hotline outcome is acknowledged and stored nowhere', G,
	 """		try:
			outcome = channels.record_call_outcome(code, msisdn)""",
	 """		try:
			outcome = None
			_ = (code, msisdn)""",
	 'test_hotline_follow_up_lands_in_the_feed'),

	# 2. The code settles the *newest* open request rather than the oldest. Every "an outcome was
	#    recorded" assertion still passes; the call that was actually closed is left open and a later
	#    one is marked answered.
	('the call outcome settles the wrong request', C,
	 """				settled = open_calls[0]""",
	 """				settled = open_calls[-1]""",
	 'test_a_call_outcome_settles_the_request_it_closes'),

	# 3. The §18.5 correction route loses its guard — the defect as it shipped, and the only route on
	#    that block that could reach MoHF's intake with no token at all.
	('the facility correction route is an open proxy again', G,
	 """	async def facility_correction(facility_id: str, correction: dict[str, object],
	                              _subject: str = Depends(require_scope('infrastructure'))) -> dict[str, object]:""",
	 """	async def facility_correction(facility_id: str, correction: dict[str, object]) -> dict[str, object]:""",
	 'test_the_facility_correction_route_is_guarded_like_its_siblings'),

	# 4. The outcome refuses a call with no queue entry behind it — rows 1 and 2 of the section's own
	#    table made unreachable. The mutation is the first cut's `raise KeyError` on no match, which
	#    every assertion about a *settled* call still passes.
	('the outcome is refused for a call that filed no request', C,
	 """			if open_calls:
				settled = open_calls[0]
				settled.handled = True""",
	 """			if not open_calls:
				raise KeyError(normalised)
			settled = open_calls[0]
			settled.handled = True""",
	 'test_a_call_outcome_settles_the_request_it_closes'),
]

# Every canary node names a test in one of these files; a canary whose test does not exist would
# "pass" for the wrong reason, so collection is asserted before anything is mutated.
_FILES = ['tests/ci/test_integrations.py', 'tests/ci/test_chan_callbacks.py']


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
	backup = pathlib.Path(f'/tmp/canary_hotline_wire.{path.name}.bak')
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
