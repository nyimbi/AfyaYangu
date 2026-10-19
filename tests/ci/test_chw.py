"""Behavioural tests for the CHW trust layer (spec §5 CHAN-005, §11.4 COM-101)."""
import re

import pytest
from pydantic import ValidationError

from afya.chw.service import ChwService
from afya.chw.views import JOB_AIDS, TRAINING_MODULES, ActivityLogEntry, ChwCase, ChwProfile
from afya.records.pdf import CHARS_PER_LINE


def _profile(chw_ref: str, *, registry_verified: bool = True, provisioned_by: str = 'County') -> ChwProfile:
	return ChwProfile(
		chw_ref=chw_ref, name='Amina Wanjiru', county='Kilifi', community='Gede',
		registry_verified=registry_verified, provisioned_by=provisioned_by,
	)


def _case(report_id: str, *, status: str = 'reported') -> ChwCase:
	return ChwCase(
		report_id=report_id, status=status, suspected_disease='cholera',
		reported_iso='2026-10-05T09:00:00Z', surveillance_officer='SO-7',
		ppe_reminder_due=True, next_action='collect stool sample',
	)


async def test_provision_refused_without_registry_verification() -> None:
	"""Trust layer: an unverified person cannot self-enrol as a health worker."""
	svc = ChwService()
	with pytest.raises(AssertionError, match='national registry'):
		await svc.provision(_profile('CHW-1', registry_verified=False))
	assert svc._chws == {}, 'a refused provision stores nothing'


async def test_provision_refused_when_not_provisioned_by_county_or_moh() -> None:
	"""The vocabulary is the model's now, so a bad provisioner never reaches the service.

	This used to be the service assert alone: the model took any string and `provision` refused
	`Self` at the door. The set is declared on `ChwProfile` now — which is what lets the mobile form
	be a view of it — so the refusal happens at construction. Asserted at both ends, because the
	service keeps its own assert for the in-process caller that builds a profile some other way, and
	a second door should not be a weaker one.
	"""
	with pytest.raises(ValidationError, match='provisioned_by'):
		_profile('CHW-2', provisioned_by='Self')
	svc = ChwService()
	# The service door still refuses a value that got past the model.
	with pytest.raises(AssertionError, match='provisioned by a county health team'):
		await svc.provision(ChwProfile.model_construct(
			chw_ref='CHW-2', name='Amina Wanjiru', county='Kilifi', community='Gede',
			registry_verified=True, provisioned_by='Self',
		))
	assert svc._chws == {}


async def test_provision_accepted_by_county_and_moh() -> None:
	svc = ChwService()
	county = await svc.provision(_profile('CHW-3', provisioned_by='County'))
	moh = await svc.provision(_profile('CHW-4', provisioned_by='MoH'))
	assert county.chw_ref == 'CHW-3' and county.provisioned_by == 'County'
	assert moh.chw_ref == 'CHW-4' and moh.provisioned_by == 'MoH'
	assert svc.profile('CHW-3').county == 'Kilifi'


def test_profile_refuses_unknown_worker() -> None:
	with pytest.raises(AssertionError, match='unknown or unprovisioned CHW'):
		ChwService().profile('CHW-ghost')


async def test_unknown_worker_cannot_be_assigned_a_case() -> None:
	svc = ChwService()
	with pytest.raises(AssertionError, match='unknown or unprovisioned CHW'):
		await svc.assign_case('CHW-ghost', _case('R-1'))
	assert svc.cases('CHW-ghost') == []


async def test_unknown_worker_cannot_log_activity() -> None:
	svc = ChwService()
	entry = ActivityLogEntry(
		chw_ref='CHW-ghost', at_iso='2026-10-05T10:00:00Z', activity='report', community='Gede',
	)
	with pytest.raises(AssertionError, match='unknown or unprovisioned CHW'):
		await svc.log_activity(entry)
	assert svc._activity == []


async def test_case_load_counts_open_cases_only() -> None:
	svc = ChwService()
	await svc.provision(_profile('CHW-5'))
	await svc.assign_case('CHW-5', _case('R-1', status='reported'))
	await svc.assign_case('CHW-5', _case('R-2', status='investigated'))
	await svc.assign_case('CHW-5', _case('R-3', status='closed'))

	assert svc.case_load('CHW-5') == 2
	assert len(svc.cases('CHW-5')) == 3, 'closed cases remain in the record'

	# closing an open case reduces the load
	svc.cases('CHW-5')[0].status = 'closed'
	assert svc.case_load('CHW-5') == 1
	assert svc.case_load('CHW-nobody') == 0


def test_job_aid_returned_for_known_topic_and_refused_for_unknown() -> None:
	svc = ChwService()
	for topic in JOB_AIDS:
		aid = svc.job_aid(topic)
		assert aid == JOB_AIDS[topic]
		assert aid.strip(), f'{topic} job aid is empty'
	with pytest.raises(AssertionError, match='no job aid for'):
		svc.job_aid('ebola_airborne_protocol')


def test_ppe_reminder_is_the_donning_aid() -> None:
	assert ChwService.ppe_reminder() == JOB_AIDS['ppe_donning']


def test_every_job_aid_renders_as_a_printable_sheet() -> None:
	"""§CHAN-5's "Printed job aids" — the half of the bullet this tree can carry.

	The module held both halves and joined neither: `JOB_AIDS` is the text and `afya.records.pdf` is
	the writer, so a job aid was a string a screen showed and nothing a worker could carry. The sheet
	is checked structurally — a PDF header, a trailer, and the aid's own words wrapped into the
	stream — because a `.pdf` filename with the raw string inside it is the claim-with-nothing-behind
	it the records module keeps finding.
	"""
	svc = ChwService()
	for topic in JOB_AIDS:
		sheet = svc.job_aid_sheet(topic)
		raw = sheet.content.encode('latin-1')
		assert sheet.topic == topic and sheet.media_type == 'application/pdf'
		assert sheet.filename == f'job-aid-{topic}.pdf'
		assert raw.startswith(b'%PDF-1.4'), f'{topic} is not a PDF'
		assert raw.rstrip().endswith(b'%%EOF'), f'{topic} has no trailer'
		# cp1252, not latin-1: the aids carry em dashes, and the writer's font declares
		# `/WinAnsiEncoding`, which is the encoding that gives those bytes glyphs.
		assert sheet.title.encode('cp1252') in raw, f'{topic} lost its title'
		# Every word of the aid must survive the wrap, or the printed sheet is not the aid.
		for word in JOB_AIDS[topic].split():
			assert word.encode('cp1252') in raw, f'{topic} lost the word {word!r}'
		# And every drawn line must fit the column. `render` draws one line per element and clips
		# nothing, so an aid passed unwrapped becomes a single line running past the margin and off
		# the page — legible in the byte stream (all the words are there) and illegible on paper.
		drawn = [line for line in raw.split(b'\n') if line.endswith(b') Tj')]
		assert len(drawn) > 1, f'{topic} was not wrapped: one drawn line for a {len(JOB_AIDS[topic])}-char aid'
		for line in drawn:
			assert len(line) - len(b'() Tj') <= CHARS_PER_LINE, (
				f'{topic} has a drawn line past the {CHARS_PER_LINE}-char column: {line[:40]}...'
			)


def test_the_job_aid_titles_are_the_aids_and_name_no_spec_code() -> None:
	"""Every aid has a printable title, the title set is exactly the aid set, and no title carries a
	spec id — a printed sheet is read by a person, and §3.3 principle 9 governs it as much as a
	screen does."""
	from afya.chw.views import JOB_AID_TITLES

	assert set(JOB_AID_TITLES) == set(JOB_AIDS), (
		f'aid/title mismatch: {set(JOB_AID_TITLES) ^ set(JOB_AIDS)}'
	)
	for topic, title in JOB_AID_TITLES.items():
		assert title.strip() and title != topic, f'{topic} has no human title'
		assert not re.search(r'\b(?:CHAN|COM|REC|INF|SEN|ACC)-\d{3}\b', title), title


def test_an_unknown_topic_has_no_printable_sheet() -> None:
	with pytest.raises(AssertionError, match='no job aid for'):
		ChwService.job_aid_sheet('ebola_airborne_protocol')


def test_training_covers_required_modules() -> None:
	modules = ChwService().training()
	assert [m['module'] for m in modules] == [m['module'] for m in TRAINING_MODULES]
	required = {m['module'] for m in modules if m['required']}
	assert required == {'orientation', 'case_report_form', 'supervised_first_three_reports'}


async def test_activity_summary_counts_by_type_and_changes_supervision_note() -> None:
	svc = ChwService()
	await svc.provision(_profile('CHW-6'))
	await svc.provision(_profile('CHW-7'))
	for activity in ('report', 'report', 'report', 'followup', 'followup'):
		await svc.log_activity(ActivityLogEntry(
			chw_ref='CHW-6', at_iso='2026-10-06T08:00:00Z', activity=activity, community='Gede',
		))
	await svc.log_activity(ActivityLogEntry(
		chw_ref='CHW-7', at_iso='2026-10-06T08:00:00Z', activity='training', community='Gede',
	))

	light = svc.activity_summary('CHW-6', '2026-10')
	assert light.by_activity == {'report': 3, 'followup': 2}
	assert light.total == 5
	assert 'Light activity logged' in light.supervision_note

	# a different CHW's entries are not counted
	other = svc.activity_summary('CHW-7', '2026-10')
	assert other.total == 1 and other.by_activity == {'training': 1}

	for _ in range(5):
		await svc.log_activity(ActivityLogEntry(
			chw_ref='CHW-6', at_iso='2026-10-07T08:00:00Z', activity='referral', community='Gede',
		))
	good = svc.activity_summary('CHW-6', '2026-10')
	assert good.total == 10
	assert good.by_activity == {'report': 3, 'followup': 2, 'referral': 5}
	assert 'Good coverage this period' in good.supervision_note
	assert good.supervision_note != light.supervision_note


async def test_the_summary_is_scoped_to_the_period_it_names() -> None:
	"""`period` was echoed into the response and otherwise ignored, so a lifetime count decided a
	period's sentence.

	The mobile catalogue offers this as "My activity this week". A CHW who logged ten visits in
	September and none since read "Good coverage this period" in October — the sentence was about a
	week and the number behind it was about a career. The two shapes the tree already writes are
	asserted here, because `/ai/early-warning` takes an ISO week while a supervision summary is the
	same question asked over a month.
	"""
	svc = ChwService()
	await svc.provision(_profile('CHW-6'))
	for at in ('2026-09-08T08:00:00Z',) * 10 + ('2026-10-06T08:00:00Z',) * 2:
		await svc.log_activity(ActivityLogEntry(
			chw_ref='CHW-6', at_iso=at, activity='report', community='Gede'))

	# The week that holds the two October entries, and the month that holds the same two.
	week = svc.activity_summary('CHW-6', '2026-W41')
	assert week.total == 2, 'a lifetime total is not this week'
	assert 'Light activity logged' in week.supervision_note
	month = svc.activity_summary('CHW-6', '2026-10')
	assert month.total == 2 and month.period == '2026-10'
	# September's ten are the ones that must not leak forward.
	assert svc.activity_summary('CHW-6', '2026-09').total == 10
	assert svc.activity_summary('CHW-6', '2026-09').supervision_note != week.supervision_note
	# A period nothing was logged in is empty rather than everyone's lifetime.
	assert svc.activity_summary('CHW-6', '2026-W40').total == 0
	assert svc.activity_summary('CHW-6', '2026-11').total == 0
	assert svc.activity_summary('CHW-6', '2026-W41').by_activity == {'report': 2}
	# An undated row is a data defect, not a fact about any period: counting it would put it in every
	# one of them at once, which is the same "a lifetime total wearing a period's name" failure.
	await svc.log_activity(ActivityLogEntry(
		chw_ref='CHW-6', at_iso='not-a-date', activity='report', community='Gede'))
	expected = {'2026-09': 10, '2026-10': 2, '2026-W41': 2, '2026-11': 0}
	assert {p: svc.activity_summary('CHW-6', p).total for p in expected} == expected, (
		'an unparseable date was counted into a period'
	)


async def test_the_activity_route_defaults_to_the_week_it_is_running_in(tmp_path) -> None:
	"""The catalogue's title is "My activity this week", and the route's default was a literal week.

	`period: str = '2026-W41'` meant the screen read week 41 for the life of the deployment — a
	title that is a week and a number that is a constant. The period is now computed from the clock,
	the way `/ai/early-warning` does it one route up, so leaving the parameter out cannot be pointed
	at a stale week. The assertion is against the clock rather than against a fixture date, because
	a test pinned to `2026-W41` is the same bug wearing a test's clothes.
	"""
	import base64
	import datetime
	import hashlib

	import httpx

	from afya.service import build_services, create_app

	app = create_app(build_services(db_path=str(tmp_path / 'afya.db')))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		verifier = 'v' * 43
		challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
		authz = (await c.post('/auth/pkce/authorize', json={
			'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': challenge, 'role': 'chw',
			'state': 'state-1234'})).json()
		tok = (await c.post('/auth/pkce/token', params={'role': 'chw'}, json={
			'authorization_code': authz['authorization_code'], 'client_id': 'app',
			'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()
		headers = {'Authorization': f'Bearer {tok["access_token"]}'}

		year, week, _ = datetime.datetime.now(datetime.timezone.utc).date().isocalendar()
		today = f'{year}-W{week:02d}'
		now = (await c.get('/chw/CHW-9/activity', headers=headers)).json()
		assert now['period'] == today, f'the default period is the running week, not {now["period"]}'
		# And an explicit period is still honoured, so the default did not replace the parameter.
		asked = (await c.get('/chw/CHW-9/activity', headers=headers, params={'period': '2026-09'})).json()
		assert asked['period'] == '2026-09'
