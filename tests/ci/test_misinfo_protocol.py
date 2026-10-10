"""Gate: §6.4's misinformation response protocol, which was a table with no clock behind it.

§6.4 prints six steps with an owner and an SLA each, and six myth categories "to pre-draft". Both were
prose. `MisinfoCluster` carried a velocity and a correction string and no time at all, so a rumour
could be `spiking` and `correction_published` on the call that first saw it, and nothing anywhere
measured whether the four-hour triage or the twenty-four-hour correction had happened. §6.2.7's
"correct misinformation within 24 hours" was a sentence with no clock behind it.

Two things are checked here: that the clock is *computed* rather than asserted — every deadline is
derived from a detection instant the caller supplies — and that the two categories §6.4 names with no
correction drafted are reported as gaps rather than left to be noticed.
"""
from pathlib import Path

import pytest

from afya.community.protocol import (
	CORRECTION_LANGS,
	MYTH_CATEGORIES,
	PROTOCOL,
	StepState,
	coverage,
	response_clock,
	step_statuses,
)
from afya.community.service import CORRECTION_LIBRARY, CommunityService
from afya.community.views import MisinfoSubmission
from afya.info.principles import NON_GSM7

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

HOUR = 3_600_000
DETECTED = 1_770_000_000_000


def _flag(topic: str = 'cure_claim', **kw: object) -> MisinfoSubmission:
	return MisinfoSubmission(
		submission_id=f'MIS-ABCD{kw.pop("n", 1):04d}', claim='Drinking salt water cures Ebola',
		county='Busia', medium='text', topic=topic, **kw,  # type: ignore[arg-type]
	)


# --- the clock ----------------------------------------------------------------------------------

def test_every_deadline_is_computed_from_detection_not_asserted() -> None:
	"""The point of the whole module. §6.4's SLAs are durations, so a step's due time must move when
	the detection instant moves — a table that stored absolute times would be right once."""
	for offset_hours in (0, 3, 100):
		clock = response_clock('cure_claim', DETECTED + offset_hours * HOUR, DETECTED + offset_hours * HOUR)
		assert clock.steps[1].due_at_ms == DETECTED + offset_hours * HOUR + 4 * HOUR
		assert clock.steps[3].due_at_ms == DETECTED + offset_hours * HOUR + 24 * HOUR
		assert clock.detected_at_ms == DETECTED + offset_hours * HOUR


def test_the_continuous_and_ongoing_steps_have_no_deadline() -> None:
	"""§6.4 writes steps 1 and 6 as "Continuous" and "Ongoing". Inventing an hour count for either
	would be inventing a commitment the section declines to make, so they carry none and read as
	open-ended — a state that never completes, because "continuous" is not something that finishes."""
	assert [s.sla_hours for s in PROTOCOL if s.step in (1, 6)] == [None, None]
	states = {s.step: s.state for s in step_statuses(DETECTED, DETECTED + 30 * HOUR, completed_through=0)}
	assert states[1] is StepState.open_ended and states[6] is StepState.open_ended
	assert all(s.due_at_ms is None for s in response_clock('t', DETECTED, DETECTED).steps if s.step in (1, 6))


def test_a_step_is_not_overdue_at_its_own_deadline() -> None:
	"""At the four-hour mark the triage is due, not late. The boundary matters: an off-by-one on a
	four-hour SLA is the difference between a breach report and a false alarm."""
	at_due = {s.step: s.state for s in step_statuses(DETECTED, DETECTED + 4 * HOUR, 0)}
	assert at_due[2] is StepState.due, 'at the deadline the step is due'
	just_past = {s.step: s.state for s in step_statuses(DETECTED, DETECTED + 4 * HOUR + 1, 0)}
	assert just_past[2] is StepState.overdue, 'a millisecond past the deadline is a breach'


def test_breach_is_a_fact_about_the_open_steps() -> None:
	"""`breached` is not "time has passed" — it is "work that was due was not done". A response that
	completed through step 5 inside the hour is not in breach at hour 30, and one that has done
	nothing is in breach at hour 5."""
	fast = response_clock('t', DETECTED, DETECTED + 30 * HOUR, completed_through=5)
	assert fast.breached is False, 'completed work cannot be overdue'
	slow = response_clock('t', DETECTED, DETECTED + 5 * HOUR, completed_through=0)
	assert slow.breached is True, 'four hours of triage left undone at hour five is a breach'
	early = response_clock('t', DETECTED, DETECTED + 3 * HOUR, completed_through=0)
	assert early.breached is False, 'nothing is due yet at hour three'
	assert early.next_due_ms == DETECTED + 4 * HOUR, 'the next deadline is the triage'


def test_the_clock_refuses_a_now_before_detection() -> None:
	"""A response cannot be measured before it started. The assertion is the guard against a caller
	passing the wall clock to a detection instant from the future, which would read as on time."""
	with pytest.raises(AssertionError, match='a clock needs a detection'):
		response_clock('t', DETECTED, DETECTED - HOUR)


# --- the coverage -------------------------------------------------------------------------------

def test_the_two_undrafted_categories_are_reported() -> None:
	"""§6.4 names six categories to pre-draft. Two of them had no correction anywhere: conspiracy
	narratives and stigma narratives. A correction drafted during a spike is drafted under pressure,
	which is the thing pre-drafting exists to avoid — so the gap is reported, not silently tolerated."""
	cov = coverage(CORRECTION_LIBRARY)
	assert cov.undrafted == ['conspiracy', 'stigma'], cov.undrafted
	assert {c.slug for c in MYTH_CATEGORIES} == {
		'false_cures', 'transmission', 'vaccine', 'conspiracy', 'stigma', 'burial',
	}, 'the six categories §6.4 names'


def test_a_drafted_category_is_not_reported_as_a_gap() -> None:
	"""The canary for the gate above: a coverage check that reported everything as missing would
	pass this file while telling an operator nothing. Four of the six categories do have a
	correction, and those must come back clean."""
	cov = coverage(CORRECTION_LIBRARY)
	drafted = {c.slug for c in MYTH_CATEGORIES if c.topics}
	assert drafted == {'false_cures', 'transmission', 'vaccine', 'burial'}
	assert not (drafted & set(cov.undrafted)), 'a category with a correction is not undrafted'


def test_coverage_reports_an_english_only_correction() -> None:
	"""§6.4 step 4 drafts the correction "in all relevant languages" and §6.2.4 forbids publishing
	English-only for a life-safety message. A correction missing Swahili is one the audience §3.3
	principle 8 puts first cannot read."""
	thin = {'cure_claim': {'en': 'No remedy cures Ebola.'}, 'unknown': dict(CORRECTION_LIBRARY['unknown'])}
	cov = coverage(thin)
	assert cov.untranslated == {'cure_claim': ['sw']}, cov.untranslated
	assert coverage(CORRECTION_LIBRARY).untranslated == {}, 'the shipped library is fully translated'


def test_every_correction_is_postable_on_every_channel() -> None:
	"""§6.4 step 5 publishes on "all channels simultaneously" and §6.2.6 names SMS as one. All six
	corrections carried an em dash until this module was built, so every one of them was unpostable
	on a channel the section requires — the attribution separator is now a hyphen."""
	bad = [
		f'{topic}:{lang}: {ch!r}' for topic, texts in CORRECTION_LIBRARY.items() for lang, text in texts.items()
		for ch in NON_GSM7 if ch in text
	]
	assert bad == [], f'corrections that cannot be sent as SMS: {bad}'
	assert '—' not in ''.join(t for texts in CORRECTION_LIBRARY.values() for t in texts.values())


def test_an_orphan_correction_is_visible_rather_than_hidden() -> None:
	"""`denial_claim` and `unknown` answer no category §6.4 lists. Not an error — denial is a real
	narrative — but a reader should be able to tell the section's list from the library's coverage,
	which is only possible if the difference is reported."""
	cov = coverage(CORRECTION_LIBRARY)
	assert cov.orphan_corrections == ['denial_claim', 'unknown'], cov.orphan_corrections


# --- the tables cannot drift from the section they transcribe -------------------------------------

def test_the_protocol_is_the_sections_own_table() -> None:
	"""Owners and SLAs are transcribed from §6.4, not paraphrased. If the section is revised this
	fails until the table moves with it, so the clock keeps measuring the rule that exists."""
	spec = SPEC.read_text(encoding='utf-8')
	for step in PROTOCOL:
		assert step.action in spec, f'step action {step.action!r} is not in the spec'
		assert step.owner in spec, f'owner {step.owner!r} is not §6.4’s own wording'
		assert step.sla_label in spec, f'SLA label {step.sla_label!r} is not §6.4’s own wording'
	for cat in MYTH_CATEGORIES:
		assert cat.label in spec, f'myth category {cat.label!r} is not in §6.4'
		for example in cat.examples:
			assert example in spec, f'example {example!r} is not §6.4’s own wording'


def test_the_hours_agree_with_the_label_they_are_printed_beside() -> None:
	"""The number the clock computes from and the number a reader sees are the same number.

	Checking the label against the spec is not enough: the first version of this file asserted
	`sla_label in spec` and passed while `sla_hours` had been changed to 2 beside a label that still
	said "4 hours" — the clock would then breach a step at two hours and report it as the four-hour
	SLA, which is the failure of a rate stated in one place and used in another. The hours are
	derived from the label here, so the two cannot drift apart.
	"""
	for step in PROTOCOL:
		if step.sla_hours is None:
			assert step.sla_label in ('continuous', 'ongoing'), step.sla_label
			continue
		stated = float(step.sla_label.split()[0])
		assert step.sla_hours == stated, f'step {step.step} computes from {step.sla_hours} but prints {step.sla_label!r}'


def test_a_category_the_section_prints_bare_carries_no_invented_example() -> None:
	"""§6.4 gives a parenthetical for four categories and none for two: "Vaccine myths" and "Burial
	and body-handling myths" are printed bare. The first version of this table gave the vaccine row
	['infertility', 'microchip', 'untested'] and the burial row two myths of its own — plausible, and
	not the section. A pre-drafting brief is acted on, so an invented example is an invented work
	item. The bare rows stay bare and this pins which they are."""
	bare = {c.slug for c in MYTH_CATEGORIES if not c.examples}
	assert bare == {'vaccine', 'burial'}, bare
	examples = {c.slug: c.examples for c in MYTH_CATEGORIES if c.examples}
	assert examples == {
		'false_cures': ['herbal', 'spiritual', 'pharmaceutical'],
		'transmission': ['airborne', 'mosquito-borne', 'cursed'],
		'conspiracy': ['population control', 'bioweapon'],
		'stigma': ['blaming specific communities', 'counties', 'nationalities'],
	}, examples


def test_the_clock_is_not_vacuous() -> None:
	"""A canary for the canaries: six steps, two with no deadline, and four distinct SLA hours — if
	the table collapsed, every rule above would pass while measuring nothing."""
	assert len(PROTOCOL) == 6
	assert sorted(s.sla_hours for s in PROTOCOL if s.sla_hours is not None) == [4.0, 12.0, 24.0, 24.0]
	assert len(CORRECTION_LANGS) == 2


# --- the call sites, so the clock is applied and not merely available -----------------------------

async def test_a_flagged_rumour_comes_back_with_its_clock() -> None:
	"""The cluster is what a flagger and PHEOC both read. It carried velocity and no time, so
	nothing on the surface said whether the response was running or stalled."""
	svc = CommunityService()
	cluster = await svc.flag_misinfo(_flag(), at_ms=DETECTED)
	assert cluster.detected_at_ms == DETECTED, 'the first report starts the clock'
	assert cluster.next_due_at_ms == DETECTED + 4 * HOUR, 'the next deadline is the triage'
	assert cluster.response_overdue is False
	# A later report does not restart the clock: the rumour was detected when it was detected.
	later = await svc.flag_misinfo(_flag(n=2), at_ms=DETECTED + 6 * HOUR)
	assert later.detected_at_ms == DETECTED, 'detection is the first sighting, not the latest'
	assert later.response_overdue is True, 'six hours with no triage is a breach, and the surface says so'


async def test_the_protocol_view_serves_the_steps_and_the_gaps() -> None:
	"""Served rather than documented. A coverage report that exists only in a test is one an operator
	cannot read, and PHEOC is the owner of the step that is most often late."""
	import httpx

	from afya.service import build_services, create_app
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/community/misinformation/protocol')).json()
	assert [s['action'] for s in body['steps']] == ['Detect', 'Triage', 'Verify', 'Draft correction', 'Publish', 'Monitor']
	assert body['steps'][1]['owner'] == 'PHEOC risk communication team'
	assert body['steps'][1]['sla_hours'] == 4
	assert body['coverage']['undrafted'] == ['conspiracy', 'stigma'], 'the served report must name the gaps'


async def test_the_pheoc_feed_carries_the_deadline() -> None:
	"""PHEOC owns the triage step and reads this feed hourly. A cluster that arrives `spiking` with no
	due time is a rumour the one team able to act on it has no way to know is late."""
	from afya.integrations.feeds import build as build_feed
	svc = CommunityService()
	await svc.flag_misinfo(_flag(), at_ms=DETECTED)
	wire = [c.model_dump(mode='json') for c in svc.clusters(at_ms=DETECTED + 5 * HOUR)]
	rows, dropped = build_feed('misinformation_flags', wire)
	assert dropped == 0
	assert rows[0]['response_overdue'] is True
	# The missed four-hour triage is behind us at hour five; the next deadline is the 12-hour verify.
	assert rows[0]['detected_at_ms'] == DETECTED and rows[0]['next_due_at_ms'] == DETECTED + 12 * HOUR
