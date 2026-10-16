"""Gate: every served route is reachable from the catalogue, or named in `API_ONLY` with a reason.

The question this answers is the one the catalogue's own tests could not: *which routes are
API-only?* The catalogue test asserts each *action* maps to a route — the direction that finds a
broken screen. Nothing asked the reverse, and the reverse is where the defect was: eleven routes on
the citizen's own data, guarded `require_self`, offered by no action, so a capability existed and no
handset could reach it. §REC-001's wallet could be read by a guardian and enrolled into by nobody;
§17.2's correction workflow had a right with no way to exercise it; §16.3's conflicts were computed
and never shown.

That defect was invisible to `test_feature_coverage.py`, and the reason is worth stating: that gate
asks about *features*, and every one of those modules had another route covering the feature. A
route on an already-covered feature slips through a feature-level gate by construction. This one
asks at route granularity, which is the granularity the defect lives at.

**Both directions, because each alone is half an answer.** An action whose path is not served is a
screen that 404s; a served route with no action is a capability nobody can reach. The two sets are
crossed, and the only honest escape from the second is a named jurisdiction — `API_ONLY` in
`afya.mobile.actions`, where each entry carries the reason it is not a citizen action.

**The `client_direct` entries are read, not asserted.** A path a native client names literally is
the one jurisdiction that can be *verified* rather than declared, so it is: the test extracts the
path literals from the iOS and Android sources and asserts that set equals the `client_direct`
entries. A client that stops calling the resumable-upload route, or one that starts calling a route
the register does not name, fails here. That is the §16.4 canary's finding — "the route exists" and
"a handset calls it" are different facts — turned into a standing check.
"""
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from afya.mobile.actions import API_ONLY, catalogue
from afya.service import build_services, create_app

REPO = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def _app() -> Any:
	"""One app for the whole module.

	`create_app` spins up a native engine per call, and five tests each building their own exhausted
	the process — the suite aborted at teardown with `recursive_mutex lock failed` *after* printing
	`2373 passed`, which is a green run that exits 134. Building once is what the other route-walking
	gates in this directory already do implicitly by being one test per file.
	"""
	return create_app(build_services())


def _served() -> set[tuple[str, str]]:
	"""Every `(method, path)` the app actually serves, read off the running object.

	Not from the source. `app.routes` on the object `create_app()` returns holds four entries — the
	root, the OpenAPI document and two mounts — because every route is declared on the sub-app the
	`/v1` mount wraps. An AST walk over `service.py` finds them, and an inventory read from source
	is not an inventory the app serves: the two agree today and nothing keeps them agreeing. This
	walks the mounts, so what is compared is what a request reaches.
	"""
	app = _app()
	found: set[tuple[str, str]] = set()

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			path = getattr(r, 'path', None)
			if not path:
				continue
			for method in getattr(r, 'methods', None) or []:
				if method not in ('HEAD', 'OPTIONS'):
					found.add((method, path))

	walk(app.routes)
	# FastAPI's own documentation routes. Not this app's surface: they are the framework's, they
	# serve no data, and naming them in a register of *our* routes would be four entries of noise.
	return {r for r in found if r[1] not in ('/', '/docs', '/docs/oauth2-redirect',
	                                         '/openapi.json', '/redoc')}


def _client_paths() -> set[str]:
	"""Path literals the two native clients name, rather than draw from the catalogue.

	Read from the sources so the `client_direct` jurisdiction is checked rather than trusted. The
	pattern is deliberately narrow — a quoted string with a slash, lower-case and not a URL — which
	is what a route path looks like in both languages. Interpolations (`\\(sessionId)`,
	`$sessionId`) normalise to `*`, the same way the served set's `{param}` does.

	Two things it matches that are not routes, filtered here rather than by tightening the pattern:
	a media type (`/application/json`, `/image/jpeg`) is a quoted string with a slash too, and a
	path a client names literally *and* the catalogue also offers (`/triage/preliminary`,
	`/facilities/nearest`) is a hardcoded call to a route that already has an action — the client
	choosing not to go through the catalogue for it, which is not a jurisdiction. `client_direct`
	means named literally **and** reached by no action, so the filter is the catalogue itself.
	"""
	pattern = re.compile(r'"([a-z][a-z0-9/_{}$()\\\\.-]*)"')
	found: set[str] = set()
	for path in (sorted((REPO / 'ios' / 'AfyaYangu').glob('*.swift'))
	             + sorted((REPO / 'android' / 'app' / 'src' / 'main').rglob('*.kt'))):
		for literal in pattern.findall(path.read_text()):
			if '/' not in literal or literal.startswith('http'):
				continue
			if literal.split('/')[0] in ('application', 'image', 'text', 'audio', 'multipart'):
				continue  # a media type, not a path
			literal = re.sub(r'\\\(.*?\)|\$\{?[A-Za-z_][A-Za-z0-9_.]*\}?', '*', literal)
			found.add('/' + literal)
	return found


def test_every_served_route_is_reachable_or_named_api_only() -> None:
	"""The gate. A route with no action and no jurisdiction fails here."""
	served = _served()
	reached = {(a.method.upper(), a.path) for a in catalogue()}
	unaccounted = sorted(f'{m} {p}' for m, p in served - reached if (m, p) not in API_ONLY)
	assert unaccounted == [], (
		f'{len(unaccounted)} served routes no action reaches and no jurisdiction claims: {unaccounted}. '
		'Add a catalogue action, or name the route in API_ONLY with the party that reaches it.'
	)


def test_every_catalogue_action_has_a_route() -> None:
	"""The other direction: an action whose path is not served is a screen that 404s.

	The catalogue's own build assert already ties each action to a *feature*; this ties it to a
	route, which is the half a feature cannot check.
	"""
	served = _served()
	reached = {(a.method.upper(), a.path) for a in catalogue()}
	broken = sorted(f'{m} {p}' for m, p in reached - served)
	assert broken == [], f'catalogue actions with no served route: {broken}'


def test_the_register_does_not_drift() -> None:
	"""An entry naming a route that is now reached, or gone, is stale and must come off.

	The same rule `ON_DEVICE` and `UNGATED_WRITES` carry, and for the same reason: a list that
	accumulates reasons for gaps that no longer exist stops meaning anything, and the next reader
	cannot tell a live jurisdiction from a leftover.
	"""
	served = _served()
	reached = {(a.method.upper(), a.path) for a in catalogue()}
	stale = sorted(f'{m} {p}' for m, p in API_ONLY if (m, p) in reached or (m, p) not in served)
	assert stale == [], f'API_ONLY names routes that are reached, absent or misspelled: {stale}'
	# A jurisdiction is one scope, or several joined with `+` where the route carries
	# `require_any_scope` and any of them opens it. Every component must be a real scope: a typo
	# here would read as a jurisdiction nobody can check.
	scopes = {
		'assigned', 'audit_logs', 'infrastructure', 'county_aggregate', 'national_aggregate',
		'consented_patient', 'community_aggregate', 'family',
	}
	parties = {'client_direct', 'device_only', 'citizen_self', 'inbound_wire', 'device_write',
	           'public_read'}
	for route, jurisdiction in API_ONLY.items():
		parts = set(jurisdiction.split('+'))
		assert parts <= (scopes | parties), (
			f'{route} carries an unknown jurisdiction {jurisdiction!r}; '
			f'not a scope or party: {sorted(parts - scopes - parties)}')


def test_the_client_direct_entries_are_the_paths_the_clients_actually_name() -> None:
	"""The one jurisdiction that can be verified rather than declared, so it is.

	`client_direct` says a native client calls this path by name. That is a fact about two source
	trees, not a judgement, and asserting it here is what stops the entry becoming a place to park a
	route whose action nobody wants to write. A client that stops naming the path, or names one the
	register does not list, fails.
	"""
	named = _client_paths()
	# Both sides normalise a parameter to `*`, because the client writes `\(sessionId)` and the
	# route writes `{session_id}`. Comparing them raw is the "one of two spellings" defect: the
	# client's `/channels/chw/tasks/*/done` and the catalogue's `/channels/chw/tasks/{task_id}/done`
	# are the same route, and a raw comparison would call the first one client-direct.
	reached = {re.sub(r'\{[^}]+\}', '*', a.path) for a in catalogue()}
	named = {p for p in named if p not in reached}
	registered = {p for (_, p) in API_ONLY if API_ONLY[(_, p)] == 'client_direct'}
	missing = sorted(named - registered)
	extra = sorted(registered - named)
	assert missing == [], (
		f'a native client names these paths and the register does not: {missing}. '
		'They are either a new client-direct route or a literal the extractor should not match.'
	)
	assert extra == [], (
		f'the register calls these client_direct and no client names them: {extra}. '
		'A path a client stopped calling is a route reached by nobody.'
	)


def test_the_gate_catches_an_unaccounted_route() -> None:
	"""Canary, driven against a synthetic set, so it proves the comparison rather than the data.

	The mutation is a route genuinely absent from both sets — not one spelled differently — because
	a predicate that is a strict subset of what it tests fails open, and the failure mode of this
	gate is exactly that.
	"""
	served = {('GET', '/records/wallet'), ('GET', '/zzz/invented')}
	reached = {('GET', '/records/wallet')}
	api_only: dict[tuple[str, str], str] = {}
	unaccounted = sorted(f'{m} {p}' for m, p in served - reached if (m, p) not in api_only)
	assert unaccounted == ['GET /zzz/invented'], 'the gate must flag a route with no action and no entry'
	api_only[('GET', '/zzz/invented')] = 'public_read'
	assert [f'{m} {p}' for m, p in served - reached if (m, p) not in api_only] == []
