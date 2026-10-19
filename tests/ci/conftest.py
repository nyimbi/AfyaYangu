"""Shared fixtures for the route tests.

Only one thing lives here: how a test signs an inbound webhook. Every channel route and every §18
wire is HMAC-signed (`require_webhook`), so a test that drives one has to sign the body the same
way the carrier would — and a copy of that eight-line helper in each file is a copy that drifts
the first time the header or the digest changes.
"""
import hashlib
import hmac
import json
import uuid
from typing import Any

import pytest

WEBHOOK_SECRET = 'test-webhook-secret'


def sign(body: dict[str, Any], secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict[str, str]]:
	"""A body as the carrier sends it: raw bytes, plus the signature over exactly those bytes."""
	raw = json.dumps(body).encode()
	digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
	return raw, {'content-type': 'application/json', 'x-afya-signature': digest}


def multipart_body(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]],
		boundary: str | None = None) -> tuple[bytes, str]:
	"""A multipart webhook body, as the carrier puts it on the wire.

	`boundary` is a parameter so a test can build a *second* body with the same framing and a
	different recording: the signature covers the boundary and the part headers, so a tampering test
	that regenerated the boundary would be refused for the wrong reason.
	"""
	boundary = boundary or f'afya-{uuid.uuid4().hex}'
	parts: list[bytes] = []
	for name, value in fields.items():
		parts.append(
			f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
			+ value.encode() + b'\r\n')
	for name, (filename, content, mime) in files.items():
		parts.append(
			f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
			f'Content-Type: {mime}\r\n\r\n'.encode() + content + b'\r\n')
	parts.append(f'--{boundary}--\r\n'.encode())
	return b''.join(parts), boundary


def sign_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]],
		secret: str = WEBHOOK_SECRET) -> tuple[bytes, dict[str, str]]:
	"""A multipart webhook, signed over the bytes it actually puts on the wire.

	The guard reads the raw body before Starlette parses the form, so the signature covers the
	boundary, the part headers and the file bytes — not a dict. Built here rather than with a
	client helper because the digest has to be taken over the finished body, and a client that
	re-encodes the form afterwards produces a different body than the one signed.
	"""
	raw, boundary = multipart_body(fields, files)
	digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
	return raw, {'content-type': f'multipart/form-data; boundary={boundary}', 'x-afya-signature': digest}


@pytest.fixture
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> str:
	"""Configure a secret for one test, so a signed webhook reaches the route's own logic.

	Explicit rather than assumed: the guard answers 503 when no secret is configured, which is the
	behaviour `test_inbound_webhooks.py` asserts on purpose, so a test that wants the *content*
	path has to say that a secret exists.
	"""
	monkeypatch.setenv('AFYA_WEBHOOK_SECRET', WEBHOOK_SECRET)
	return WEBHOOK_SECRET
