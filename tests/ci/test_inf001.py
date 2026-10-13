"""§INF-001's three missing Displays: case counts with trend, affected sub-counties, service status.

The section printed seven Displays and four were carried. The three that were not are the three a
reader actually opens the screen for: how many cases, where inside my county, and can I go there
today. The fourth Display the audit called carried — "service status (schools, borders, markets)" —
is the one §INF-007 had just built a producer for, and the wiring from that producer to this
dashboard is the half of this unit that is not new machinery.

Each test below names the failure it prevents rather than the function it calls.
"""
import httpx

from afya.info.views import CaseCounts, CountyDashboard, CountyRisk, SubCountyStatus
from afya.info.service import InfoService


def _counts(**over: object) -> CaseCounts:
	base: dict[str, object] = {
		'county': 'Busia', 'disease': 'evd', 'confirmed': 3, 'suspected': 5, 'as_of_iso': '2026-10-13',
	}
	return CaseCounts(**{**base, **over})  # type: ignore[arg-type]


def _sub(**over: object) -> SubCountyStatus:
	base: dict[str, object] = {
		'county': 'Busia', 'sub_county': 'Teso North', 'disease': 'evd', 'confirmed': 1, 'suspected': 2,
		'locations': ['Amagoro market'], 'as_of_iso': '2026-10-13',
	}
	return SubCountyStatus(**{**base, **over})  # type: ignore[arg-type]


def _worker_token(auth: object, ref: str, role: str = 'county_officer') -> dict[str, str]:
	"""A county officer token through the app's own PKCE flow — `provision_staff` refuses app roles."""
	import secrets

	from afya.auth.views import PKCETokenRequest, PKCEStart, s256
	from afya.privacy.views import RBACRole
	verifier = secrets.token_urlsafe(64)[:64]
	code = auth.start_pkce(PKCEStart(  # type: ignore[attr-defined]
		client_id='county-app', redirect_uri='afya://cb', code_challenge=s256(verifier),
		state=ref + '-state')).authorization_code
	token = auth.exchange_pkce(  # type: ignore[attr-defined]
		PKCETokenRequest(authorization_code=code, client_id='county-app', redirect_uri='afya://cb',
		                 code_verifier=verifier), RBACRole[role])
	return {'authorization': f'Bearer {token.access_token}'}


# --- the counts, and the word that must not be typed -----------------------------------------------

async def test_confirmed_and_suspected_are_two_facts_and_stay_two() -> None:
	"""The section prints "(confirmed, suspected)" as a pair and the distinction is the whole point: a
	reader of an outbreak dashboard is deciding whether a feverish child has Ebola or malaria, and a
	single `cases` number would answer that question with the wrong one of the two."""
	svc = InfoService()
	await svc.record_case_counts(_counts(confirmed=3, suspected=41))
	row = svc.case_counts('Busia')[0]
	assert (row.confirmed, row.suspected) == (3, 41), 'a suspected case is not a confirmed one'
	assert row.confirmed + row.suspected == 44


async def test_the_trend_is_derived_and_cannot_be_typed() -> None:
	"""A carried trend is a word a caller asserts, and "rising" on an outbreak dashboard is the one
	word that must follow from the figures. The property is computed from the two periods, so a body
	carrying `trend` is refused by `extra='forbid'` rather than quietly believed."""
	svc = InfoService()
	first = await svc.record_case_counts(_counts(confirmed=3, suspected=5))
	assert first.trend == 'new', 'a first report has not held steady'
	second = await svc.record_case_counts(_counts(confirmed=6, suspected=9, as_of_iso='2026-10-20'))
	assert (second.previous_confirmed, second.previous_suspected) == (3, 5), 'carried forward'
	assert second.trend == 'rising', second.model_dump()
	third = await svc.record_case_counts(_counts(confirmed=4, suspected=4, as_of_iso='2026-10-27'))
	assert third.trend == 'falling', third.model_dump()
	fourth = await svc.record_case_counts(_counts(confirmed=4, suspected=4, as_of_iso='2026-11-03'))
	assert fourth.trend == 'steady', fourth.model_dump()
	# A week where the confirmed count held still and the suspected count tripled is not a steady
	# week: the suspected count is where an Ebola outbreak announces itself, and a trend computed
	# from confirmed cases alone would call the week it arrives a quiet one.
	fifth = await svc.record_case_counts(_counts(confirmed=4, suspected=12, as_of_iso='2026-11-10'))
	assert fifth.trend == 'rising', fifth.model_dump()

	# The word cannot be posted: `trend` is computed, and `DerivedFields` drops it from an incoming
	# mapping so the API's own output is not a 422 against the API's own input.
	assert _counts().model_dump()['trend'] == 'new'
	round_tripped = CaseCounts(**{**_counts().model_dump(), 'previous_confirmed': 1, 'previous_suspected': 1})
	assert round_tripped.trend == 'rising', 'a round trip keeps the figures and recomputes the word'


async def test_the_previous_period_is_the_earlier_row_and_not_the_callers_memory() -> None:
	"""A trend needs two periods and the service already holds the earlier one. A caller who had to
	restate last week's figures would sooner or later restate them wrongly, and the word on the
	dashboard would then be a transcription of their recollection rather than a reading of the data."""
	svc = InfoService()
	await svc.record_case_counts(_counts(confirmed=10, suspected=2))
	await svc.record_case_counts(_counts(confirmed=1, suspected=1, as_of_iso='2026-10-06'))
	assert svc.case_counts('Busia')[0].previous_confirmed == 10, 'the earlier row is the comparison'
	# A caller who *does* supply one wins: a county may be comparing against a period this
	# deployment never saw, and refusing that would make the field unusable where it is needed.
	supplied = await svc.record_case_counts(
		_counts(confirmed=2, suspected=2, previous_confirmed=99, previous_suspected=99,
		        as_of_iso='2026-11-10'))
	assert (supplied.previous_confirmed, supplied.previous_suspected) == (99, 99)


async def test_a_correction_to_the_period_on_file_does_not_become_a_change_in_the_outbreak() -> None:
	"""Re-posting the same `as_of_iso` is a correction, not a new period. Shifting the stored figures
	into `previous_*` would make a corrected count read as a rise or fall — the dashboard would report
	an epidemiological event that did not happen, caused by someone fixing a typo."""
	svc = InfoService()
	await svc.record_case_counts(_counts(confirmed=3, suspected=5))
	corrected = await svc.record_case_counts(_counts(confirmed=4, suspected=5))
	assert corrected.previous_confirmed is None, 'a correction has no previous period'
	assert corrected.trend == 'new', corrected.model_dump()


async def test_the_counts_are_per_disease_because_the_section_says_other_diseases() -> None:
	"""§INF-001's first Display is "Ebola **and other notifiable diseases**". A county at three
	confirmed Ebola and forty confirmed cholera has two answers, and one total is a number nobody can
	act on — the response to each is different."""
	svc = InfoService()
	await svc.record_case_counts(_counts(disease='evd', confirmed=3, suspected=1))
	await svc.record_case_counts(_counts(disease='cholera', confirmed=40, suspected=0))
	rows = {c.disease: c for c in svc.case_counts('Busia')}
	assert set(rows) == {'evd', 'cholera'}, 'one row per disease, not one total'
	assert svc.case_counts('Busia', disease='evd')[0].confirmed == 3
	assert svc.case_counts('Nairobi') == [], 'another county is not this county'


async def test_a_previous_period_is_known_for_both_counts_or_neither() -> None:
	"""Half a comparison is not a comparison. A model that allowed `previous_confirmed` alone would
	let a caller compare confirmed cases against a period whose suspected count is unknown, and the
	trend would then be computed from a number nobody supplied."""
	import pydantic
	import pytest
	with pytest.raises(pydantic.ValidationError):
		_counts(previous_confirmed=1)
	with pytest.raises(pydantic.ValidationError):
		_counts(previous_suspected=1)


# --- the sub-counties, and what "affected" means ---------------------------------------------------

async def test_an_affected_sub_county_with_nothing_to_report_is_refused() -> None:
	"""A place with no case and no named location is not affected, and listing it puts a name on a
	life-safety screen that has nothing behind it. The refusal is at the model, so a caller filling a
	table cannot create one and a route cannot serve one."""
	import pydantic
	import pytest
	with pytest.raises(pydantic.ValidationError):
		_sub(confirmed=0, suspected=0, locations=[])
	# Either half is enough on its own: a sub-county with a case but no named place, and one with a
	# named place but no case yet (an exposure site being watched).
	assert _sub(confirmed=0, suspected=0, locations=['Amagoro market']).locations
	assert _sub(confirmed=2, suspected=0, locations=[]).confirmed == 2


async def test_the_sub_counties_are_the_countys_own_and_ordered_by_how_affected_they_are() -> None:
	"""The section asks for "affected sub-counties and locations" — the places with cases in them. A
	reader scanning the list is looking for the worst, so the order is by total cases descending, and
	ties break on the name so two identical deployments serve the same screen."""
	svc = InfoService()
	await svc.record_sub_county(_sub(sub_county='Teso North', confirmed=1, suspected=1))
	await svc.record_sub_county(_sub(sub_county='Budalangi', confirmed=9, suspected=2,
	                                 locations=['Budalangi market', 'Port Victoria']))
	await svc.record_sub_county(_sub(sub_county='Nambale', confirmed=0, suspected=0,
	                                 locations=['Nambale health centre']))
	await svc.record_sub_county(_sub(county='Kisumu', sub_county='Kibuye', confirmed=7, suspected=0))
	# A second disease in the *same* county. §INF-001's first Display is "Ebola **and other notifiable
	# diseases**", so a cholera-affected area is not an Ebola-affected one, and a dashboard that mixed
	# them would tell a reader Ebola is somewhere it is not.
	await svc.record_sub_county(_sub(sub_county='Matayos', disease='cholera', confirmed=12, suspected=3,
	                                 locations=['Matayos market']))
	# No disease named is the dashboard's own question — "what is affected in my county", all
	# notifiable diseases at once — and the two are distinguishable, not mixed: each row says which
	# disease it is a count of.
	all_diseases = svc.sub_counties('Busia')
	assert [r.sub_county for r in all_diseases] == ['Matayos', 'Budalangi', 'Teso North', 'Nambale'], \
		[r.sub_county for r in all_diseases]
	assert all(r.county == 'Busia' for r in all_diseases), "another county's areas are not this county's"

	# Naming a disease narrows to it, which is what a dashboard filtered to Ebola must do: a
	# cholera-affected market is not an Ebola-affected one, and mixing them tells a reader Ebola is
	# somewhere it is not.
	rows = svc.sub_counties('Busia', disease='evd')
	assert [r.sub_county for r in rows] == ['Budalangi', 'Teso North', 'Nambale'], [r.sub_county for r in rows]
	assert all(r.disease == 'evd' for r in rows), "another disease's areas are not this outbreak's"
	assert rows[0].locations == ['Budalangi market', 'Port Victoria'], 'the places travel with the row'
	cholera = svc.sub_counties('Busia', disease='cholera')
	assert [r.sub_county for r in cholera] == ['Matayos'], 'and the other disease is askable'


async def test_re_reporting_a_sub_county_supersedes_it_rather_than_listing_it_twice() -> None:
	"""A sub-county's status is *current*: a place that had two cases and now has five has one
	answer, and a screen that listed both would make the reader work out which is today's from two
	dates. The feed keeps the history; this is the answer to "is it near me"."""
	svc = InfoService()
	await svc.record_sub_county(_sub(confirmed=2, suspected=0, as_of_iso='2026-10-06'))
	await svc.record_sub_county(_sub(confirmed=5, suspected=0, as_of_iso='2026-10-13'))
	rows = svc.sub_counties('Busia')
	assert len(rows) == 1, f'one row per place, saw {len(rows)}'
	assert rows[0].confirmed == 5 and rows[0].as_of_iso == '2026-10-13'


# --- the dashboard, assembled ----------------------------------------------------------------------

async def test_the_dashboard_carries_all_seven_displays_and_stays_flat() -> None:
	"""§8.5 prints seven Displays as one flat list, and a client drawing a traffic-light dashboard
	reads `risk_level` — not `risk.risk_level`. The four keys that were already top-level stay
	top-level: moving them under `risk` would break every client to gain nothing a reader can see."""
	svc = InfoService()
	await svc.set_county_risk(CountyRisk(county='Busia', risk_level='high', active_signals=3,
	                                     bulletin='Stay alert.', source='Busia County Health Office'))
	await svc.record_case_counts(_counts())
	await svc.record_sub_county(_sub())
	alerts: list[dict[str, object]] = [
		{'alert_id': 'AL-1', 'kind': 'outbreak_evd', 'headline': 'Ebola in Busia'}]
	statuses: list[dict[str, object]] = [
		{'status_id': 'SS-1', 'kind': 'market_closure', 'name': 'Amagoro market',
		 'state': 'closed', 'county': 'Busia'}]
	wire: dict[str, object] = svc.county_dashboard('Busia', alerts, statuses).served('Updated just now')
	counts = wire['case_counts']
	areas = wire['sub_counties']
	neighbours_served = wire['neighbouring']
	assert isinstance(counts, list) and isinstance(areas, list) and isinstance(neighbours_served, list)

	# Display 1 — outbreak status. Display 6 — the timestamp. Display 7 — attribution.
	assert wire['county'] == 'Busia' and wire['risk_level'] == 'high' and wire['active_signals'] == 3
	assert wire['updated_line'] == 'Updated just now' and wire['source'] == 'Busia County Health Office'
	# Display 2 — case counts with trend. Display 3 — sub-counties and locations.
	assert counts[0]['trend'] == 'new' and counts[0]['confirmed'] == 3
	assert areas[0]['locations'] == ['Amagoro market']
	# Display 4 — alerts and advisories. Display 5 — service status.
	assert wire['alerts'] == alerts and wire['service_status'] == statuses
	# And the section's Description: "in the user's county **and neighbouring counties**".
	assert [n['county'] for n in neighbours_served] == ['Bungoma', 'Kakamega', 'Siaya']


async def test_a_neighbouring_county_is_served_with_its_own_risk_and_its_own_stamp() -> None:
	"""The section asks for neighbouring counties because a reader in Busia is affected by what
	happens in Bungoma. A neighbour row carrying the *caller's* risk level would answer the section's
	question with the wrong county's answer — which looks exactly like a correct one on a screen."""
	svc = InfoService()
	await svc.set_county_risk(CountyRisk(county='Busia', risk_level='high', active_signals=9, bulletin='x'))
	await svc.set_county_risk(CountyRisk(county='Bungoma', risk_level='moderate', active_signals=2, bulletin='y'))
	rows = {n.county: n for n in svc.county_dashboard('Busia', [], []).neighbouring}
	assert rows['Bungoma'].risk_level == 'moderate' and rows['Bungoma'].active_signals == 2
	assert rows['Kakamega'].risk_level == 'low', 'an unassessed neighbour is served its default'
	from afya.info.recency import UNDATED_MS
	assert rows['Kakamega'].updated_at_ms == UNDATED_MS, 'and claims no date for it'


async def test_an_unknown_county_still_gets_a_drawable_dashboard() -> None:
	"""The risk read already answers an unknown county with a defaulted low-risk row so a client
	always has something to draw. A dashboard that 500'd on the same input would be inconsistent with
	the route it replaces, and the neighbour list is empty because the table knows nothing about the
	place — a distinguishable answer, since no real county has no neighbours."""
	dash = InfoService().county_dashboard('Atlantis', [], [])
	assert dash.risk.risk_level == 'low' and dash.neighbouring == []
	assert dash.case_counts == [] and dash.sub_counties == []


async def test_the_dashboard_is_served_end_to_end_with_the_service_status_the_other_feed_produces() -> None:
	"""The half of this unit that is wiring. §INF-001's fifth Display is §INF-007's status feed — the
	same fact on two screens — and the read that had no producer is the defect §INF-007 closed. Here
	the producer is driven through its own route and the *dashboard* is asked whether the fact
	arrived: a join the server makes, not one each client makes and one client gets wrong."""
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	transport = httpx.ASGITransport(app=app)
	chw = _worker_token(services['auth'], 'chw-1', role='chw')
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		status = {
			'status_id': 'SS-1', 'kind': 'market_closure', 'county': 'Busia', 'name': 'Amagoro market',
			'state': 'closed', 'detail': 'Closed after a suspected case among traders.',
			'affects_facility_access': False, 'source': 'Busia County Health Office', 'verified': True,
			'effective_iso': '2026-10-13T06:00:00Z',
		}
		published = await c.post('/alerting/service-status', headers=chw, json=status)
		assert published.status_code == 200, published.text

		dash = await c.get('/info/dashboard/Busia')
		assert dash.status_code == 200, dash.text
		body = dash.json()
		markets = [s for s in body['service_status'] if s['kind'] == 'market_closure']
		assert markets and markets[0]['name'] == 'Amagoro market', body['service_status']
		assert markets[0]['state'] == 'closed', 'the state a reader acts on travelled with it'

		# And it is this county's statuses: the dashboard for a county with none carries none.
		other = (await c.get('/info/dashboard/Kisumu')).json()
		assert other['service_status'] == [], other['service_status']


# --- the writes, and who may make them ---------------------------------------------------------------

async def test_recording_counts_and_areas_is_guarded_and_the_two_counties_must_agree() -> None:
	"""Two separate refusals, because they fail differently.

	The guard: a case count is the county health team's epidemiological report, and an unguarded
	write would let anyone put a number on a public outbreak dashboard. The path/body agreement: a
	route that took the county from the path and the rest from the body could file Bungoma's counts
	against Busia, and the mismatch would surface as a dashboard contradicting the report it was
	built from — with nothing to point at in between.
	"""
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	officer = _worker_token(services['auth'], 'co-1')
	body = _counts().model_dump()
	sub = _sub().model_dump()

	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = await c.post('/info/dashboard/Busia/cases', json=body)
		anon_sub = await c.post('/info/dashboard/Busia/sub-counties', json=sub)
		mismatch = await c.post('/info/dashboard/Kisumu/cases', headers=officer, json=body)
		mismatch_sub = await c.post('/info/dashboard/Kisumu/sub-counties', headers=officer, json=sub)
		ok = await c.post('/info/dashboard/Busia/cases', headers=officer, json=body)
		ok_sub = await c.post('/info/dashboard/Busia/sub-counties', headers=officer, json=sub)
		dash = await c.get('/info/dashboard/Busia')

	assert anon.status_code in (401, 403), anon.text
	assert anon_sub.status_code in (401, 403), anon_sub.text
	assert mismatch.status_code == 422, mismatch.text
	assert 'Busia' in mismatch.json()['detail'], mismatch.json()
	assert mismatch_sub.status_code == 422, mismatch_sub.text
	assert ok.status_code == 200 and ok.json()['trend'] == 'new', ok.text
	assert ok_sub.status_code == 200, ok_sub.text
	served = dash.json()
	assert served['case_counts'][0]['confirmed'] == 3 and served['case_counts'][0]['trend'] == 'new'
	assert served['sub_counties'][0]['sub_county'] == 'Teso North'
	assert served['sub_counties'][0]['locations'] == ['Amagoro market']


async def test_the_citizen_read_is_unguarded_and_carries_no_codes() -> None:
	"""§INF-001 is a Tier-1 read a person opens about where they live, so the dashboard must be
	served to a caller with no token — and nothing in the payload may carry a spec feature code."""
	import json as _json
	import re

	from afya.service import build_services, create_app
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = await c.get('/info/dashboard/Busia')
	assert anon.status_code == 200, anon.text
	assert re.search(r'\b[A-Z]{2,4}-\d{3}\b', _json.dumps(anon.json())) is None, anon.text


# --- the model's own contract ---------------------------------------------------------------------

async def test_the_dashboard_model_refuses_a_payload_it_did_not_serve() -> None:
	"""`extra='forbid'` is what stops a client inventing a field. The container carries no computed
	fields, so it needs no `DerivedFields` mixin — asserted rather than assumed, because a computed
	field added later would make the API's own output a 422 against the API's own input."""
	import pydantic
	import pytest

	assert not CountyDashboard.model_computed_fields, 'a computed field here would need the mixin'
	assert set(CaseCounts.model_computed_fields) == {'trend'}, 'the trend is the one computed field'
	payload: dict[str, object] = {
		'county': 'Busia', 'risk': CountyRisk(county='Busia', risk_level='low', active_signals=0,
		                                      bulletin='x'),
		'case_counts': [], 'sub_counties': [], 'alerts': [], 'service_status': [],
		'neighbouring': [], 'typo': 1,
	}
	with pytest.raises(pydantic.ValidationError):
		CountyDashboard(**payload)  # type: ignore[arg-type]
