"""Canaries for tests/ci/test_sec006.py.

§SEC-006's second Feature was `missing` while a model named `TransparencyReport` existed, was
tested, and was the *first* Feature of the same section. The defect is not an absence of code — it
is a document about a person standing in for a publication to the public, and the canaries are the
cheap ways to reproduce that substitution and its neighbours:

* **#1** is the defect exactly as it was found: the publication draws from the subject register.
* **#4** is the subtlest of the set — the read records the publication. It looks like tidiness and
  it means any reader can mark a duty met, including for a quarter that has not ended.
* **#7** and **#8** are the two halves of the cadence claim: without the third state a quarter
  still running is indistinguishable from a met one, and without `missing_periods` a skipped quarter
  is averaged away by the count of the ones that were published.
* **#9** is the substitution the whole unit is about: a public route answered with a token required.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
RS = ROOT / 'src/afya/retention/service.py'
G = ROOT / 'src/afya/service.py'
M = ROOT / 'src/afya/mobile/actions.py'
RV = ROOT / 'src/afya/retention/views.py'

CANARIES = [
	# 1. The published model grows a field for a person. It is the substitution the whole unit is
	#    about, one level down: a document that names nobody acquires the vocabulary of one that
	#    does, and the next change fills it in. (The first version of this canary added an unused
	#    local to the builder, which is not a defect at all — the mutation has to be the shape the
	#    test looks for, not merely a change.)
	('the published model carries a field for a person', RV,
	 "\tperiod: str\n\tgenerated_at_iso: str\n\tcadence_days: int = Field(gt=0)\n\taudience: str",
	 "\tperiod: str\n\tsubject_ref: str | None = None\n\tgenerated_at_iso: str\n\tcadence_days: int = Field(gt=0)\n\taudience: str",
	 'test_the_publication_names_no_person_and_no_spec_code'),

	# 2. The min-cell rule is recomputed here against a threshold of the publication's own, so a cell
	#    §11.7's dashboard withheld comes back with a number in the public document. This is the
	#    "second place the rule lives" the module docstring warns about.
	('the publication applies its own threshold', RS,
	 "\t\t\t\t\twithheld_cells=dash.suppressed_cells,",
	 "\t\t\t\t\twithheld_cells=0,",
	 'test_a_suppressed_cell_does_not_reappear_in_the_publication'),

	# 3. A source that was never wired is silently skipped, so a deployment gap reads as a quiet
	#    quarter. The section is empty and nothing says why.
	('an unwired source is omitted rather than named', RS,
	 "\t\t\tabsent.append('dashboards')",
	 "\t\t\tpass",
	 'test_a_source_that_is_not_wired_is_named_rather_than_omitted'),

	# 4. The read records the publication. It looks like tidiness — one call instead of two — and it
	#    means any reader satisfies the schedule by looking at it, including for a quarter that has
	#    not ended. This is the canary that makes `build_publication` and `publish` two methods.
	('the read records a publication', RS,
	 "\t\tsections, absent = self._publication_sections(as_at_iso)",
	 "\t\tsections, absent = self._publication_sections(as_at_iso)\n\t\tself._publications[period] = as_at_iso",
	 'test_building_a_publication_does_not_record_one'),

	# 5. The publication route is guarded, so the quarterly *public* report needs a token and is not
	#    public. The bullet's own claim, refuted by the front door.
	('the public report needs a token', G,
	 "\tasync def transparency_publication(period: str, as_at_iso: str) -> dict[str, object]:",
	 "\tasync def transparency_publication(period: str, as_at_iso: str, _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:",
	 'test_the_public_route_serves_with_no_token'),

	# 6. The recording route is left open, so a citizen token marks a quarter published and the
	#    schedule reports a duty met that nobody performed.
	('recording a publication is unguarded', G,
	 "\tasync def transparency_publish(period: str, as_at_iso: str,\n\t                               _subject: str = Depends(require_scope('audit_logs'))) -> dict[str, object]:",
	 "\tasync def transparency_publish(period: str, as_at_iso: str) -> dict[str, object]:",
	 'test_recording_a_publication_is_guarded_and_the_read_is_not'),

	# 7. The third state collapses: a quarter that has not ended reports `due`, which is the same
	#    answer a quarter that ended unpublished gives. A boolean cannot tell them apart.
	('a quarter still running reports overdue', RS,
	 "\t\telif today <= end:\n\t\t\tstatus = PublicationStatus.not_yet_due",
	 "\t\telif False:\n\t\t\tstatus = PublicationStatus.not_yet_due",
	 'test_a_quarter_that_has_not_ended_is_not_yet_due_rather_than_overdue'),

	# 8. A skipped quarter is not named. Two periods published with one between them missing reports
	#    two publications and no gap, which is the overstatement a count makes.
	('a skipped quarter is not named', RS,
	 "\t\t\t\tmissing.append(candidate)",
	 "\t\t\t\tpass",
	 'test_a_skipped_quarter_is_named_rather_than_averaged_away'),

	# 9. The publication is not the document the audit row names — the row goes back to the
	#    per-subject report while the aggregate is built beside it. The substitution itself.
	('the row names the personal report', RS,
	 "\tdef build_publication(self, period: str, as_at_iso: str) -> TransparencyPublication:",
	 "\tdef build_publication_aggregate(self, period: str, as_at_iso: str) -> TransparencyPublication:",
	 'test_the_publication_is_the_document_the_audit_row_names'),

	# 10. The period is pattern-matched rather than parsed, so `2026-Q5` and `last quarter` are
	#     accepted and reported as missing quarters forever instead of as inputs to fix.
	('the period is not parsed', RS,
	 "\t\tif not (year_s.isdigit() and q_s.isdigit() and 1 <= int(q_s) <= 4):\n\t\t\traise ValueError(f'{period!r} does not name a quarter (expected e.g. 2026-Q3)')",
	 "\t\tif not year_s:\n\t\t\traise ValueError(f'{period!r} does not name a quarter (expected e.g. 2026-Q3)')",
	 'test_a_period_that_is_not_a_quarter_is_refused'),

	# 11. The window's end is computed by adding a month's worth of days, which reports 1 March for
	#     Q1 — a window that ends before it starts, and a schedule that is late in the wrong quarter.
	('the quarter end is off by a month', RS,
	 "\t\topens = date(year + 1, 1, 1) if q == 4 else date(year, q * 3 + 1, 1)\n\t\treturn (opens - timedelta(days=1)).isoformat()",
	 "\t\treturn date(year, q * 3, 1).isoformat()",
	 'test_the_period_end_is_the_last_day_of_the_quarter'),

	# 12. The catalogue loses the publication, so the document exists and no client can open it —
	#     a capability nobody can reach, which is the `report_stock` defect one level up.
	('the catalogue drops the public report', M,
	 "\t\t_a('public_transparency_report', 'What the programme publishes', 'Privacy', 'GET', '/transparency/report', [_f('period', 'Quarter', ph='2026-Q3'), _f('as_at_iso', 'As at')]),",
	 "",
	 'test_the_catalogue_reaches_the_publication_and_its_cadence'),

	# 13. The obligations are restated in the publication instead of read off §24's register, so the
	#     document carries a second copy of the duty list and goes stale on its own.
	('the obligations are restated', RS,
	 "\t\tfrom afya.operations.service import OBLIGATIONS\n\t\treturn sorted(o.duty for o in OBLIGATIONS if o.control is not None)",
	 "\t\treturn ['Security audit', 'Privacy policy review']",
	 'test_the_publication_reports_the_obligations_that_have_a_software_control'),

	# 14. The breach record takes a person. The register is the public shape of a breach — classes
	#     and counts — and a subject reference in it makes the transparency report personal data.
	('the breach record takes a subject', RS,
	 "\t\tassert breach.get('affected_data') is not None, 'a breach record must name the data classes'",
	 "\t\tbreach.setdefault('subject_ref', 'someone')\n\t\tassert breach.get('affected_data') is not None, 'a breach record must name the data classes'",
	 'test_the_breach_record_holds_classes_and_counts_never_a_person'),
]


def _node(canary_node: str) -> str:
	return canary_node if '/' in canary_node else f'tests/ci/test_sec006.py::{canary_node}'


_collected = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', '--collect-only',
	'tests/ci/test_sec006.py'],
	cwd=ROOT, capture_output=True, text=True)
assert _collected.returncode == 0, _collected.stdout[-2000:]
_known = {line.strip() for line in _collected.stdout.splitlines() if '::' in line}
_missing = sorted({_node(c[-1]) for c in CANARIES} - _known)
assert not _missing, f'canaries name tests that do not exist: {_missing}'

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_sec006.{path.name}.bak')
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
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
