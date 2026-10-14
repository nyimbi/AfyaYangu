"""§SEC-006's "Public transparency reports (quarterly)" — the aggregate document, and its cadence.

The bullet was `missing` while a model called `TransparencyReport` existed and was tested. That is
the whole shape of the defect: the section prints *two* Features one name apart — "In-app data
dashboard: what is stored, what has been shared, with whom, when" and "Public transparency reports
(quarterly)" — and the first was built while the second was not. A report about a person is not a
publication to the public, and every visible part of the second existed under the first's name.

Three claims are load-bearing and each is asserted against the artefact rather than the label:

* **It is public.** The document route answers with no token. A quarterly public report that needed
  one would be a private report about a public duty.
* **The min-cell rule is applied once.** The withheld counts are counted from the rows §19.4's
  dashboards returned, not recomputed against a second copy of the threshold — so a cell the
  dashboard suppressed cannot reappear in the publication.
* **The cadence has three states.** `published`, `due` and `not_yet_due`, because `overdue: bool`
  cannot distinguish a met duty from a quarter that has not ended, and a duty nobody has been asked
  for yet must not read as one that was skipped.
"""
from datetime import date

import pytest

from afya.retention.service import RetentionService
from afya.retention.views import PublicationStatus, TransparencyPublication


def _svc(with_sources: bool = False) -> RetentionService:
	svc = RetentionService()
	if with_sources:
		from afya.analytics.service import AnalyticsService
		from afya.security.service import SecurityService
		svc.register_sources({'dashboards': AnalyticsService(), 'scans': SecurityService()})
	return svc


def test_a_period_that_is_not_a_quarter_is_refused() -> None:
	"""Parsed, not pattern-matched: a period compared as a string would be reported as a missing
	quarter forever rather than as an input the caller can fix."""
	for bad in ('2026', '2026-Q5', '2026-Q0', 'last quarter', ''):
		with pytest.raises(ValueError):
			_svc().build_publication(bad, '2026-10-01T00:00:00Z')


def test_the_period_end_is_the_last_day_of_the_quarter() -> None:
	"""The window has an end, so a generated-at date can be compared against it. Q1 ends in March,
	Q4 in December — a quarter whose end is computed from its start would put Q4 in the next year."""
	assert RetentionService.period_end_iso('2026-Q1') == '2026-03-31'
	assert RetentionService.period_end_iso('2026-Q2') == '2026-06-30'
	assert RetentionService.period_end_iso('2026-Q3') == '2026-09-30'
	assert RetentionService.period_end_iso('2026-Q4') == '2026-12-31'


def test_a_quarter_that_has_not_ended_is_not_yet_due_rather_than_overdue() -> None:
	"""The third state. Without it a quarter still running reports `overdue: false`, which is the
	same answer a quarter that *was* published gives — and the two are different facts."""
	schedule = _svc().publication_schedule('2026-Q4', date(2026, 10, 14))
	assert schedule.status is PublicationStatus.not_yet_due
	assert schedule.overdue is False


def test_a_quarter_that_ended_unpublished_is_due() -> None:
	schedule = _svc().publication_schedule('2026-Q3', date(2026, 10, 14))
	assert schedule.status is PublicationStatus.due
	assert schedule.overdue is True, 'a quarter that ended with no publication is late'


def test_publishing_records_the_period_and_moves_the_schedule() -> None:
	"""The write and the read cannot disagree about whether it happened: the schedule is computed
	from the same register the publication writes into."""
	svc = _svc()
	assert svc.publication_schedule('2026-Q3', date(2026, 10, 14)).status is PublicationStatus.due
	svc.publish('2026-Q3', '2026-10-05T09:00:00Z')
	schedule = svc.publication_schedule('2026-Q3', date(2026, 10, 14))
	assert schedule.status is PublicationStatus.published
	assert schedule.last_published_iso == '2026-10-05T09:00:00Z'
	assert schedule.overdue is False and schedule.periods_published == 1


def test_building_a_publication_does_not_record_one() -> None:
	"""The read is pure, which is what makes it safe to serve with no token. A build that recorded
	would let any reader mark a quarter published — including one that has not ended — and the
	schedule would then report a duty met that nobody performed."""
	svc = _svc()
	svc.build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	assert svc.publications() == {}
	assert svc.publication_schedule('2026-Q3', date(2026, 10, 14)).status is PublicationStatus.due


def test_a_skipped_quarter_is_named_rather_than_averaged_away() -> None:
	"""A single gap has to be visible. Two periods published with one between them missing reports
	the missing one by name, not as a smaller count."""
	svc = _svc()
	svc.publish('2026-Q1', '2026-04-05T09:00:00Z')
	svc.publish('2026-Q3', '2026-10-05T09:00:00Z')
	schedule = svc.publication_schedule('2026-Q3', date(2026, 10, 14))
	assert schedule.missing_periods == ['2026-Q2']
	assert schedule.periods_published == 2


def test_a_service_that_has_just_started_has_not_skipped_four_years() -> None:
	"""The missing list is bounded by the earliest publication, not by the beginning of time. A
	list that claimed every quarter since the epoch was skipped would make a real gap unreadable."""
	svc = _svc()
	assert svc.publication_schedule('2026-Q3', date(2026, 10, 14)).missing_periods == []


def test_the_publication_carries_the_min_cell_rule_and_the_withheld_count() -> None:
	"""§11.7's rule travels with the section that governs it, and the withheld count is reported
	rather than hidden: a publication that silently dropped small cells reads as complete."""
	pub = _svc(with_sources=True).build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	assert pub.min_cell_size == 10
	assert pub.audience == 'public'
	assert pub.sections, 'a publication with no sections is a cover page'
	for section in pub.sections:
		assert section.rule, f'{section.key} carries no rule, so its numbers cannot be read'
	assert pub.withheld_cells == sum(s.withheld_cells for s in pub.sections)


def test_a_suppressed_cell_does_not_reappear_in_the_publication() -> None:
	"""The join that matters: the publication reads the dashboards' own rows, so a cell §11.7
	withheld is still withheld here. A publication that recomputed counts would be a second place
	the threshold lives, and the first to be wrong."""
	from afya.analytics.service import AnalyticsService

	dash = AnalyticsService()
	dash.set_population('Nairobi', 4_000_000)
	dash.record_triage('Nairobi', 'low')  # one person: below the min cell
	svc = RetentionService()
	svc.register_sources({'dashboards': dash})
	pub = svc.build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	rows = [r for s in pub.sections for r in s.rows]
	assert rows, 'the dashboard produced no rows, so this test would pass vacuously'
	assert all(r.suppressed and r.value is None for r in rows if r.denominator is None), \
		'a cell the dashboard withheld came back with a number'
	assert pub.withheld_cells > 0, 'the withheld count is not reported'


def test_a_source_that_is_not_wired_is_named_rather_than_omitted() -> None:
	"""A section missing because the deployment has no source is a fact about the deployment. A
	reader comparing two quarters has to be able to tell it from a quarter in which the thing it
	measures did not happen."""
	pub = _svc().build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	assert pub.sections == []
	assert any('no source' in n for n in pub.notes), pub.notes
	assert 'dashboards' in ' '.join(pub.notes) and 'scans' in ' '.join(pub.notes)


def test_the_publication_names_no_person_and_no_spec_code() -> None:
	"""The two vocabularies a public document must not carry: a subject reference, and a spec
	feature id. The first would make the document personal data; the second is internal."""
	import re

	pub = _svc(with_sources=True).build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	blob = pub.model_dump_json()
	assert 'subject_ref' not in blob, 'a public document carries the personal vocabulary'
	assert not re.search(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b', blob), \
		'a spec feature code reached a published document'


def test_the_breach_record_holds_classes_and_counts_never_a_person() -> None:
	"""§24.8's notices are part of what a transparency report is for, and the register is the
	public shape of them: which data classes, how many people — never who."""
	svc = _svc()
	svc.record_breach({'affected_data': ['location'], 'affected_count': 40})
	pub = svc.build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	assert pub.breaches == [{'affected_data': ['location'], 'affected_count': 40}]
	assert 'subject' not in pub.model_dump_json()


def test_the_publication_reports_the_obligations_that_have_a_software_control() -> None:
	"""Read off §24's own register rather than restated: a publication carrying its own list of
	duties would be the second place they live and the first to go stale."""
	from afya.operations.service import OBLIGATIONS

	pub = _svc().build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	expected = sorted(o.duty for o in OBLIGATIONS if o.control is not None)
	assert pub.open_obligations == expected and expected


def test_the_publication_is_the_document_the_audit_row_names() -> None:
	"""The row's carrier must be the thing that produces the document, and it must resolve — a
	`carried` row naming a method that was renamed is the finding wearing a repair."""
	from afya.content_audit.service import content_report
	from afya.refs import resolves

	rows = [b for f in content_report().features if f.feature_id == 'SEC-006' for b in f.bullets]
	row = next(b for b in rows if 'transparency reports' in b.bullet)
	assert row.kind == 'carried', row.note
	assert row.carried_by == 'afya.retention.service:RetentionService.build_publication'
	assert resolves(row.carried_by)
	# And the carrier is not the per-subject report the row's own note said was all there was.
	assert resolves('afya.retention.service:RetentionService.transparency_report')
	assert row.carried_by != 'afya.retention.service:RetentionService.transparency_report'


def test_the_model_is_a_publication_and_not_the_subject_report() -> None:
	"""Two models, two audiences. The personal one carries `subject_ref`; the published one carries
	`audience` and has no field for a person at all."""
	from afya.retention.views import TransparencyReport

	assert 'subject_ref' in TransparencyReport.model_fields
	assert 'subject_ref' not in TransparencyPublication.model_fields
	assert 'audience' in TransparencyPublication.model_fields


async def test_the_public_route_serves_with_no_token() -> None:
	"""A quarterly *public* report that required a token would not be public. This is the claim the
	bullet makes and the only way to test it is to ask the front door without one."""
	import httpx

	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		r = await c.get('/transparency/report', params={'period': '2026-Q3', 'as_at_iso': '2026-10-05T09:00:00Z'})
		assert r.status_code == 200, r.text
		body = r.json()
		assert body['audience'] == 'public' and body['min_cell_size'] == 10
		s = await c.get('/transparency/schedule', params={'period': '2026-Q3'})
		assert s.status_code == 200 and s.json()['status'] in ('published', 'due', 'not_yet_due')
		# A period that is not a quarter is the caller's to fix, so it is 422 and not a 500.
		bad = await c.get('/transparency/report', params={'period': '2026', 'as_at_iso': '2026-10-05T09:00:00Z'})
		assert bad.status_code == 422, bad.text
		# And the 200s are not a catch-all: an unrouted path is still a 404.
		assert (await c.get('/zzz/deep/path')).status_code == 404


async def test_recording_a_publication_is_guarded_and_the_read_is_not() -> None:
	"""The asymmetry is the point. Marking a quarter published is a duty performed by the
	operator; reading the document is what the public does. A reader who could record would let
	any caller satisfy the schedule by looking at it."""
	import httpx

	from afya.service import build_services, create_app

	services = build_services()
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'probe-sec006'})).json()['token']
		body = {'period': '2026-Q1', 'as_at_iso': '2026-04-05T09:00:00Z'}
		refused = await c.post('/transparency/publish', params=body, headers={'authorization': f'Bearer {anon}'})
		assert refused.status_code in (401, 403), refused.text
		svc = services['retention']
		assert svc.publications() == {}, 'a citizen token recorded a publication'  # type: ignore[union-attr]


def test_the_catalogue_reaches_the_publication_and_its_cadence() -> None:
	"""A document no client can open is the `report_stock` defect at the level of a feature. Both
	new actions are ordinary reads a citizen's catalogue carries, and each fills its own route."""
	from afya.mobile.actions import FEATURE_OF, catalogue

	by_id = {a.id: a for a in catalogue()}
	assert by_id['public_transparency_report'].path == '/transparency/report'
	assert by_id['publication_schedule'].path == '/transparency/schedule'
	for slug in ('public_transparency_report', 'publication_schedule'):
		assert FEATURE_OF[slug] == 'SEC-006'
		assert {f.name for f in by_id[slug].fields}, f'{slug} offers no field, so its form is empty'
		assert not any(f.client_supplied for f in by_id[slug].fields), \
			f'{slug} is a public read and must not be bound to a subject'


def test_nothing_served_carries_a_spec_feature_code() -> None:
	"""The user-facing vocabulary rule, applied to the payload this unit added."""
	import re

	pub = _svc(with_sources=True).build_publication('2026-Q3', '2026-10-05T09:00:00Z')
	blob = pub.model_dump_json()
	assert not re.search(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b', blob)
