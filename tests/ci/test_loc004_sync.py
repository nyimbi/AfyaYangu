"""§LOC-004's third Behaviour bullet: "Check-in logged locally; synced with consent".

The bullet has two halves and the tree had one. `check_in` wrote the check-in to `self._checkins`
and that is a real local write — §16.1 principle 1, "every user action is written to the local
database first" — but the second half was a boolean taken from the request body:

	shared=checkin.share_with_authority

So `CheckInReceipt.shared` answered "did the person tick the box", not "did anything leave the
phone", and `follow_up`'s `CheckInAttendance.shared` read the same stored flag back months later as
if it were the delivery. The audit row was `carried` on `check_in`, which is a ref that resolves
and a claim that was false: a person who asked to share with no standing consent, or on a device
with no queue, was told their visit had reached the health team.

The tests come in the two halves plus the four states. The four are the half worth reading, because
"not asked", "asked and not permitted", "asked and permitted but nowhere to send it" and "sent" are
four different things to say to someone standing at a gate, and one sentence covering the middle
two is the defect this closes.
"""
import re

import pytest
from fastapi.testclient import TestClient

from afya.info.recency import instant_iso, instant_ms, midnight_ms
from afya.location.service import CHECKIN_SYNC_DATASET, SHARE_AUTHORITY_CATEGORY, LocationService
from afya.location.views import CheckIn, CheckInPoint
from afya.strings import CHECKIN_STRINGS, checkin
from afya.sync.service import SyncService
from afya.sync.views import STRATEGY_MATRIX, ConflictStrategy, SyncOp

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


def _point(kind: str = 'border_post', token: str = 'BORDER01') -> CheckInPoint:
	return CheckInPoint(point_id='P-1', kind=kind, label='Busia border post', county='Busia',
	                    token=token)


def _checkin(share: bool = True, **kw: object) -> CheckIn:
	return CheckIn(checkin_id='CHK-BORDER01', point_token='BORDER01', subject_ref='U-1',
	               method='qr', at_iso='2026-10-01T09:00:00Z', share_with_authority=share, **kw)  # type: ignore[arg-type]


class FailingQueue:
	"""A queue that is wired and cannot take the op. §16.1 principle 5: the local write happened
	first, so a transport that blows up costs the send and not the record."""

	async def enqueue(self, op: SyncOp) -> SyncOp:
		raise RuntimeError('queue unavailable')


def _consent(*granted: str) -> object:
	"""A consent ledger that grants exactly the categories named. The service asks it one question
	per act, and a stub that always said yes could not tell the two toggles apart."""
	held = set(granted)

	def holds(_subject_ref: str, category: str) -> bool:
		return category in held

	return holds


def _queued(sync: SyncService) -> list[SyncOp]:
	"""The check-in ops on the queue. Read through the service's own store, as §MON-004's and
	§COM-101's queue tests do: a read surface invented for the test would not be the one a flush
	walks."""
	return [o for o in sync._queue.values() if o.dataset == CHECKIN_SYNC_DATASET]  # noqa: SLF001


async def _svc(*granted: str, sync: SyncService | None = None, **kw: object) -> LocationService:
	svc = LocationService(share_consent=_consent(*granted), sync=sync, **kw)  # type: ignore[arg-type]
	await svc.register_point(_point())
	return svc


# --- the local half, which was already there ---------------------------------------------------

async def test_the_local_write_happens_whether_or_not_anything_is_sent() -> None:
	"""§16.1 principle 1, and it is unconditional: a person with no permission and no signal still
	has a record of having been somewhere. A sync gate that could refuse the *write* would be a
	check-in lost at the one moment it was made."""
	local = await (await _svc()).check_in(_checkin(share=False))
	assert local.logged_locally is True and local.synced is False
	sent = await (await _svc(SHARE_AUTHORITY_CATEGORY, sync=SyncService())).check_in(_checkin())
	assert sent.logged_locally is True and sent.synced is True


async def test_a_queue_that_raises_costs_the_send_and_not_the_record() -> None:
	"""Order matters, and this is the test that says so: the append happens before the send, so a
	queue that blows up leaves the visit on file. A version that appended only on a successful send
	would lose the check-in at the one moment it must be kept — §16.1 principle 5."""
	svc = await _svc(SHARE_AUTHORITY_CATEGORY, sync=FailingQueue())  # type: ignore[arg-type]
	with pytest.raises(RuntimeError):
		await svc.check_in(_checkin())
	assert len(svc.checkins_for('U-1')) == 1, 'the local write is unconditional'
	assert svc.checkins_for('U-1')[0].synced is False, (
		'a record that survived a failed send does not claim the send happened')


async def test_the_permission_is_checked_on_the_send_path_and_not_only_in_the_prose() -> None:
	"""The gate has to be where the send is decided. Every other refusal test wires no queue, so
	`_sync_checkin` returns at the queue check before the consent block is reached — which means a
	gate that lived only in the receipt's branch would pass all of them and send anyway. This one
	wires a queue and asserts the queue is still empty."""
	sync = SyncService()
	receipt = await (await _svc(sync=sync)).check_in(_checkin())
	assert receipt.synced is False
	assert _queued(sync) == [], 'nothing reached the queue without the permission'
	tracking_only = SyncService()
	svc = await _svc('location_tracking', sync=tracking_only)
	await svc.check_in(_checkin())
	assert _queued(tracking_only) == [], 'the tracking toggle is not the sharing permission'
	assert svc.checkins_for('U-1')[0].synced is False, (
		'the stored record carries the outcome, so `follow_up` cannot read a send that did not happen')


async def test_a_deployment_with_no_consent_ledger_refuses_to_send() -> None:
	"""Fail closed. A service with no ledger cannot establish §SEC-001's permission, so the send is
	refused — and the refusal is reached on the *send* path, with a queue wired, which is the case a
	gate living only in the receipt's prose branch would never consult."""
	sync = SyncService()
	svc = LocationService(sync=sync)  # no `share_consent` at all
	await svc.register_point(_point())
	receipt = await svc.check_in(_checkin())
	assert receipt.synced is False and receipt.synced_with is None
	assert _queued(sync) == [], 'a ledger that is absent is not a ledger that says yes'
	assert receipt.message == checkin('en', 'sync_no_consent', place='Busia border post')


# --- the four states ---------------------------------------------------------------------------

async def test_a_check_in_nobody_asked_to_share_stays_local_and_says_so() -> None:
	"""Not asked. The receipt must not mention permission, because there is nothing the person did
	wrong and nothing for them to go and switch on."""
	receipt = await (await _svc()).check_in(_checkin(share=False))
	assert receipt.synced is False and receipt.synced_with is None
	assert receipt.message == checkin('en', 'sync_local_only', place='Busia border post')
	assert 'permission' not in receipt.message


async def test_asking_to_share_without_the_permission_is_refused_in_those_words() -> None:
	"""Asked and not permitted. The refusal names the permission, because that is the thing the
	person can act on — and it is the sentence that used to be missing entirely."""
	receipt = await (await _svc()).check_in(_checkin())
	assert receipt.synced is False and receipt.synced_with is None
	assert receipt.message == checkin('en', 'sync_no_consent', place='Busia border post')


async def test_the_tracking_category_is_not_the_sharing_permission() -> None:
	"""§SEC-001's two toggles. A ledger holding `location_tracking` is a person who allowed a diary
	and did not allow the Ministry, and reading the first as the second is the consent-that-is-not-
	the-one-the-act-requires defect §COM-103 and §LOC-003 both closed."""
	receipt = await (await _svc('location_tracking')).check_in(_checkin())
	assert receipt.synced is False
	assert receipt.message == checkin('en', 'sync_no_consent', place='Busia border post')


async def test_the_permission_with_nowhere_to_send_it_is_a_different_sentence() -> None:
	"""Asked, permitted, no queue. The refusal is about the deployment and not the person, so it must
	not send them to a settings screen that is already switched on."""
	receipt = await (await _svc(SHARE_AUTHORITY_CATEGORY)).check_in(_checkin())
	assert receipt.synced is False and receipt.synced_with is None
	assert receipt.message == checkin('en', 'sync_no_queue', place='Busia border post')
	assert 'permission' not in receipt.message


async def test_a_check_in_that_was_sent_says_so_and_names_where_it_went() -> None:
	"""Sent. `synced_with` is the dataset rather than a boolean, so a client can tell what left
	without parsing the prose."""
	receipt = await (await _svc(SHARE_AUTHORITY_CATEGORY, sync=SyncService())).check_in(_checkin())
	assert receipt.synced is True and receipt.synced_with == CHECKIN_SYNC_DATASET
	assert receipt.message == checkin('en', 'sync_sent', place='Busia border post')


async def test_the_four_states_are_four_different_sentences() -> None:
	"""The instrument for the defect. One sentence covering the middle two is exactly what shipped,
	so the four are pinned as a set of four distinct strings rather than each asserted alone."""
	messages = {
		checkin('en', key, place='Busia border post')
		for key in ('sync_local_only', 'sync_no_consent', 'sync_no_queue', 'sync_sent')
	}
	assert len(messages) == 4


# --- the payload -------------------------------------------------------------------------------

async def test_what_is_queued_names_the_place_and_not_the_person() -> None:
	"""The consent this act runs under is §SEC-001's `share_health_authorities`, whose own words are
	"Counts of illness, **with no names**". A payload carrying `subject_ref` would be a share under a
	consent that does not cover it — the same reading §LOC-003's geohash truncation comes from."""
	sync = SyncService()
	await (await _svc(SHARE_AUTHORITY_CATEGORY, sync=sync)).check_in(_checkin())
	op = _queued(sync)[0]
	assert 'subject_ref' not in op.payload, op.payload
	assert op.payload['point_id'] == 'P-1' and op.payload['county'] == 'Busia'
	assert op.payload['method'] == 'qr' and op.payload['at_iso'] == '2026-10-01T09:00:00Z'


async def test_the_op_carries_the_instant_and_not_the_day_it_falls_on() -> None:
	"""`client_ts` and the payload's `at_iso` are one fact, so they must not be two readings of it.

	The first cut built `client_ts` with `midnight_ms`, which reads a *bare date* and truncates
	anything longer to its first ten characters. A check-in at 09:00 and one at 21:30 at the same post
	then carried the same timestamp, and §16.3's `facility` row is server-authoritative precisely
	because the server compares versions — so a queue of one afternoon's check-ins all bearing
	midnight is a set the server cannot order. The payload said 09:00 while the op said 00:00.
	"""
	sync = SyncService()
	await (await _svc(SHARE_AUTHORITY_CATEGORY, sync=sync)).check_in(_checkin())
	op = _queued(sync)[0]
	assert instant_iso(op.client_ts) == op.payload['at_iso'], (
		f'the op says {instant_iso(op.client_ts)} and the payload says {op.payload["at_iso"]}')
	assert op.client_ts == instant_ms('2026-10-01T09:00:00Z')
	assert op.client_ts != midnight_ms('2026-10-01T09:00:00Z'), 'the day boundary is not the instant'


async def test_the_dataset_is_the_one_the_conflict_matrix_carries_a_rule_for() -> None:
	"""`SyncService.enqueue` asserts the dataset against `STRATEGY_MATRIX`, so a name the spec has no
	rule for raises at the one moment a check-in must be kept. The rule is `facility`'s —
	server-authoritative, because the facility is the central source of truth — and that is the right
	one here: a check-in the county has not seen has not happened to its attendance figure."""
	assert CHECKIN_SYNC_DATASET in STRATEGY_MATRIX
	assert STRATEGY_MATRIX[CHECKIN_SYNC_DATASET] is ConflictStrategy.server_auth
	assert SyncService().rule_for(CHECKIN_SYNC_DATASET).rationale == 'Central source of truth'


async def test_two_check_ins_in_one_millisecond_do_not_collide_in_the_queue() -> None:
	"""The *tail* of the id, not the head: a UUID7's leading bytes are its millisecond timestamp, so
	a prefix collides for a coach-load arriving at one gate and the queue — keyed on `op_id` — keeps
	the last and drops the rest. §MON-004's dose queue takes its suffix for the same reason."""
	sync = SyncService()
	svc = await _svc(SHARE_AUTHORITY_CATEGORY, sync=sync)
	for n in range(1, 6):
		await svc.check_in(CheckIn(
			checkin_id=f'CHK-BORDER{n:02d}', point_token='BORDER01', subject_ref='U-1',
			method='qr', at_iso='2026-10-01T09:00:00Z', share_with_authority=True))
	assert len(_queued(sync)) == 5, 'five check-ins in one millisecond are five ops, not one'


async def test_a_caller_cannot_assert_its_own_sync_outcome() -> None:
	"""`synced` is written by `check_in` and by nothing else, exactly as `SyncService.enqueue`
	overwrites the `synced` on the op it is handed. A field a caller can set to True is a field that
	says nothing — which is the whole shape of the defect, one level down."""
	svc = await _svc()
	forged = _checkin(share=False)
	forged.synced = True
	receipt = await svc.check_in(forged)
	assert receipt.synced is False
	assert svc.checkins_for('U-1')[0].synced is False, (
		'the stored record is corrected too, or `follow_up` reads the forgery back')


# --- the read-back, which is where the old flag did its second job -----------------------------

async def test_attendance_reports_the_send_rather_than_the_request() -> None:
	"""`CheckInAttendance.shared` read `c.share_with_authority` off the stored record, so a check-in
	that was refused still showed as shared in the person's own attendance months later."""
	svc = await _svc()
	await svc.check_in(_checkin())
	row = svc.follow_up('U-1', 1_790_845_200_000).attendance
	assert row is not None and row[0].synced is False
	sent = await _svc(SHARE_AUTHORITY_CATEGORY, sync=SyncService())
	await sent.check_in(_checkin())
	row = sent.follow_up('U-1', 1_790_845_200_000).attendance
	assert row is not None and row[0].synced is True


# --- the language, which the receipt had none of -----------------------------------------------

async def test_the_receipt_is_served_in_the_language_the_person_asked_for() -> None:
	"""§ACC-002's rule reaches a person at a gate as much as a triage answer. The receipt was built
	with no `lang` at all, so a Swahili speaker read an English sentence about whether their visit
	had been sent."""
	sw = await (await _svc()).check_in(_checkin(share=False, lang='sw'))
	assert sw.served_in == 'sw'
	assert sw.message == checkin('sw', 'sync_local_only', place='Busia border post')
	assert sw.message != checkin('en', 'sync_local_only', place='Busia border post')


async def test_a_language_with_no_table_is_served_english_and_says_so() -> None:
	"""The documented fallback, and it is not silent: `served_in` reports what the person actually
	got, so a Dholuo speaker is not left reading English believing it is Dholuo."""
	luo = await (await _svc()).check_in(_checkin(share=False, lang='luo'))
	assert luo.served_in == 'en'
	assert luo.message == checkin('en', 'sync_local_only', place='Busia border post')


def test_the_sync_strings_are_translated_and_keep_their_placeholder() -> None:
	"""`{place}` is the point's own label, and a translation that dropped it prints a sentence with
	a hole where the one fact the person needs goes."""
	for key in ('sync_local_only', 'sync_no_consent', 'sync_sent', 'sync_no_queue'):
		assert key in CHECKIN_STRINGS['en'] and key in CHECKIN_STRINGS['sw'], key
		assert '{place}' in CHECKIN_STRINGS['en'][key]
		assert '{place}' in CHECKIN_STRINGS['sw'][key], f'{key} lost {{place}} in sw'
		assert CHECKIN_STRINGS['sw'][key] != CHECKIN_STRINGS['en'][key], f'{key} is untranslated'


def test_the_two_category_names_agree() -> None:
	"""`SHARE_AUTHORITY_CATEGORY` is written in `afya.location` rather than imported, so that the
	module keeps no import edge to `afya.privacy`. A copy that drifts would make the gate read a
	category the ledger has never been asked about, and it would refuse every share forever."""
	from afya.privacy.views import ConsentCategory
	assert SHARE_AUTHORITY_CATEGORY == ConsentCategory.share_health_authorities.value


# --- the route ---------------------------------------------------------------------------------

def _client() -> TestClient:
	from afya.service import build_services, create_app
	return TestClient(create_app(build_services()))


def _citizen(c: TestClient, subject: str) -> dict[str, str]:
	r = c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'authorization': f'Bearer {r.json()["token"]}'}


def test_the_route_serves_the_sync_outcome_and_not_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
	"""A green unit test says nothing about what the front door serves. The person posts the flag and
	reads back what happened; with no sharing consent on the ledger the two disagree, and the
	disagreement is the point."""
	c = _client()
	h = _citizen(c, 'probe-1')
	assert c.post('/location/checkin/point', json={
		'point_id': 'P-ROUTE', 'kind': 'border_post', 'label': 'Busia border post',
		'county': 'Busia', 'token': 'ROUTEP1',
	}).status_code == 200
	served = c.post('/location/checkin', headers=h, json={
		'checkin_id': 'CHK-ROUTE001', 'point_token': 'ROUTEP1', 'subject_ref': 'probe-1',
		'method': 'qr', 'at_iso': '2026-10-01T09:00:00Z', 'share_with_authority': True,
	})
	assert served.status_code == 200, served.text
	body = served.json()
	assert body['logged_locally'] is True
	assert body['synced'] is False and body['synced_with'] is None, body
	assert 'permission' in body['message'], body['message']
	assert body['served_in'] == 'en'
	assert not FEATURE_CODE.search(served.text), served.text


def test_the_route_reads_the_sent_state_back_off_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
	"""The other side of the same route: with §SEC-001's sharing category granted, the same post
	reports a send and names the dataset. Without this the gate could be a constant `False` and the
	first test would still pass."""
	monkeypatch.setenv('AFYA_APP_LAYER_KEY', 'ab' * 32)
	c = _client()
	h = _citizen(c, 'probe-2')
	grant = c.post('/privacy/consent', headers=h, json={
		'subject_ref': 'probe-2', 'purpose': SHARE_AUTHORITY_CATEGORY,
		'data_types': ['checkin'], 'retention_days': 21, 'legal_basis': 'consent', 'lang': 'en',
	})
	assert grant.status_code == 200, grant.text
	assert c.post('/location/checkin/point', json={
		'point_id': 'P-ROUTE2', 'kind': 'border_post', 'label': 'Malaba border post',
		'county': 'Busia', 'token': 'ROUTEP2',
	}).status_code == 200
	served = c.post('/location/checkin', headers=h, json={
		'checkin_id': 'CHK-ROUTE002', 'point_token': 'ROUTEP2', 'subject_ref': 'probe-2',
		'method': 'nfc', 'at_iso': '2026-10-01T09:00:00Z', 'share_with_authority': True,
	})
	assert served.status_code == 200, served.text
	body = served.json()
	assert body['synced'] is True and body['synced_with'] == CHECKIN_SYNC_DATASET, body
	assert 'has been sent' in body['message'], body['message']


def test_the_audit_row_names_the_sync_half() -> None:
	"""The row this unit closes. It was `carried` on `check_in` — a ref that resolves — while the
	sync half of its own sentence did not exist, which is the failure a resolving ref cannot catch.
	The ref now names the method that does the second half, and the note records what it does."""
	from afya.content_audit.service import FEATURE_CONTENT
	from afya.refs import resolves

	row = [r for r in FEATURE_CONTENT if r[0] == 'LOC-004' and r[2].startswith('Check-in logged')][0]
	assert row[3] == 'carried' and row[4] == 'afya.location.service:LocationService._sync_checkin', row
	assert resolves(row[4]), row[4]
	assert row[5] and 'no names' in row[5], row[5]
