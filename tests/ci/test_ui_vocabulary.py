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

import httpx
import pytest

from afya.mobile.actions import DORMANT_SLUGS, FEATURE_OF, FRIENDLY_COPY, available, catalogue
from afya.service import create_app

# The registry's own id grammar, reused so the gate cannot drift from what ids actually look like.
FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

REPO = Path(__file__).resolve().parents[2]


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


async def test_dormant_capabilities_are_withheld_until_activation() -> None:
	"""§11.1: the client must not see a control that would refuse it. Served, not just filtered."""
	assert len(available(False)) < len(available(True)), 'activation must reveal something'
	assert {a.id for a in available(True)} - {a.id for a in available(False)} == set(DORMANT_SLUGS)

	app = create_app()
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		before = {a['id'] for a in (await c.get('/mobile/actions')).json()}
		assert not (before & DORMANT_SLUGS), 'dormant capabilities served before activation'
		await c.post('/tier4/activate', json={'authorized_by_pheoc': True, 'dpia_reviewed': True, 'flag_enabled': True})
		after = {a['id'] for a in (await c.get('/mobile/actions')).json()}
		assert after - before == set(DORMANT_SLUGS), 'activation must unlock exactly the dormant set'


async def test_served_mobile_payloads_are_code_free() -> None:
	"""The gate that matters: what the client actually receives."""
	app = create_app()
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		for path in ('/mobile/actions', '/mobile/features'):
			body = (await c.get(path)).text
			assert _scan(path, body) == [], f'feature codes served at {path}'


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
