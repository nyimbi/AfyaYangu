"""Canary for §ACC-002's `tts` flag: a served field that was a restatement of another field.

`LANGUAGE_MATRIX` carries `tier` (the spec's launch priority order) and `tts` (whether a spoken form
of the language exists). Every tier-1 row carried `tts: True`, so the two fields were the same fact
written twice — and `tts` is *served* on `/access/languages`, so a client was told Dholuo, Luhya
(Bukusu) and Kikuyu had text-to-speech while `answerable()` composed their replies in English.

The mutation is the pre-fix value on the one row that makes the difference visible: Dholuo is tier 1
and has no table, so restoring `tts: True` on it is exactly the state the fix removed. A canary that
passes is a bug in the canary, so a MISSED line fails this script.

The second mutation is the stronger form — it makes `tts` equal `tier == 1` on *every* row, which is
what the defect was in general rather than on one language. A test that only looked at Dholuo would
miss it; the assertion in `test_acc002.py` walks every row against the served reply, so this must
fail too.

`__pycache__` is purged after each write and after each revert. `access/views.py` is imported by six
modules, so a stale `.pyc` would let the mutation outlive its revert.

Reverted from a `cp` backup, never with `git checkout --`: the mutation and the real change live in
the same uncommitted tree.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
VIEWS = ROOT / 'src/afya/access/views.py'
NODE = ('tests/ci/test_acc002.py::'
        'test_the_tts_flag_says_whether_a_voice_exists_not_which_tier_a_language_is')

CANARIES = [
	# 1. Dholuo goes back to advertising a voice it does not have. This is the pre-fix literal.
	('a tier-1 language with no table advertises text-to-speech', VIEWS,
		"\t'Dholuo': {'code': 'luo', 'tier': 1, 'asr': False, 'tts': False},",
		"\t'Dholuo': {'code': 'luo', 'tier': 1, 'asr': False, 'tts': True},",
		NODE),

	# 2. The general form: `tts` collapses back into `tier == 1` on the two other rows that differ.
	#    Mutating Dholuo alone would leave the class of the bug untested; these three together are the
	#    old matrix exactly.
	('tts becomes tier == 1 restated on every row that differs', VIEWS,
		"\t'Luhya (Bukusu)': {'code': 'bxk', 'tier': 1, 'asr': False, 'tts': False},\n"
		"\t'Luhya (Maragoli)': {'code': 'rag', 'tier': 2, 'asr': False, 'tts': False},\n"
		"\t'Kalenjin': {'code': 'kln', 'tier': 2, 'asr': False, 'tts': False},\n"
		"\t'Kikuyu': {'code': 'ki', 'tier': 1, 'asr': False, 'tts': False},",
		"\t'Luhya (Bukusu)': {'code': 'bxk', 'tier': 1, 'asr': False, 'tts': True},\n"
		"\t'Luhya (Maragoli)': {'code': 'rag', 'tier': 2, 'asr': False, 'tts': False},\n"
		"\t'Kalenjin': {'code': 'kln', 'tier': 2, 'asr': False, 'tts': False},\n"
		"\t'Kikuyu': {'code': 'ki', 'tier': 1, 'asr': False, 'tts': True},",
		NODE),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_tts_flag.{path.name}.bak')
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
