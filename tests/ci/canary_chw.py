"""Canaries for tests/ci/test_chw.py and tests/ci/test_intermediaries.py.

§CHAN-5's "Printed job aids and flip charts" names two artefacts, and the tree held both halves of
one of them without joining them: `JOB_AIDS` is the aid text and `afya.records.pdf` is a printable
writer, so a job aid was a string a screen showed and nothing a worker could carry. The unit that
joined them added `ChwService.job_aid_sheet` and `/chw/job-aid/{topic}/print`, and these canaries
are the cheap wrong versions.

*A `.pdf` filename with the aid text inside it is the claim, not the document.* The records module
keeps finding this shape and writes it down — "a route returning a `.pdf` filename with JSON inside
it would be exactly the claim-with-nothing-behind-it". **#1** is that: the sheet returns the aid
string with the media type and suffix it should have been, and the structural assertion (header,
trailer) is what catches it while a test checking `media_type == 'application/pdf'` passes.

*An unwrapped aid runs off the page.* The aids are single long sentences, and `render` does not wrap
for you — a caller that passes the raw text draws one line past the margin, which the writer's own
docstring says is the failure it cannot recover from. **#2** drops the `wrap`. It fired on the second
run and **missed on the first**, and the miss is the finding worth recording: the test checked that
every *word* of the aid survived into the stream, and an unwrapped line contains every word — the
words are all present, they are simply drawn off the page. The test now asserts the drawn lines fit
the column, which is the property the wrap exists for.

*The aid must be the aid.* **#3** renders a *different* topic's text under the requested title — the
copy-paste slip a per-topic generator invites, caught only because the test walks every word of the
aid into the stream rather than checking the header.

*A title is not a slug.* **#4** sets the printable title to the topic key, so the sheet's heading is
`ppe_donning` — an internal identifier on a printed page a person reads, which is §3.3 principle 9
the other way round.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line fails this script. The `__pycache__` purge
after each write is load-bearing for the reason `canary_inf001.py` documents: a same-second write
of the same size reuses the previous canary's bytecode and the canary then tests code it never
mutated.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/chw/service.py'
V = ROOT / 'src/afya/chw/views.py'

CANARIES = [
	# 1. The sheet is a string wearing a PDF's clothes. The media type and the filename are right and
	#    the bytes are the aid text, which is exactly the defect `records` keeps recording.
	('the printable sheet is the raw aid text with a PDF filename', S,
		"			filename=f'job-aid-{topic}.pdf', content=render(title, lines).decode('latin-1'),",
		"			filename=f'job-aid-{topic}.pdf', content=JOB_AIDS[topic],",
		'test_every_job_aid_renders_as_a_printable_sheet'),

	# 2. The aid is not wrapped. `render` draws one line per element and does not break a long one, so
	#    a single-sentence aid becomes a single line running past the margin and off the page.
	('the aid is passed to the writer unwrapped', S,
		"		lines = wrap(JOB_AIDS[topic])",
		"		lines = [JOB_AIDS[topic]]",
		'test_every_job_aid_renders_as_a_printable_sheet'),

	# 3. The wrong topic's text is rendered under the requested title. The copy-paste slip a per-topic
	#    generator invites; caught because the test walks every word of the aid into the stream.
	('one topic is rendered with another topic’s text', S,
		"		lines = wrap(JOB_AIDS[topic])",
		"		lines = wrap(JOB_AIDS['ppe_donning'])",
		'test_every_job_aid_renders_as_a_printable_sheet'),

	# 4. The title is the topic key. A printed sheet's heading becomes `ppe_donning`, an internal
	#    identifier on a page a person reads — §3.3 principle 9, which governs print as much as screen.
	('the printable title is the internal topic key', V,
		"	'ppe_donning': 'Putting on PPE',",
		"	'ppe_donning': 'ppe_donning',",
		'test_the_job_aid_titles_are_the_aids_and_name_no_spec_code'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_chw.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_chw.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
