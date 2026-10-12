"""§17.4's RBAC table against the routes and the token-issuing paths.

`_SCOPE` transcribes §17.4's eight rows and §17.5's Authorisation control names it as the enforcement
of "RBAC with least privilege". Nothing compared it to the routes, so three declared scopes had no
guard anywhere and one role could never hold a token — a capability the table claims and no caller can
reach. What is tested here is that the comparison is made against what the app serves, and that the
two findings are reported rather than repaired.
"""
import httpx

from afya.auth.service import ISSUABLE_ROLES, OPERATIONAL_ROLES, AuthService
from afya.privacy.rbac import (
	ROLE_ACCESS,
	declared_scopes,
	identity_gap,
	report,
	roles_with_scope,
	route_scopes,
	unissuable_roles,
	unreachable_scopes,
)
from afya.privacy.views import CITIZEN_ROLES, RBACRole, _SCOPE
from afya.service import build_services, create_app


def test_the_table_is_the_sections_eight_rows() -> None:
	"""§17.4's role column, read against the spec. The Access cell is carried verbatim so a revision
	that widens a role's access fails here until the map moves with it — "Patients who have consented
	to share" is the rule and `consented_patient` is this codebase's name for it."""
	from pathlib import Path
	spec = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = spec.split('### 17.4 Role-Based Access Control', 1)[1].split('\n### ', 1)[0]
	rows = [ln for ln in section.splitlines() if ln.startswith('|') and not set(ln) <= set('|-: ')]
	rows = [r for r in rows if r.strip('|').strip().split('|')[0].strip() != 'Role']
	spec_rows = [(c[0].strip(), c[1].strip()) for c in ([x.strip() for x in r.strip('|').split('|')] for r in rows)]

	assert len(spec_rows) == 8
	assert [access for _, access in ROLE_ACCESS] == [access for _, access in spec_rows]
	assert len(ROLE_ACCESS) == len(RBACRole) == 8


def test_the_scope_map_is_read_from_the_table_and_not_the_other_way_round() -> None:
	"""Every §17.4 row has a scope set, and the scopes are the ones the Access cell names. This is the
	direction that matters: `_SCOPE` is derived from the table, so a row with no scope is a role the
	guard cannot authorise and a scope on a role the table does not give it is a widening."""
	assert set(_SCOPE) == {r for r, _ in ROLE_ACCESS}
	assert 'assigned' in _SCOPE[RBACRole.chw] and 'community_aggregate' in _SCOPE[RBACRole.chw]
	assert _SCOPE[RBACRole.sysadmin] == {'infrastructure'}, '§17.4: "Infrastructure only"'
	assert _SCOPE[RBACRole.auditor] == {'audit_logs'}, '§17.4: "Read-only access to audit logs"'
	assert _SCOPE[RBACRole.clinician] == {'consented_patient'}


def test_the_route_scopes_are_read_from_the_source_not_from_a_list() -> None:
	"""`route_scopes()` reads `service.py`, because a hand-kept list is the thing that drifts — the
	whole finding is that the table and the routes disagree, and a second list would agree with
	whichever of the two it was written beside. The canary in the module's history replaced a guard
	with a different scope and this function moved; a list would not have."""
	found = route_scopes()
	assert found == {'assigned', 'audit_logs', 'consented_patient', 'county_aggregate',
	                 'infrastructure', 'national_aggregate', 'self'}, sorted(found)
	# The assertion is exact rather than a superset, so a `route_scopes` that reported every scope it
	# could think of would fail it — the only way this test can be wrong in the direction that
	# matters. `self` arrives both route-level and through the guards' own `dataset` literal.
	assert 'self' in found
	# A scope that appears in no guard is not reported as guarded, which is what makes the gap real.
	assert 'family' not in found and 'community_aggregate' not in found


def test_the_two_scopes_with_no_route_are_reported_with_their_roles() -> None:
	"""The finding, and the one that closed.

	`family` and `community_aggregate` are §17.4's "Own and linked family data" and "community
	aggregates", and no route requires either — so the table names an access two roles have and no
	caller can exercise. Reported rather than repaired: adding a route so a scope has a caller would
	be this code inventing an endpoint the spec does not ask for.

	`consented_patient` was the third and is no longer here. §17.4's clinician row is "Patients who
	have consented to share", and §10.1's "Provider-side view (for participating facilities)" is the
	sentence that asks for the route — a clinician reading a record through a share the patient
	issued. The share *is* the consent that makes the row reachable, so `GET
	/records/share/{grant_id}/view` is the endpoint the spec asks for rather than one invented to
	give a scope a caller, and the scope left this list when the route arrived. The other two remain
	because nothing in the spec asks for the route that would close them: a `family`-scoped caller
	needs the identity upgrade §15.5 does not specify, and a `community_aggregate` route would be a
	new aggregate surface, not an existing one.
	"""
	assert unreachable_scopes() == ['community_aggregate', 'family']
	assert roles_with_scope('family') == [RBACRole.citizen_identified]
	assert roles_with_scope('community_aggregate') == [RBACRole.chw]
	assert roles_with_scope('consented_patient') == [RBACRole.clinician]
	# The scope the provider view guards on is one the table declares, and the route is what makes it
	# reachable — asserted through the same reader the finding uses, so this cannot drift from it.
	assert 'consented_patient' in route_scopes()
	# And every guarded scope is one the table declares, so the comparison is not against noise.
	assert route_scopes() <= declared_scopes()


def test_the_role_no_path_can_issue_is_reported_as_the_identity_gap() -> None:
	"""§17.4's second row describes a principal the system cannot produce. `require_token` resolves
	any anonymous token to `citizen_anonymous`, and the PKCE flow asserts the requested role is in
	`ISSUABLE_ROLES`, which excludes both citizen roles — so `citizen_identified` holds `self` and
	`family` and no token ever carries it. §3.3 principle 6's "Identity is opt-in" is the sentence
	that gives the row a reason to exist, and nothing implements the opt-in."""
	assert RBACRole.citizen_identified in unissuable_roles()
	assert identity_gap() is RBACRole.citizen_identified
	assert RBACRole.citizen_anonymous not in unissuable_roles(), 'the anonymous token resolves to it'
	for role in ISSUABLE_ROLES | OPERATIONAL_ROLES:
		assert role not in unissuable_roles(), role.value
	assert RBACRole.citizen_identified not in ISSUABLE_ROLES
	assert CITIZEN_ROLES == frozenset({RBACRole.citizen_anonymous, RBACRole.citizen_identified})


def test_the_family_routes_are_reached_through_self_and_not_through_family() -> None:
	"""The concrete consequence of the `family` gap, asserted where it bites. §ALT-002's family board
	is a Tier 3 feature and its three routes are guarded on `self` — so a caller reaches a family
	route through a scope §17.4 does not give it, and the `family` scope the table grants
	`citizen_identified` is what the row says and not what the app does. Both readings are safe here
	(the `self` guard compares the subject and the board checks membership), which is why this is a
	finding rather than a defect."""
	import inspect

	app = create_app(build_services())

	# `app.routes` is nested: every `include_router` is an `_IncludedRouter` whose paths live on
	# `original_router.routes` under `include_context.prefix`, so a flat walk sees six entries and
	# misses all of them. The walk recurses, which is what test_ui_vocabulary.py does for the same
	# reason — an inventory read off the top level is not an inventory of the routes the app serves.
	leaves: list[object] = []

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			leaves.append(r)

	walk(app.routes)
	by_path = {getattr(r, 'path', ''): r for r in leaves}
	assert '/alerting/family/link' in by_path and '/alerting/family/{family_ref}' in by_path, sorted(by_path)[:5]
	ep = by_path['/alerting/family/{family_ref}'].endpoint  # type: ignore[attr-defined]
	dep = next(p.default for p in inspect.signature(ep).parameters.values()
	           if type(p.default).__name__ == 'Depends')
	closure = getattr(getattr(dep, 'dependency', None), '__closure__', None) or ()
	names = {c.cell_contents for c in closure if isinstance(c.cell_contents, str)}
	assert 'family' not in names, 'the board is not guarded on the family scope'


async def test_the_report_is_served_to_the_auditor() -> None:
	"""§17.4 over HTTP, auditor-scoped. The route is reached with a provisioned auditor token, so the
	guard is exercised rather than assumed — a route that 403s for everyone would pass a weaker test."""
	services = build_services()
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/privacy/rbac')).status_code == 401
		anon = (await c.post('/auth/anonymous', json={})).json()['token']
		assert (await c.get('/privacy/rbac', headers={'authorization': f'Bearer {anon}'})).status_code == 403
		auth_svc: AuthService = services['auth']  # type: ignore[assignment]
		auditor = auth_svc.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
		body = (await c.get('/privacy/rbac', headers={'authorization': f'Bearer {auditor}'})).json()

	assert body == report()
	assert len(body['roles']) == 8
	assert [r['scope'] for r in body['unreachable_scopes']] == ['community_aggregate', 'family']
	assert body['identity_gap'] == 'citizen_identified'
	assert set(body['guarded_scopes']) >= {'assigned', 'audit_logs', 'infrastructure'}
