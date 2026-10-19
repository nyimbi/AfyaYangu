"""The offline queue's three ways to lose a write, and the key that has to survive a restart.

§16.1 says a write made with no network is kept, not lost. Both clients keep one — and both had a
rule that deleted from it:

1. **A 429 was dropped as "refused".** `flushQueue` dropped every 4xx, and a rate limit is the one
   4xx a retry fixes: the server answered with `Retry-After: 60` and the device deleted the person's
   report because it had been busy. The queue is already the thing that waits, so the right answer
   is to wait for as long as the server asked.

2. **iOS's idempotency key was `String.hashValue`.** Swift seeds that randomly per process, so the
   same queued write carried a different key after every launch. The replay was therefore not
   recognised as a repeat — the §15.5 guarantee the key exists for — and a write that had committed
   before a 5xx landed twice. Android had the mirror-image defect: its first attempt carried *no*
   key at all, so a 5xx after a commit queued an op whose key the server had never seen.

3. **Android's key was `String.hashCode()`,** 32 bits of JVM hash, while the server keys its replay
   table by the string. Two distinct writes colliding on 32 bits would be replayed as each other.

Parts 1–3 are client source rules; no Python execution observes a Kotlin `catch` branch. Part 4
pins the server side: the 429 really does carry `Retry-After`, so a client honouring it is honouring
something the server sends.
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]
KOTLIN = REPO / 'android/app/src/main/java/ke/go/health/afyayangu/BackendClient.kt'
SWIFT = REPO / 'ios/AfyaYangu/BackendClient.swift'


def test_a_rate_limited_replay_waits_rather_than_deleting_the_write() -> None:
	"""429 is a delay, not a refusal — on both clients, and for the server's stated duration."""
	kotlin = KOTLIN.read_text()
	assert 'if (err.code == 429) {' in kotlin, (
		'Android drops a 429 with the other 4xx, so a rate-limited replay deletes the queued write')
	assert 'conn.getHeaderField("Retry-After")' in kotlin, (
		'Android\'s HttpError carries no Retry-After, so the 429 branch cannot honour it')
	# The branch must *defer*, not drop, and must sit before the blanket 4xx drop or it can never
	# run. Reading the branch body rather than the file: `store.drop` appears in the branch below.
	k_branch = kotlin[kotlin.index('if (err.code == 429) {'): kotlin.index('store.drop(op.opId)  // refused')]
	assert 'store.defer(op.opId, attempt, now + wait)' in k_branch, (
		'Android\'s 429 branch does not defer the op to its retry window')
	assert 'store.drop' not in k_branch, 'Android\'s 429 branch drops the op'
	assert 'err.retryAfterSeconds?.times(1000) ?: backoffDelayMs(attempt)' in k_branch, (
		'Android waits its own backoff instead of the Retry-After the server sent')

	swift = SWIFT.read_text()
	assert '} else if code == 429 {' in swift, (
		'iOS drops a 429 with the other 4xx, so a rate-limited replay deletes the queued write')
	s_branch = swift[swift.index('} else if code == 429 {'): swift.index('store.drop(op.opId) // refused')]
	assert 'store.deferOp(op.opId, attempt: attempt, retryAtMs: now + wait)' in s_branch, (
		'iOS\'s 429 branch does not defer the op to its retry window')
	assert 'store.drop' not in s_branch, 'iOS\'s 429 branch drops the op'
	assert 'http?.value(forHTTPHeaderField: "Retry-After")' in s_branch, (
		'iOS waits its own backoff instead of the Retry-After the server sent')


def test_the_idempotency_key_is_a_digest_of_the_content_on_both_clients() -> None:
	"""A key that changes across launches is not a key, and a 32-bit key is not a unique one."""
	swift = SWIFT.read_text()
	assert 'String(UInt(bitPattern: material.hashValue)' not in swift, (
		'iOS derives the key from `hashValue`, which Swift seeds per process: the same write gets a '
		'different key after every launch and the replay double-writes')
	assert 'SHA256.hash(data: Data(material.utf8))' in swift, 'iOS does not digest the op content'

	kotlin = KOTLIN.read_text()
	assert 'Integer.toHexString(material.hashCode())' not in kotlin, (
		'Android keys the replay table on a 32-bit hash, so two writes can collide')
	assert 'MessageDigest.getInstance("SHA-256")' in kotlin, 'Android does not digest the op content'
	# One derivation, used by both the first attempt and the queued op. Two spellings of the same
	# key is how the first attempt ends up keyless. Scoped to the key's own material: the file has
	# other SHA-256 uses (evidence chunking), and a count over the whole file would be a gate on
	# those rather than on this.
	assert kotlin.count('digest(material.toByteArray())') == 1, (
		'the op key is derived in more than one place, so the first attempt and the replay can differ')
	assert kotlin.count('private fun opKey(') == 1, 'the key derivation is not one function'
	assert 'val key = opKey(method, path, pathValues, params)' in kotlin


def test_the_first_attempt_carries_the_key_the_replay_will() -> None:
	"""A 5xx returned after the write committed must be recognisable on replay."""
	kotlin = KOTLIN.read_text()
	assert 'perform(method, path, pathValues, params, key)' in kotlin, (
		'Android\'s first attempt carries no idempotency key, so a 5xx after a commit queues an op '
		'whose key the server has never seen and the write lands twice')
	swift = SWIFT.read_text()
	assert 'req.setValue(op.key, forHTTPHeaderField: "idempotency-key")' in swift, (
		'iOS does not send the stored key on replay')


def test_the_server_answers_a_rate_limited_write_with_retry_after() -> None:
	"""The header the clients now honour is one the server actually sends.

	Without this, "wait as long as the server asked" is a client honouring a header nothing emits.
	"""
	import asyncio

	import httpx

	from afya.service import build_services, create_app

	async def probe() -> None:
		transport = httpx.ASGITransport(app=create_app(build_services()))
		async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
			headers = {'X-Device-Id': 'queue-gate-device'}
			limited = None
			for _ in range(200):
				resp = await client.get('/health', headers=headers)
				if resp.status_code == 429:
					limited = resp
					break
			assert limited is not None, 'the limiter never fired for this device'
			hinted = limited.headers.get('retry-after')
			assert hinted is not None and hinted.isdigit(), (
				'a 429 without a numeric Retry-After is a wait the client has to guess')
			assert hinted == '60'

	asyncio.run(probe())
