"""§COM-104's two missing bullets, held shut.

§11.4's tracker had four of its five bullets: the button posted, the clusters aggregated, the
dashboard read them. The two that were missing failed in the two shapes this codebase keeps
finding.

* **Text, voice, or screenshot submission** — `medium` was a four-value pattern with no payload
  behind any of them. A person with the rumour as a WhatsApp voice note had to retype it as a
  claim, and the two media that cannot be retyped are the two a forward arrives in. A `screenshot`
  report was indistinguishable from a `text` one while the cluster counts read "12 screenshots".
* **Push notification with corrections when a rumour the user flagged is addressed** — the
  section's flow ends "published on all channels → flagger notified", `correction_for` drafted the
  text, `flagger_ref` was written on every submission and read nowhere, and `ChannelService.push`
  existed with no call sites. The same shape as §COM-103: every part present, the join absent.

So the tests come in two halves. The first holds the medium honest — a report that names a
recording or an image must carry one, and the bytes never enter the model because §SEC-002 gives
the photograph its own consent. The second holds the notification honest, which is harder: a
notice is easy to report as sent, so what is checked is the three cases in which it must *not* be,
and that each says which it was.
"""
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from afya.alerting.service import AlertingService
from afya.channels.views import PushPayload
from afya.community.service import (
	NOTICE_WITHHELD_NO_TRANSPORT,
	NOTICE_WITHHELD_TRANSPORT_FAILED,
	NOTICE_WITHHELD_UNDRAFTED,
	NOTICE_WITHHELD_UNSUBSCRIBED,
	CommunityService,
)
from afya.community.views import MisinfoSubmission
from afya.service import build_services, create_app

REPO = Path(__file__).resolve().parents[2]

FEATURE_CODE = __import__('re').compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


def _submission(**kw: Any) -> MisinfoSubmission:
	base: dict[str, Any] = {
		'submission_id': 'MIS-ABCD0001', 'claim': 'Drinking salt water cures Ebola',
		'county': 'Busia', 'medium': 'text', 'topic': 'cure_claim',
	}
	base.update(kw)
	return MisinfoSubmission(**base)


class RecordingPush:
	"""The delivery path, as §11.4 sees it. Records what it was handed and can be made to fail.

	It takes the model rather than a dict, like `ChannelService.push` does — the first version of the
	service passed a dict and the mismatch surfaced as a transport failure, which is the one place a
	caller cannot see it.
	"""

	def __init__(self, fail: bool = False) -> None:
		self.sent: list[PushPayload] = []
		self._fail = fail

	async def push(self, payload: PushPayload) -> PushPayload:
		if self._fail:
			raise RuntimeError('transport unreachable')
		self.sent.append(payload)
		return payload


def _service(notifier: Any = None, alerts: AlertingService | None = None) -> CommunityService:
	return CommunityService(notifier=notifier, alerts=alerts)


# --- the medium: a voice note and a screenshot have somewhere to live -------------------------

def test_a_screenshot_report_must_carry_the_image() -> None:
	"""The audit row's own gap: a `screenshot` with no image is a `text` report under another label."""
	with pytest.raises(ValidationError, match='must carry the recording, the image or its transcript'):
		_submission(medium='screenshot')
	with pytest.raises(ValidationError, match='must carry the recording, the image or its transcript'):
		_submission(medium='voice')
	with pytest.raises(ValidationError, match='must carry the recording, the image or its transcript'):
		_submission(medium='whatsapp_forward')


def test_a_text_report_carries_no_payload() -> None:
	"""The other direction. A `text` report is complete without one, and demanding it would make the
	button that already worked stop working."""
	assert _submission(medium='text').evidence_ref is None


def test_a_voice_note_is_carried_as_a_transcript() -> None:
	"""A spoken rumour reaches `classify()` as words. Without this a voice report is a claim nobody
	can read, and the voice path is the one a person who cannot type needs."""
	s = _submission(medium='voice', transcript='They said drinking salt water cures Ebola')
	assert s.transcript and s.medium == 'voice'


def test_the_recording_is_shared_only_with_per_item_consent() -> None:
	"""§SEC-002's own words for this data: "Photos encrypted and only shared with explicit per-item
	consent". A reference with no consent is the gate skipped, not a gate defaulted open."""
	with pytest.raises(ValidationError, match='explicit per-item consent'):
		_submission(medium='screenshot', evidence_ref='v1.abc.def')
	assert _submission(medium='screenshot', evidence_ref='v1.abc.def', evidence_consent=True).evidence_consent


def test_no_bytes_field_exists_on_the_model() -> None:
	"""The reference is a reference. A model that could hold the image would put a rumour someone
	forwarded into every log line and every cluster payload that carries the submission."""
	fields = set(MisinfoSubmission.model_fields)
	assert 'evidence_ref' in fields and 'transcript' in fields
	assert not any(f in fields for f in ('image', 'blob', 'bytes', 'photo', 'data'))


# --- the notice: the flagger is told, and the refusals are named ------------------------------

async def test_the_flagger_is_told_when_the_correction_is_ready() -> None:
	"""§11.4's last arrow. `flagger_ref` was written and never read; this is the read."""
	push = RecordingPush()
	svc = _service(notifier=push)
	await svc.flag_misinfo(_submission(flagger_ref='s1'))
	notices = await svc.notify_flaggers('cure_claim')
	assert len(notices) == 1
	assert notices[0].sent and notices[0].subject_ref == 's1'
	assert notices[0].correction and notices[0].correction != ''
	assert len(push.sent) == 1 and push.sent[0].subject_ref == 's1'
	assert push.sent[0].category == 'community_alerts', 'the toggle that governs it travels with it'


async def test_the_notice_carries_the_correction_not_the_fallback() -> None:
	"""An undrafted rumour is not answered with "under verification" pushed to the person who
	reported it — they are the one who already knows. The notice is owed once there is something
	to say, and until then the refusal says which it is."""
	push = RecordingPush()
	svc = _service(notifier=push)
	await svc.flag_misinfo(_submission(topic='stigma_claim', flagger_ref='s1'))
	notices = await svc.notify_flaggers('stigma_claim')
	assert len(notices) == 1
	assert not notices[0].sent
	assert notices[0].withheld == NOTICE_WITHHELD_UNDRAFTED
	assert push.sent == [], 'a rumour under verification must not be pushed'


async def test_a_report_with_no_flagger_is_not_reported_as_sent() -> None:
	"""A notice "sent" to nobody is the §COM-103 defect wearing §COM-104's clothes. A report that
	named no one to tell produces no notice at all rather than a sent one."""
	push = RecordingPush()
	svc = _service(notifier=push)
	await svc.flag_misinfo(_submission(flagger_ref=None))
	assert await svc.notify_flaggers('cure_claim') == []
	assert push.sent == []


async def test_a_person_who_switched_community_alerts_off_is_not_pushed() -> None:
	"""§ALT-003's own toggle, read through the ledger that holds it. The correction is kept for them
	to read — switching a category off is a preference about being interrupted, not a way to lose
	the answer to a rumour they reported."""
	push = RecordingPush()
	alerts = AlertingService()
	alerts.set_preference('s1', 'community_alerts', False)
	svc = _service(notifier=push, alerts=alerts)
	await svc.flag_misinfo(_submission(flagger_ref='s1'))
	notices = await svc.notify_flaggers('cure_claim')
	assert len(notices) == 1 and not notices[0].sent
	assert notices[0].withheld == NOTICE_WITHHELD_UNSUBSCRIBED
	assert push.sent == []
	assert svc.notices_for('s1')[0].correction, 'the correction is still readable in the app'


async def test_a_deployment_with_no_transport_says_so_rather_than_claiming_delivery() -> None:
	"""The §COM-103 lesson: a control that reports success with nothing wired is worse than one that
	reports the gap. With a subscriber and no transport the notice is composed and withheld."""
	svc = _service(notifier=None)
	await svc.flag_misinfo(_submission(flagger_ref='s1'))
	notices = await svc.notify_flaggers('cure_claim')
	assert len(notices) == 1 and not notices[0].sent
	assert notices[0].withheld == NOTICE_WITHHELD_NO_TRANSPORT


async def test_a_transport_that_fails_does_not_lose_the_correction() -> None:
	"""A transport that is down is this route's normal case. The correction is composed either way,
	and the person can read it — nothing is lost (§16.1 principle 5)."""
	svc = _service(notifier=RecordingPush(fail=True))
	await svc.flag_misinfo(_submission(flagger_ref='s1'))
	notices = await svc.notify_flaggers('cure_claim')
	assert len(notices) == 1 and not notices[0].sent
	assert notices[0].correction
	assert notices[0].withheld == NOTICE_WITHHELD_TRANSPORT_FAILED, (
		'a transport that failed and a deployment with no transport are different facts')
	assert svc.notices_for('s1')


async def test_the_notice_is_keyed_on_the_person_and_the_rumour() -> None:
	"""Twenty people who reported the same rumour are twenty notices, and one person who reported it
	twice is one. A topic-keyed store would tell exactly one of the twenty."""
	push = RecordingPush()
	svc = _service(notifier=push)
	for i, flagger in enumerate(('s1', 's2', 's1')):
		await svc.flag_misinfo(_submission(submission_id=f'MIS-ABCD{i:04d}', flagger_ref=flagger))
	notices = await svc.notify_flaggers('cure_claim')
	assert sorted(n.subject_ref for n in notices) == ['s1', 's2']
	assert len(push.sent) == 2
	again = await svc.notify_flaggers('cure_claim')
	assert [n.sent for n in again] == [True, True]
	assert len(push.sent) == 2, 'a second call must not push a second time'


async def test_an_unclassified_rumour_is_not_answered_with_the_fallback() -> None:
	"""A report filed with no topic resolves to `unknown`, which has a library entry — so the
	fallback topic is the case that matters most, and it is the one a naive `in CORRECTION_LIBRARY`
	would push."""
	push = RecordingPush()
	svc = _service(notifier=push)
	await svc.flag_misinfo(_submission(topic=None, flagger_ref='s1'))
	notices = await svc.notify_flaggers('unknown')
	assert len(notices) == 1 and not notices[0].sent
	assert push.sent == []


async def test_no_spec_feature_code_reaches_a_served_notice() -> None:
	"""The standing constraint: feature ids are traceability handles, never user-facing copy."""
	push = RecordingPush()
	svc = _service(notifier=push)
	await svc.flag_misinfo(_submission(flagger_ref='s1'))
	served = (await svc.notify_flaggers('cure_claim'))[0].model_dump(mode='json')
	blob = repr(served)
	assert not FEATURE_CODE.search(blob), blob


async def test_push_payload_requires_a_recipient() -> None:
	"""`PushPayload` had no subject, so a notification could be "sent" for a year with nobody it was
	for — which is exactly what the audit row describes."""
	with pytest.raises(ValidationError):
		PushPayload(title='t', body='b')  # type: ignore[call-arg]


# --- the route --------------------------------------------------------------------------------

@pytest.fixture
async def client() -> Any:
	svc = build_services()
	app = create_app(svc)
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://test') as c:
		yield c


async def _citizen(c: httpx.AsyncClient, subject: str) -> dict[str, str]:
	r = await c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'Authorization': f'Bearer {r.json()["token"]}'}


async def test_the_route_notifies_and_serves_the_notice(client: httpx.AsyncClient) -> None:
	"""A green unit test says nothing about what the front door serves. The flag route composes the
	notice on the same call, and the `self`-scoped route hands it back."""
	headers = await _citizen(client, 's1')
	flag = await client.post('/community/misinformation', json={
		'submission_id': 'MIS-ROUTE001', 'claim': 'Drinking salt water cures Ebola',
		'county': 'Busia', 'medium': 'text', 'topic': 'cure_claim', 'flagger_ref': 's1',
	}, headers=headers)
	assert flag.status_code == 200, flag.text
	body = flag.json()
	assert 'notices' in body and len(body['notices']) == 1
	assert body['notices'][0]['sent'] is True
	served = await client.get('/community/misinformation/notices/s1', headers=headers)
	assert served.status_code == 200, served.text
	rows = served.json()
	assert len(rows) == 1 and rows[0]['topic'] == 'cure_claim'
	assert not FEATURE_CODE.search(served.text), served.text


async def test_the_route_refuses_a_screenshot_with_no_image(client: httpx.AsyncClient) -> None:
	"""The medium contract is the request's, so a violation is the caller's 422 rather than an
	unhandled 500."""
	r = await client.post('/community/misinformation', json={
		'submission_id': 'MIS-ROUTE002', 'claim': 'A forwarded screenshot says the schools are closed',
		'county': 'Busia', 'medium': 'screenshot',
	})
	assert r.status_code == 422, r.text


async def test_the_notices_route_is_self_scoped(client: httpx.AsyncClient) -> None:
	"""A notice names the rumour this person reported and the correction they were owed. That is a
	fact about them, so naming someone else is refused rather than served."""
	headers = await _citizen(client, 's1')
	r = await client.get('/community/misinformation/notices/s2', headers=headers)
	assert r.status_code == 403, r.text


def test_the_two_audit_rows_are_carried() -> None:
	"""The rows this unit closes, and the refs they point at — `afya.refs.resolves` walks dotted
	attributes, so a ref that does not import fails here rather than in an audit run."""
	from afya.content_audit.service import FEATURE_CONTENT
	from afya.refs import resolves

	rows = [r for r in FEATURE_CONTENT if r[0] == 'COM-104']
	assert not [r for r in rows if r[3] == 'missing'], rows
	for row in rows:
		if row[4]:
			assert resolves(row[4]), row[4]
