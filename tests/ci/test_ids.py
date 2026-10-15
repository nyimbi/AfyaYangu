"""References a person reads out, and the one property they must have: no two are the same.

Written after §ACC-001's diary test failed for a reason that had nothing to do with §ACC-001. Two
`DiaryEntry`s appended back to back shared an `entry_id` — `'DIARY-' + uuid7str()[:10]` — so the
second replaced the first in the store's dict and `/triage/{ref}/diary/trend` read one day of
symptoms where there were two. The trend screen was right about the data it was given and wrong
about the person, which is the failure mode this repo keeps meeting: every part works and the join
does not.

The cause is that a UUID7 is not uniformly random. Its leading 48 bits are a millisecond timestamp,
so the first ten hex characters are constant across a **256 ms** window — long enough that anything
a person does twice in a row collides. `[-6:]` is the same mistake at the other end: 24 bits of
random field, which repeats by birthday at roughly 4,800 ids in a process.

These tests pin the guarantee rather than the implementation: a reference is distinct, and it is
eight characters, because the point of the short form is that it survives being read aloud.
"""

import ast
import pathlib

from afya.emergency.views import SOSEvent
from afya.ids import ref8, uuid7str
from afya.registry.service import FeatureRegistry
from afya.triage.service import TriageService
from afya.triage.views import DiaryEntry
from afya.women.views import ContraceptionPlan, ReproductiveReferral


def test_ref8_does_not_repeat_across_a_burst() -> None:
	"""Fifty thousand in a tight loop, which is the window the truncated UUID7 failed in.

	The size is the whole test. A burst is where an id read off a clock collides — two calls in the
	same millisecond produce the same reference — and fifty thousand calls span far more than the
	256 ms window the original defect was constant across, so the collision is certain rather than
	likely. A guard at this size is deterministic; a smaller one would make the canary flaky and a
	flaky canary is not a gate.
	"""
	ids = [ref8() for _ in range(50_000)]
	assert len(set(ids)) == len(ids), f'{len(ids) - len(set(ids))} of {len(ids)} references repeated'


def test_ref8_is_eight_hex_characters() -> None:
	"""The shape the prefix convention is built on — `'SOS-' + ref8()` is twelve characters."""
	ids = [ref8() for _ in range(500)]
	assert all(len(i) == 8 and all(c in '0123456789ABCDEF' for c in i) for i in ids)


def test_the_truncation_it_replaced_would_have_failed_this() -> None:
	"""The canary, and it is the reason this file exists.

	A test that only asserts `ref8()` is distinct says nothing about whether the thing it replaced
	was broken — it would pass against any implementation, including a correct one that was never
	needed. This asserts the *old* expression fails, so the file records the defect rather than the
	fix. A UUID7 minted in the same 256 ms shares its first ten hex; if a future Python or a future
	`uuid6` makes that untrue, this test says so instead of the property quietly becoming vacuous.
	"""
	truncated = [uuid7str().replace('-', '').upper()[:10] for _ in range(50_000)]
	assert len(set(truncated)) < len(truncated), (
		'the truncated form no longer collides, so this file no longer records a defect — check '
		'whether `ref8` is still earning its counter')


async def test_two_diary_entries_in_the_same_breath_are_two_entries() -> None:
	"""The product-level shape of the bug, on the service that lost the entry."""
	svc = TriageService(FeatureRegistry())
	for day, temp in ((1, 36.5), (2, 39.1)):
		await svc.diary_append(DiaryEntry(
			subject_ref='U1', day=day, symptoms=['fever'], temperature_c=temp))
	entries = svc.diary('U1')
	assert len(entries) == 2, f'{len(entries)} of 2 entries survived; ids {[e.entry_id for e in entries]}'
	assert {e.day for e in entries} == {1, 2}
	assert svc.diary_trend('U1').direction.value == 'worsening'


def test_the_prefixed_references_are_distinct_within_a_burst() -> None:
	"""Every model that mints its own id, since each one had the same expression."""
	sos = [SOSEvent(lat=-1.3, lon=36.8, severity='high').sos_id for _ in range(2_000)]
	assert len(set(sos)) == len(sos)
	assert all(s.startswith('SOS-') and len(s) == 12 for s in sos)

	plans = [ContraceptionPlan(subject_ref='U1', method='pill', label='Pill', reliability='typical use',
	                   prevents_sti=False, started_iso='2026-10-14').plan_id for _ in range(2_000)]
	assert len(set(plans)) == len(plans)

	refs = [ReproductiveReferral(subject_ref='U1', reason='r', services=[], unreachable=[],
	                             advise='a').referral_id for _ in range(2_000)]
	assert len(set(refs)) == len(refs)


def _truncations_in(source: str, label: str) -> list[str]:
	"""Every truncation of a UUID7 in one module's source.

	The predicate is a function of the *text*, so the canary below can point this exact walk at a
	string it wrote instead of re-deriving the rule — a canary that tests a second implementation of
	the gate proves nothing about the gate that runs. Parsing with `ast` rather than grepping is the
	other half: `afya/ids.py` and the two modules that already carry the fix *describe* this defect
	in prose, and a text scan flags its own documentation, which is a gate failing for a reason its
	operator cannot act on.
	"""
	found: list[str] = []
	for node in ast.walk(ast.parse(source, filename=label)):
		# A Subscript whose value is a `uuid7str()` call (possibly through `.replace`/`.upper`) and
		# whose slice is a `Slice` — i.e. an id truncated out of a UUID7.
		if not isinstance(node, ast.Subscript) or not isinstance(node.slice, ast.Slice):
			continue
		base: ast.expr = node.value
		while isinstance(base, ast.Call) and isinstance(base.func, ast.Attribute):
			base = base.func.value
		if isinstance(base, ast.Call) and isinstance(base.func, ast.Name) \
				and base.func.id == 'uuid7str':
			found.append(f'{label}:{node.lineno}')
	return found


def _truncated_id_sources() -> list[str]:
	"""Every truncation of a UUID7 used as an id, read out of the source tree."""
	found: list[str] = []
	for path in sorted(pathlib.Path('src/afya').rglob('*.py')):
		found += _truncations_in(path.read_text(), str(path))
	return found


def test_the_truncation_scan_sees_the_shape_it_is_looking_for() -> None:
	"""The scan's own canary, run against source it is meant to catch.

	An empty offender list is the pass condition, and an empty list is also what a scan that walks
	nothing returns. This points `_truncations_in` — the exact predicate the gate calls — at every
	spelling the tree has used, so a scan that stopped matching reports here rather than reading as
	a clean tree. A second implementation written for the canary would prove nothing about this one.
	"""
	for form in ("doc_id = 'DOC-' + uuid7str().replace('-', '').upper()[:12]",
	             "op_id = 'OP-' + uuid7str().replace('-', '').upper()[-8:]",
	             "rid = f'MH-{uuid7str()[:12].upper()}'",
	             "cid = 'CMP-' + uuid7str().replace('-', '')[-8:].upper()",
	             "sid = 'MED-' + uuid7str().replace('-', '').upper()[:6]"):
		assert _truncations_in(form, 'canary'), f'the scan no longer matches: {form}'
	assert not _truncations_in("entry_id = 'X-' + ref8()", 'canary'), 'the scan flags the fix'


def test_no_model_truncates_a_uuid7_into_a_reference() -> None:
	"""The gate the four-model fix did not have, which is why the fix stopped at four.

	`test_the_prefixed_references_are_distinct_within_a_burst` above enumerates its models by hand,
	so a model added later is not covered by it — and twenty-five fields across eleven modules were
	still reading a millisecond timestamp as a random reference while that test passed. A hand-kept
	list is the thing that drifts; the scan is over the tree, so the next model is covered the day
	it is written. `ref8()` is the counter that carries the guarantee (`afya/ids.py`).
	"""
	offenders = _truncated_id_sources()
	assert offenders == [], (
		'these read a UUID7 timestamp as a random reference, so they repeat within a 65.5-second '
		'window (or by birthday, for a trailing slice); use `ref8()`: ' + ', '.join(offenders))
