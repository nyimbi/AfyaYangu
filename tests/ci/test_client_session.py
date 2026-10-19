"""The session a device keeps, and what happens when the server will not give it back.

The anonymous subject is the device's identity, and the route that re-issues it now refuses a name
the caller merely chose. Two client behaviours follow from that, and neither is observable from
Python:

1. **The held token goes with the reclaim.** A subject is honoured only when the request carries
   that subject's live token, so a device that has one must present it — a reclaim that sent the
   name alone was refused, and the device silently lost its record.

2. **A refused reclaim falls back to a new identity.** Revoking is what `DELETE MY DATA` does, and a
   server whose store was wiped answers 403 for every subject it once minted. A client that treats
   that as fatal has no token and therefore cannot send anything at all: the app is bricked by the
   correct behaviour of the server.

The server half — that a subject is claimed once and a re-claim needs its token — is gated
behaviourally in `test_auth.py`; this file reads the clients that have to use it.
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
KOTLIN = REPO / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'
SWIFT = REPO / 'ios/AfyaYangu/BackendClient.swift'


def test_both_clients_present_the_held_token_when_reclaiming_a_subject() -> None:
	kotlin = KOTLIN.read_text()
	assert 'val held = prefs.getString("session.token", null)' in kotlin, (
		'Android reclaims its subject with no credential, so a subject that is not service-shaped '
		'is refused and the device loses its record')
	assert 'authorize = false, bearer = held' in kotlin, (
		'Android reads the stored token but does not send it on the reclaim')

	swift = SWIFT.read_text()
	assert 'let held = defaults.string(forKey: "session.token")' in swift, (
		'iOS reclaims its subject with no credential, so a subject that is not service-shaped '
		'is refused and the device loses its record')
	assert 'issueAnonymous(subject: known, bearer: held)' in swift, (
		'iOS reads the stored token but does not send it on the reclaim')


def test_a_refused_reclaim_asks_for_a_new_identity_rather_than_bricking_the_app() -> None:
	kotlin = KOTLIN.read_text()
	assert 'if (e.code != 403 || known == null) throw e' in kotlin, (
		'Android treats a refused reclaim as fatal: a revoked subject leaves it with no token, so '
		'it cannot send anything at all')
	assert 'request("auth/anonymous", "{}", authorize = false)' in kotlin, (
		'Android has no fallback to a fresh identity')

	swift = SWIFT.read_text()
	assert 'issueAnonymous(subject: nil, bearer: nil)' in swift, (
		'iOS treats a refused reclaim as fatal: a revoked subject leaves it with no token, so it '
		'cannot send anything at all')
	# The fallback must be reachable only after a failed attempt, not instead of one.
	assert swift.index('issueAnonymous(subject: known, bearer: held)') < swift.index('issueAnonymous(subject: nil, bearer: nil)'), (
		'the fresh-identity request runs before the reclaim it is meant to fall back from')
	assert kotlin.index('authorize = false, bearer = held') < kotlin.index('request("auth/anonymous", "{}"'), (
		'the fresh-identity request runs before the reclaim it is meant to fall back from')
