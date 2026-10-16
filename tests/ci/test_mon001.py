"""§MON-001 — the child immunisation tracker, and the four Features that had no carrier.

The section prints nine Features. Five were implemented; the four that were not all failed the same
way — the fact existed somewhere and nothing acted on it, or the fact existed twice and the two
copies disagreed:

- **"Record doses given (with photo of card)"** had no photo field and, worse, `record_dose` took
  four scalars and added a tuple to a set of its own. A dose recorded through the tracker screen —
  the screen a parent uses — never reached the wallet, so `immunisation_gaps`, the vaccination
  certificate and the export could not see it. The section's own "Why this works" says the record
  "outlives the paper card"; a dose filed in the tracker and absent from the record is that promise
  lost at the seam between two modules.
- **"Missed-dose alerts"** — `schedule` could say a dose was `overdue` and nothing raised an alert.
  `immunisation_reminders` was a §9.6 toggle with no producer at all.
- **"Campaign notifications (polio, measles)"** — no campaign notice existed anywhere, and the feed
  had no category a campaign could travel in.
- **"Shareable immunisation record"** — `immunisation_gaps` returned the doses *outstanding* and
  there was no shareable record of the doses *given*. It is now the wallet's `ShareGrant` over the
  `immunisation` document kind, which already existed and already had an expiry.

Two defects in the code the audit had marked carried, both of the same shape — a schedule and a
record that existed twice and disagreed:

- **`EPI_SCHEDULE` was two dicts.** `records` named `RV1` and `MMR` with IPV at dose 2; `monitoring`
  named `RV` and `Measles-Rubella` with IPV at dose 1. A dose recorded through one was invisible to
  the other's key. There is now one copy, in `records.views`, and the tracker re-exports it.
- **`immunisation_gaps` measured age in whole years times twelve.** Every child under one had age 0,
  so the six-week, ten-week and fourteen-week sets — three visits carrying most of the infant
  schedule — first appeared on the child's *first birthday*, a year late. A gap list silent for the
  exact period it exists to cover is worse than none: the parent reads it as "nothing due".

Each gate below is canaried against a planted defect in `canary_mon001.py`.
"""
import httpx
import pytest

from afya.monitoring.service import MonitoringService
from afya.monitoring.views import CampaignNotice, EPI_DUE_WEEKS
from afya.records.service import RecordsService
from afya.records.views import EPI_SCHEDULE, ImmunisationRecord, WalletMember
from afya.service import build_services, create_app

DOB = '2026-01-01'


def _svc() -> tuple[MonitoringService, RecordsService]:
	"""A tracker wired to a wallet, the way the composition root wires them."""
	wallet = RecordsService()
	return MonitoringService(wallet), wallet


async def _child(member_ref: str = 'c1') -> tuple[MonitoringService, RecordsService]:
	svc, wallet = _svc()
	await wallet.add_member(WalletMember(member_ref=member_ref, dob_iso=DOB, guardian_ref='g1'))
	await svc.register_child(member_ref, DOB)
	return svc, wallet


async def _token(c: httpx.AsyncClient, subject: str = 's') -> dict[str, str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token']
	return {'Authorization': f'Bearer {tok}'}


# --- the schedule is one fact, not two -----------------------------------------------------------

def test_the_schedule_is_one_dict_and_the_tracker_re_exports_it() -> None:
	"""The defect: two schedules keyed differently, so a dose in one was invisible to the other.

	`records` had `dict[str, list[int]]` naming `RV1`/`MMR` with IPV at dose 2; `monitoring` had ages
	naming `RV`/`Measles-Rubella` with IPV at dose 1. A gate that only compared lengths would pass on
	two schedules that disagree, so this compares identity and then compares the two vocabularies.
	"""
	assert EPI_DUE_WEEKS is EPI_SCHEDULE, 'the tracker must not keep a second copy of the schedule'
	assert set(EPI_SCHEDULE) == {
		'BCG', 'OPV', 'PCV10', 'DPT-HepB-Hib', 'RV', 'IPV', 'Measles-Rubella', 'Yellow Fever', 'HPV',
	}, '§MON-001 names nine vaccines and each must be a row'
	for vaccine, doses in EPI_SCHEDULE.items():
		assert doses, f'{vaccine} has no doses'
		for dose_no, weeks in doses:
			assert isinstance(dose_no, int) and isinstance(weeks, int), 'both fields are integers'
			assert weeks >= 0, f'{vaccine} dose {dose_no} is due before birth'


async def test_a_dose_recorded_on_the_tracker_reaches_the_wallet() -> None:
	"""The defect the section's own promise turns on: the record outlives the paper card.

	A dose filed through the tracker must be visible to the wallet's gap check and its certificate.
	This is the gate that would have caught the two separate stores, and it checks the *wallet's*
	view rather than the tracker's, because the tracker's view was the one that always worked.
	"""
	svc, wallet = _svc()
	await wallet.add_member(WalletMember(member_ref='c1', dob_iso=DOB, guardian_ref='g1'))
	await svc.register_child('c1', DOB)
	assert 'BCG dose 1' in wallet.immunisation_gaps('c1', _d(2026, 3, 1))
	await svc.record_dose(ImmunisationRecord(member_ref='c1', vaccine='BCG', dose_no=1,
	                                         given_iso='2026-01-02'))
	assert 'BCG dose 1' not in wallet.immunisation_gaps('c1', _d(2026, 3, 1)), (
		'the dose is in the tracker and not in the wallet — the two stores are back')
	cert = wallet.vaccination_certificate('g1', 'c1', 'school', '2026-10-12T09:00:00', 'secret')
	assert [d['vaccine'] for d in cert.doses] == ['BCG'], 'the certificate reads the dose log'


def test_the_card_photo_travels_as_a_digest_and_is_optional() -> None:
	"""§MON-001's "(with photo of card)". A digest, not the image — every other upload in this tree
	is kept behind a reference — and optional, because a dose given at a campaign post may have no
	card, and requiring one would refuse the *dose* rather than the photograph."""
	rec = ImmunisationRecord(member_ref='c1', vaccine='BCG', dose_no=1, given_iso='2026-01-02',
	                         card_photo_sha256='a' * 64)
	assert rec.card_photo_sha256 == 'a' * 64
	assert ImmunisationRecord(member_ref='c1', vaccine='BCG', dose_no=1,
	                          given_iso='2026-01-02').card_photo_sha256 is None
	with pytest.raises(ValueError):
		ImmunisationRecord(member_ref='c1', vaccine='BCG', dose_no=1, given_iso='2026-01-02',
		                   card_photo_sha256='not-a-digest')


def test_dose_zero_is_recordable_because_opv0_is_a_real_dose() -> None:
	"""The defect: `dose_no` was `ge=1`, so the wallet refused OPV0 — the birth dose every child in
	the country receives in their first two weeks — and `EPI_SCHEDULE` has carried a dose 0 row all
	along. A field that cannot hold the first row of its own table is a field that is wrong."""
	assert ('OPV', 0) in [(v, d) for v, ds in EPI_SCHEDULE.items() for d, _ in ds]
	rec = ImmunisationRecord(member_ref='c1', vaccine='OPV', dose_no=0, given_iso='2026-01-02')
	assert rec.dose_no == 0


# --- the gap list measures days, not whole years -------------------------------------------------

async def test_the_gap_list_sees_the_infant_schedule_before_the_first_birthday() -> None:
	"""The defect: `age_years(...) * 12` gave every child under one an age of 0 months, so no dose was
	ever due. The six-, ten- and fourteen-week sets appeared for the first time on the first
	birthday, by which point they were a year late."""
	wallet = RecordsService()
	await wallet.add_member(WalletMember(member_ref='c1', dob_iso=DOB, guardian_ref='g1'))
	at_six_weeks = wallet.immunisation_gaps('c1', _d(2026, 2, 12))  # 42 days old
	assert 'BCG dose 1' in at_six_weeks, 'the birth dose is due at birth'
	assert 'OPV dose 1' in at_six_weeks, 'the six-week set is due at six weeks, not at one year'
	assert 'PCV10 dose 1' in at_six_weeks
	assert 'DPT-HepB-Hib dose 1' in at_six_weeks
	assert 'Measles-Rubella dose 1' not in at_six_weeks, 'nine months has not come round yet'
	at_nine_months = wallet.immunisation_gaps('c1', _d(2026, 10, 1))
	assert 'Measles-Rubella dose 1' in at_nine_months


# --- missed-dose alerts, as data -----------------------------------------------------------------

async def test_a_missed_dose_raises_an_alert_and_a_coming_one_raises_a_different_alert() -> None:
	"""§MON-001's "Missed-dose alerts". `schedule` could always say `overdue`; nothing raised an
	alert. The two kinds are two different messages to a parent, which is why they are two kinds."""
	svc, _ = await _child()
	overdue = svc.missed_dose_alerts('c1', '2026-03-05')  # 63 days old, BCG long past grace
	kinds = {(a.vaccine, a.dose_no): a.kind for a in overdue}
	assert kinds[('BCG', 1)] == 'overdue'
	bcg = next(a for a in overdue if a.vaccine == 'BCG')
	assert bcg.days_overdue == 63 and bcg.due_iso == '2026-01-01'
	assert 'safe and free' in bcg.message, 'a missed dose is a catch-up, not a failure'
	assert [a for a in overdue if a.kind == 'overdue'] == sorted(
		[a for a in overdue if a.kind == 'overdue'], key=lambda a: a.due_iso), 'oldest first'


async def test_the_coming_alert_fires_three_days_out_and_not_before() -> None:
	"""The 3-day lead is §MON-001's own, and it is what makes the reminder fire *before* the visit is
	missed. An alert list built only from `overdue` rows is a report of failures, not a reminder."""
	svc, _ = await _child()
	early = svc.missed_dose_alerts('c1', '2026-02-07')  # 37 days old; OPV1 due day 42, 5 days out
	assert not [a for a in early if (a.vaccine, a.dose_no) == ('OPV', 1)], 'five days is too early'
	near = svc.missed_dose_alerts('c1', '2026-02-09')  # 39 days old, 3 days out
	opv1 = next(a for a in near if (a.vaccine, a.dose_no) == ('OPV', 1))
	assert opv1.kind == 'due_soon' and opv1.days_overdue == 0
	assert opv1.due_iso == '2026-02-12' and '3 day(s)' in opv1.message


async def test_a_given_dose_raises_no_alert() -> None:
	"""The alert list reads the same schedule the parent's screen does, so a dose that is recorded
	can never also be reported as missed — the two cannot disagree because there is one source."""
	svc, _ = await _child()
	await svc.record_dose(ImmunisationRecord(member_ref='c1', vaccine='BCG', dose_no=1,
	                                         given_iso='2026-01-02'))
	assert not [a for a in svc.missed_dose_alerts('c1', '2026-03-05') if a.vaccine == 'BCG']


# --- campaign notifications ----------------------------------------------------------------------

async def test_a_campaign_is_published_into_the_feed_under_a_category_a_parent_can_choose() -> None:
	"""§MON-001's "Campaign notifications (polio, measles)". `immunisation_reminders` was a §9.6
	toggle with no producer and the feed had no category a campaign could travel in, so the feature
	was two absent halves. This drives both: the notice is published, and it lands under the
	preference a parent actually set."""
	from afya.alerting.service import AlertingService
	from afya.alerting.views import governing_preference
	svc, _ = await _child()
	feed = AlertingService()
	notice = await svc.publish_campaign(CampaignNotice(
		disease='measles', counties=['Garissa'], target_age_months=(9, 59),
		starts_iso='2026-11-01', ends_iso='2026-11-30',
		headline='Measles campaign in Garissa', body='Free measles-rubella vaccine for children 9 to 59 months.',
		issued_by='MoH'), feed)
	assert notice.campaign_id.startswith('CMP-')
	items = feed.feed(county='Garissa')
	assert len(items) == 1 and items[0].category == 'immunisation'
	assert governing_preference('immunisation') == 'immunisation_reminders', (
		'the campaign must be governed by the preference a parent set for immunisation')
	assert feed.should_deliver('s', 'immunisation_reminders') is True
	assert items[0].verified is True, '§ALT-001: an unverified item must not reach the feed'


async def test_polio_is_expressible_as_a_campaign_and_never_as_an_outbreak_kind() -> None:
	"""The two the section names are not the same kind of thing. Measles is one of §3.3 principle
	12's outbreak diseases; polio is not, and the registry's vocabulary is what makes that a fact
	rather than an omission — a campaign targets a disease, an outbreak alert is raised for one."""
	from afya.alerts.views import AlertKind
	from afya.registry.diseases import DISEASES
	assert 'measles' in DISEASES and 'polio' not in DISEASES
	assert AlertKind('outbreak_measles') in AlertKind
	with pytest.raises(ValueError):
		AlertKind('outbreak_polio')
	svc, _ = await _child()
	notice = await svc.publish_campaign(CampaignNotice(
		disease='polio', counties=['Turkana'], target_age_months=(0, 59),
		starts_iso='2026-11-01', ends_iso='2026-11-30',
		headline='Polio campaign in Turkana', body='Free oral polio vaccine for all children under five.',
		issued_by='MoH'), None)
	assert notice.disease == 'polio' and svc.campaigns('Turkana', '2026-11-15') == [notice]


async def test_a_campaign_with_no_county_or_a_backwards_window_is_refused() -> None:
	"""A campaign that reaches nobody and one that ends before it starts are both notices that would
	be published and never acted on — the failure mode of a public notice is that it looks fine."""
	svc, _ = await _child()
	with pytest.raises(AssertionError, match='reaches nobody'):
		await svc.publish_campaign(CampaignNotice(
			disease='measles', counties=[], target_age_months=(9, 59),
			starts_iso='2026-11-01', ends_iso='2026-11-30', headline='x', body='y', issued_by='MoH'),
			None)
	with pytest.raises(AssertionError, match='must end after it begins'):
		await svc.publish_campaign(CampaignNotice(
			disease='measles', counties=['Garissa'], target_age_months=(9, 59),
			starts_iso='2026-11-30', ends_iso='2026-11-01', headline='x', body='y', issued_by='MoH'),
			None)
	with pytest.raises(ValueError):
		CampaignNotice(disease='measles', counties=['Garissa'], target_age_months=(59, 9),
		               starts_iso='2026-11-01', ends_iso='2026-11-30', headline='x', body='y',
		               issued_by='MoH')


async def test_a_campaign_is_running_only_between_its_dates() -> None:
	"""The question a parent asks is "is there a campaign near me today", which is a date filter and
	not a list of every campaign ever issued."""
	svc, _ = await _child()
	await svc.publish_campaign(CampaignNotice(
		disease='measles', counties=['Garissa', 'Wajir'], target_age_months=(9, 59),
		starts_iso='2026-11-01', ends_iso='2026-11-30', headline='x', body='y', issued_by='MoH'), None)
	assert svc.campaigns('Garissa', '2026-11-15')
	assert svc.campaigns('Garissa', '2026-10-31') == [], 'not started'
	assert svc.campaigns('Garissa', '2026-12-01') == [], 'over'
	assert svc.campaigns('Mombasa', '2026-11-15') == [], 'not this county'


# --- shareable record: the wallet's grant, over the kind that already exists ----------------------

async def test_the_immunisation_record_is_shareable_through_the_wallets_own_grant() -> None:
	"""§MON-001's "Shareable immunisation record". It is not a second share mechanism: the wallet
	already issues time-limited grants over document kinds, and `immunisation` is one of them. A
	share that kept its own expiry rule would be the second rule that drifts."""
	svc, wallet = await _child()
	await svc.record_dose(ImmunisationRecord(member_ref='c1', vaccine='BCG', dose_no=1,
	                                         given_iso='2026-01-02'))
	from afya.records.views import ShareGrant
	await wallet.grant_share(ShareGrant(
		grant_id='G-1', member_ref='c1', issued_by='g1', recipient='Garissa clinic',
		issued_iso='2026-10-12T09:00:00', expires_iso='2026-10-19T09:00:00', kinds=['immunisation']))
	view = wallet.share_view('G-1', '2026-10-13T09:00:00')
	assert [d.kind for d in view.documents] == ['immunisation']
	assert view.documents[0].payload['vaccine'] == 'BCG', 'the shared doc is the dose, with its photo hash'
	with pytest.raises(AssertionError, match='this share ended'):
		wallet.share_view('G-1', '2026-10-20T09:00:00')


# --- end to end through the real app -------------------------------------------------------------

async def _county_officer(c: httpx.AsyncClient) -> str:
	"""A county health team token through the app's own PKCE flow — §17.4's `county_aggregate`.

	The same helper `test_ai001.py` uses, and for the same reason: a campaign notice speaks for the
	authority, and the authority's scope is the one that says who may speak for it.
	"""
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier),
		'state': 'state-1234'})).json()
	return (await c.post('/auth/pkce/token', params={'role': 'county_officer'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()['access_token']


async def test_the_routes_serve_the_dose_the_alerts_and_the_campaign() -> None:
	"""The Features are wired in `create_app`; a test that built its own service would not notice a
	route going missing, and three of these four are routes."""
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		head = await _token(c, 'g1')
		child = await c.post('/monitoring/child', json={'member_ref': 'g1', 'dob_iso': '2026-01-01'}, headers=head)
		assert child.status_code == 200, child.text
		dose = await c.post('/monitoring/child/dose', headers=head, json={
			'member_ref': 'g1', 'vaccine': 'BCG', 'dose_no': 1, 'given_iso': '2026-01-02'})
		assert dose.status_code == 200, dose.text
		assert dose.json()['card_photo_sha256'] is None
		alerts = await c.get('/monitoring/child/g1/alerts?today_iso=2026-03-05', headers=head)
		assert alerts.status_code == 200, alerts.text
		assert not [a for a in alerts.json() if a['vaccine'] == 'BCG'], 'the dose was given'
		assert [a for a in alerts.json() if a['kind'] == 'overdue'], 'other doses are behind'
		# The campaign is the *authority's* act, so it is posted by the county health team and
		# refused to the citizen whose wallet the rest of this test is. Until this was written the
		# route carried `require_self`, which admits only citizen roles: the anonymous token this
		# test holds published a notice attributed to MoH and got a 200, while the officer the
		# notice is from was refused. Asserting only the 200 is what let that stand, so both
		# directions are asserted here.
		camp = await c.post('/monitoring/campaign', headers=head, json={
			'disease': 'measles', 'counties': ['Garissa'], 'target_age_months': [9, 59],
			'starts_iso': '2026-11-01', 'ends_iso': '2026-11-30',
			'headline': 'Measles campaign', 'body': 'Free vaccine for children under five.',
			'issued_by': 'MoH'})
		assert camp.status_code == 403, (
			f'a citizen published a notice attributed to MoH: {camp.status_code} {camp.text}')
		officer = {'Authorization': f'Bearer {await _county_officer(c)}'}
		camp = await c.post('/monitoring/campaign', headers=officer, json={
			'disease': 'measles', 'counties': ['Garissa'], 'target_age_months': [9, 59],
			'starts_iso': '2026-11-01', 'ends_iso': '2026-11-30',
			'headline': 'Measles campaign', 'body': 'Free vaccine for children under five.',
			'issued_by': 'MoH'})
		assert camp.status_code == 200, camp.text
		running = await c.get('/monitoring/campaigns?county=Garissa&on_iso=2026-11-15', headers=head)
		assert len(running.json()) == 1


async def test_another_persons_child_is_refused() -> None:
	"""§17.6: the child named must be in the caller's own wallet.

	The child is *registered* first, and that is the whole point of the test. Asking for a ref that
	does not exist is refused three times over — by the route guard, by the route's own ownership
	check and by the service's "unknown child" assertion — so a test written that way passes whether
	or not the ownership rule is applied at all, which is a gate that cannot fail. The case that
	distinguishes them is a child who exists in somebody else's wallet: only the ownership rule
	refuses that, and without it the caller is served a named child's vaccination schedule.
	"""
	services = build_services()
	app = create_app(services)
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		guardian = await _token(c, 'g1')
		registered = await c.post('/monitoring/child', headers=guardian,
		                          json={'member_ref': 'g1', 'dob_iso': '2026-01-01'})
		assert registered.status_code == 200, registered.text
		own = await c.get('/monitoring/child/g1/schedule', headers=guardian)
		assert own.status_code == 200, 'the guardian reads their own child'
		stranger = await c.get('/monitoring/child/g1/schedule', headers=await _token(c, 's'))
		assert stranger.status_code == 403, (
			f'a stranger was served a named child\'s schedule: {stranger.status_code} {stranger.text}')


def _d(year: int, month: int, day: int):
	from datetime import date
	return date(year, month, day)
