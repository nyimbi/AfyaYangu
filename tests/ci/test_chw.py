"""Behavioural tests for the CHW trust layer (spec §5 CHAN-005, §11.4 COM-101)."""
import pytest

from afya.chw.service import ChwService
from afya.chw.views import JOB_AIDS, TRAINING_MODULES, ActivityLogEntry, ChwCase, ChwProfile


def _profile(chw_ref: str, *, registry_verified: bool = True, provisioned_by: str = 'County') -> ChwProfile:
	return ChwProfile(
		chw_ref=chw_ref, name='Amina Wanjiru', county='Kilifi', community='Gede',
		registry_verified=registry_verified, provisioned_by=provisioned_by,
	)


def _case(report_id: str, *, status: str = 'reported') -> ChwCase:
	return ChwCase(
		report_id=report_id, status=status, suspected_disease='cholera',
		reported_iso='2026-10-05T09:00:00Z', surveillance_officer='SO-7',
		ppe_reminder_due=True, next_action='collect stool sample',
	)


async def test_provision_refused_without_registry_verification() -> None:
	"""Trust layer: an unverified person cannot self-enrol as a health worker."""
	svc = ChwService()
	with pytest.raises(AssertionError, match='national registry'):
		await svc.provision(_profile('CHW-1', registry_verified=False))
	assert svc._chws == {}, 'a refused provision stores nothing'


async def test_provision_refused_when_not_provisioned_by_county_or_moh() -> None:
	svc = ChwService()
	with pytest.raises(AssertionError, match='provisioned by a county health team'):
		await svc.provision(_profile('CHW-2', provisioned_by='Self'))
	assert svc._chws == {}


async def test_provision_accepted_by_county_and_moh() -> None:
	svc = ChwService()
	county = await svc.provision(_profile('CHW-3', provisioned_by='County'))
	moh = await svc.provision(_profile('CHW-4', provisioned_by='MoH'))
	assert county.chw_ref == 'CHW-3' and county.provisioned_by == 'County'
	assert moh.chw_ref == 'CHW-4' and moh.provisioned_by == 'MoH'
	assert svc.profile('CHW-3').county == 'Kilifi'


def test_profile_refuses_unknown_worker() -> None:
	with pytest.raises(AssertionError, match='unknown or unprovisioned CHW'):
		ChwService().profile('CHW-ghost')


async def test_unknown_worker_cannot_be_assigned_a_case() -> None:
	svc = ChwService()
	with pytest.raises(AssertionError, match='unknown or unprovisioned CHW'):
		await svc.assign_case('CHW-ghost', _case('R-1'))
	assert svc.cases('CHW-ghost') == []


async def test_unknown_worker_cannot_log_activity() -> None:
	svc = ChwService()
	entry = ActivityLogEntry(
		chw_ref='CHW-ghost', at_iso='2026-10-05T10:00:00Z', activity='report', community='Gede',
	)
	with pytest.raises(AssertionError, match='unknown or unprovisioned CHW'):
		await svc.log_activity(entry)
	assert svc._activity == []


async def test_case_load_counts_open_cases_only() -> None:
	svc = ChwService()
	await svc.provision(_profile('CHW-5'))
	await svc.assign_case('CHW-5', _case('R-1', status='reported'))
	await svc.assign_case('CHW-5', _case('R-2', status='investigated'))
	await svc.assign_case('CHW-5', _case('R-3', status='closed'))

	assert svc.case_load('CHW-5') == 2
	assert len(svc.cases('CHW-5')) == 3, 'closed cases remain in the record'

	# closing an open case reduces the load
	svc.cases('CHW-5')[0].status = 'closed'
	assert svc.case_load('CHW-5') == 1
	assert svc.case_load('CHW-nobody') == 0


def test_job_aid_returned_for_known_topic_and_refused_for_unknown() -> None:
	svc = ChwService()
	for topic in JOB_AIDS:
		aid = svc.job_aid(topic)
		assert aid == JOB_AIDS[topic]
		assert aid.strip(), f'{topic} job aid is empty'
	with pytest.raises(AssertionError, match='no job aid for'):
		svc.job_aid('ebola_airborne_protocol')


def test_ppe_reminder_is_the_donning_aid() -> None:
	assert ChwService.ppe_reminder() == JOB_AIDS['ppe_donning']


def test_training_covers_required_modules() -> None:
	modules = ChwService().training()
	assert [m['module'] for m in modules] == [m['module'] for m in TRAINING_MODULES]
	required = {m['module'] for m in modules if m['required']}
	assert required == {'orientation', 'case_report_form', 'supervised_first_three_reports'}


async def test_activity_summary_counts_by_type_and_changes_supervision_note() -> None:
	svc = ChwService()
	await svc.provision(_profile('CHW-6'))
	await svc.provision(_profile('CHW-7'))
	for activity in ('report', 'report', 'report', 'followup', 'followup'):
		await svc.log_activity(ActivityLogEntry(
			chw_ref='CHW-6', at_iso='2026-10-06T08:00:00Z', activity=activity, community='Gede',
		))
	await svc.log_activity(ActivityLogEntry(
		chw_ref='CHW-7', at_iso='2026-10-06T08:00:00Z', activity='training', community='Gede',
	))

	light = svc.activity_summary('CHW-6', '2026-10')
	assert light.by_activity == {'report': 3, 'followup': 2}
	assert light.total == 5
	assert 'Light activity logged' in light.supervision_note

	# a different CHW's entries are not counted
	other = svc.activity_summary('CHW-7', '2026-10')
	assert other.total == 1 and other.by_activity == {'training': 1}

	for i in range(5):
		await svc.log_activity(ActivityLogEntry(
			chw_ref='CHW-6', at_iso='2026-10-07T08:00:00Z', activity='referral', community='Gede',
		))
	good = svc.activity_summary('CHW-6', '2026-10')
	assert good.total == 10
	assert good.by_activity == {'report': 3, 'followup': 2, 'referral': 5}
	assert 'Good coverage this period' in good.supervision_note
	assert good.supervision_note != light.supervision_note
