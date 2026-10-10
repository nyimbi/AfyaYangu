"""Behavioural tests for afya.community (§10.4 COM-005, §11.4 COM-101..104)."""
import pytest

from afya.community.service import CommunityService
from afya.community.views import (
	ISSUE_ROUTING, CaseReport, CaseStatus, CommunityIssue, ContactEntry, ContactList, IssueKind,
	IssueStatus, MisinfoSubmission, PeerAlert,
)


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
		'headline': 'Boil drinking water in Budalangi',
		'body': 'Cholera cases confirmed nearby. Boil or treat all drinking water for the next 14 days.',
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
		await svc.send_peer_alert(_alert(body='Everyone will die unless you act now.'))
	with pytest.raises(AssertionError):
		await svc.send_peer_alert(_alert('PA-2', headline='Panic: outbreak spreads'))
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
	svc = CommunityService()
	contacts = ContactList(
		subject_ref='s2',
		entries=[ContactEntry(description='Pastor', setting='worship')],
		share_consent=True,
	)
	summary = await svc.save_contacts(contacts)
	assert summary.shared is True
	assert summary.total == 1
	assert 'Shared with the health team.' in summary.message


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
		))
	rising = svc.clusters()[0]
	assert rising.velocity == 'rising'
	assert rising.status == 'correction_published'

	for i in range(24, 25):
		await svc.flag_misinfo(MisinfoSubmission(
			submission_id=f'MIS-ABCD{i:04d}', claim='Drinking salt water cures Ebola', county='Busia',
			medium='voice', topic='cure_claim',
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
