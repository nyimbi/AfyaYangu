"""Behavioural tests for afya.community (§10.4 COM-005, §11.4 COM-101..104)."""
import pytest

from afya.community.service import CommunityService
from afya.community.views import (
	ISSUE_ROUTING, CaseReport, CaseStatus, CommunityIssue, ContactEntry, ContactList, IssueKind,
	IssueStatus, MisinfoSubmission, PeerAlert,
)
from afya.crypto.service import CryptoService


def _crypto() -> CryptoService:
	"""A deployment holding both §SEC-003 keys. The application layer is the one a contact list
	needs, and a service built with the at-rest key alone refuses to share rather than sending
	under the key an operator holds."""
	return CryptoService(at_rest_key=b'a' * 32, app_layer_key=b'b' * 32)


def _issue(kind: IssueKind, issue_id: str = 'CIS-ABCD1234') -> CommunityIssue:
	return CommunityIssue(issue_id=issue_id, kind=kind, county='Busia', description='Reported by a community member')


async def test_issue_routed_to_correct_county_authority() -> None:
	svc = CommunityService()
	water = await svc.report_issue(_issue(IssueKind.broken_water_point, 'CIS-AAAA1111'))
	assert water.routed_to == 'County Water Services'
	assert water.status is IssueStatus.routed
	sewage = await svc.report_issue(_issue(IssueKind.open_sewage, 'CIS-BBBB2222'))
	assert sewage.routed_to == 'County Public Health Office'
	animal = await svc.report_issue(_issue(IssueKind.dead_animal, 'CIS-CCCC3333'))
	assert animal.routed_to == 'County Veterinary Services'
	fake = await svc.report_issue(_issue(IssueKind.counterfeit_medicine, 'CIS-DDDD4444'))
	assert fake.routed_to == 'Pharmacy and Poisons Board'
	stockout = await svc.report_issue(_issue(IssueKind.facility_stockout, 'CIS-EEEE5555'))
	assert stockout.routed_to == 'County Health Management Team'


def test_every_issue_kind_has_a_route() -> None:
	assert set(ISSUE_ROUTING) == set(IssueKind)


async def test_issue_status_tracks_resolution() -> None:
	svc = CommunityService()
	await svc.report_issue(_issue(IssueKind.illegal_dumping))
	assert svc.issue_status('CIS-ABCD1234') is IssueStatus.routed
	assert await svc.resolve_issue('CIS-ABCD1234') is IssueStatus.resolved
	assert svc.issue_status('CIS-ABCD1234') is IssueStatus.resolved
	with pytest.raises(AssertionError):
		await svc.resolve_issue('CIS-UNKNOWN1')


def _case(report_id: str = 'CR-ABCD1234', **kw: object) -> CaseReport:
	base: dict[str, object] = {
		'report_id': report_id, 'chw_ref': 'chw-1', 'county': 'Busia', 'community': 'Budalangi',
		'symptoms': ['fever', 'vomiting'],
	}
	base.update(kw)
	return CaseReport.model_validate(base)


async def test_case_report_fires_automatic_officer_alert() -> None:
	svc = CommunityService()
	view = await svc.submit_case(_case())
	assert view.alerts_sent == 1
	assert view.surveillance_officer == 'Busia disease surveillance officer'
	assert view.status is CaseStatus.reported
	assert 'automatically' in view.next_step


async def test_case_photo_requires_geotag() -> None:
	svc = CommunityService()
	with pytest.raises(AssertionError):
		await svc.submit_case(_case(photo_sha256='a' * 64, geotagged=False))
	view = await svc.submit_case(_case('CR-EEEE5555', photo_sha256='a' * 64, geotagged=True))
	assert view.status is CaseStatus.reported


async def test_case_status_advances_forward_only() -> None:
	svc = CommunityService()
	await svc.submit_case(_case())
	assert await svc.advance_case('CR-ABCD1234', CaseStatus.investigated) is CaseStatus.investigated
	assert await svc.advance_case('CR-ABCD1234', CaseStatus.lab_result) is CaseStatus.lab_result
	assert svc.case_status('CR-ABCD1234') is CaseStatus.lab_result
	with pytest.raises(AssertionError):
		await svc.advance_case('CR-ABCD1234', CaseStatus.investigated)
	with pytest.raises(AssertionError):
		await svc.advance_case('CR-ABCD1234', CaseStatus.reported)
	assert svc.case_status('CR-ABCD1234') is CaseStatus.lab_result


def _alert(alert_id: str = 'PA-1', **kw: object) -> PeerAlert:
	base: dict[str, object] = {
		'alert_id': alert_id, 'county': 'Busia', 'lat': -0.5, 'lon': 34.0, 'radius_m': 1000,
		'headline': 'Cholera cases confirmed nearby',
		'location': 'Budalangi market',
		'issued_iso': '2026-10-10',
		'verified_by': 'County',
	}
	base.update(kw)
	return PeerAlert.model_validate(base)


async def test_peer_alert_requires_county_verification() -> None:
	svc = CommunityService()
	with pytest.raises(AssertionError):
		await svc.send_peer_alert(_alert(verified_by='NGO'))
	receipt = await svc.send_peer_alert(_alert(verified_by='PHEOC'))
	assert receipt.verification == 'verified by PHEOC'
	assert receipt.recipients == 12566  # pi * (1km)^2 * 4000, rounded down
	assert len(svc.peer_alerts('Busia')) == 1


async def test_peer_alert_rejects_alarmist_tone() -> None:
	svc = CommunityService()
	with pytest.raises(AssertionError):
		await svc.send_peer_alert(_alert(headline='Everyone will die unless you act now'))
	with pytest.raises(AssertionError):
		await svc.send_peer_alert(_alert('PA-2', headline='Panic: outbreak spreads'))
	# The location is the only free text left in the body once the sentence is the section's, so it
	# is the one place a stigmatising alert can still be planted — and the judge still reads it.
	with pytest.raises(AssertionError):
		await svc.send_peer_alert(_alert('PA-3', location='An Ebola victim was found at the market'))
	assert svc.peer_alerts('Busia') == []


async def test_contact_tracing_summary_counts_by_setting() -> None:
	svc = CommunityService()
	svc.add_contact('s1', ContactEntry(description='Spouse', setting='home'))
	svc.add_contact('s1', ContactEntry(description='Child', setting='home'))
	svc.add_contact('s1', ContactEntry(description='Desk mate', setting='work'))
	summary = svc.summary('s1')
	assert summary.by_setting == {'home': 2, 'work': 1}
	assert summary.total == 3
	assert summary.shared is False
	assert summary.progress_pct == 33.3  # 2 of 6 prompt categories covered
	assert 'Held on your phone' in summary.message


async def test_contact_list_shared_only_with_consent() -> None:
	"""Consent is the gate, and `shared` means a share actually left — not that the flag was set.

	This test used to assert `summary.shared is True` after `save_contacts` with
	`share_consent=True`, on a service that transmitted nothing. It passed for as long as the flag
	and the fact wore one name, which is the audit row's own finding: a person was told "Shared with
	the health team." while the list sat on the phone. The two are asserted separately here.
	"""
	svc = CommunityService(crypto=_crypto())
	contacts = ContactList(
		subject_ref='s2',
		entries=[ContactEntry(description='Pastor', setting='worship')],
		share_consent=True,
	)
	summary = await svc.save_contacts(contacts)
	# Consent given, nothing sent yet: the message offers the share rather than claiming it.
	assert summary.shared is False
	assert 'Ready to share' in summary.message
	assert summary.total == 1
	# A list saved *without* consent is refused, even though a key and a recipient are available.
	await svc.save_contacts(ContactList(
		subject_ref='s3',
		entries=[ContactEntry(description='Neighbour', setting='home')],
		share_consent=False,
	))
	with pytest.raises(AssertionError, match='explicit consent'):
		await svc.share_contacts('s3')
	# With consent, the share leaves and `shared` turns true.
	receipt = await svc.share_contacts('s2')
	assert receipt.entries == 1
	assert svc.summary('s2').shared is True
	assert 'Shared with the health team.' in svc.summary('s2').message


async def test_misinfo_cluster_velocity_thresholds() -> None:
	svc = CommunityService()
	for i in range(3):
		await svc.flag_misinfo(MisinfoSubmission(
			submission_id=f'MIS-ABCD{i:04d}', claim='Drinking salt water cures Ebola', county='Busia',
			medium='text', topic='cure_claim',
		))
	slow = svc.clusters()[0]
	assert slow.velocity == 'slow'
	assert slow.status == 'aggregating'
	assert slow.reports == 3

	for i in range(3, 24):
		await svc.flag_misinfo(MisinfoSubmission(
			submission_id=f'MIS-ABCD{i:04d}', claim='Drinking salt water cures Ebola', county='Busia',
			medium='whatsapp_forward', topic='cure_claim',
			transcript='Drinking salt water cures Ebola',
		))
	rising = svc.clusters()[0]
	assert rising.velocity == 'rising'
	assert rising.status == 'correction_published'

	for i in range(24, 25):
		await svc.flag_misinfo(MisinfoSubmission(
			submission_id=f'MIS-ABCD{i:04d}', claim='Drinking salt water cures Ebola', county='Busia',
			medium='voice', topic='cure_claim',
			transcript='Drinking salt water cures Ebola',
		))
	spiking = svc.clusters()[0]
	assert spiking.velocity == 'spiking'
	assert spiking.reports == 25


async def test_misinfo_unknown_topic_gets_default_correction() -> None:
	svc = CommunityService()
	await svc.flag_misinfo(MisinfoSubmission(
		submission_id='MIS-ABCD0001', claim='A rumour with no known topic', county='Busia', medium='text',
		topic='mystery_claim',
	))
	cluster = svc.clusters()[0]
	assert cluster.topic == 'mystery_claim'
	assert cluster.correction == svc.correction_for('unknown')
	assert cluster.correction is not None
	assert 'under verification' in cluster.correction


async def test_flagged_rumour_returns_its_own_topic_not_the_busiest() -> None:
	"""Regression: flagging a rumour must show the correction for that rumour. The cluster for the
	submitted topic is returned even when another topic has more reports."""
	svc = CommunityService()
	for i in range(5):
		await svc.flag_misinfo(MisinfoSubmission(
			submission_id=f'MIS-BETA{i:04d}', claim='Salt water cures everything', county='Busia',
			medium='text', topic='beta',
		))
	got = await svc.flag_misinfo(MisinfoSubmission(
		submission_id='MIS-ALPHA001', claim='A brand new rumour', county='Busia', medium='text', topic='alpha',
	))
	assert got.topic == 'alpha', 'must report the submitted topic, not the busiest one'
	assert got.reports == 1
	assert got.correction == svc.correction_for('alpha')


async def test_the_contacts_route_reads_the_typed_entries_the_form_sends() -> None:
	"""The catalogue draws one text box for `entries`, and both clients send a `list` as an array of
	strings. The route took `list[ContactEntry]` — an object list no client can build — so the
	control's own value was refused. The coercion is at the model, so the same request works whether
	the caller hand-builds objects or sends the strings a person typed.

	The comma split is asserted as its own step: the first version replaced only the first comma, so
	`Jane:market, the tailor:work` filed the tailor as part of Jane's setting. Two people in, two
	people out, each with the setting it named.
	"""
	import httpx
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		token = (await c.post('/auth/anonymous', json={'subject_ref': 'U-contacts'})).json()['token']
		h = {'authorization': f'Bearer {token}'}
		# The string a client produces from one text box, split on the commas the client splits on.
		typed = 'Jane:market, the tailor:work'
		res = await c.post('/community/contacts', headers=h, json={
			'subject_ref': 'U-contacts',
			'entries': [part.strip() for part in typed.split(',')],
			'share_consent': True,
		})
		assert res.status_code == 200, res.text
		body = res.json()
		assert body['total'] == 2, body
		assert body['by_setting'] == {'market': 1, 'work': 1}, body
		# And the object form a hand-built request sends is still accepted, so the coercion is a
		# widening rather than a replacement.
		obj = await c.post('/community/contacts', headers=h, json={
			'subject_ref': 'U-contacts',
			'entries': [{'description': 'Neighbour', 'setting': 'home'}],
		})
		assert obj.status_code == 200, obj.text
		assert obj.json()['by_setting'] == {'home': 1}, obj.text
		# And the same list as one unsplit string, which is what a hand-built request or a client
		# that does not split its own control sends. The comma split has to happen here, before the
		# `who:where` split, or the second person is swallowed into the first one's setting.
		bare = await c.post('/community/contacts', headers=h, json={
			'subject_ref': 'U-contacts',
			'entries': 'Jane:market, the tailor:work',
		})
		assert bare.status_code == 200, bare.text
		assert bare.json()['by_setting'] == {'market': 1, 'work': 1}, bare.text
