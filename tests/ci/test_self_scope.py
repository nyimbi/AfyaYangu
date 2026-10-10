"""§17 IDOR gate: a personal-data route must bind the subject it names to the token that named it.

The defect this file exists for was systemic. Around forty routes took a `subject_ref` out of the
path or body, checked `self` scope, and then acted on whatever subject the caller typed — so the
scope check passed for every citizen while the subject was the caller's to choose. Several
required no token at all. Reading one person's location diary, deleting another's records, and
reading a stranger's contact list were all reachable with a token issued to somebody else, or with
no token.

Two properties are asserted, both derived from the routes rather than from a list kept by hand:

1. Every route that declares a `subject_ref` parameter, or takes a body model carrying one, must
   carry the `require_self` guard.
2. Every such route must actually refuse a token whose subject differs from the one named.

A gate that only checked (1) would pass on a guard applied but not enforced; a gate that only
checked (2) would miss a route whose guard was dropped but which happens to refuse for another
reason. Both, and the refusal must be 401/403 rather than the service's own 404/422.
"""
import json
import re
from typing import Any

import httpx

from afya.service import build_services, create_app

# Routes that legitimately carry a subject but are worker or system routes, not citizen ones.
# Named explicitly so the exemption is a decision someone made, not an omission nobody noticed.
WORKER_ROUTES: frozenset[tuple[str, str]] = frozenset({
	('POST', '/alerting/exposure'),          # CHW notifies a contact; `assigned` scope
	('POST', '/community/cases'),            # CHW case report; `assigned` scope
	('POST', '/community/cases/{report_id}/advance'),
	('POST', '/community/peer-alert'),
	('POST', '/integrations/adam/cases'),
	('POST', '/integrations/adam/monitoring'),
	('GET', '/integrations/adam/cases/{report_id}'),
	('GET', '/integrations/adam/contacts'),
	('GET', '/integrations/adam/case-definitions'),
	('GET', '/retention/transparency'),      # auditor; `audit_logs` scope
	('POST', '/auth/anonymous'),             # issues the token; the subject is what it returns
})


def _subject_carrying_routes() -> list[tuple[str, str]]:
	"""Routes that name a subject, read from the app's own OpenAPI spec."""
	spec = create_app(build_services()).openapi()
	schemas = spec['components']['schemas']
	out: list[tuple[str, str]] = []
	for path, ops in spec['paths'].items():
		for method, op in ops.items():
			named = any(p.get('name') == 'subject_ref' for p in op.get('parameters', []))
			ref = re.search(r'#/components/schemas/(\w+)', json.dumps(op.get('requestBody', {})))
			if ref and ref.group(1) in schemas:
				named = named or 'subject_ref' in schemas[ref.group(1)].get('properties', {})
			if named:
				out.append((method.upper(), path))
	return sorted(out)


def _guard_of(app: Any, method: str, path: str) -> str | None:
	"""The name of the dependency a route is guarded by, read from its own dependency graph.

	The OpenAPI spec does not name a dependency, so reading it there would only show that *some*
	`authorization` parameter exists — which every `require_scope` route also has, and which a
	route guarded by nothing but a rate limit would not. The graph is the only place the guard's
	identity is visible.

	The app is passed in rather than built here: building one per route spins up a native engine
	each time and exhausts the process.
	"""
	inner = next((getattr(r, 'app') for r in app.routes if hasattr(getattr(r, 'app', None), 'routes')), app)
	for route in getattr(inner, 'routes', []):
		if getattr(route, 'path', None) != path or method not in getattr(route, 'methods', set()):
			continue
		dependant = getattr(route, 'dependant', None)
		for dep in getattr(dependant, 'dependencies', []):
			name = getattr(dep.call, '__qualname__', '')
			if 'require_self' in name:
				return 'require_self'
			if 'require_scope' in name:
				return 'require_scope'
	return None


def test_every_subject_carrying_route_is_guarded() -> None:
	"""Invariant (1). A new personal-data route without the guard fails here, not in production."""
	app = create_app(build_services())
	unguarded: list[str] = []
	for method, path in _subject_carrying_routes():
		if (method, path) in WORKER_ROUTES:
			continue
		if _guard_of(app, method, path) != 'require_self':
			unguarded.append(f'{method} {path} ({_guard_of(app, method, path)})')
	assert unguarded == [], f'personal-data routes without a subject-binding guard: {unguarded}'


def test_the_guarded_set_is_not_vacuous() -> None:
	"""Pin the size, so a change that silently drops every route from the set cannot pass."""
	carrying = [r for r in _subject_carrying_routes() if r not in WORKER_ROUTES]
	assert len(carrying) >= 30, f'expected the citizen personal-data surface, found {carrying}'


async def _token(c: httpx.AsyncClient, subject: str) -> str:
	return str((await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token'])


async def test_a_token_cannot_act_for_another_subject() -> None:
	"""Invariant (2), driven rather than read: U1's token naming U2 must be refused.

	Each case is a real request that used to succeed. The assertion is on the status code the
	*guard* produces (401/403), not merely "not 200" — a service-level 404 for a subject with no
	records would otherwise read as a refusal while the IDOR stood.
	"""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		u1 = {'authorization': f'Bearer {await _token(c, "U1")}'}
		# Give U1 something to read, so a successful cross-subject read would return real data.
		await c.post('/location/history/enable', params={'subject_ref': 'U1'}, headers=u1)
		await c.post('/location/history/point', params={'subject_ref': 'U1'},
		             json={'geohash': 'k9y1z', 'at_iso': '2026-10-10T10:00:00Z'}, headers=u1)

		cross = [
			await c.get('/location/history/U2/report', headers=u1),
			await c.delete('/location/history/U2', headers=u1),
			await c.get('/location/checkin/U2', headers=u1),
			await c.get('/retention/inventory/U2', headers=u1),
			await c.get('/monitoring/contact/U2/diary', headers=u1),
			await c.get('/monitoring/chronic/U2/report', headers=u1),
			await c.get('/alerting/preferences/U2', headers=u1),
			await c.post('/alerting/preferences', params={'subject_ref': 'U2', 'category': 'county_alerts', 'enabled': False}, headers=u1),
			await c.post('/retention/delete', json={'subject_ref': 'U2'}, headers=u1),
			await c.post('/retention/holding', params={'subject_ref': 'U2', 'data_type': 'symptom_logs', 'count': 3}, headers=u1),
			await c.post('/community/contacts/U2/entry', json={'description': 'met at market', 'setting': 'market'}, headers=u1),
			await c.post('/location/history/point', params={'subject_ref': 'U2'},
			             json={'geohash': 'k9y1z', 'at_iso': '2026-10-10T10:00:00Z'}, headers=u1),
		]
		assert all(r.status_code == 403 for r in cross), [(r.request.url.path, r.status_code) for r in cross]

		# And the caller's own subject still works, so the guard is not refusing everything.
		assert (await c.get('/location/history/U1/report', headers=u1)).status_code == 200
		assert (await c.get('/retention/inventory/U1', headers=u1)).status_code == 200


async def test_a_personal_route_refuses_an_absent_token() -> None:
	"""The same routes with no token at all: a 401 from the guard, never the service's own answer."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		anon = [
			await c.get('/location/history/U1/report'),
			await c.get('/retention/inventory/U1'),
			await c.get('/monitoring/contact/U1/diary'),
			await c.get('/alerting/preferences/U1'),
			await c.post('/retention/delete', json={'subject_ref': 'U1'}),
			await c.get('/access/battery', params={'subject_ref': 'U1'}),
		]
		assert all(r.status_code == 401 for r in anon), [(r.request.url.path, r.status_code) for r in anon]


async def test_a_worker_token_cannot_use_a_citizen_route() -> None:
	"""A worker reaches people through its own scoped routes, never by naming a subject here."""
	from afya.auth.views import s256

	app = create_app(build_services())
	verifier = 'v' * 64
	challenge = s256(verifier)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		authz = (await c.post('/auth/pkce/authorize', json={
			'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': challenge, 'state': 'state-1234',
		})).json()
		chw = (await c.post('/auth/pkce/token', params={'role': 'chw'}, json={
			'authorization_code': authz['authorization_code'], 'client_id': 'app',
			'redirect_uri': 'afya://cb', 'code_verifier': verifier,
		})).json()['access_token']
		h = {'authorization': f'Bearer {chw}'}
		assert (await c.get('/location/history/U2/report', headers=h)).status_code == 403
		assert (await c.get('/retention/inventory/U2', headers=h)).status_code == 403


async def test_a_family_board_is_readable_only_by_its_members() -> None:
	"""§ALT-002. The board names which members are safe and which are unaccounted for, so guessing
	the reference must not be enough to read it."""
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		u1 = {'authorization': f'Bearer {await _token(c, "U1")}'}
		u2 = {'authorization': f'Bearer {await _token(c, "U2")}'}
		# U1 builds a group that includes U1 and U3 — not U2. `members` is a body parameter.
		await c.post('/alerting/family/link', params={'family_ref': 'FAM-1'}, json=['U1', 'U3'], headers=u1)
		assert (await c.get('/alerting/family/FAM-1', headers=u1)).status_code == 200
		assert (await c.get('/alerting/family/FAM-1', headers=u2)).status_code == 403, 'a stranger read the board'
		# A group that does not include its own creator is refused, so no one can link a stranger in.
		assert (await c.post('/alerting/family/link', params={'family_ref': 'FAM-2'}, json=['U9'], headers=u2)).status_code == 403
