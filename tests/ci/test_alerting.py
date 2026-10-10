"""Behavioural tests for afya.alerting (ALT-001..004).

The refusals are the point: an unverified item must not reach the feed, and a critical
category must have no toggle to flip rather than one that is quietly ignored.
"""
import pytest

from afya.alerting.service import AlertingService
from afya.alerting.views import (
	CRITICAL, TOGGLEABLE, ExposureAck, ExposureNotification, FeedItem,
)


def _item(**over: object) -> FeedItem:
	base: dict[str, object] = {
		'item_id': 'FI-1',
		'category': 'outbreak',
		'headline': 'Cholera cases rising in Kisumu',
		'body': 'Three new cases reported near the lake shore.',
		'source': 'MoH PHEOC',
		'verified': True,
		'published_iso': '2026-10-01T08:00:00Z',
		'county': 'Kisumu',
	}
	base.update(over)
	return FeedItem(**base)  # type: ignore[arg-type]


# --- ALT-001 community alert feed ---------------------------------------------------------

async def test_unverified_feed_item_is_refused() -> None:
	svc = AlertingService()
	with pytest.raises(AssertionError, match='unverified'):
		await svc.publish(_item(verified=False))
	assert svc.feed() == [], 'nothing may enter the feed on a refused publish'


async def test_publish_requires_source_attribution() -> None:
	svc = AlertingService()
	with pytest.raises(AssertionError, match='source'):
		await svc.publish(_item(source=''))


async def test_publish_accepts_verified_item_and_orders_newest_first() -> None:
	svc = AlertingService()
	older = _item(item_id='FI-old', published_iso='2026-09-01T00:00:00Z')
	newer = _item(item_id='FI-new', published_iso='2026-10-01T00:00:00Z')
	await svc.publish(older)
	await svc.publish(newer)
	assert [i.item_id for i in svc.feed()] == ['FI-new', 'FI-old']


async def test_feed_county_filter_includes_national_items() -> None:
	svc = AlertingService()
	await svc.publish(_item(item_id='FI-kis', county='Kisumu'))
	await svc.publish(_item(item_id='FI-nat', county=None))
	await svc.publish(_item(item_id='FI-nai', county='Nairobi'))
	assert {i.item_id for i in svc.feed(county='Kisumu')} == {'FI-kis', 'FI-nat'}


# --- ALT-003 personalised preferences -----------------------------------------------------

def test_critical_category_has_no_toggle_and_receipt_says_so() -> None:
	svc = AlertingService()
	assert 'exposure_notification' in CRITICAL
	receipt = svc.set_preference('U-1', 'exposure_notification', enabled=False)
	assert receipt.enabled is True, 'a critical alert cannot be switched off'
	assert receipt.critical is True
	assert 'cannot be switched off' in receipt.message
	assert 'exposure_notification' not in svc.preferences('U-1').enabled, 'no toggle exists to flip'


def test_immediate_danger_is_also_non_disableable() -> None:
	svc = AlertingService()
	receipt = svc.set_preference('U-1', 'immediate_danger', enabled=False)
	assert (receipt.enabled, receipt.critical) == (True, True)


def test_toggleable_category_honours_the_switch() -> None:
	svc = AlertingService()
	assert 'health_tips' in TOGGLEABLE
	receipt = svc.set_preference('U-1', 'health_tips', enabled=False)
	assert (receipt.enabled, receipt.critical) == (False, False)
	assert svc.preferences('U-1').enabled['health_tips'] is False
	assert receipt.message == 'Health Tips alerts off.'
	assert svc.should_deliver('U-1', 'health_tips') is False


def test_should_deliver_always_true_for_critical() -> None:
	svc = AlertingService()
	svc.set_preference('U-1', 'exposure_notification', enabled=False)
	assert svc.should_deliver('U-1', 'exposure_notification') is True
	assert svc.should_deliver('U-1', 'immediate_danger') is True


def test_unknown_category_is_refused() -> None:
	svc = AlertingService()
	with pytest.raises(AssertionError, match='unknown alert category'):
		svc.set_preference('U-1', 'not_a_real_category', enabled=False)


def test_new_subject_defaults_every_toggleable_on() -> None:
	svc = AlertingService()
	prefs = svc.preferences('U-new')
	assert set(prefs.enabled) == set(TOGGLEABLE)
	assert all(prefs.enabled.values())


# --- ALT-002 family safety check-in -------------------------------------------------------

async def test_family_checkin_moves_member_from_unknown_to_safe() -> None:
	svc = AlertingService()
	board = svc.link_family('FAM-1', ['M-1', 'M-2'])
	assert (board.members_safe, board.members_unknown) == ([], ['M-1', 'M-2'])

	board = await svc.check_in('M-1', 'FAM-1', '2026-10-10T06:00:00Z')
	assert board.members_safe == ['M-1']
	assert board.members_unknown == ['M-2']
	assert board.last_checkin_iso == '2026-10-10T06:00:00Z'
	assert board.board == '1 of 2 checked in safe.'

	board = await svc.check_in('M-2', 'FAM-1', '2026-10-10T06:05:00Z')
	assert (board.members_safe, board.members_unknown) == (['M-1', 'M-2'], [])
	assert board.board == 'Everyone in this group has checked in safe (2).'


async def test_checkin_refused_for_unknown_family_or_non_member() -> None:
	svc = AlertingService()
	svc.link_family('FAM-1', ['M-1'])
	with pytest.raises(AssertionError, match='unknown family group'):
		await svc.check_in('M-1', 'FAM-404', '2026-10-10T06:00:00Z')
	with pytest.raises(AssertionError, match='not a member'):
		await svc.check_in('M-9', 'FAM-1', '2026-10-10T06:00:00Z')


# --- ALT-004 exposure notification --------------------------------------------------------

async def test_exposure_notification_enrols_monitoring_and_offers_callback() -> None:
	svc = AlertingService()
	note = await svc.notify_exposure('U-1', case_ref='CASE-9')
	assert isinstance(note, ExposureNotification)
	assert note.enrols_monitoring is True
	assert note.callback_offered is True
	assert note.contact_window_days == 21
	assert note.delivery_channels == ['native', 'sms', 'whatsapp']
	assert note.acknowledged is False
	assert note.notification_id.startswith('EXP-')
	assert 'CASE-9' not in note.body, 'the notification never names the case'


async def test_acknowledge_marks_notification_and_records_callback() -> None:
	svc = AlertingService()
	note = await svc.notify_exposure('U-1')
	ack = ExposureAck(
		notification_id=note.notification_id, subject_ref='U-1',
		acknowledged_iso='2026-10-10T06:10:00Z', request_callback=True,
	)
	back = await svc.acknowledge(ack)
	assert back.acknowledged is True
	assert svc.exposure(note.notification_id).acknowledged is True


async def test_acknowledging_unknown_notification_is_refused() -> None:
	svc = AlertingService()
	ack = ExposureAck(notification_id='EXP-DOESNOTEXIST', subject_ref='U-1', acknowledged_iso='2026-10-10T06:10:00Z')
	with pytest.raises(AssertionError, match='unknown notification'):
		await svc.acknowledge(ack)
