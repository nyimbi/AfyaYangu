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
