"""§19.4 public-health dashboards, and the min-cell rule that governs every row.

The failure this exists to prevent is a dashboard that reports a number small enough to read back
to a person. §11.7 and §19.3 both set a minimum cell size of 10; a row drawn from nine people
re-identifies whether or not it carries a flag, so the count must not reach the wire at all.
"""
import httpx

from afya.analytics.service import AnalyticsService
from afya.analytics.views import MIN_CELL_SIZE, DASHBOARDS, DashboardId
from afya.service import build_services, create_app


def _seeded() -> AnalyticsService:
	svc = AnalyticsService()
	svc.set_population('Nairobi', 4_000_000)
	svc.set_population('Turkana', 1_000_000)
	for _ in range(40):
		svc.record_triage('Nairobi', 'malaria_suspect')
	for _ in range(12):
		svc.record_triage('Nairobi', 'high')
	svc.record_triage('Turkana', 'low')  # one person in Turkana
	return svc


def test_every_dashboard_the_spec_names_has_a_builder() -> None:
	"""§19.4 lists nine dashboards; each must be buildable, and the ids must not drift from the list."""
	svc = _seeded()
	built = svc.all_dashboards('2026-10-10')
	assert len(built) == 9 and {d.dashboard for d in built} == set(DashboardId)
	assert len(DASHBOARDS) == 9


def test_a_small_cell_is_suppressed_and_carries_no_number() -> None:
	"""The rule. A county cell drawn from fewer than ten people is withheld — and the count is
	absent, not merely flagged, because a flagged small count is still a small count on the wire."""
	svc = _seeded()
	dash = svc.dashboard(DashboardId.symptom_surveillance, '2026-10-10')
	turkana = next(r for r in dash.rows if r.key == 'Turkana')
	assert turkana.suppressed is True
	assert turkana.value is None and turkana.denominator is None, 'a suppressed cell carries no number'
	assert str(MIN_CELL_SIZE) in (turkana.note or ''), 'the row must say why it was withheld'
	nairobi = next(r for r in dash.rows if r.key == 'Nairobi')
	assert nairobi.suppressed is False and nairobi.value == 52.0
	assert dash.suppressed_cells == 1, 'the report says how many cells it withheld'


def test_the_cell_size_is_the_group_not_the_county_population() -> None:
	"""The rule tests the group the cell describes, not the county it sits in. A county of four
	million with one reported case is a cell of one: clearing it on the population would report the
	single case §11.7 forbids. The population is context in the breakdown, not a licence."""
	svc = AnalyticsService()
	svc.set_population('Nairobi', 4_000_000)
	svc.record_triage('Nairobi', 'low')
	dash = svc.dashboard(DashboardId.symptom_surveillance, '2026-10-10')
	assert dash.rows[0].suppressed is True, 'one case in a county of four million is a cell of one'


def test_the_canary_watches_the_rule_fail() -> None:
	"""Canary. Point the threshold at a known-bad input and confirm it suppresses. Without this the
	test above proves only that the current data happens to be small, not that the rule fires."""
	below = AnalyticsService()
	for _ in range(MIN_CELL_SIZE - 1):
		below.record_triage('Test', 'low')
	assert below.dashboard(DashboardId.symptom_surveillance, '2026-10-10').rows[0].suppressed is True, \
		'one below the threshold must be withheld'
	# And exactly at the threshold it is reported, so the rule is a boundary and not a blanket.
	at = AnalyticsService()
	for _ in range(MIN_CELL_SIZE):
		at.record_triage('Test', 'low')
	assert at.dashboard(DashboardId.symptom_surveillance, '2026-10-10').rows[0].suppressed is False


def test_adherence_and_reach_use_their_own_denominator() -> None:
	"""Contact adherence is completed over recorded, alert reach acknowledged over delivered. The
	min-cell test uses that denominator — a contact list is small by nature, which is the risk."""
	svc = AnalyticsService()
	svc.record_contacts('Nairobi', recorded=100, completed=90)
	svc.record_contacts('Turkana', recorded=4, completed=4)
	rows = {r.key: r for r in svc.dashboard(DashboardId.contact_monitoring, '2026-10-10').rows}
	assert rows['Nairobi'].breakdown['adherence_pct'] == 90.0
	assert rows['Turkana'].suppressed is True, 'four contacts is a re-identifiable group'
	svc.record_alert('Nairobi', delivered=200, acknowledged=150)
	reach = {r.key: r for r in svc.dashboard(DashboardId.alert_reach, '2026-10-10').rows}
	assert reach['Nairobi'].breakdown['acknowledged_pct'] == 75.0


def test_the_access_rule_is_reported_and_says_no_individual_data() -> None:
	"""§19.4: "PHEOC, county health teams, MoH. Role-based. Audit logged." The claim is data so a
	reader can check it, and `individual_level_data` is False because no dashboard returns a person."""
	access = AnalyticsService().access()
	assert access.audit_logged is True and access.individual_level_data is False
	assert set(access.roles_allowed) == {'county_officer', 'pheoc_analyst', 'auditor'}
	assert len(access.dashboards) == 9


async def _staff(c: httpx.AsyncClient, role: str) -> str:
	"""A staff token through the app's own PKCE flow, which is how §17.4's non-operational roles
	are issued — `provision_staff` deliberately refuses anything but sysadmin and auditor."""
	from afya.auth.views import s256
	verifier = 'v' * 64
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(verifier), 'state': 'state-1234',
	})).json()
	return (await c.post('/auth/pkce/token', params={'role': role}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier,
	})).json()['access_token']


async def test_the_routes_are_scoped_and_an_unknown_dashboard_is_refused() -> None:
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		analyst = await _staff(c, 'pheoc_analyst')
		h = {'authorization': f'Bearer {analyst}'}
		# A citizen may not read county aggregates.
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		assert (await c.get('/analytics/dashboards', headers={'authorization': f'Bearer {anon}'})).status_code == 403
		assert (await c.get('/analytics/dashboards')).status_code in (401, 403)
		cat = (await c.get('/analytics/dashboards', headers=h)).json()
		assert len(cat['dashboards']) == 9 and cat['access']['individual_level_data'] is False
		one = (await c.get('/analytics/dashboards/triage_volume', headers=h)).json()
		assert one['dashboard'] == 'triage_volume' and one['min_cell_size'] == MIN_CELL_SIZE
		assert (await c.get('/analytics/dashboards/nonsense', headers=h)).status_code == 422
