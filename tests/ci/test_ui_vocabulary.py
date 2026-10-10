"""Gate: no spec feature code may reach a surface a person reads.

Spec ids (REC-004, MON-009, CHAN-005, ...) are internal traceability handles. A user of the app
or an SMS reply must never see one. This test walks every user-facing surface we control — the
mobile action catalogue, the friendly-copy table, the served /mobile/* payloads, and the native
client string literals — and fails if the pattern `PREFIX-000` appears anywhere in them.

It is deliberately structural: it inspects the *served* objects rather than the source text, so a
code that reaches a screen through any route is caught, not just one written into a literal.
"""
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from afya.mobile.actions import (
	DORMANT_SLUGS,
	FEATURE_OF,
	FRIENDLY_COPY,
	OPERATOR_SCOPES,
	available,
	catalogue,
	dormant_slugs,
	tier4_feature_ids,
)
from afya.service import create_app

# The registry's own id grammar, reused so the gate cannot drift from what ids actually look like.
FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

REPO = Path(__file__).resolve().parents[2]


def _outbreak_app() -> tuple[Any, dict[str, str]]:
	"""The app and an operator's token for it.

	The token must come from the *same* service instance the app was built with — `AuthService`
	holds issued tokens in memory, so a token minted on a fresh `build_services()` is unknown to a
	separately built app and every request reads as unauthenticated.
	"""
	from afya.privacy.views import RBACRole
	from afya.service import build_services
	services = build_services()
	ops = services['auth'].provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token  # type: ignore[union-attr]
	return create_app(services), {'authorization': f'Bearer {ops}'}


def _silent_wav(seconds: int = 2) -> bytes:
	"""A valid 16 kHz mono WAV, so the cough route reaches its gate instead of failing to parse."""
	import io
	import struct
	import wave

	buf = io.BytesIO()
	with wave.open(buf, 'wb') as w:
		w.setnchannels(1)
		w.setsampwidth(2)
		w.setframerate(16000)
		w.writeframes(struct.pack('<%dh' % (16000 * seconds), *([0] * 16000 * seconds)))
	return buf.getvalue()


def _scan(label: str, text: str) -> list[str]:
	return [f'{label}: {m.group(0)}' for m in FEATURE_CODE.finditer(text)]


def test_gate_catches_a_planted_code() -> None:
	"""Canary. A gate never watched failing is not evidence — point it at known-bad text first."""
	planted = _scan('planted', '{"title": "Blood donor matching (REC-004)"}')
	assert planted == ['planted: REC-004'], 'the detector must fire on a code embedded in a label'
	# And it must not fire on the legitimate things that look similar.
	for clean in ('Take 400 mg', 'USSD-1 menu', 'COVID-19', 'REC-00', 'the 2026-10-10 report'):
		assert _scan('clean', clean) == [], f'false positive on {clean!r}'


def test_catalogue_actions_carry_no_codes() -> None:
	bad: list[str] = []
	for act in catalogue():
		payload = act.model_dump(mode='json')
		payload.pop('id', None)  # the slug is the wire id and is code-free by construction
		bad += _scan(f'action {act.id}', str(payload))
	assert bad == [], f'feature codes leaked into the action catalogue: {bad}'


def test_action_ids_are_slugs_not_codes() -> None:
	for act in catalogue():
		assert FEATURE_CODE.search(act.id) is None, f'action id {act.id} is a spec code, not a slug'
		assert re.fullmatch(r'[a-z][a-z0-9_]*', act.id), f'action id {act.id} is not a slug'


def test_friendly_copy_is_code_free() -> None:
	bad: list[str] = []
	for slug, (title, desc) in FRIENDLY_COPY.items():
		bad += _scan(f'copy {slug}', f'{title} {desc}')
	assert bad == [], f'feature codes leaked into friendly copy: {bad}'


def test_every_action_declares_a_spec_feature() -> None:
	"""Traceability both ways: every slug maps to a feature, and no declaration dangles."""
	ids = {a.id for a in catalogue()}
	assert ids - set(FEATURE_OF) == set(), 'actions with no declared source feature'
	assert set(FEATURE_OF) - ids == set(), 'FEATURE_OF declares features no action implements'


def test_dormant_slugs_are_real_actions() -> None:
	"""A dormant slug that is not an action is a filter entry that can never fire, and the
	outbreak gate would silently stop hiding a capability."""
	ids = {a.id for a in catalogue()}
	assert DORMANT_SLUGS - ids == set(), f'dormant slugs with no action: {sorted(DORMANT_SLUGS - ids)}'
	assert DORMANT_SLUGS, 'the dormant set must not be empty or the outbreak gate hides nothing'


def test_every_tier4_action_is_dormant() -> None:
	"""The invariant the earlier gate lacked: dormancy follows the tier model, not a hand-kept list.

	Six Tier-4 features had live actions — the whole COM-101 CHW reporting module, contact-tracing
	prompts, check-in points, cough analysis and symptom-photo upload — because `DORMANT_SLUGS` was
	checked only against itself. A client showed controls the spec says stay dark until PHEOC
	activates the event, and the server refused them, which is exactly the "switch that refuses
	you" §11.1 exists to prevent.
	"""
	tier4 = tier4_feature_ids()
	live = sorted(slug for slug, feat in FEATURE_OF.items() if feat in tier4 and slug not in DORMANT_SLUGS)
	assert live == [], f'Tier-4 features with live actions: {live}'


def test_tier4_feature_set_is_not_vacuous() -> None:
	"""Canary for the gate above: if the registry ever returns no Tier-4 features, the check would
	pass while proving nothing. Pin the count so that failure is loud."""
	assert len(tier4_feature_ids()) >= 15, 'Tier-4 set collapsed — the dormancy gate would be vacuous'
	assert 'COM-101' in tier4_feature_ids() and 'SENS-004' in tier4_feature_ids(), 'tier lookup drifted'


def test_travel_advisory_belongs_to_travel_advisory() -> None:
	"""INF-005 Travel Advisory is Tier 1; LOC-005 is the Tier-4 border module. Mis-mapping the
	slug to LOC-005 made an always-on capability look dormant-gated and hid it for no reason."""
	assert FEATURE_OF['travel_advisory'] == 'INF-005'
	assert 'travel_advisory' not in dormant_slugs(), 'a Tier-1 advisory must not be withheld'


async def test_dormant_capabilities_are_withheld_until_activation() -> None:
	"""§11.1: the client must not see a control that would refuse it. Served, not just filtered."""
	hidden = dormant_slugs()
	assert len(available(False)) < len(available(True)), 'activation must reveal something'
	assert {a.id for a in available(True)} - {a.id for a in available(False)} == set(hidden)

	app, h = _outbreak_app()
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		# Read with the operator's token. The exact-equality claim is made above against the pure
		# function, where no scope filter applies; here the claim is about the served payload, and
		# a caller only ever sees the dormant controls its own scope reaches — a CHW caseload
		# screen is not unlocked *for a sysadmin* by activating the outbreak, it was never his.
		before = {a['id'] for a in (await c.get('/mobile/actions', headers=h)).json()}
		assert not (before & hidden), 'dormant capabilities served before activation'
		await c.post('/tier4/activate', headers=h,
		             json={'authorized_by_pheoc': True, 'dpia_reviewed': True, 'flag_enabled': True})
		after = {a['id'] for a in (await c.get('/mobile/actions', headers=h)).json()}
		assert after - before, 'activation must reveal something to the caller who opened the gate'
		assert (after - before) <= set(hidden), 'activation revealed a control that was never dormant'

	# And every dormant control is reachable by some role once the gate is open — one no role can
	# reach is a capability the activation claims to unlock and nobody can use.
	reachable: set[str] = set()
	for scope in ('self', 'family', 'assigned', 'county_aggregate', 'national_aggregate', 'infrastructure', 'audit_logs'):
		reachable |= {a.id for a in available(True, frozenset({scope}))}
	unreachable = sorted(set(hidden) - reachable)
	assert unreachable == [], f'dormant controls no role can reach: {unreachable}'


async def test_served_mobile_payloads_are_code_free() -> None:
	"""The gate that matters: what the client actually receives."""
	app = create_app()
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		for path in ('/mobile/actions', '/mobile/features'):
			body = (await c.get(path)).text
			assert _scan(path, body) == [], f'feature codes served at {path}'


async def test_tier4_refusals_carry_no_codes() -> None:
	"""A refusal is read by a person. Four of them named the feature id and the tier number:
	"Tier 4 dormant (SENS-004)", "TRI-003 is Tier 4 dormant", "SENS-002 acoustic cough...".

	The code leaks through the error path rather than the success path, which is why a gate that
	only scanned served payloads never saw it.
	"""
	app = create_app()
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		# Each of these is refused while the outbreak gate is closed, and each used to name a code.
		# A token is presented because these are personal-data routes: the refusal under test is the
		# feature gate's, so the request must clear the auth guard to reach it.
		tok = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		auth = {'authorization': f'Bearer {tok}'}
		blob = b'\xff\xd8\xff' + b'x' * 2000
		refusals = [
			await c.post('/triage/evd', json={'symptoms': ['fever'], 'temperature_c': 39.0, 'ebola_contact': True}),
			await c.post('/sensors/ingest', json={'kind': 'cough', 'subject_ref': 'U1', 'value': 20.0, 'county': 'Nairobi'}, headers=auth),
			await c.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
			             data={'kind': 'rash', 'subject_ref': 'U1', 'county': 'Nairobi'}, headers=auth),
			# The cough engine refuses independently of the ingest route, so it is its own surface.
			await c.post('/ml/cough/analyze', files={'file': ('a.wav', _silent_wav(), 'audio/wav')}),
		]
		assert all(r.status_code == 403 for r in refusals), [r.status_code for r in refusals]
		bad: list[str] = []
		for r in refusals:
			bad += _scan('refusal', r.text)
		assert bad == [], f'feature codes served in a refusal: {bad}'


async def test_the_symptom_photo_gate_cannot_be_encoded_around() -> None:
	"""The gate is on the *feature the request selects*, so the encoding must not change it.

	FastAPI leaves undeclared parameters at their defaults when a request is multipart, so
	`kind=rash` in a form body was ignored and the route's `scene_photo` default was submitted
	instead — a Tier-3 feature. The same request as query parameters was refused. Android's
	uploader writes the form shape, so the SENS-004 gate was bypassable from the shipped client.
	"""
	app = create_app()
	transport = httpx.ASGITransport(app=app)
	blob = b'\xff\xd8\xff' + b'x' * 2000
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		tok = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		auth = {'authorization': f'Bearer {tok}'}
		as_form = await c.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
		                       data={'kind': 'rash', 'subject_ref': 'U1', 'county': 'Nairobi'}, headers=auth)
		assert as_form.status_code == 403, as_form.text
		assert 'rash' not in as_form.text, 'the refusal must not echo what the caller claimed'
		# The encoding that used to slip through is now refused outright rather than reinterpreted:
		# a multipart upload with the kind in the query string binds nothing, so it cannot submit a
		# defaulted kind behind the caller's back.
		as_query = await c.post('/evidence?kind=rash&subject_ref=U1&county=Nairobi',
		                        files={'file': ('p.jpg', blob, 'image/jpeg')}, headers=auth)
		assert as_query.status_code == 422, as_query.text
		# And the community kind still passes while dormant, because COM-005 is Tier 3.
		scene = await c.post('/evidence', files={'file': ('p.jpg', blob, 'image/jpeg')},
		                     data={'kind': 'scene_photo', 'subject_ref': 'U1', 'county': 'Nairobi'}, headers=auth)
		assert scene.status_code == 200, scene.text
		# A content type outside the model's contract is refused, not silently relabelled.
		bad_mime = await c.post('/evidence', files={'file': ('p.txt', blob, 'text/plain')},
		                        data={'kind': 'scene_photo', 'subject_ref': 'U1', 'county': 'Nairobi'}, headers=auth)
		assert bad_mime.status_code == 422, bad_mime.text


@pytest.mark.parametrize('client_dir', ['ios/AfyaYangu', 'android/app/src/main/java/ke/go/health/afyayangu'])
def test_native_clients_carry_no_codes(client_dir: str) -> None:
	"""Native string literals are user-facing too. Scan the sources, not the built artefacts."""
	root = REPO / client_dir
	if not root.exists():
		pytest.skip(f'{client_dir} not present')
	bad: list[str] = []
	for src in sorted(root.rglob('*')):
		if src.suffix not in ('.swift', '.kt'):
			continue
		for line_no, line in enumerate(src.read_text(encoding='utf-8').splitlines(), 1):
			# Comment lines are developer-facing and may legitimately cite the spec.
			stripped = line.strip()
			if stripped.startswith(('//', '///', '*', '/*')):
				continue
			bad += _scan(f'{src.relative_to(REPO)}:{line_no}', line)
	assert bad == [], f'feature codes in native client strings: {bad}'


@pytest.mark.parametrize('client_dir', ['ios/AfyaYangu', 'android/app/src/main/java/ke/go/health/afyayangu'])
def test_clients_do_not_read_the_code_bearing_registry(client_dir: str) -> None:
	"""A code can reach a screen through a served payload, not only a literal.

	`/features` is the ops registry and its `id` is the spec code (`CHAN-000`); the client-facing
	endpoint is `/mobile/features`, whose ids are slugs. Android read the registry and printed
	`it.id` on screen, which the literal scan could not see. No client may read `/features`.
	"""
	root = REPO / client_dir
	if not root.exists():
		pytest.skip(f'{client_dir} not present')
	bad: list[str] = []
	for src in sorted(root.rglob('*')):
		if src.suffix not in ('.swift', '.kt'):
			continue
		for line_no, line in enumerate(src.read_text(encoding='utf-8').splitlines(), 1):
			stripped = line.strip()
			if stripped.startswith(('//', '///', '*', '/*')):
				continue
			# The registry is read by the string "features" as a path; "/mobile/features" is fine.
			if re.search(r'["\']features["\']', line) and 'mobile' not in line:
				bad.append(f'{src.relative_to(REPO)}:{line_no}: {stripped[:70]}')
	assert bad == [], f'clients read the code-bearing /features registry: {bad}'


async def test_an_operator_control_is_not_offered_to_a_citizen() -> None:
	"""The other half of §11.1's rule, on the other axis.

	Dormancy withholds a control whose *feature* is dark. This is the same failure on the caller's
	axis: `publish_content` writes what the Ministry says and `content_governance` reads who signed
	it off, and both are guarded on an operator dataset. A citizen token calling them gets a 403,
	so serving the controls to a citizen offers four screens that refuse — the exact thing the
	dormancy rule exists to prevent, wearing a different hat.

	The list is crossed against the routes' real guards in `test_operator_scopes_match_the_routes`,
	so a guard that changes cannot leave a stale control behind.
	"""
	app, h = _outbreak_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		await c.post('/tier4/activate', headers=h,
		             json={'authorized_by_pheoc': True, 'dpia_reviewed': True, 'flag_enabled': True})
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		citizen = {a['id'] for a in (await c.get('/mobile/actions', headers={'authorization': f'Bearer {anon}'})).json()}
		operator = {a['id'] for a in (await c.get('/mobile/actions', headers=h)).json()}
		assert not (citizen & set(OPERATOR_SCOPES)), 'operator controls served to a citizen'
		# Each control is reachable by *a* role holding its scope. §17.4 splits the two operator
		# scopes across different roles, so this is asserted per scope rather than against one token.
		for slug, scope in OPERATOR_SCOPES.items():
			assert slug in {a.id for a in available(True, frozenset({scope}))}, \
				f'{slug} is unreachable even by a role holding {scope}'
		assert 'publish_content' in operator, 'the operator token must reach what its scope opens'
		# And the control really would have refused: the claim is about the route, not the label.
		refused = await c.post('/info/content', headers={'authorization': f'Bearer {anon}'}, json={})
		assert refused.status_code == 403
		# The broadcast routes are the sharp end of this: an anonymous caller used to be able to
		# publish "Ebola confirmed in Nairobi" to every phone in the county.
		for path, body in (
			('/alerts', {'alert_id': 'AL-FAKE0001', 'kind': 'outbreak_evd', 'county': 'Nairobi',
			             'headline': 'Ebola confirmed in Nairobi', 'body': 'Not from the Ministry', 'issued_by': 'PHEOC'}),
			('/alerting/feed', {'item_id': 'F-1', 'category': 'outbreak', 'headline': 'Fake',
			                    'body': 'x', 'source': 'unknown', 'verified': True, 'published_iso': '2026-10-10T00:00:00+03:00'}),
		):
			anon_write = await c.post(path, headers={'authorization': f'Bearer {anon}'}, json=body)
			assert anon_write.status_code == 403, f'{path} accepted a broadcast from a citizen'
			assert (await c.post(path, json=body)).status_code in (401, 403), f'{path} accepted an anonymous broadcast'


def test_operator_scopes_match_the_routes() -> None:
	"""The catalogue's operator list must name the scope each route actually checks.

	A control withheld under the wrong scope is offered to someone who will be refused, or hidden
	from someone who could have used it. Read off the route's own dependency rather than restated.
	"""
	from afya.service import build_services
	import inspect
	app = create_app(build_services())
	scopes = {'infrastructure', 'audit_logs', 'county_aggregate', 'national_aggregate', 'assigned'}
	by_path: dict[str, str] = {}

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			ep = getattr(r, 'endpoint', None)
			if ep is None:
				continue
			dep = next((p.default for p in inspect.signature(ep).parameters.values()
			            if type(p.default).__name__ == 'Depends'), None)
			for cell in getattr(getattr(dep, 'dependency', None), '__closure__', None) or ():
				if isinstance(cell.cell_contents, str) and cell.cell_contents in scopes:
					by_path[getattr(r, 'path', '')] = cell.cell_contents

	walk(app.routes)
	if True:
		for action in catalogue():
			if action.id not in OPERATOR_SCOPES:
				continue
			assert by_path.get(action.path) == OPERATOR_SCOPES[action.id], \
				f'{action.id}: catalogue says {OPERATOR_SCOPES[action.id]}, route {action.path} checks {by_path.get(action.path)}'


def test_every_operator_action_is_marked_and_every_marked_action_is_guarded() -> None:
	"""The two directions of the same claim, so neither list can rot.

	An action that writes shared or broadcast state but is not marked operator-only is served to
	citizens who will be refused. A marked action whose route carries no guard is a control hidden
	from people who could have used it — and, worse, a route left open. This reads the routes, so
	the marking cannot drift from the guard it mirrors.
	"""
	from afya.service import build_services
	import inspect
	app = create_app(build_services())
	guarded: set[tuple[str, str]] = set()

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			ep = getattr(r, 'endpoint', None)
			if ep is None:
				continue
			if any(type(p.default).__name__ == 'Depends' for p in inspect.signature(ep).parameters.values()):
				for method in getattr(r, 'methods', None) or []:
					guarded.add((method, getattr(r, 'path', '')))

	walk(app.routes)
	for slug in OPERATOR_SCOPES:
		action = next(a for a in catalogue() if a.id == slug)
		assert (action.method, action.path) in guarded, \
			f'{slug} is marked operator-only but {action.method} {action.path} carries no guard'

	# The other direction: a route guarded on a non-citizen dataset must have its action marked,
	# or the control is offered to a caller who will be refused. `alert_feed` is the case that
	# makes the method matter — `GET /alerting/feed` is a citizen's read of the same path whose
	# `POST` is the broadcast, so a path-only lookup would mark the read as operator-only.
	CITIZEN_SCOPES = {'self', 'family'}
	by_route: dict[tuple[str, str], str] = {}

	def scope_of(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				scope_of(r.routes)
				continue
			ep = getattr(r, 'endpoint', None)
			if ep is None:
				continue
			dep = next((p.default for p in inspect.signature(ep).parameters.values()
			            if type(p.default).__name__ == 'Depends'), None)
			for cell in getattr(getattr(dep, 'dependency', None), '__closure__', None) or ():
				if isinstance(cell.cell_contents, str) and cell.cell_contents not in CITIZEN_SCOPES:
					for method in getattr(r, 'methods', None) or []:
						by_route[(method, getattr(r, 'path', ''))] = cell.cell_contents

	scope_of(app.routes)
	unmarked = sorted(
		a.id for a in catalogue()
		if (a.method, a.path) in by_route and a.id not in OPERATOR_SCOPES
	)
	assert unmarked == [], f'actions reachable only by an operator scope, but not marked: {unmarked}'


# Write routes that legitimately carry no guard, each for a reason that is about *how a person
# reaches the service* rather than about the data. Named explicitly so "unguarded write" cannot
# quietly come to mean "nobody looked at it".
UNGATED_WRITES: frozenset[tuple[str, str]] = frozenset({
	('POST', '/auth/anonymous'),      # issues the token; requiring one is a deadlock
	('POST', '/auth/pkce/authorize'), # starts the PKCE flow, before any token exists
	('POST', '/auth/pkce/token'),     # redeems the code; the verifier is the proof
	('POST', '/auth/revoke'),         # revokes the presented token; a bad one revokes nothing
	('POST', '/channels/sms'),        # the telco's inbound webhook, authenticated by signature
	('POST', '/channels/ussd'),       # the aggregator's inbound USSD session
	('POST', '/channels/whatsapp'),   # the WhatsApp Business webhook
	('POST', '/sync/batch'),          # a device's own queued ops, keyed by its device id
	('POST', '/sync/delta'),
	('POST', '/sync/flush'),
	('POST', '/sync/ops'),
	('POST', '/ml/cough/analyze'),    # a pure computation: audio in, verdict out, nothing stored
	('POST', '/triage/diagnose'),     # the same: no subject, no record, no shared state
	('POST', '/triage/preliminary'),
	('POST', '/triage/evd'),
	('POST', '/ai/risk-score'),       # derived on-device score; the caller supplies the inputs
	('POST', '/ai/fairness-audit'),
	('POST', '/facilities/nearest'),  # a read expressed as a POST: a coordinate in, a list out
	('POST', '/facilities/{facility_id}/booking'),
	('POST', '/facilities/{facility_id}/correction'),
	('POST', '/facilities/{facility_id}/wait'),
	('POST', '/insurance/prices'),
	('POST', '/insurance/sha-check'),
	('POST', '/medicine/dose'),
	('POST', '/medicine/interactions'),
	('POST', '/medicine/verify'),
	('POST', '/medicine/stock'),      # a crowd-sourced stock report; `reported_by` is the claim
	('POST', '/environment/air'),
	('POST', '/environment/flood'),
	('POST', '/environment/water'),
	('POST', '/monitoring/breeding-site'),
	('POST', '/monitoring/vector-risk'),
	('POST', '/monitoring/medication/adherence'),
	('POST', '/community/issues'),    # a citizen's own report of a problem where they live
	('POST', '/community/misinformation'),
	('POST', '/emergency/sos'),       # an emergency must not wait for a token
	('POST', '/emergency/fall'),
	('POST', '/emergency/card/qr'),
	('POST', '/blood/donors'),        # a donor enrols themselves
	('POST', '/blood/match'),
	('POST', '/privacy/dpia'),        # a self-assessment of a proposed use; stores nothing
	('POST', '/location/border'),
	('POST', '/location/checkin/point'),
	('POST', '/location/proximity/check'),
	('POST', '/location/proximity/declare'),
	('POST', '/location/proximity/ebid'),
	('POST', '/location/proximity/encounter'),
	('POST', '/maternal/danger'),
	('POST', '/channels/chw/tasks/{task_id}/done'),  # CHW closes a task by its id
})


def test_every_unguarded_write_is_named_and_justified() -> None:
	"""A write with no guard at all is the shape of the bug this file found three times over.

	`POST /tier4/activate`, `POST /alerts` and `POST /alerting/feed` each had no guard and each
	wrote state every other user read. The IDOR gate walks routes that name a subject and the
	operator-marking gate walks routes a catalogue action points at; neither asks the plainest
	question, which is which writes carry no guard. This asks it, against a named list so a new
	one has to be argued for rather than appearing.
	"""
	from afya.service import build_services
	import inspect
	app = create_app(build_services())
	seen: set[tuple[str, str]] = set()
	unguarded: set[tuple[str, str]] = set()

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			ep = getattr(r, 'endpoint', None)
			if ep is None:
				continue
			if any(type(p.default).__name__ == 'Depends' for p in inspect.signature(ep).parameters.values()):
				continue
			for method in getattr(r, 'methods', None) or []:
				if method in ('POST', 'PUT', 'PATCH', 'DELETE'):
					unguarded.add((method, getattr(r, 'path', '')))

	walk(app.routes)
	unjustified = sorted(unguarded - UNGATED_WRITES)
	assert unjustified == [], f'write routes with no guard and no justification: {unjustified}'
	# And the list cannot rot in the other direction: a route that has since been guarded, or
	# removed, must come off it, or the list stops meaning anything.
	stale = sorted(UNGATED_WRITES - unguarded)
	assert stale == [], f'listed as unguarded but now guarded or gone: {stale}'
