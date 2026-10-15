"""Gate: §6.2.3 "Timestamp everything" — the age line, computed rather than stored.

§6.2.3 is one sentence: "**Timestamp everything.** 'Updated 2 hours ago' builds trust; undated
content destroys it." It was the only one of §6.2's ten principles with nothing behind it. The
library route served `{slug,title,body,harmony_tag,lang,answers_rank}` and no time at all, so the
line the section prints as its example could not be rendered by any client; `dashboard()` answered
an unknown county with a defaulted low-risk row that read as today's assessment; and a hotline
carried `verified=False` with nothing saying when anyone last looked at the number.

Two things this file is careful about, because both are ways the gate could pass while the rule
does not hold:

* **The stamp and the sentence are different facts.** A stored "2 hours ago" is wrong an hour later,
  so the test moves the clock and requires the line to move with it. A test that only checked the
  line existed would pass on a hard-coded string.
* **Withholding is half the rule.** Serving the text with no age satisfies every other check in
  `afya.info.service` while doing the one thing §6.2.3 forbids, so the withheld item and the audit
  that names it are both asserted.
"""
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from afya.info.recency import (
	HOUR_MS, MINUTE_MS, UNDATED_MS, age_label, band_for, freshness, freshness_line, instant_iso,
	instant_ms, midnight_ms,
)
from afya.info.service import InfoService
from afya.info.views import ContentItem, ContentStage, CountyRisk, HotlineInfo

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

# A fixed instant to hang every assertion on. Nothing here reads the wall clock: a test that did
# would pass or fail depending on when it ran, and the rule is about a computed age, not about now.
T0 = midnight_ms('2026-10-10')


def _item(**overrides: object) -> ContentItem:
	body: dict[str, object] = {
		'item_id': 'x', 'title': 't', 'body': 'b', 'lang': 'en', 'harmony_tag': 'official', 'slug': 's',
		'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1, 'stage': ContentStage.published,
	}
	return ContentItem(**{**body, **overrides})  # type: ignore[arg-type]


# --- the rule's own wording, and the arithmetic behind it -----------------------------------------

def test_the_rule_is_the_sections_own_and_its_example_renders() -> None:
	"""§6.2.3 prints one example line, so the template is pinned to it rather than to a shape that
	merely looks like an age. A spec revision that changes the wording fails here until the code
	moves with it."""
	spec = SPEC.read_text(encoding='utf-8')
	assert '**Timestamp everything.**' in spec
	assert '"Updated 2 hours ago" builds trust; undated content destroys it.' in spec
	assert freshness_line(T0, T0 + 2 * HOUR_MS) == 'Updated 2 hours ago'


def test_the_age_is_computed_from_two_instants_not_stored() -> None:
	"""The canary for the whole design. One item, three clocks, three lines — a hard-coded or stored
	phrase cannot produce this, and a stored phrase is wrong the moment it is an hour old."""
	item = _item(updated_at_ms=T0)
	svc = InfoService()
	assert svc.item_freshness(item, T0 + 2 * HOUR_MS).line == 'Updated 2 hours ago'
	assert svc.item_freshness(item, T0 + 5 * HOUR_MS).line == 'Updated 5 hours ago'
	assert svc.item_freshness(item, T0 + 3 * 86_400_000).line == 'Updated 3 days ago'


def test_the_bands_and_the_boundaries_between_them() -> None:
	"""Where the unit changes. An off-by-one at 60 minutes or 24 hours prints "60 minutes ago", which
	is a number no reader converts — and a band boundary is exactly where a computed age goes wrong."""
	assert age_label(T0, T0) == 'just now'
	assert age_label(T0, T0 + MINUTE_MS - 1) == 'just now', 'under a minute is not "0 minutes ago"'
	assert age_label(T0, T0 + MINUTE_MS) == '1 minute ago'
	assert age_label(T0, T0 + 59 * MINUTE_MS) == '59 minutes ago'
	assert age_label(T0, T0 + HOUR_MS) == '1 hour ago', 'the minutes band ends at the hour'
	assert age_label(T0, T0 + 23 * HOUR_MS) == '23 hours ago'
	assert age_label(T0, T0 + 86_400_000) == '1 day ago', 'the hours band ends at the day'
	assert [band_for(MINUTE_MS), band_for(HOUR_MS), band_for(86_400_000)] == ['minutes', 'hours', 'days']


def test_a_stamp_from_the_future_reads_as_now_rather_than_as_a_negative_age() -> None:
	"""Device and server clocks drift. "-1 hours ago" names a direction that is not real, which is a
	worse lie than rounding to the present — and §16.4's content caching makes a client-side clock
	the ordinary case, not an exotic one. Both the label and the numeric age are clamped: a negative
	`age_ms` would reach a client that draws a progress bar off it."""
	assert age_label(T0, T0 - 5 * HOUR_MS) == 'just now'
	assert freshness_line(T0, T0 - 5 * HOUR_MS) == 'Updated just now'
	assert freshness(T0, T0 - 5 * HOUR_MS).age_ms == 0, 'the numeric age is clamped too'


def test_an_undated_stamp_cannot_be_represented_or_rendered() -> None:
	"""§6.2.3's rule as a type. `ServedFreshness.updated_at_ms` is `gt=0`, so the undated case is
	refused rather than rendered as "Updated 0 minutes ago", and `instant_iso` refuses it too."""
	with pytest.raises(AssertionError):
		instant_iso(UNDATED_MS)
	with pytest.raises(AssertionError):
		age_label(UNDATED_MS, T0)
	assert UNDATED_MS == 0 and UNDATED_MS < MINUTE_MS, 'the sentinel must be a value no clock produces'


def test_the_instant_is_utc_and_the_reader_can_compare_it() -> None:
	"""The relative age is unreadable the moment a page is cached offline (§16.4) and an instant is
	unreadable at a glance, so both travel. UTC because the reader may be in Nairobi and the server
	anywhere — an instant in the server's zone is one nobody can compare against their own clock."""
	assert instant_iso(T0) == '2026-10-10T00:00:00Z'
	svc = InfoService()
	f = svc.item_freshness(_item(updated_at_ms=T0), T0 + 2 * HOUR_MS)
	assert f.updated_iso == '2026-10-10T00:00:00Z' and f.updated_at_ms == T0
	assert f.age_ms == 2 * HOUR_MS and f.line == 'Updated 2 hours ago'


def test_the_line_is_swahili_first_and_agrees_with_its_noun_class() -> None:
	"""§6.2.4 puts local language first, and Swahili's noun class governs the verb: "saa 2 zilizopita"
	but "saa 1 iliyopita". A single template would print "saa 1 zilizopita", which is not Swahili —
	so the singular and plural are separate strings and both are asserted."""
	assert freshness_line(T0, T0 + 2 * HOUR_MS, 'sw') == 'Imesasishwa saa 2 zilizopita'
	assert freshness_line(T0, T0 + HOUR_MS, 'sw') == 'Imesasishwa saa 1 iliyopita'
	assert freshness_line(T0, T0 + 5 * MINUTE_MS, 'sw') == 'Imesasishwa dakika 5 zilizopita'
	assert freshness_line(T0, T0, 'sw') == 'Imesasishwa sasa hivi'
	with pytest.raises(AssertionError):
		freshness_line(T0, T0 + HOUR_MS, 'fr')


def test_the_age_line_is_forwardable() -> None:
	"""§6.2.6 and §3.3 principle 10: every answer travels as a WhatsApp card or an SMS. The age is
	part of what is forwarded, so a line carrying a character outside GSM-7 would break the SMS half
	of the promise for the whole answer — the same failure an em dash caused in the myth library."""
	from afya.channels.service import GSM7
	for lang in ('en', 'sw'):
		for offset in (0, MINUTE_MS, HOUR_MS, 2 * HOUR_MS, 90 * 86_400_000):
			line = freshness_line(T0, T0 + offset, lang)
			assert not (set(line) - GSM7), f'{lang} {offset}: {sorted(set(line) - GSM7)} is outside GSM-7'


# --- the library withholds an undated item, and the writer cannot date it -------------------------

def test_an_undated_item_is_withheld_and_the_gap_is_named() -> None:
	"""Serving the text with no age satisfies every other filter in `library()` while doing the one
	thing §6.2.3 forbids. The item is withheld in both directions — never served, and named by
	`undated()` so the reviewer sees a gap rather than an absence."""
	svc = InfoService()
	svc._content['lonely'] = _item(item_id='lonely', slug='no-stamp')
	assert 'no-stamp' not in {c.slug for c in svc.library('en')}, 'undated content must not be served'
	assert svc.undated() == ['no-stamp'], 'and the gap must be named, not silent'
	svc._content['lonely'] = svc._content['lonely'].model_copy(update={'updated_at_ms': T0})
	assert 'no-stamp' in {c.slug for c in svc.library('en')}, 'with a stamp it is served'
	assert svc.undated() == []


def test_the_seed_ships_every_item_stamped_and_dated_by_its_review() -> None:
	"""The corpus obeys its own rule, and its stamp is the item's own review date rather than the
	moment the process started. A seed that claimed "Updated just now" for text written in September
	would render a freshness line nobody can believe, which is the failure the section names — and it
	would also make the `undated()` path vacuous, so the canary asserts the path is exercised."""
	svc = InfoService()
	assert svc.undated() == [], 'the seed must not ship undated content'
	assert all(c.updated_at_ms == midnight_ms(c.reviewed_on_iso) for c in svc.all_items())
	assert all(c.updated_at_ms > UNDATED_MS for c in svc.all_items())
	assert svc.item_freshness(svc.library('en')[0], T0).line == 'Updated 9 days ago'


def test_a_date_helper_and_an_instant_helper_are_two_different_answers() -> None:
	"""`midnight_ms` reads a bare date and `instant_ms` reads a stamp, and the two must not be swapped.

	`midnight_ms` truncates its argument to ten characters, which is right for §6.5's review date and
	wrong for anything carrying a time: two check-ins hours apart at one border post both come back as
	midnight of that day. A `SyncOp.client_ts` is an instant, and a queue whose ops for one afternoon
	all share a timestamp is one §16.3's last-write-wins row resolves against the wrong pair.

	Pinned from both sides, because the failure is symmetric: the instant helper must separate two
	stamps on one day, and the date helper must still collapse them to the day they fall on.
	"""
	morning, evening = '2026-10-01T09:00:00Z', '2026-10-01T21:30:00Z'
	assert instant_ms(morning) != instant_ms(evening), 'two instants on one day are two instants'
	assert instant_iso(instant_ms(morning)) == morning, 'the pair round-trips'
	assert instant_ms(morning) - midnight_ms(morning) == 9 * HOUR_MS
	assert midnight_ms(morning) == midnight_ms(evening), (
		'a bare date reads as the day it begins, so both instants land on one day boundary — which is '
		'the property `LocationService._window` wants and a `client_ts` must not have')
	assert instant_ms(morning.replace('Z', '+00:00')) == instant_ms(morning), 'both spellings parse'
	assert instant_ms('2026-10-01T09:00:00') == instant_ms(morning), 'a naive stamp is read as UTC'


async def test_a_client_cannot_choose_its_own_freshness() -> None:
	"""The stamp is the service's, not the writer's.

	`updated_at_ms` is a declared field, so a body carrying one is *accepted by the model* — it is
	the storage shape — and the guarantee is that `upsert_content` overwrites it unconditionally
	rather than keeping what it was handed. A freshness signal a writer can choose is one it can lie
	about, which defeats the only thing the signal is for. The `freshness_line` half is refused
	outright: the *sentence* is never a stored fact at all, so there is no field for it.
	"""
	with pytest.raises(ValidationError):
		_item(freshness_line='Updated 2 minutes ago')
	svc = InfoService()
	posted = _item(item_id='posted', slug='posted', updated_at_ms=T0 + 99 * HOUR_MS)
	assert posted.updated_at_ms == T0 + 99 * HOUR_MS, 'the model carries the field a client may post'
	stored = await svc.upsert_content(posted, at_ms=T0)
	assert stored.updated_at_ms == T0, 'and the service overwrites it with its own clock'
	assert svc._content['posted'].updated_at_ms == T0, 'the stored row, not just the return value'
	assert svc.item_freshness(svc._content['posted'], T0).line == 'Updated just now'


def test_the_stamp_advances_with_the_workflow() -> None:
	"""§6.5's workflow is what makes an item current, so the stamp moves when the item does. An item
	published an hour ago is not an English draft written in September, and a reader shown the draft's
	age for the published text is being told the wrong thing."""
	svc = InfoService()
	svc._content['d-1'] = _item(item_id='d-1', stage=ContentStage.draft, updated_at_ms=T0)
	step = svc.advance('d-1', ContentStage.clinical_review, at_ms=T0 + 3 * HOUR_MS)
	assert step.updated_at_ms == T0 + 3 * HOUR_MS
	assert svc.advance('d-1', ContentStage.archived, at_ms=T0 + 4 * HOUR_MS).updated_at_ms == T0 + 4 * HOUR_MS


# --- the dashboard and the directory, which §8.5 and §18.4 name ------------------------------------

def test_an_unassessed_county_is_not_given_a_freshness_line() -> None:
	"""`dashboard()` answers an unknown county with a defaulted low-risk row so a client always has
	something to draw. Without the stamp that default is indistinguishable from an assessment someone
	made today, and §6.2.3 calls undated content destructive — so the line is None and a client can
	tell the two apart. This is the canary that keeps the default honest."""
	svc = InfoService()
	assert svc.dashboard('Turkana').risk_level == 'low', 'the default row still exists'
	assert svc.dashboard_freshness('Turkana', T0) is None, 'but it claims no date'


async def test_an_assessed_county_carries_when_it_was_assessed() -> None:
	svc = InfoService()
	await svc.set_county_risk(CountyRisk(county='Nairobi', risk_level='high', active_signals=12,
	                                    bulletin='Stay alert.'), at_ms=T0)
	assert svc.dashboard_freshness('Nairobi', T0 + 2 * HOUR_MS) == 'Updated 2 hours ago'
	assert svc.dashboard_freshness('Kisumu', T0 + 2 * HOUR_MS) is None, 'a county never assessed'


def test_a_number_claimed_as_verified_carries_when_it_was_checked() -> None:
	"""§18.4's directory and §6.2.3 together. `verified=True` is an assertion about a phone number
	that nobody can act on without knowing when it was last checked, so the flag without the instant
	is refused at construction rather than served as a bare tick."""
	with pytest.raises(ValidationError):
		HotlineInfo(name='Hotline', number='719', hours='24/7', verified=True)
	checked = HotlineInfo(name='Hotline', number='719', hours='24/7', verified=True, verified_at_ms=T0)
	assert InfoService().hotline_freshness(checked, T0 + 2 * HOUR_MS) == 'Updated 2 hours ago'
	assert InfoService().hotline_freshness(InfoService().hotlines()[0], T0) is None, \
		'an unverified entry claims no date either'


# --- served -------------------------------------------------------------------------------------

def _app_and_headers() -> tuple[Any, dict[str, str]]:
	from afya.auth.service import AuthService
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	token = auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
	return create_app(services), {'authorization': f'Bearer {token}'}


async def test_the_library_route_serves_the_line_the_section_prints() -> None:
	"""§6.2.3 is a promise about what a reader sees, and this is the surface they see it on. The
	route takes the clock, so the line is checked at a known instant rather than at whenever CI ran."""
	app, _ = _app_and_headers()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		rows = (await c.get(f'/info/library?lang=en&now_ms={T0}')).json()
		sw = (await c.get(f'/info/library?lang=sw&now_ms={T0}')).json()
	assert rows, 'the library is served'
	for row in rows:
		assert row['line'].startswith('Updated ') and row['updated_iso'].endswith('Z')
		assert row['updated_at_ms'] > UNDATED_MS and row['age_label']
	assert rows[0]['line'] == 'Updated 9 days ago', rows[0]['line']
	assert sw[0]['line'] == 'Imesasishwa siku 9 zilizopita', sw[0]['line']


async def test_the_dashboard_and_directory_routes_carry_the_stamp() -> None:
	"""§8.5 lists "Last updated timestamp" among the dashboard's fields and §18.4's directory is where
	a number is asserted. Both are served with the line, and both say None rather than inventing one."""
	app, h = _app_and_headers()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		posted = await c.post(
			f'/info/dashboard/Nairobi?risk_level=high&active_signals=3&bulletin=Stay+alert&at_ms={T0}',
			headers=h)
		assert posted.status_code == 200, posted.text
		assert posted.json()['updated_line'] == 'Updated just now', posted.json()
		dash = (await c.get(f'/info/dashboard/Nairobi?now_ms={T0 + 2 * HOUR_MS}')).json()
		assert dash['updated_line'] == 'Updated 2 hours ago', dash
		assert dash['risk_level'] == 'high' and dash['active_signals'] == 3, 'the assessment is served'
		unassessed = (await c.get(f'/info/dashboard/Marsabit?now_ms={T0}')).json()
		assert unassessed['updated_line'] is None, 'an unassessed county claims no date'
		hotlines = (await c.get(f'/info/hotlines?now_ms={T0}')).json()
		assert all('updated_line' in row for row in hotlines['contacts']), hotlines
		assert all(row['updated_line'] is None for row in hotlines['contacts']), \
			'the seed directory is not claimed as verified'


async def test_the_governance_view_names_the_undated_items() -> None:
	"""A gate that withheld content silently would be worse than the undated item it prevents: the
	audience sees nothing and nobody is told why. The audit is served on §6.5's own governance view,
	where the reviewer already is — the same place §6.2.4's language audit lives."""
	from afya.auth.service import AuthService
	from afya.info.service import InfoService as IS
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	auditor = auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
	svc: IS = services['info']  # type: ignore[assignment]
	svc._content['lonely'] = _item(item_id='lonely', slug='no-stamp')
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		gov = (await c.get('/info/content/governance', headers={'authorization': f'Bearer {auditor}'})).json()
		served = {r['slug'] for r in (await c.get('/info/library?lang=en')).json()}
	assert gov['undated'] == ['no-stamp'], gov['undated']
	assert 'no-stamp' not in served, 'the withheld item must not be served while the audit names it'
	assert all('updated_at_ms' in i for i in gov['items']), 'the reviewer sees the stamp on every item'
