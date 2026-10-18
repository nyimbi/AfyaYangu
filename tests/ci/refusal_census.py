"""What the routes still refuse once every form draws what it means. A script, not a pytest module.

Run: `uv run python -I tests/ci/refusal_census.py`

The number this produces is the closing measurement of the conditional-requirement unit: before the
marking, a form offered 443 fields its route refused without and said nothing about them; after, the
refusals that remain should be **value-shape** — the form asks the question and the person supplies
the answer — rather than a field the form failed to draw.

The distinction is the whole point, so it is read off the refusal's own error type rather than
asserted. FastAPI reports a body property it never received as `missing`; everything else
(`string_pattern_mismatch`, `less_than_equal`, `value_error` from a model validator, a handler's
`HTTPException`) is a refusal of an answer that was given. A `missing` refusal is the defect this
unit is about; a `value_error` is a business rule the form cannot pre-empt and is not.

Every route is probed with **all** its required fields filled and every optional field answered, so a
`missing` can only mean a field the catalogue does not draw at all — not one this script forgot.

Not named `test_*`, so pytest's default collection ignores it; running it *by name* under pytest
forces collection and raises `SystemExit`, which is a confusing way to learn it is a script.
"""
import asyncio
import collections
import json
import secrets

import httpx

from afya.access.forms import required_fields
from afya.auth.views import s256
from afya.mobile.actions import catalogue, marked
from afya.service import build_services, create_app

VERIFIER = secrets.token_urlsafe(64)[:64]


async def token_for(c: httpx.AsyncClient, role: str) -> str:
	"""A token for `role`, through the same PKCE flow the app uses.

	Needed because 105 of the 162 write routes answer **401** to an anonymous probe, and a 401 is not
	a fact about a form. Counting them as refusals would have made this census read "149 refusals"
	when most of them are the transport's, and the number that matters — a field the form failed to
	draw — would have been buried in it.

	Only `ISSUABLE_ROLES` can be asked for here: `sysadmin` and `auditor` are provisioned
	operationally, so the flow refuses them by design (`assert role in ISSUABLE_ROLES`) and a probe
	that asked would read a correct refusal as a missing token.
	"""
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': s256(VERIFIER),
		'state': 'state-1234'})).json()
	resp = await c.post('/auth/pkce/token', params={'role': role}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': VERIFIER})
	out = resp.json()
	assert 'access_token' in out, f'no token for {role}: {resp.status_code} {resp.text[:200]}'
	return str(out['access_token'])


def value_for(field: dict) -> object:
	"""A value the field's own type accepts, so a refusal is about the route and not the probe."""
	if field['type'] == 'select':
		return (field.get('options') or ['x'])[0]
	if field['type'] == 'list':
		# A list of ints, not of strings: `target_age_months` is `list[int]`, and sending `['a']`
		# makes Pydantic report a *missing* element at index 1 — a `missing` the form did draw, which
		# would have gone into this census as a defect of the catalogue. The refusal's own location
		# (`body.target_age_months.1`) is what says it is the probe's, not the form's.
		return [40]
	if field['type'] == 'int':
		return 40
	if field['type'] == 'decimal':
		return 36.5
	if field['type'] == 'bool':
		return True
	if field['type'] == 'path':
		return 'P1'
	return 'a value long enough to pass a minimum'


def refusal_kind(resp: httpx.Response) -> str:
	"""The refusal's own classification, read off the response rather than guessed from the status.

	The first cut of this script called everything without a schema detail "route-level" and got 126
	of them, which is not a fact about forms: the probe carries no token, so a route behind a scope
	answers 401/403 and the handler's `HTTPException` is indistinguishable from a business rule by
	its body alone. Status first, then the detail — a refusal the *transport* makes says nothing about
	whether the form drew the right fields.
	"""
	if resp.status_code < 400:
		return 'accepted'
	if resp.status_code in (401, 403):
		# Named rather than bucketed: "77 unauthorized" says nothing about whether the form is right,
		# while `role chw may not read infrastructure` says the route is behind a scope no app-issued
		# role carries. The detail is the guard's own words.
		try:
			body = resp.json().get('detail')
		except Exception:
			body = None
		return f'unauthorized: {str(body)[:60]}' if body else 'unauthorized'
	try:
		detail = resp.json().get('detail')
	except Exception:
		return 'route-level'
	if not isinstance(detail, list) or not detail:
		return 'route-level'  # an HTTPException the handler raised: a business rule, not a schema
	kinds = {str(d.get('type', '?')) for d in detail if isinstance(d, dict)}
	if not kinds:
		return 'route-level'
	if kinds == {'missing'}:
		return 'missing'
	# A body carrying both a missing field and a bad one is a value-shape refusal with a tail; the
	# field the form failed to draw is the `missing` one, so it is reported separately below.
	return 'value-shape' if 'missing' not in kinds else 'value-shape+missing'


async def main() -> None:
	app = create_app(build_services())
	required = required_fields(app)
	served = {a.id: a.model_dump(mode='json') for a in marked(catalogue(), required)}

	kinds: collections.Counter[str] = collections.Counter()
	statuses: collections.Counter[int] = collections.Counter()
	missing_sites: list[tuple[str, list[str]]] = []
	probed = 0
	# Read before the probe loop, because the loop needs two facts off the document: which routes are
	# multipart (a JSON body cannot reach them) and which have a required *query* parameter (a body
	# carrying it is refused for a `missing` the form draws perfectly well).
	spec = app.openapi()
	multipart: set[str] = set()
	query_required: dict[str, set[str]] = {}
	for path, ops in spec['paths'].items():
		for method, op in ops.items():
			content = ((op.get('requestBody') or {}).get('content') or {})
			key = f'{method.upper()} {path}'
			if 'multipart/form-data' in content:
				multipart.add(key)
			query_required[key] = {p['name'] for p in op.get('parameters', [])
			                       if p.get('in') == 'query' and p.get('required')}
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		# One token per role, because no §17.4 role carries every scope — `_SCOPE` gives a chw
		# `assigned`, a county officer `county_aggregate` — so a route is probed under the role whose
		# scope it guards on. A route refused under all of them is guarded by a scope no role carries,
		# which is a finding of its own and is reported rather than counted as a form defect.
		tokens = {role: await token_for(c, role) for role in
		          ('chw', 'clinician', 'county_officer', 'pheoc_analyst')}
		# And a citizen, because 75 of the write routes are the person's own — `/triage/diary`,
		# `/info/stories`, `/records/member` — and each answers every staff role
		# `role X may not act for a citizen subject`. Without this token the census would report
		# three quarters of its routes as unreachable and never see what they refuse.
		tokens['citizen'] = str((await c.post(
			'/auth/anonymous', json={'subject_ref': 'census-caller'})).json()['token'])
		# Each token's own subject, read from the token rather than assumed: `subject_ref` on a form
		# must equal it, and the PKCE flow issues the worker's subject while the anonymous flow issues
		# the one it was asked for.
		subjects: dict[str, str] = {}
		for role, tok in tokens.items():
			me = await c.get('/auth/whoami', headers={'Authorization': f'Bearer {tok}',
			                                          'x-device-id': f'who-{role}'})
			subjects[role] = str(me.json()['subject_ref'])
		# A fresh device id per request: the limiter is keyed on `x-device-id` and falls back to the
		# client host, so an unset header puts all 162 probes on one budget and 12 answer 429.
		for i, act in enumerate(served.values()):
			if act['method'] not in ('POST', 'PUT', 'PATCH'):
				continue
			base = {f['name']: value_for(f) for f in act['fields'] if not f.get('client_supplied')}
			# A client-supplied field is one the client computes — a hash, a device id — and the
			# catalogue marks it so the form does not ask. Sent as a placeholder so the probe is not
			# refused for a reason the catalogue already accounts for.
			base.update({f['name']: 'ME' for f in act['fields']
			             if f.get('client_supplied') and f['name'] != 'subject_ref'})
			path = act['path']
			for seg in path.split('/'):
				if seg.startswith('{'):
					path = path.replace(seg, 'P1')
			best: httpx.Response | None = None
			route_key = f"{act['method']} {act['path']}"
			# A required *query* parameter is not a body property, and a JSON body carrying it is
			# refused for a `missing` the form now draws perfectly well. Sending it in the right place
			# is what makes this census about the form rather than about where the probe put a value.
			params = {n: '2026-10-12T08:30' for n in query_required.get(route_key, set())}
			for role, tok in tokens.items():
				# `subject_ref` is client-supplied *and* `require_self` checks it against the token, so
				# it has to carry that token's own subject. A placeholder of `'ME'` answers
				# `a token may act only for its own subject` — a 403 that looks like a scope refusal
				# and hid 65 citizen routes behind it. Rebuilt per role, because the subject differs.
				body = dict(base)
				if any(f['name'] == 'subject_ref' for f in act['fields']):
					body["subject_ref"] = subjects[role]
				headers = {'Authorization': f'Bearer {tok}', 'x-device-id': f'census-{i}-{role}'}
				try:
					resp = await c.request(act['method'], path, json=body, params=params, headers=headers)
				except Exception as exc:
					kinds[f'raised:{type(exc).__name__}'] += 1
					break
				# The answer the form must satisfy is the one from a role the route *admits*, so a
				# 401/403 is kept only as a fallback. Picking the numerically lowest status instead —
				# which this did first — lets 403 beat 422 and reports `submit_case` as unreachable when
				# a chw reaches it fine and gets a schema answer; 106 routes read that way. A transport
				# refusal is not evidence about the fields, so it must not outrank a schema refusal.
				rank = (0 if resp.status_code in (401, 403) else 1, -resp.status_code)
				if best is None or rank > (0 if best.status_code in (401, 403) else 1, -best.status_code):
					best = resp
				if resp.status_code < 400:
					break
			if best is None:
				continue
			probed += 1
			statuses[best.status_code] += 1
			kind = refusal_kind(best)
			kinds[kind] += 1
			if 'missing' in kind:
				try:
					detail = best.json()['detail']
					# A `missing` whose location is *inside* a list (`body.target_age_months.1`) is an
					# element the probe did not send, not a field the form failed to draw. Only a
					# top-level missing names a question the catalogue owes the person.
					names = sorted({str(d['loc'][-1]) for d in detail
					                if isinstance(d, dict) and d.get('type') == 'missing'
					                and len(d.get('loc', [])) == 2})
					if not names:
						continue
				except Exception:
					names = ['?']
				missing_sites.append((act['id'], names))

	refusals = sum(v for k, v in kinds.items() if k != 'accepted')
	print(f'probed {probed} write routes')
	print(f'statuses: {dict(sorted(statuses.items()))}')
	print(f'refusals: {refusals}  {dict(sorted(kinds.items()))}')
	print(f'MISSING-field refusals: {len(missing_sites)}')
	for site, names in missing_sites:
		print(f'   {site}: {names}')

	# The claim this census exists to make: every `missing` left is a field the catalogue *does* mark
	# required and this probe cannot send, not a question the form fails to draw. Asserted rather than
	# printed, because "the remaining ones look like probe artifacts" is exactly the reading that
	# turns a defect into a footnote.
	#
	# The artifact class is the **route's** media type, not the field's type. The first version of
	# this check asked "is it a `file` field?" and `whatsapp_voice` failed it on `from_msisdn` — a
	# `Form(...)` parameter that a JSON body cannot carry either. The route consumes
	# `multipart/form-data`, so *no* body property on it is reachable from this probe; scoping the
	# exemption to one field type was scoping it to one of the two ways a form is written, and the
	# assertion caught it.
	by_id = {a['id']: a for a in served.values()}
	unexplained: list[str] = []
	for site, names in missing_sites:
		act = by_id[site]
		route = f"{act['method']} {act['path']}"
		# Two separate claims, and the exemption applies to only the first. A multipart route is
		# excused from *reachability* — a JSON body cannot carry a `Form(...)` part — but not from
		# marking: `submit_evidence.kind` is drawn and required, and if it were not, the form would be
		# wrong in exactly the way this census exists to catch. An early `continue` on the media type
		# skipped the marking check too, which is the exemption quietly widening to the thing it must
		# not excuse.
		unmarked = [n for n in names if not any(f['name'] == n and f['required'] for f in act['fields'])]
		if unmarked:
			unexplained.append(f'{site}: {unmarked} not marked required by the catalogue')
		elif route not in multipart:
			unexplained.append(f'{site}: {names} refused on a JSON-reachable route')
	print(f'multipart routes (exempt from reachability, not from marking): {len(multipart)}')
	print(f'unexplained missing-field refusals: {len(unexplained)}')
	for line in unexplained:
		print(f'   {line}')
	assert not unexplained, f'missing-field refusals the catalogue does not account for: {unexplained}'

	print()
	print(json.dumps({'probed': probed, 'statuses': dict(statuses), 'kinds': dict(kinds),
	                  'multipart_routes': sorted(multipart), 'missing': missing_sites,
	                  'unexplained': unexplained}, indent=2))


if __name__ == '__main__':
	asyncio.run(main())
