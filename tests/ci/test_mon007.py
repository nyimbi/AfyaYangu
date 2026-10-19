"""§MON-007 — Vector and Environmental Risk: the two bullets that had no producer.

The section's five Features are all about *acting* on a vector risk, and three of them already had
a carrier: `vector_risk` gives the rain band, `report_breeding_site` routes a report, and
`rvf_alert` fires for livestock-adjacent households. The two that did not were the two that reach
a person:

* **larviciding campaign notifications** — the audit row read "no campaign notice is produced
  anywhere; the alert feed has no vector or larviciding category and `AlertKind` carries none"
* **personal protection reminders** — "the advice names nets and draining containers as text;
  nothing schedules a reminder"

Both are tested here against the WHO operational manual archived at
`sources/who-larval-source-management/`, because two of that source's statements are load-bearing
and a notice or a reminder that dropped either would be telling people something the manual does
not say: that larviciding "should never be seen as a substitute for ITNs or IRS in areas with
significant malaria risk", and that biting is a dusk-to-dawn affair.
"""
import httpx
import pytest

from afya.alerting.service import AlertingService
from afya.alerting.views import FEED_PREFERENCE, TOGGLEABLE, governing_preference
from afya.monitoring.service import MonitoringService
from afya.monitoring.views import (
	DUSK_HOUR, LARVICIDE_CLASSES, LARVICIDE_INTERVAL_FLOOR_DAYS, SUPPLEMENT_RULE, LarvicidingNotice,
)


def _notice(**kw: object) -> LarvicidingNotice:
	base: dict[str, object] = {
		'campaign_id': 'LSM-TEST0001', 'counties': ['Kisumu'], 'larvicide': 'bacterial',
		'habitats': ['Nyamasaria drain', 'rice paddies off the A1'],
		'first_round_iso': '2026-10-12T06:00:00+03:00', 'issued_by': 'County',
		'headline': 'Mosquito control in Kisumu', 'body': 'Teams will treat standing water.',
	}
	return LarvicidingNotice(**{**base, **kw})  # type: ignore[arg-type]


# --- the feed category, and the preference behind it -------------------------------------------

def test_the_vector_category_is_governed_by_a_preference_a_person_can_set() -> None:
	"""The audit row's exact complaint: "the alert feed has no vector or larviciding category".

	A category with no preference behind it is worse than no category — a subscriber could never
	match it, so the notice would publish into a feed nobody is listening to and every test that
	only checked `publish` was called would pass.

	The preference is pinned by its literal *and* by its membership, for the reason
	`test_content_escalation` gives: asserting only `in TOGGLEABLE` is an assertion about a constant
	and itself, and a canary that repointed the category at `air_quality` would still pass it while
	sending a larviciding notice to people who asked for air readings.
	"""
	assert 'vector_control' in FEED_PREFERENCE
	assert governing_preference('vector_control') == 'county_alerts'
	assert 'county_alerts' in TOGGLEABLE


def test_no_new_toggle_was_invented_for_it() -> None:
	"""§ALT-003's Options list is the spec's, and it does not name a vector or larviciding toggle.

	A twelfth switch would be a preference the section never offered, and §ALT-003's Options are
	audited row by row — so the honest mapping is onto "County alerts", which the section does list.
	"""
	from afya.alerting.views import TOGGLEABLE as toggles
	assert len(toggles) == 11, 'a toggle was added without §ALT-003 gaining an option'
	assert 'vector_control' not in toggles, 'the feed category is not itself a preference name'


# --- publishing a round ------------------------------------------------------------------------

async def test_a_round_reaches_the_feed_under_the_vector_category() -> None:
	svc, feed = MonitoringService(), AlertingService()
	notice = await svc.publish_larviciding(_notice(), feed)
	items = feed.feed('Kisumu')
	assert len(items) == 1
	assert items[0].category == 'vector_control'
	assert items[0].item_id == 'LSM-TEST0001-Kisumu'
	assert items[0].county == 'Kisumu'
	assert items[0].source == 'County'
	assert items[0].verified is True
	assert notice.campaign_id == 'LSM-TEST0001'


async def test_one_item_per_county_and_no_item_for_a_county_not_named() -> None:
	"""A round covering two counties is two notices, because the feed filters by county — one item
	carrying a list would be invisible to a subscriber in either."""
	svc, feed = MonitoringService(), AlertingService()
	await svc.publish_larviciding(_notice(counties=['Kisumu', 'Siaya']), feed)
	assert {i.county for i in feed.feed()} == {'Kisumu', 'Siaya'}
	assert feed.feed('Nairobi') == []


async def test_every_published_body_carries_the_supplement_rule() -> None:
	"""The manual is unambiguous that larviciding "should never be seen as a substitute for ITNs or
	IRS in areas with significant malaria risk".

	A county notice is exactly the document in which that sentence goes missing: the round is
	visible and the nets are not, so a resident reads "mosquitoes are being controlled" and stops
	using a net. The rule is appended by the publisher rather than trusted to the caller's `body`,
	which is why a caller that omits it still cannot publish a notice without it.
	"""
	svc, feed = MonitoringService(), AlertingService()
	await svc.publish_larviciding(_notice(body='Teams will treat standing water.'), feed)
	body = feed.feed('Kisumu')[0].body
	assert SUPPLEMENT_RULE in body
	assert 'does not replace them' in body
	assert 'net every night' in body


async def test_an_unknown_larvicide_class_is_refused() -> None:
	"""The class decides the re-treatment interval the round is planned around. A free-text class
	would let a county announce a round with no interval behind it, and the next round would be
	scheduled by nobody."""
	from pydantic import ValidationError
	with pytest.raises(ValidationError, match='not a larvicide class'):
		_notice(larvicide='something_the_county_uses')


async def test_a_round_with_no_county_or_no_habitat_is_refused() -> None:
	from pydantic import ValidationError
	with pytest.raises(ValidationError, match='no county reaches nobody'):
		_notice(counties=[])
	with pytest.raises(ValidationError, match='no habitat treats nothing'):
		_notice(habitats=[])


async def test_the_round_is_kept_not_only_published() -> None:
	"""The feed answers "what is new"; the county's own record answers "is this drain being
	treated", which is the question a person living beside it actually asks. A publisher that only
	wrote to the feed would leave that second question unanswerable once the feed window passed."""
	svc, feed = MonitoringService(), AlertingService()
	await svc.publish_larviciding(_notice(), feed)
	assert [n.campaign_id for n in svc.larviciding_rounds('Kisumu', '2026-10-13')] == ['LSM-TEST0001']
	assert svc.larviciding_rounds('Siaya', '2026-10-13') == []


async def test_a_round_is_not_hidden_by_a_day_it_has_not_reached() -> None:
	"""A round is not a window with an end: the manual's figures are *re-treatment* intervals, so a
	round begun before today is still running. Filtering on an `ends_iso` the model does not carry
	would answer "nothing is happening" about a programme mid-round."""
	svc, feed = MonitoringService(), AlertingService()
	await svc.publish_larviciding(_notice(first_round_iso='2026-10-01T06:00:00+03:00'), feed)
	assert svc.larviciding_rounds('Kisumu', '2026-10-13') != []
	assert svc.larviciding_rounds('Kisumu', '2026-09-30') == []


async def test_publishing_without_a_feed_still_records_the_round() -> None:
	"""The composition root may hand this a feed that is not up. The county's record is not
	conditional on the transport, the same reasoning `AlertingService` gives for the durable write
	not depending on a connected socket."""
	svc = MonitoringService()
	await svc.publish_larviciding(_notice(), None)
	assert len(svc.larviciding_rounds('Kisumu', '2026-10-13')) == 1


# --- personal protection reminders -------------------------------------------------------------

def test_the_net_reminder_is_placed_at_dusk() -> None:
	"""The manual puts anopheline biting "between dusk and dawn (and especially during the early
	hours of the morning)" and names `An. gambiae` and `An. funestus` peaking "an hour before dawn".
	A net reminder at any other hour is a reminder to do the thing at the wrong time of day."""
	svc = MonitoringService()
	r = svc.protection_reminder('Kisumu', 60.0, '2026-10-13T09:30:00+03:00')
	assert r.net_due_iso.startswith('2026-10-13T18:00:00')
	assert DUSK_HOUR == 18


def test_a_reminder_asked_for_after_dusk_rolls_to_tomorrow() -> None:
	"""Otherwise the reminder fires in the past, which on a device means it fires immediately — a
	person is told to go to bed at the moment they are already up."""
	svc = MonitoringService()
	r = svc.protection_reminder('Kisumu', 60.0, '2026-10-13T21:15:00+03:00')
	assert r.net_due_iso.startswith('2026-10-14T18:00:00')


def test_the_container_reminder_uses_the_shortest_interval_any_class_carries() -> None:
	"""Habitat manipulation is "a recurrent activity" in the manual's own words, and its interval is
	derived from `LARVICIDE_CLASSES` rather than typed. A household is then asked to clear standing
	water at least as often as a county would re-treat the same water — and a class added to the
	table with a shorter interval moves this date without anyone editing a second constant.
	"""
	svc = MonitoringService()
	r = svc.protection_reminder('Kisumu', 60.0, '2026-10-13T09:30:00+03:00')
	assert r.container_due_iso.startswith('2026-10-20T09:30:00')
	assert LARVICIDE_INTERVAL_FLOOR_DAYS == min(
		c[1] for c in LARVICIDE_CLASSES.values() if c[1] is not None)
	assert LARVICIDE_INTERVAL_FLOOR_DAYS == 7


def test_the_message_changes_with_the_rain_band() -> None:
	"""One string would have to be the wet one and would then be wrong for half the year. The
	manual's dry-season position is preparation before the next rains; the wet-season one is that
	the risk is here now."""
	svc = MonitoringService()
	wet = svc.protection_reminder('Kisumu', 60.0, '2026-10-13T09:30:00+03:00')
	dry = svc.protection_reminder('Kisumu', 2.0, '2026-10-13T09:30:00+03:00')
	assert wet.message != dry.message
	assert 'tonight' in wet.message
	assert 'before the next rains' in dry.message
	assert (wet.rainfall_band, dry.rainfall_band) == ('wet', 'dry')


def test_the_four_rain_bands_are_one_definition() -> None:
	"""`vector_risk` decided these inline and the reminder needs the same four. A second copy is a
	second definition, and the two would eventually disagree about where `wet` starts — which is the
	difference between "keep using your net" and "drain the containers now"."""
	svc = MonitoringService()
	for mm, expected in ((0.0, 'dry'), (9.9, 'dry'), (10.0, 'normal'), (49.9, 'normal'),
	                     (50.0, 'wet'), (99.9, 'wet'), (100.0, 'flood')):
		assert svc.vector_risk('Kisumu', mm).rainfall_band == expected
		assert svc.protection_reminder('Kisumu', mm, '2026-10-13T09:30:00+03:00').rainfall_band == expected


def test_an_instant_that_is_not_a_time_is_refused() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError, match='not an instant a reminder can be scheduled for'):
		svc.protection_reminder('Kisumu', 60.0, 'sometime next week')


def test_negative_rainfall_is_refused() -> None:
	svc = MonitoringService()
	with pytest.raises(AssertionError, match='rainfall non-negative'):
		svc.protection_reminder('Kisumu', -1.0, '2026-10-13T09:30:00+03:00')


# --- the front door ----------------------------------------------------------------------------

async def _county_officer(c: 'httpx.AsyncClient') -> str:
	"""A county health team token through the app's own PKCE flow — §17.4's `county_aggregate`."""
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'role': 'county_officer',
		'state': 'state-1234'})).json()
	return (await c.post('/auth/pkce/token', params={'role': 'county_officer'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()['access_token']


def _client() -> 'httpx.AsyncClient':
	import httpx
	from afya.service import build_services, create_app
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(build_services())),
	                         base_url='http://t')


async def test_the_round_is_issued_over_the_wire_and_read_back_by_the_county() -> None:
	"""A service method no route reaches is a capability nobody can use, so the whole round is
	exercised through the app: issue it as a county team, then read it back as a resident would.

	The read-back is the half that matters. A route that accepted a notice and served nothing would
	pass a publish-only test while leaving "is this drain being treated" unanswerable — which is the
	question the section's own bullet is about.
	"""
	async with _client() as c:
		assert (await c.post('/monitoring/larviciding', json={
			'counties': ['Kisumu'], 'larvicide': 'bacterial', 'habitats': ['a drain'],
			'first_round_iso': '2026-10-12T06:00:00+03:00', 'issued_by': 'County',
			'headline': 'Mosquito control', 'body': 'Teams will treat standing water.'}
		)).status_code in (401, 403), 'an anonymous caller issued a public round'

		token = await _county_officer(c)
		issued = await c.post('/monitoring/larviciding', headers={'authorization': f'Bearer {token}'},
		                      json={
			'counties': ['Kisumu'], 'larvicide': 'bacterial', 'habitats': ['Nyamasaria drain'],
			'first_round_iso': '2026-10-12T06:00:00+03:00', 'issued_by': 'County',
			'headline': 'Mosquito control in Kisumu', 'body': 'Teams will treat standing water.'})
		assert issued.status_code == 200, issued.text
		assert issued.json()['larvicide'] == 'bacterial'
		assert 'MON-' not in issued.text, 'a spec feature code reached the wire'

		back = await c.get('/monitoring/larviciding/Kisumu', params={'on_iso': '2026-10-13'})
		assert back.status_code == 200
		rows = back.json()
		assert len(rows) == 1 and rows[0]['habitats'] == ['Nyamasaria drain']
		assert (await c.get('/monitoring/larviciding/Siaya',
		                    params={'on_iso': '2026-10-13'})).json() == []

		# The supplement rule is the source's condition, and it survives the round trip: the route
		# publishes into the same feed the app serves, so the sentence a county might have dropped
		# is in the payload a resident reads.
		feed = await c.get('/alerting/feed', params={'county': 'Kisumu'})
		assert feed.status_code == 200
		rows = feed.json()['items']
		assert [i['category'] for i in rows] == ['vector_control']
		assert SUPPLEMENT_RULE in rows[0]['body']
		assert rows[0]['item_id'].endswith('-Kisumu')


async def test_a_bad_larvicide_class_is_a_422_from_the_route_not_a_500() -> None:
	"""The refusal is a sentence a county team can act on, not a stack trace."""
	async with _client() as c:
		token = await _county_officer(c)
		r = await c.post('/monitoring/larviciding', headers={'authorization': f'Bearer {token}'}, json={
			'counties': ['Kisumu'], 'larvicide': 'something_the_county_uses', 'habitats': ['a drain'],
			'first_round_iso': '2026-10-12T06:00:00+03:00', 'issued_by': 'County',
			'headline': 'Mosquito control', 'body': 'Teams will treat standing water.'})
		assert r.status_code == 422, r.text
		assert 'not a larvicide class' in r.text


async def test_the_reminder_route_serves_the_bands_and_refuses_a_bad_instant() -> None:
	async with _client() as c:
		for mm, band, word in ((2.0, 'dry', 'before the next rains'),
		                       (60.0, 'wet', 'tonight'),
		                       (120.0, 'flood', 'tonight')):
			r = await c.get('/monitoring/protection-reminder', params={
				'county': 'Kisumu', 'rainfall_mm_72h': mm, 'at_iso': '2026-10-13T09:30:00+03:00'})
			assert r.status_code == 200, r.text
			assert r.json()['rainfall_band'] == band
			assert r.json()['net_due_iso'].startswith('2026-10-13T18:00:00')
			assert word in r.json()['message']

		bad = await c.get('/monitoring/protection-reminder', params={
			'county': 'Kisumu', 'rainfall_mm_72h': 60, 'at_iso': 'yesterday'})
		assert bad.status_code == 422


async def test_no_spec_feature_code_appears_in_any_served_field() -> None:
	"""The standing constraint: §MON-007 is an internal identifier. A person reads "Mosquito and
	vector risk", never "MON-007"."""
	import json
	svc, feed = MonitoringService(), AlertingService()
	notice = _notice()
	await svc.publish_larviciding(notice, feed)
	payload = json.dumps([
		notice.model_dump(mode='json'),
		feed.feed('Kisumu')[0].model_dump(mode='json'),
		svc.protection_reminder('Kisumu', 60.0, '2026-10-13T09:30:00+03:00').model_dump(mode='json'),
		svc.vector_risk('Kisumu', 60.0).model_dump(mode='json'),
	])
	assert 'MON-007' not in payload
	assert 'MON-' not in payload
