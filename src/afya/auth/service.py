"""Auth, idempotency and rate limiting (spec §15.5, §17).

Three invariants hold here, and each is a refusal rather than a warning:
  * A PKCE code is single-use and expires; replaying it yields nothing.
  * An idempotency key replays the first response only when the request body is byte-identical.
    The same key with different content is a client bug, and answering it with the earlier
    response would silently drop a real write.
  * Rate limiting counts per device, so one noisy client cannot consume another's budget.
"""
from afya.auth.views import (
	ACCESS_TOKEN_TTL_SECONDS, IDEMPOTENCY_TTL_SECONDS, RATE_LIMIT_BURST, RATE_LIMIT_PER_MINUTE,
	RATE_LIMIT_WINDOW_SECONDS, REFRESH_TOKEN_TTL_SECONDS, AnonymousToken, IdempotencyRecord,
	PKCEAuthorization, PKCETokenRequest, PKCEStart, RateLimitDecision, TokenKind, WorkerToken,
	fingerprint, new_opaque_token, now_ms, verify_pkce,
)
from afya.logmixin import LogMixin
from afya.privacy.views import RBACRole, _SCOPE

# Which roles a worker flow may issue. `sysadmin` and `auditor` are provisioned operationally, not
# handed out through the app, and a citizen cannot request a role at all.
ISSUABLE_ROLES: frozenset[RBACRole] = frozenset({
	RBACRole.chw, RBACRole.clinician, RBACRole.county_officer, RBACRole.pheoc_analyst,
})

AUTHORIZATION_CODE_TTL_MS = 60_000


class AuthService(LogMixin):
	def __init__(self) -> None:
		self._anonymous: dict[str, AnonymousToken] = {}
		self._workers: dict[str, WorkerToken] = {}
		self._codes: dict[str, PKCEAuthorization] = {}
		self._used_codes: set[str] = set()
		self._idempotency: dict[str, IdempotencyRecord] = {}
		self._hits: dict[str, list[int]] = {}
		assert self._anonymous == {} and self._codes == {} and self._used_codes == set()

	# --- anonymous citizen tokens ------------------------------------------------------------

	async def issue_anonymous(self, subject_ref: str | None = None) -> AnonymousToken:
		"""§15.5 anonymous tokens: a citizen endpoint needs no account, so the token is random and
		the subject is assigned here rather than supplied."""
		subject = subject_ref or f'anon-{new_opaque_token()[:16]}'
		issued = now_ms()
		token = AnonymousToken(
			token=new_opaque_token(), subject_ref=subject, kind=TokenKind.anonymous,
			issued_at_ms=issued, expires_at_ms=issued + REFRESH_TOKEN_TTL_SECONDS * 1000,
		)
		self._anonymous[token.token] = token
		self._log_info('anonymous token issued', subject=subject)
		return token

	def resolve_anonymous(self, token: str) -> AnonymousToken:
		assert token in self._anonymous, 'unknown or revoked token'
		rec = self._anonymous[token]
		assert rec.expires_at_ms > now_ms(), 'token expired'
		return rec

	async def revoke(self, token: str) -> int:
		"""Revoking a citizen token is how `DELETE MY DATA` ends the session that asked for it."""
		removed = 1 if self._anonymous.pop(token, None) else 0
		removed += 1 if self._workers.pop(token, None) else 0
		assert removed <= 2
		return removed

	# --- OAuth 2.0 + PKCE for health workers -------------------------------------------------

	def start_pkce(self, req: PKCEStart) -> PKCEAuthorization:
		# code_challenge_method is pinned to S256 by the model; `plain` cannot be represented, so
		# there is nothing to re-check here.
		assert req.redirect_uri, 'redirect_uri required'
		code = new_opaque_token()
		auth = PKCEAuthorization(
			authorization_code=code, client_id=req.client_id, redirect_uri=req.redirect_uri,
			code_challenge=req.code_challenge, state=req.state, expires_at_ms=now_ms() + AUTHORIZATION_CODE_TTL_MS,
		)
		self._codes[code] = auth
		self._log_info('pkce flow started', client=req.client_id)
		return auth

	def exchange_pkce(self, req: PKCETokenRequest, role: RBACRole) -> WorkerToken:
		"""The verifier proves the client that started the flow. Single use, and it expires."""
		assert req.authorization_code in self._codes, 'unknown authorization code'
		assert req.authorization_code not in self._used_codes, 'authorization code already redeemed'
		auth = self._codes[req.authorization_code]
		assert auth.expires_at_ms > now_ms(), 'authorization code expired'
		assert auth.client_id == req.client_id, 'code was issued to a different client'
		assert auth.redirect_uri == req.redirect_uri, 'redirect_uri must match the one used at start'
		assert verify_pkce(req.code_verifier, auth.code_challenge), 'PKCE verifier does not match the challenge'
		assert role in ISSUABLE_ROLES, 'this role is not issued through the app'
		self._used_codes.add(req.authorization_code)
		issued = now_ms()
		token = WorkerToken(
			access_token=new_opaque_token(), refresh_token=new_opaque_token(),
			expires_in=ACCESS_TOKEN_TTL_SECONDS, role=role.value, subject_ref=req.client_id,
			scopes=sorted(_SCOPE.get(role, set())),
		)
		self._workers[token.access_token] = token
		self._log_info('worker token issued', client=req.client_id, role=role.value, issued_ms=issued)
		return token

	def resolve_worker(self, access_token: str) -> WorkerToken:
		assert access_token in self._workers, 'unknown or revoked worker token'
		return self._workers[access_token]

	# --- idempotency (§15.5) -----------------------------------------------------------------

	def replay(self, key: str, body: str) -> IdempotencyRecord | None:
		"""The stored first response for this key, or None. A key reused with different content is
		refused: returning the earlier response would silently discard the new write."""
		rec = self._idempotency.get(key)
		if rec is None:
			return None
		assert rec.stored_at_ms + IDEMPOTENCY_TTL_SECONDS * 1000 > now_ms(), 'idempotency key expired'
		assert rec.request_fingerprint == fingerprint(body), (
			'idempotency key reused with a different request body'
		)
		self._log_info('idempotent replay', key=key)
		return rec

	def store(self, key: str, body: str, response: dict[str, object], status_code: int) -> IdempotencyRecord:
		assert key, 'idempotency key required'
		rec = IdempotencyRecord(
			key=key, request_fingerprint=fingerprint(body), response=response,
			status_code=status_code, stored_at_ms=now_ms(),
		)
		self._idempotency[key] = rec
		return rec

	def purge_expired_keys(self) -> int:
		cutoff = now_ms() - IDEMPOTENCY_TTL_SECONDS * 1000
		stale = [k for k, r in self._idempotency.items() if r.stored_at_ms < cutoff]
		for k in stale:
			self._idempotency.pop(k, None)
		return len(stale)

	# --- rate limiting (§15.5) ---------------------------------------------------------------

	def check_rate(self, device_id: str, at_ms: int | None = None) -> RateLimitDecision:
		"""Sliding window per device: the burst allowance absorbs retries on a flaky link, the
		sustained rate stops enumeration. Counted per device so neighbours never share a budget."""
		assert device_id, 'rate limiting is per device and needs one'
		now = at_ms if at_ms is not None else now_ms()
		window_start = now - RATE_LIMIT_WINDOW_SECONDS * 1000
		recent = [t for t in self._hits.get(device_id, []) if t >= window_start]
		allowed = len(recent) < RATE_LIMIT_PER_MINUTE + RATE_LIMIT_BURST
		if allowed:
			recent.append(now)
		else:
			self._log_warn('rate limit hit', device=device_id, hits=len(recent))
		self._hits[device_id] = recent
		remaining = max(0, RATE_LIMIT_PER_MINUTE + RATE_LIMIT_BURST - len(recent))
		retry_after = 0 if allowed else RATE_LIMIT_WINDOW_SECONDS
		return RateLimitDecision(
			allowed=allowed, limit=RATE_LIMIT_PER_MINUTE + RATE_LIMIT_BURST, remaining=remaining,
			retry_after_seconds=retry_after,
			message='OK' if allowed else f'Too many requests. Try again in {retry_after} seconds.',
		)

	def reset_rate(self, device_id: str) -> None:
		self._hits.pop(device_id, None)
