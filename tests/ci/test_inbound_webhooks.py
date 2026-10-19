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
	# The two WhatsApp arrivals and the USSD session are the same class: an inbound message
	# attributed to a phone number, filed as a §5.4 case report under it. The voice route is
	# multipart, so it is covered by its own signed-form test below rather than by this map.
	'/channels/ussd': {'session_id': 's1', 'msisdn': '+254711222333', 'text': ''},
	'/channels/whatsapp': {'from_msisdn': '+254711222333', 'body': 'I have fever'},
	'/integrations/hotline/follow-up': {'case_ref': 'C-1', 'message': 'Lab result ready.'},
	'/integrations/hotline/outcome': {'outcome_code': 'transported', 'consented': True},
	'/integrations/telco/sms/inbound': {'from': '0712345678', 'text': 'I have fever'},
	# §5.4's cross-channel consent: a grant made on a channel, written to the one registry the app
	# reads. The caller is a carrier-side integration holding a phone and no app token, so the phone
	# is a query parameter and the category a query parameter beside it.
	'/privacy/consent/by-phone': {'msisdn': '+254712345678', 'category': 'symptom_storage'},
}

# A webhook whose body is a multipart form, so it cannot be signed from a dict and is driven by
# `test_the_voice_webhook_is_signed_over_its_own_bytes` instead. Named rather than filtered out of
# the derived set: a route that is skipped silently is a route the gate stopped covering.
MULTIPART_ROUTES: frozenset[str] = frozenset({'/channels/whatsapp/voice'})


def _wav() -> bytes:
	"""A tenth of a second of silence, so the signed request reaches the route's own logic.

	The bytes only have to be a readable WAV for the acceptance half of the test below; the refusal
	half would pass against any bytes at all, which is why the accepted one is asserted separately.
	"""
	import io
	import wave

	buf = io.BytesIO()
	with wave.open(buf, 'wb') as w:
		w.setnchannels(1)
		w.setsampwidth(2)
		w.setframerate(16_000)
		w.writeframes(b'\x00\x00' * 1600)
	return buf.getvalue()


def test_the_signature_guarded_set_is_not_vacuous() -> None:
	"""Pins the count, so the derived set cannot silently become empty and every check below pass
	for want of routes to check."""
	routes = _signature_guarded_routes()
	assert len(routes) >= 4, routes
	assert ('POST', '/channels/ussd/callback') in routes, 'the USSD carrier callback is a webhook'
	assert all(path in BODIES or path in MULTIPART_ROUTES for _, path in routes), \
		f'a guarded route has no test body: {routes}'
	assert {'/channels/ussd', '/channels/whatsapp'} <= {p for _, p in routes}, (
		'the two WhatsApp/USSD inbound routes are the class this file was written for')


async def test_every_webhook_route_refuses_unsigned_and_wrongly_signed(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', SECRET)
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for _method, path in _signature_guarded_routes():
			if path in MULTIPART_ROUTES:
				continue
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
			if path in MULTIPART_ROUTES:
				continue
			raw, headers = _signed(BODIES[path])
			resp = await c.post(path, content=raw, headers=headers)
			assert resp.status_code == 200, f'{path} refused a correctly signed body: {resp.status_code} {resp.text}'


async def test_the_voice_webhook_is_signed_over_its_own_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
	"""The multipart route, which the three loops above skip.

	A skipped route is a route the gate stopped covering, so this file names it and drives it here.
	The guard reads the raw body before Starlette parses the form, which means the digest covers the
	boundary and the part headers as well as the recording — and the form still arrives intact
	afterwards, because Starlette caches the body the guard consumed.
	"""
	from conftest import multipart_body, sign_multipart
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', SECRET)
	app = create_app(build_services())
	note = _wav()
	files = {'file': ('note.wav', note, 'audio/wav')}
	fields = {'from_msisdn': '+254711222333', 'voice_note_lang': 'en'}
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		raw, headers = sign_multipart(fields, files, SECRET)
		unsigned = await c.post('/channels/whatsapp/voice', content=raw,
			headers={'content-type': headers['content-type']})
		assert unsigned.status_code == 401, f'an unsigned voice note was accepted: {unsigned.text}'
		wrong, wrong_headers = sign_multipart(fields, files, 'not-the-secret')
		assert (await c.post('/channels/whatsapp/voice', content=wrong, headers=wrong_headers)).status_code == 401
		# A signature over this body with one byte of the recording changed is refused: the file is
		# the payload, so a digest that covered only the fields would let anyone swap the audio. The
		# second body reuses the first's boundary, so it differs from the signed one in exactly the
		# byte that was flipped — regenerating the boundary would make it a different body for a
		# reason that has nothing to do with the recording, and the test would pass without ever
		# proving the file is inside the digest.
		boundary = headers['content-type'].split('boundary=')[1]
		tampered, _ = multipart_body(fields, {'file': ('note.wav', note[:-1] + bytes([note[-1] ^ 0xFF]), 'audio/wav')}, boundary)
		assert tampered != raw and len(tampered) == len(raw), 'the tampered body must differ only in one byte'
		replayed = await c.post('/channels/whatsapp/voice', content=tampered,
			headers={'content-type': f'multipart/form-data; boundary={boundary}',
				'x-afya-signature': headers['x-afya-signature']})
		assert replayed.status_code == 401, f'a signature over a different recording was accepted: {replayed.text}'
		# And the correctly signed one reaches the route's own logic rather than the guard.
		resp = await c.post('/channels/whatsapp/voice', content=raw, headers=headers)
		assert resp.status_code != 401, f'a correctly signed voice note was refused: {resp.status_code} {resp.text}'


async def test_an_unconfigured_deployment_refuses_rather_than_opens(monkeypatch: pytest.MonkeyPatch) -> None:
	"""A dev box with no secret must not serve an open webhook: that is how an open webhook ships to
	production. 503 says "this deployment cannot authenticate", which is the honest answer."""
	monkeypatch.delenv('AFYA_WEBHOOK_SECRET', raising=False)
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		for _method, path in _signature_guarded_routes():
			if path in MULTIPART_ROUTES:
				continue
			raw, headers = _signed(BODIES[path])
			assert (await c.post(path, content=raw, headers=headers)).status_code == 503, f'{path} served an unauthenticated deployment'
		# The voice route's own shape: unsigned, it is refused before the form is parsed.
		unsigned = await c.post('/channels/whatsapp/voice',
			files={'file': ('note.wav', b'RIFF', 'audio/wav')}, data={'from_msisdn': '+254711222333'})
		assert unsigned.status_code == 503, 'the voice webhook served an unauthenticated deployment'
