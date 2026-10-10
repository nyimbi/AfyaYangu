"""Authentication and request-integrity models (spec §15.5, §17).

§15.5 asks for four things the API otherwise lacks: OAuth 2.0 + PKCE for health workers, anonymous
tokens for citizen endpoints, idempotency keys on every write, and per-device rate limiting. They
live together because they are all properties of a request rather than of a feature.

The token model is deliberately narrow. A citizen token is a random opaque string bound to one
subject and no role beyond `citizen_anonymous`/`citizen_identified`; it carries no personal data, so
stealing one reveals nothing about its holder. A worker token is issued through PKCE and carries an
RBACRole, which is what `PrivacyService.check_access` has always expected and never received.
"""
import hashlib
import hmac
import secrets
import time
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# Access tokens are short-lived; the refresh path re-issues. Long enough to survive a sync burst
# on a slow connection, short enough that a leaked token stops working within the same shift.
ACCESS_TOKEN_TTL_SECONDS = 3600
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30
PKCE_CHALLENGE_METHODS: tuple[str, ...] = ('S256',)
ANONYMOUS_TOKEN_BYTES = 32
MIN_VERIFIER_LENGTH = 43
MAX_VERIFIER_LENGTH = 128

# §15.5 rate limiting, per device. Sized so a person on a flaky link is never locked out while a
# scripted scraper is: the burst allowance absorbs retries, the sustained rate stops enumeration.
RATE_LIMIT_BURST = 30
RATE_LIMIT_PER_MINUTE = 120
RATE_LIMIT_WINDOW_SECONDS = 60

# Writes are idempotent for a day: long enough to cover a device that was offline overnight and
# replays its whole queue on reconnect, which is exactly when duplicate case reports would appear.
IDEMPOTENCY_TTL_SECONDS = 60 * 60 * 24


class TokenKind(str, Enum):
	anonymous = 'anonymous'
	worker = 'worker'


class AnonymousToken(BaseModel):
	"""A citizen token. Opaque, subject-bound, and carrying no personal data of its own."""
	model_config = MODEL_CONFIG
	token: str
	subject_ref: str
	kind: TokenKind = TokenKind.anonymous
	issued_at_ms: int
	expires_at_ms: int


class TokenRequest(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str | None = Field(default=None, description='omit to be assigned a fresh anonymous subject')


class PKCEStart(BaseModel):
	"""The client's authorization request. `code_challenge` is S256(verifier), never the verifier."""
	model_config = MODEL_CONFIG
	client_id: str
	redirect_uri: str
	code_challenge: str = Field(min_length=43, max_length=128)
	code_challenge_method: str = Field(default='S256', pattern=r'^S256$')
	state: str = Field(min_length=8, max_length=128)


class PKCEAuthorization(BaseModel):
	model_config = MODEL_CONFIG
	authorization_code: str
	client_id: str
	redirect_uri: str
	code_challenge: str
	state: str
	expires_at_ms: int


class PKCETokenRequest(BaseModel):
	"""Exchanging the code for a token. The verifier proves the same client that started the flow."""
	model_config = MODEL_CONFIG
	authorization_code: str
	client_id: str
	redirect_uri: str
	code_verifier: str = Field(min_length=MIN_VERIFIER_LENGTH, max_length=MAX_VERIFIER_LENGTH)


class StaffProvision(BaseModel):
	"""Operational provisioning of a role the app flow refuses (§17.5).

	`role` is a plain string, not `RBACRole`: the service asserts the role is in
	`OPERATIONAL_ROLES` and returns a 422 naming the reason, which is a better refusal than a
	generic enum-validation error that cannot say "this one is issued through the app instead".
	"""
	model_config = MODEL_CONFIG
	operator_ref: str = Field(min_length=1)
	registrar: str = Field(min_length=1)
	role: str


class WorkerToken(BaseModel):
	model_config = MODEL_CONFIG
	access_token: str
	refresh_token: str
	token_type: str = 'Bearer'
	expires_in: int
	role: str
	subject_ref: str
	scopes: list[str]


class RateLimitDecision(BaseModel):
	model_config = MODEL_CONFIG
	allowed: bool
	limit: int
	remaining: int
	retry_after_seconds: int
	message: str


class IdempotencyRecord(BaseModel):
	"""A stored first response, replayed verbatim for a repeated key (§15.5)."""
	model_config = MODEL_CONFIG
	key: str
	request_fingerprint: str
	response: dict[str, object]
	status_code: int
	stored_at_ms: int


def s256(verifier: str) -> str:
	"""RFC 7636 S256: base64url(sha256(verifier)) without padding. The only method we accept —
	`plain` would make the challenge pointless, since the verifier would travel in the open."""
	digest = hashlib.sha256(verifier.encode('ascii')).digest()
	import base64
	return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')


def verify_pkce(verifier: str, challenge: str) -> bool:
	"""Constant-time comparison, so a challenge cannot be recovered by timing the mismatch."""
	return hmac.compare_digest(s256(verifier), challenge)


def new_opaque_token() -> str:
	return secrets.token_urlsafe(ANONYMOUS_TOKEN_BYTES)


def fingerprint(payload: str) -> str:
	"""A stable digest of a request body, used to detect a reused idempotency key carrying
	different content — which is a client bug, and must not silently return the first response."""
	return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def now_ms() -> int:
	return int(time.time() * 1000)
