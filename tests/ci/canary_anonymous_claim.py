"""Canary for the anonymous-subject gate in tests/ci/test_auth.py.

The mutation restores the route as it shipped — `issue_anonymous(req.subject_ref)` — while leaving
the gate alone. The canary is run against the whole test node, so a gate that passes on the planted
defect is a gate that never read the thing it names.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
SVC = ROOT / 'src/afya/service.py'
GATE = 'tests/ci/test_auth.py::test_an_anonymous_subject_cannot_be_claimed_by_a_stranger'

# The route's body after the fix, reduced to the shipped one-liner. Anchored on the docstring's
# closing line so the replacement cannot match a different function.
OLD = """		if req.subject_ref is None:
			token = await auth.issue_anonymous()
			return token.model_dump(mode='json')
"""
NEW = """		token = await auth.issue_anonymous(req.subject_ref)
		return token.model_dump(mode='json')
		if False:
"""
backup = pathlib.Path('/tmp/canary_anon.service.py.bak')
shutil.copy2(SVC, backup)
s = SVC.read_text()
assert s == backup.read_text(), 'the backup is not this file'
count = s.count(OLD)
assert count == 1, f'target not unique/found ({count})'
SVC.write_text(s.replace(OLD, NEW))
try:
	proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', GATE],
		cwd=ROOT, capture_output=True, text=True)
	caught = proc.returncode != 0
finally:
	shutil.copy2(backup, SVC)
	assert SVC.read_text() == s, 'revert did not restore'
print('CAUGHT ' if caught else 'MISSED ', 'a stranger claims any anonymous subject')
if not caught:
	print(proc.stdout[-1500:])
sys.exit(0 if caught else 1)
