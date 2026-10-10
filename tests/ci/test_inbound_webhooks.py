"""Inbound webhooks are signed, not open (§18.4, §18.8, §5 CHAN-006).

The class-wide defect this pins: `/channels/ussd/callback` shipped open, and every webhook added
after it inherited the shape. An unauthenticated webhook is not a missing nicety — it is an open
write into the system, and each of these writes is attributed to a real person. A hotline follow-up
is a message from "719" that a citizen reads; a USSD callback is someone driving the national menu;
an inbound SMS is a report from a number nobody verified.

The gate is derived from the routes' own OpenAPI parameters rather than a hand-kept list, so a
webhook added later without the guard fails here without anyone remembering to add it.
"""
import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest

from afya.service import build_services, create_app

SECRET = 'gate-secret'


def _signed(body: dict[str, Any], secret: str = SECRET) -> tuple[bytes, dict[str, str]]:
	raw = json.dumps(body).encode()
	sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
	return raw, {'content-type': 'application/json', 'x-afya-signature': sig}


def _signature_guarded_routes() -> list[tuple[str, str]]:
	"""Every route whose declared parameters include the signature header."""
	spec = create_app(build_services()).openapi()
	out: list[tuple[str, str]] = []
	for path, ops in spec['paths'].items():
		for method, op in ops.items():
			if 'x-afya-signature' in [p.get('name') for p in op.get('parameters', [])]:
				out.append((method.upper(), path))
	return sorted(out)


# Bodies that reach each guarded route's own logic, so a signed request is expected to be accepted
# (or refused for its *content*, never for its signature).
BODIES: dict[str, dict[str, Any]] = {
	'/channels/ussd/callback': {'session_id': 's1', 'phone_number': '+254711222333', 'text': ''},
	'/integrations/hotline/follow-up': {'case_ref': 'C-1', 'message': 'Lab result ready.'},
	'/integrations/hotline/outcome': {'outcome_code': 'transported', 'consented': True},
	'/integrations/telco/sms/inbound': {'from': '0712345678', 'text': 'I have fever'},
}


def test_the_signature_guarded_set_is_not_vacuous() -> None:
	"""Pins the count, so the derived set cannot silently become empty and every check below pass
	for want of routes to check."""
	routes = _signature_guarded_routes()
	assert len(routes) >= 4, routes
	assert ('POST', '/channels/ussd/callback') in routes, 'the USSD carrier callback is a webhook'
	assert all(path in BODIES for _, path in routes), f'a guarded route has no test body: {routes}'


async def test_every_webhook_route_refuses_unsigned_and_wrongly_signed(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', SECRET)
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for _method, path in _signature_guarded_routes():
			body = BODIES[path]
			assert (await c.post(path, json=body)).status_code == 401, f'{path} accepted an unsigned body'
			raw, headers = _signed(body, 'not-the-secret')
			assert (await c.post(path, content=raw, headers=headers)).status_code == 401, f'{path} accepted a wrong signature'
			# The signature covers the body, so a valid signature over a *different* body is refused:
			# otherwise an attacker could replay one captured signature over their own payload.
			raw, headers = _signed({'tampered': True})
			tampered = json.dumps(body).encode()
			assert (await c.post(path, content=tampered, headers=headers)).status_code == 401, f'{path} accepted a signature over another body'


async def test_every_webhook_route_accepts_a_correctly_signed_body(monkeypatch: pytest.MonkeyPatch) -> None:
	"""The other half: a gate that only checks refusals would pass on a route that refuses
	everything, including the carrier it exists to serve."""
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', SECRET)
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for _method, path in _signature_guarded_routes():
			raw, headers = _signed(BODIES[path])
			resp = await c.post(path, content=raw, headers=headers)
			assert resp.status_code == 200, f'{path} refused a correctly signed body: {resp.status_code} {resp.text}'


async def test_an_unconfigured_deployment_refuses_rather_than_opens(monkeypatch: pytest.MonkeyPatch) -> None:
	"""A dev box with no secret must not serve an open webhook: that is how an open webhook ships to
	production. 503 says "this deployment cannot authenticate", which is the honest answer."""
	monkeypatch.delenv('AFYA_WEBHOOK_SECRET', raising=False)
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for _method, path in _signature_guarded_routes():
			raw, headers = _signed(BODIES[path])
			assert (await c.post(path, content=raw, headers=headers)).status_code == 503, f'{path} served an unauthenticated deployment'
