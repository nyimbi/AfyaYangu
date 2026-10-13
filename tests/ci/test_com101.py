"""§COM-101's "Offline report queue" — a report the CHW filed with no bars, kept until there is a signal.

The bullet read as carried and was not: `SyncService` had carried a `case_reports` rule in §16.3's
matrix since the matrix was written — server-authoritative, "clinical accuracy critical" — and
`CaseReport` had carried a `reported_offline` flag, and nothing joined them. A rule with no producer
is a rule for a dataset nothing writes, and a flag nothing reads is a field that looks implemented
on every screen that renders the form.

The CHW is the user this matters for. §COM-101 is the field worker's module: the person filing
these reports is standing in a village, and the report is most likely to be filed exactly where
there is no signal. §16.1 principle 1 — "local write always succeeds" — is about that moment.

What the tests below hold, in the two directions the codebase keeps failing:

* **The fact exists** — the op reaches the queue, under the dataset §16.3 names, carrying the whole
  report rather than a reference to it.
* **Something acts on it** — the composition root passes the queue (a service that *can* take one
  proves nothing about whether production does), the op survives a flush with no network, and it
  goes out the moment a network appears.

The gate that matters most is `reported_offline`. Queueing every report would make the queue a
duplicate factory, and §5.4's dedup cannot catch the copy: a CHW logging offline carries no MSISDN,
so the key `_dedup_key` builds is `None` and two replays of one report are two cases.
"""
import httpx

from afya.community.service import CommunityService
from afya.community.views import CaseReport, CaseStatus
from afya.identity.service import IdentityService
from afya.service import build_services, create_app
from afya.sync.service import SyncService
from afya.sync.views import ConnectionClass, SyncOp

MSISDN = '+254712345678'


def _case(report_id: str = 'CR-ABCD1234', **kw: object) -> CaseReport:
	base: dict[str, object] = {
		'report_id': report_id, 'chw_ref': 'chw-1', 'county': 'Busia', 'community': 'Budalangi',
		'symptoms': ['fever', 'vomiting'],
	}
	base.update(kw)
	return CaseReport.model_validate(base)


def _svc(sync: SyncService | None = None) -> tuple[CommunityService, SyncService]:
	queue = sync if sync is not None else SyncService()
	return CommunityService(IdentityService(), queue), queue


async def _chw(c: httpx.AsyncClient) -> dict[str, str]:
	"""A CHW token, through the PKCE flow §17.4 requires.

	`/community/cases` is `require_scope('assigned')`, so a citizen token is a 403 — the route's own
	test in `test_auth.py` holds that. This helper exists because a test that quietly used an
	anonymous token would be testing the 403 path and calling it the feature.
	"""
	import base64
	import hashlib
	verifier = 'v' * 43
	challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
	authz = (await c.post('/auth/pkce/authorize', json={
		'client_id': 'app', 'redirect_uri': 'afya://cb', 'code_challenge': challenge, 'state': 'state-1234',
	})).json()
	out = (await c.post('/auth/pkce/token', params={'role': 'chw'}, json={
		'authorization_code': authz['authorization_code'], 'client_id': 'app',
		'redirect_uri': 'afya://cb', 'code_verifier': verifier,
	})).json()
	return {'Authorization': f"Bearer {out['access_token']}"}


def _ops(queue: SyncService) -> list[SyncOp]:
	return [o for o in queue._queue.values() if o.dataset == 'case_reports']  # noqa: SLF001


# --- the fact exists ------------------------------------------------------------------------------

async def test_an_offline_report_reaches_the_queue() -> None:
	"""The bullet itself: the report is stored locally rather than only posted.

	`SyncService` is passed as the queue and the op must land in it. Before this unit the report was
	recorded in `CommunityService._cases` and nowhere else, so a handset that closed lost it — and
	§16.1 principle 5's "every queued write survives app restart" was a promise about a write that
	was never queued.
	"""
	svc, queue = _svc()
	view = await svc.submit_case(_case(reported_offline=True))
	assert view.alerts_sent == 1, 'the officer alert is unchanged; this unit adds a queue, not an alert'
	ops = _ops(queue)
	assert len(ops) == 1, 'an offline report must be queued'
	assert ops[0].dataset == 'case_reports'
	assert ops[0].attempt == 1, 'enqueue seeds the first attempt'
	assert not ops[0].synced


async def test_a_report_that_arrived_over_a_network_is_not_queued() -> None:
	"""The gate, and the direction that matters more.

	Queueing every report would replay each one on the next flush. §5.4's dedup is the guard against
	a doubled case, and it cannot fire here: the key `_dedup_key` builds is the phone number, and a
	CHW logging offline carries none — so `key is None`, the dedup reports "cannot be deduplicated"
	rather than "is a duplicate", and two replays of one report become two cases in the count PHEOC
	reads. `reported_offline` is the only thing that distinguishes the two arrivals.
	"""
	svc, queue = _svc()
	await svc.submit_case(_case(reported_offline=False))
	assert _ops(queue) == [], 'a report the server already holds must not be queued'
	svc2, queue2 = _svc()
	await svc2.submit_case(_case('CR-EEEE5555'))  # the flag's default is False
	assert _ops(queue2) == []


async def test_a_service_with_no_queue_still_files_the_report() -> None:
	"""The queue is optional for the reason `identity` is: a unit test that only wants the dedup must
	not have to stand up a queue. The report is still recorded — the bullet's "stored locally" is
	satisfied by the queue where there is one and by the service's own case map where there is not."""
	svc = CommunityService(IdentityService())
	view = await svc.submit_case(_case(reported_offline=True))
	assert view.alerts_sent == 1
	assert svc.case_status('CR-ABCD1234') is CaseStatus.reported


async def test_the_dataset_is_the_one_the_spec_writes_the_rule_for() -> None:
	"""The join between the two halves of the bullet, read off the op the service actually wrote.

	`SyncService.enqueue` refuses a dataset outside `STRATEGY_MATRIX`, so a typo raises at the first
	offline report rather than silently queueing — which is why the check has to go through the
	service and read the *queued* op. A version of this test that asserted the matrix and built a
	`SyncOp` by hand passed against a service queueing under any name at all: it checked the table
	and never the string the code writes into it.
	"""
	from afya.sync.views import STRATEGY_MATRIX, ConflictStrategy

	assert STRATEGY_MATRIX['case_reports'] is ConflictStrategy.server_auth, '§16.3: clinical accuracy critical'
	svc, queue = _svc()
	await svc.submit_case(_case(reported_offline=True))
	assert _ops(queue)[0].dataset == 'case_reports', 'the op the service wrote names the spec\'s dataset'


# --- the payload carries the report, not a pointer to it -------------------------------------------

async def test_the_payload_carries_every_field_including_the_nulls() -> None:
	"""§COM-101's "reports stored locally" means the *report*, not a reference to one.

	A payload carrying only `report_id` would leave the fields on a handset that crashed, and the
	officer would receive a case with no symptoms, no village and no temperature. `None` is encoded
	rather than omitted because §16.4's delta is computed field by field: an absent key means
	"unchanged", so a field that went from a value to nothing has to be *present* and empty to be
	sent at all.
	"""
	import json
	svc, queue = _svc()
	await svc.submit_case(_case(reported_offline=True, age_years=7, temperature_c=38.5,
	                            exposure_history='shared a matatu'))
	payload = _ops(queue)[0].payload
	assert set(payload) == set(CaseReport.model_fields), 'every field travels, the nulls included'
	assert json.loads(payload['symptoms']) == ['fever', 'vomiting'], 'a list survives as a list'
	assert json.loads(payload['age_years']) == 7
	assert json.loads(payload['temperature_c']) == 38.5
	assert json.loads(payload['sex']) is None, 'a null is present and null, not absent'
	back = CaseReport.model_validate({k: json.loads(v) for k, v in payload.items()})
	assert back.symptoms == ['fever', 'vomiting'] and back.age_years == 7


async def test_the_payload_round_trips_through_the_model_it_came_from() -> None:
	"""A payload that cannot be read back is a payload the server cannot file.

	The whole report is reconstructible from what is queued, which is the property that makes the
	queue a store rather than a note that something happened.
	"""
	import json
	svc, queue = _svc()
	original = _case(reported_offline=True, voice_note='niliona homa', voice_note_lang='sw',
	                 suspected_disease='cholera', geotagged=True)
	await svc.submit_case(original)
	rebuilt = CaseReport.model_validate({k: json.loads(v) for k, v in _ops(queue)[0].payload.items()})
	assert rebuilt.report_id == original.report_id
	assert rebuilt.voice_note == 'niliona homa' and rebuilt.voice_note_lang == 'sw'
	assert rebuilt.suspected_disease == 'cholera' and rebuilt.geotagged


async def test_a_delta_over_a_queued_report_changes_only_what_changed() -> None:
	"""§16.4's delta, over a payload this queue actually produces.

	A payload of one serialised blob would make every edit resend every field, and §16.4's delta sync
	would be a claim rather than a behaviour. The per-field encoding is what lets the difference be
	computed at all.
	"""
	import json
	from afya.sync.service import delta_payload
	svc, queue = _svc()
	await svc.submit_case(_case(reported_offline=True, temperature_c=38.5))
	before = _ops(queue)[0].payload
	after = dict(before, temperature_c=json.dumps(39.1))
	delta = delta_payload(before, after)
	assert delta == {'temperature_c': '39.1'}, delta


async def test_two_reports_filed_in_one_millisecond_are_two_ops() -> None:
	"""The op id is taken from the *tail* of a UUID7, and this is the defect that makes it matter.

	A UUID7's leading bytes are its millisecond timestamp, so a prefix collides for two ids minted in
	the same millisecond — and the queue is keyed on `op_id`, so the second silently overwrites the
	first. A CHW replaying a day of reports after an outage files them in a burst, which is exactly
	when the collisions cluster, and the failure mode is losing a case report at the one moment the
	offline queue exists to keep it. §MON-004's dose queue takes its suffix for the same reason.
	"""
	svc, queue = _svc()
	for i in range(40):
		await svc.submit_case(_case(f'CR-BURST{i:03d}', reported_offline=True))
	ops = _ops(queue)
	assert len(ops) == 40, f'40 reports queued as {len(ops)} ops — an op id collided'
	assert len({o.op_id for o in ops}) == 40
	for op in ops:
		assert op.op_id.startswith('OP-') and len(op.op_id) > 8


# --- something acts on it -------------------------------------------------------------------------

async def test_the_queue_survives_an_offline_flush_and_goes_out_when_a_network_appears() -> None:
	"""§16.2's first diamond, run both ways.

	An offline flush defers without marking anything sent and without earning a backoff — the phone
	was offline, not the report at fault — so the op keeps its due-now status and goes out the
	moment a network appears rather than waiting out a delay it did not cause. That is the bullet's
	"submitted when connectivity is available", performed.
	"""
	svc, queue = _svc()
	await svc.submit_case(_case(reported_offline=True))
	offline = await queue.flush(1_000, ConnectionClass.offline)
	assert offline.pending == 1 and offline.deferred == 1 and offline.synced == 0
	assert _ops(queue)[0].retry_at_ms is None, 'no backoff earned for a network that was not there'
	online = await queue.flush(2_000, ConnectionClass.wifi)
	assert online.synced == 1 and online.pending == 0
	assert _ops(queue)[0].synced, 'the report reached the server'
	assert 'case_reports' in queue._server_state, 'the server holds it'  # noqa: SLF001


async def test_the_route_queues_a_report_for_a_signed_in_chw() -> None:
	"""The composition root wires the queue in, so the *route* is what has to be checked.

	A report posted to `/community/cases` must appear in the deployment's own sync queue — the
	service taking a queue as an optional argument proves nothing about whether production passes
	one. This is the §MON-004 gate's shape, and it is the one that catches a forgotten constructor
	argument.
	"""
	svc = build_services()
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _chw(c)
		posted = await c.post('/community/cases', json={
			'report_id': 'CR-ROUTE001', 'chw_ref': 'chw-1', 'county': 'Busia', 'community': 'Budalangi',
			'symptoms': ['fever'], 'reported_offline': True}, headers=headers)
		assert posted.status_code == 200, posted.text
		assert posted.json()['alerts_sent'] == 1
		queue: SyncService = svc['sync']  # type: ignore[assignment]
		ops = [o for o in queue._queue.values() if o.dataset == 'case_reports']  # noqa: SLF001
		assert len(ops) == 1, 'the composition root did not hand the community service a queue'
		assert ops[0].payload['report_id'] == '"CR-ROUTE001"', ops[0].payload['report_id']


async def test_a_report_that_arrived_over_the_network_leaves_the_route_queue_empty() -> None:
	"""The same route, the other arrival. A deployment that queued every case report would replay
	each one, and the duplicate is one §5.4's dedup cannot catch for a CHW with no phone on file."""
	svc = build_services()
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		headers = await _chw(c)
		posted = await c.post('/community/cases', json={
			'report_id': 'CR-ROUTE002', 'chw_ref': 'chw-1', 'county': 'Busia', 'community': 'Budalangi',
			'symptoms': ['fever']}, headers=headers)
		assert posted.status_code == 200, posted.text
		queue: SyncService = svc['sync']  # type: ignore[assignment]
		assert [o for o in queue._queue.values() if o.dataset == 'case_reports'] == []  # noqa: SLF001


# --- the parts that must not have changed ---------------------------------------------------------

async def test_a_duplicate_open_case_is_still_stored_and_still_queued_when_it_arrived_offline() -> None:
	"""The dedup docstring's own promise: the duplicate is kept, because dropping it loses the channel
	it arrived on. Queued beside the *alert* rather than beside the recording would have dropped
	exactly the second report that promise is about."""
	identity = IdentityService()
	queue = SyncService()
	svc = CommunityService(identity, queue)
	await svc.submit_case(_case('CR-AAAA1111', reporter_msisdn=MSISDN))
	second = await svc.submit_case(_case('CR-BBBB2222', reporter_msisdn=MSISDN, reported_offline=True))
	assert second.deduplicated and second.alerts_sent == 0
	assert svc.case_status('CR-BBBB2222') is CaseStatus.reported
	assert len(_ops(queue)) == 1, 'the duplicate is still a report the server does not have'


async def test_a_photo_without_geotag_is_still_refused_before_anything_is_queued() -> None:
	"""§COM-101's consent gate, and its ordering. The refusal happens before the queue is written, so
	a refused report is not a queued one — otherwise the consent check would be advisory and the
	report would reach the server on the next flush anyway."""
	import pytest
	svc, queue = _svc()
	with pytest.raises(AssertionError):
		await svc.submit_case(_case(reported_offline=True, photo_sha256='a' * 64, geotagged=False))
	assert _ops(queue) == [], 'a refused report must not be queued'


async def test_no_spec_feature_code_reaches_the_queued_payload() -> None:
	"""§17.4's rule at the surface this unit adds: the payload is a wire format the client and the
	server both read, so an internal traceability handle in it is the code leaking out of the
	backend. The queue carries the report's own fields and nothing else."""
	import json
	import re
	svc, queue = _svc()
	await svc.submit_case(_case(reported_offline=True))
	blob = json.dumps(_ops(queue)[0].payload)
	assert not re.search(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b', blob), blob
