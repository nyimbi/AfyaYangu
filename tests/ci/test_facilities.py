import pytest

from afya.facilities.service import FacilityService, haversine_km
from afya.facilities.views import Booking, Facility, FacilityKind, NearestRequest


async def test_haversine_nairobi_machakos() -> None:
	d = haversine_km(-1.2833, 36.8167, -1.5167, 37.2667)
	assert 55 <= d <= 75


async def test_nearest_orders_and_filters() -> None:
	svc = FacilityService()
	await svc.upsert(Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed, county='Nairobi', lat=-1.3, lon=36.8))
	await svc.upsert(Facility(facility_id='F2', name='Kisumu ED', kind=FacilityKind.ed, county='Kisumu', lat=-0.1, lon=34.75))
	await svc.upsert(Facility(facility_id='F3', name='Kilimani Pharmacy', kind=FacilityKind.pharmacy, county='Nairobi', lat=-1.29, lon=36.78))
	ranked = svc.nearest(NearestRequest(lat=-1.29, lon=36.8, kind=FacilityKind.ed))
	ranked = svc.nearest(NearestRequest(lat=-1.29, lon=36.8, kind=FacilityKind.ed, limit=1))
	assert [p[0].facility_id for p in ranked] == ['F1']
	mixed = svc.nearest(NearestRequest(lat=-1.29, lon=36.8, limit=2))
	assert [p[0].facility_id for p in mixed] == ['F1', 'F3']


async def test_ed_status_requires_ed_kind() -> None:
	svc = FacilityService()
	await svc.upsert(Facility(facility_id='F1', name='Pharmacy', kind=FacilityKind.pharmacy, county='X', lat=-1, lon=36))
	with pytest.raises(AssertionError):
		svc.ed_status('F1')


async def test_mohf_ingest_skips_invalid_rows() -> None:
	svc = FacilityService()
	rows = [
		{'facility_id': 'F1', 'name': 'KNH', 'kind': 'ed', 'county': 'Nairobi', 'lat': -1.3, 'lon': 36.8},
		{'facility_id': 'F9', 'name': 'broken', 'kind': 'not_a_kind', 'county': 'X', 'lat': 0.0, 'lon': 36.0},
		{'name': 'missing id'},
	]
	assert await svc.ingest_mohf(rows) == 1
	assert len(svc.nearest(NearestRequest(lat=-1.29, lon=36.8, limit=5))) == 1


async def test_booking_queue_monotonic() -> None:
	svc = FacilityService()
	await svc.upsert(Facility(facility_id='F1', name='A', kind=FacilityKind.ed, county='X', lat=-1, lon=36))
	b1 = await svc.book('F1', '2026-10-08T10:00+03:00', 'BOOK-A1B2C3D4')
	b2 = await svc.book('F1', '2026-10-08T10:30+03:00', 'BOOK-B2C3D4E5')
	assert b2.queue_position == b1.queue_position + 1