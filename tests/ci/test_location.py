"""Behavioural tests for afya.location (LOC-002..005, LOC-001).

Privacy invariants under test, in order of blast radius:
  * a declaration that is not proxied is refused;
  * the ephemeral id is derived and never stored;
  * a shared location report cannot be turned back into a coordinate.
"""
import pytest

from afya.location.service import LocationService
from afya.location.views import (
	EBID_ROTATION_MINUTES, CheckIn, CheckInPoint, EncounterToken, ExposureDeclaration,
	LocationPoint, TravelerDeclaration,
)

_DAY_MS = 86_400_000
_SLOT_MS = EBID_ROTATION_MINUTES * 60_000


# --- LOC-002 BLE proximity ---------------------------------------------------------------

def test_ebid_is_derived_from_seed_and_slot() -> None:
	svc = LocationService()
	base = 1_000 * _SLOT_MS
	a = svc.rotate_ebid('seed-A', base)
	b = svc.rotate_ebid('seed-A', base + _SLOT_MS - 1)  # same 15-minute slot
	assert a.ebid == b.ebid, 'same seed + same slot must derive the same id'
	assert a.rotated_at_ms == b.rotated_at_ms == base


def test_ebid_rotates_on_the_next_slot_and_per_seed() -> None:
	svc = LocationService()
	base = 1_000 * _SLOT_MS
	this_slot = svc.rotate_ebid('seed-A', base)
	next_slot = svc.rotate_ebid('seed-A', base + _SLOT_MS)
	other_seed = svc.rotate_ebid('seed-B', base)
	assert this_slot.ebid != next_slot.ebid, 'a later slot must give a different id'
	assert this_slot.ebid != other_seed.ebid
	assert next_slot.rotated_at_ms == base + _SLOT_MS
	assert this_slot.rotates_every_minutes == 15
	assert len(this_slot.ebid) == 32 and all(c in '0123456789abcdef' for c in this_slot.ebid)


def test_ebid_is_never_stored_on_the_service() -> None:
	svc = LocationService()
	ebid = svc.rotate_ebid('seed-A', 1_000 * _SLOT_MS).ebid
	stored = ' '.join(repr(v) for v in vars(svc).values())
	assert ebid not in stored, 'the ephemeral id must not persist anywhere on the service'


async def _arm(svc: LocationService, pet: str, seen_at_ms: int) -> None:
	await svc.log_encounter(EncounterToken(pet=pet, seen_at_ms=seen_at_ms, rssi_dbm=-70, county='Kisumu'))
	await svc.declare_exposure(ExposureDeclaration(declaration_id='D-1', pet=pet, declared_at_ms=seen_at_ms))


async def test_proximity_match_fires_inside_the_window() -> None:
	svc = LocationService()
	pet = 'a' * 40
	now = 1_000 * _DAY_MS
	await _arm(svc, pet, now - 20 * _DAY_MS)
	match = svc.check_exposure(own_pets=[pet], window_days=21, now_ms=now)
	assert match.matched is True
	assert match.encounters == 1
	assert match.window_days == 21


async def test_proximity_match_does_not_fire_outside_the_window() -> None:
	svc = LocationService()
	pet = 'a' * 40
	now = 1_000 * _DAY_MS
	await _arm(svc, pet, now - 22 * _DAY_MS)
	match = svc.check_exposure(own_pets=[pet], window_days=21, now_ms=now)
	assert match.matched is False
	assert match.encounters == 0
	assert match.message == 'No matching encounters in your window.'


async def test_proximity_match_needs_both_declared_and_own_pet() -> None:
	svc = LocationService()
	pet = 'a' * 40
	now = 1_000 * _DAY_MS
	await _arm(svc, pet, now - _DAY_MS)
	assert svc.check_exposure(own_pets=['b' * 40], now_ms=now).matched is False
	assert svc.check_exposure(own_pets=[pet], now_ms=now).matched is True


def test_window_beyond_28_days_is_refused() -> None:
	svc = LocationService()
	with pytest.raises(AssertionError, match='28 days'):
		svc.check_exposure(own_pets=[], window_days=29)


async def test_exposure_declaration_must_be_proxied() -> None:
	svc = LocationService()
	direct = ExposureDeclaration(declaration_id='D-x', pet='c' * 40, declared_at_ms=0, proxied=False)
	with pytest.raises(AssertionError, match='trusted proxy'):
		await svc.declare_exposure(direct)


async def test_encounter_token_needs_minimum_entropy() -> None:
	"""The PET entropy floor is enforced by the model, so a weak token is not constructible."""
	from pydantic import ValidationError
	with pytest.raises(ValidationError, match='at least 32 characters'):
		EncounterToken(pet='short', seen_at_ms=0, rssi_dbm=-70, county='Kisumu')

	svc = LocationService()
	ok = EncounterToken(pet='a' * 32, seen_at_ms=0, rssi_dbm=-70, county='Kisumu')
	assert (await svc.log_encounter(ok)).pet == 'a' * 32


# --- LOC-003 location history ------------------------------------------------------------

def test_location_history_requires_consent() -> None:
	svc = LocationService()
	with pytest.raises(AssertionError, match='consent'):
		svc.log_location('U-1', LocationPoint(geohash='kzcvx1234', at_iso='2026-10-01T00:00:00Z'))


def test_report_truncates_geohash_to_a_five_character_cell() -> None:
	svc = LocationService()
	svc.enable_history('U-1')
	svc.log_location('U-1', LocationPoint(geohash='kzcvx1234', at_iso='2026-10-01T00:00:00Z'))
	report = svc.build_report('U-1', share=True)
	assert report.places == ['kzcvx'], 'only the 5-character cell may be shared'
	assert all(len(p) == 5 for p in report.places)
	assert report.shared_with == 'county health team (geohashed)'
	assert report.points == 1


def test_report_prefers_place_label_over_geohash() -> None:
	svc = LocationService()
	svc.enable_history('U-1')
	svc.log_location('U-1', LocationPoint(geohash='kzcvx1234', at_iso='2026-10-01T00:00:00Z', place_label='Kisumu CBD'))
	report = svc.build_report('U-1')
	assert report.places == ['Kisumu CBD']
	assert report.shared_with is None
	assert report.message == 'Report generated on your phone. Nothing has been sent.'


def test_purge_history_clears_the_diary() -> None:
	svc = LocationService()
	svc.enable_history('U-1')
	svc.log_location('U-1', LocationPoint(geohash='kzcvx1234', at_iso='2026-10-01T00:00:00Z'))
	svc.log_location('U-1', LocationPoint(geohash='kzcvx5678', at_iso='2026-10-02T00:00:00Z'))
	assert svc.purge_history('U-1') == 2
	with pytest.raises(AssertionError, match='consent'):
		svc.log_location('U-1', LocationPoint(geohash='kzcvx9999', at_iso='2026-10-03T00:00:00Z'))
	with pytest.raises(AssertionError, match='no history'):
		svc.build_report('U-1')


def test_purge_unknown_subject_returns_zero() -> None:
	assert LocationService().purge_history('U-nobody') == 0


# --- LOC-004 QR / NFC check-in -----------------------------------------------------------

async def test_checkin_guidance_differs_per_point_kind() -> None:
	svc = LocationService()
	await svc.register_point(CheckInPoint(point_id='P-border', kind='border_post', label='Busia', county='Busia', token='BORDER1'))
	await svc.register_point(CheckInPoint(point_id='P-school', kind='school', label='Kisumu Primary', county='Kisumu', token='SCHOOL1'))

	border = await svc.check_in(CheckIn(checkin_id='CHK-BORDER01', point_token='BORDER1', subject_ref='U-1', method='qr', at_iso='2026-10-01T00:00:00Z'))
	school = await svc.check_in(CheckIn(checkin_id='CHK-SCHOOL01', point_token='SCHOOL1', subject_ref='U-1', method='nfc', at_iso='2026-10-01T00:00:00Z'))

	assert border.guidance == LocationService.GUIDANCE['border_post']
	assert school.guidance == LocationService.GUIDANCE['school']
	assert border.guidance != school.guidance
	assert border.logged_locally is True
	assert border.shared is False
	assert school.shared is False


async def test_checkin_shares_only_when_the_user_asks() -> None:
	svc = LocationService()
	await svc.register_point(CheckInPoint(point_id='P-1', kind='health_facility', label='Clinic', county='Kisumu', token='CLINIC1'))
	receipt = await svc.check_in(CheckIn(checkin_id='CHK-CLINIC01', point_token='CLINIC1', subject_ref='U-1', method='manual', at_iso='2026-10-01T00:00:00Z', share_with_authority=True))
	assert receipt.shared is True
	assert len(svc.checkins_for('U-1')) == 1


async def test_checkin_at_unknown_point_is_refused() -> None:
	svc = LocationService()
	with pytest.raises(AssertionError, match='unknown check-in point'):
		await svc.check_in(CheckIn(checkin_id='CHK-NOWHERE1', point_token='NOPOINT1', subject_ref='U-1', method='qr', at_iso='2026-10-01T00:00:00Z'))


# --- LOC-005 border and point-of-entry ---------------------------------------------------

async def test_self_declaration_returns_the_1_3_7_14_21_schedule() -> None:
	svc = LocationService()
	decl = TravelerDeclaration(declaration_id='TD-ABCDEFGH', subject_ref='U-1', destination='Nairobi', arrival_iso='2026-10-01T00:00:00Z', origin_country='UG')
	enrolment = await svc.self_declare(decl)
	assert enrolment.enrolled is True
	assert enrolment.monitoring_days == 21
	assert enrolment.report_schedule == [1, 3, 7, 14, 21]
	assert 'days 1, 3, 7, 14 and 21' in enrolment.message


async def test_self_declaration_requires_arrival_date() -> None:
	svc = LocationService()
	decl = TravelerDeclaration(declaration_id='TD-ABCDEFGH', subject_ref='U-1', destination='Nairobi', arrival_iso='', origin_country='UG')
	with pytest.raises(AssertionError, match='arrival date'):
		await svc.self_declare(decl)


async def test_advisory_names_the_destination_and_origin() -> None:
	svc = LocationService()
	text = svc.advisory('Kampala', 'Kenya')
	assert 'Kampala' in text and 'Kenya' in text
	assert '719' in text
