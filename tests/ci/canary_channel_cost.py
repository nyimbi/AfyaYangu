"""Canaries for tests/ci/test_channel_cost.py.

§5.2's cost-to-user column and §3.3 principle 3 ("Zero-rated or it doesn't count"). The module was
written because `SmsOut.zero_rated` defaulted to `True` — a claim that could not come out false. The
canaries are the cheap wrong versions of the same shape, one level further in.

*A `verified` boolean is not a sentence, and the sentence is what a person reads.* The module's own
docstring states the rule it must keep — "'The rules were never pulled' and 'the rules were pulled
and do not cover this' are different facts" — and the code kept it for `charged` while breaking it for
the prose. WhatsApp names no destination prefix in §5.2, so `rule_prefix_hint` is None and no pulled
rule can ever match; `verified` is False for an empty *pulled* list, a list with rules in it, and a
list that was never pulled, and the sentence said "have not been pulled" for all three. It is served
at a public route, so the payload told a reader that a pull that happened did not. **#1** is that
collapse restored. It is the reason this file exists: `test_channel_cost.py` had no canary, so the
wrong sentence survived every gate the repo had.

*A gate that cannot fail is the finding, not the gate.* `zero_rating_gaps` can only ever name `sms`,
because `whatsapp` is unverifiable by construction — so the gap report is correct and structurally
unable to say anything about the channel §5.3's own cell marks "(zero-rated)". **#2** makes that
explicit rather than leaving it to be rediscovered: it flips the hint so the gate *could* fire, which
must change the report. A canary that passes here would mean the report is insensitive to the one
input that decides it.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary that
passes is a bug in the canary, so a MISSED line fails this script. The `__pycache__` purge after each
write is load-bearing for the reason `canary_inf001.py` documents: a same-second write of the same
size reuses the previous canary's bytecode and the canary then tests code it never mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
CO = ROOT / 'src/afya/channels/cost.py'

CANARIES = [
	# 1. The two ways a claim is unconfirmed collapse back into one sentence. This is the defect: the
	#    boolean stays right and the prose asserts a pull that happened did not. The mutation is the
	#    pre-fix line, so the test that was written for it must fail.
	('the pulled-and-unmatchable sentence reverts to "have not been pulled"', CO,
		"		if not pulled:\n"
		"			return (\n"
		"				f'{name} is meant to be free, and the carrier’s billing rules have not been pulled, so '\n"
		"				f'nothing has confirmed it.'\n"
		"			)",
		"		if True:\n"
		"			return (\n"
		"				f'{name} is meant to be free, and the carrier’s billing rules have not been pulled, so '\n"
		"				f'nothing has confirmed it.'\n"
		"			)",
		'test_the_two_ways_a_claim_is_unconfirmed_are_told_apart_in_the_sentence'),

	# 2. The gap report stops being sensitive to the destination hint. `covering_rule` reads the
	#    channel's own `rule_prefix_hint`, which is what stops a shortcode rule being mistaken for
	#    WhatsApp data coverage; removing the guard lets any rate-0 rule match a channel with no
	#    destination, which is the false free claim the module was written to kill.
	('a rule matches a channel that names no destination', CO,
		"	if not row.zero_rating_required or row.rule_prefix_hint is None:\n		return None",
		"	if not row.zero_rating_required:\n		return None",
		'test_a_shortcode_rule_does_not_cover_whatsapp'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_channel_cost.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_channel_cost.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_channel_cost.{path.name}.bak')
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
