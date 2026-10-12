"""Facility service — nearest finder, ED status, county cache, booking queue."""
import math
from typing import Any

from afya.facilities.views import (
	Booking, CostBand, Facility, FacilityKind, FacilityLevel, FacilityReport, NearestRequest,
	OfflineFacility,
)
from afya.logmixin import LogMixin

# §FND-001's "Recent user reports" feed is shown on a public screen, so it is capped rather than
# unbounded — one facility cannot grow a feed nobody can read.
_MAX_REPORTS = 20
# §FND-001's own radius for the offline bundle: "caches facilities within 50 km of the user's home
# area".
_OFFLINE_RADIUS_KM = 50.0

# §FND-001's ladder, ordered low to high. A referral question ("nearest facility *above* a health
# centre") is a comparison on this, and the enum's declaration order is the ladder the section
# prints. Declared here rather than derived from `list(FacilityLevel)` so a member added to the
# enum without a rung fails the assert below instead of silently sorting last.
_LEVEL_RANK: dict[FacilityLevel, int] = {
	FacilityLevel.dispensary: 1,
	FacilityLevel.health_centre: 2,
	FacilityLevel.sub_county_hospital: 3,
	FacilityLevel.county_referral: 4,
	FacilityLevel.national_referral: 5,
}
assert set(_LEVEL_RANK) == set(FacilityLevel), 'every level has a rung on §FND-001\'s ladder'

# §FND-001's cost bands, ordered. `free` is rank 0 so `max_cost_band=free` keeps only free ones.
_COST_RANK: dict[CostBand, int] = {
	CostBand.free: 0, CostBand.low: 1, CostBand.medium: 2, CostBand.high: 3,
}
assert set(_COST_RANK) == set(CostBand), 'every band has a rank'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	for v in (lat1, lon1, lat2, lon2):
		assert -90 <= v <= 90 or -180 <= v <= 180, 'coord out of planet bounds'
	r = 6371.0088
	p1, p2 = math.radians(lat1), math.radians(lat2)
	dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
	a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
	return 2 * r * math.asin(math.sqrt(a))


class FacilityService(LogMixin):
	def __init__(self) -> None:
		self._facilities: dict[str, Facility] = {}
		self._bookings: dict[str, Booking] = {}
		self._queue_counts: dict[str, int] = {}
		self._waits: dict[str, list[int]] = {}
		# §FND-001's "Recent user reports ('no malaria tests today,' 'long queue')". A list per
		# facility, newest first, because the section shows them as a feed and a single latest string
		# loses the second report a person needs to see.
		self._reports: dict[str, list[FacilityReport]] = {}
		assert self._facilities == {} and self._bookings == {}

	async def upsert(self, facility: Facility) -> Facility:
		assert facility.facility_id, 'facility_id required'
		self._facilities[facility.facility_id] = facility
		return facility

	def nearest(self, req: NearestRequest) -> list[tuple[Facility, float]]:
		pool = list(self._facilities.values())
		if req.kind is not None:
			pool = [f for f in pool if f.kind is req.kind]
		assert pool, 'no facilities registered'
		ranked = sorted(
			((f, haversine_km(req.lat, req.lon, f.lat, f.lon)) for f in pool),
			key=lambda pair: (pair[1], -pair[0].crowdload * 0 + pair[0].crowdload),
		)
		out = ranked[: req.limit]
		self._log_info('nearest lookup', kind=req.kind, hits=len(out))
		return out

	def find(self, req: NearestRequest) -> tuple[list[tuple[Facility, float]], list[str]]:
		"""§FND-001's finder and §FND-002's emergency screen, with their filters applied.

		The second return value is the finding, the same contract `PlacesService.find` keeps: a filter
		whose dimension *nothing in the pool published* is reported rather than applied, because
		filtering on it would turn "no county has filed a cost band" into "no facility is affordable".
		Only a dimension with at least one published value is applied, and the dimensions nothing
		answered are named so the screen can say "cost unknown" instead of showing a shorter list that
		reads as an answer.

		`accepts_sha` and `max_cost_band` keep a facility whose field is `None` for the reason §FND-001
		gives for the field being tri-state at all: a person checking whether their insurance works is
		misled by either default, so an unpublished row stays in the list and the screen shows it as
		unconfirmed.
		"""
		pool = list(self._facilities.values())
		if not pool:
			return [], []
		if req.kind is not None:
			pool = [f for f in pool if f.kind is req.kind]
		if req.query is not None:
			q = req.query.strip().lower()
			# "Search by area name or code": one box over the three things a person types — the
			# facility name, the county, or the MoHF id they read off a card.
			pool = [f for f in pool
				if q in f.name.lower() or q in f.county.lower() or q in f.facility_id.lower()]
		unanswered: list[str] = []
		if req.service is not None:
			if not any(f.services for f in pool):
				unanswered.append('service')
			else:
				pool = [f for f in pool if f.has_service(req.service)]
		if req.level is not None:
			if not any(f.level is not None for f in pool):
				unanswered.append('level')
			else:
				pool = [f for f in pool if f.level is req.level]
		if req.max_cost_band is not None:
			if not any(f.cost_band is not None for f in pool):
				unanswered.append('cost')
			else:
				ceiling = _COST_RANK[req.max_cost_band]
				pool = [f for f in pool
					if f.cost_band is None or _COST_RANK[f.cost_band] <= ceiling]
		if req.accepts_sha is not None:
			if not any(f.accepts_sha is not None for f in pool):
				unanswered.append('SHA acceptance')
			else:
				pool = [f for f in pool if f.accepts_sha is None or f.accepts_sha is req.accepts_sha]
		# §FND-002's four capacity questions. These *do* exclude on absence: a person looking for an
		# ICU bed needs a yes, and a facility whose bed count nobody filed cannot provide one.
		if req.min_icu_beds is not None:
			pool = [f for f in pool if f.icu_beds is not None and f.icu_beds >= req.min_icu_beds]
		if req.needs_ambulance:
			pool = [f for f in pool if f.ambulances is not None and f.ambulances > 0]
		if req.needs_trauma:
			pool = [f for f in pool if f.trauma_capable is True]
		if req.needs_isolation:
			pool = [f for f in pool if f.isolation_beds is not None and f.isolation_beds > 0]
		found = sorted(((f, haversine_km(req.lat, req.lon, f.lat, f.lon)) for f in pool),
			key=lambda pair: pair[1])
		if req.within_km is not None:
			# §FND-001's offline bundle: the facilities within the radius of the home area, which is
			# what the client caches. Applied last so it is a radius on the answer, not a filter.
			found = [pair for pair in found if pair[1] <= req.within_km]
		self._log_info('facility find', filters=unanswered, hits=min(len(found), req.limit))
		return found[: req.limit], unanswered

	async def report(self, facility_id: str, text: str, reporter_ref: str | None = None) -> FacilityReport:
		"""§FND-001's "Recent user reports" — the crowdsourced half of the finder.

		`reporter_ref` is optional and is a pseudonymous subject reference, never a name: the report
		appears on a public screen and §SEC-004's "minimum cell size of 10 for any aggregated
		reporting" is the same instinct at a smaller scale. The list is capped so one facility cannot
		grow an unbounded feed on a screen a person opens in an emergency.
		"""
		assert facility_id in self._facilities, f'unknown facility {facility_id}'
		report = FacilityReport(facility_id=facility_id, text=text.strip(), reporter_ref=reporter_ref)
		feed = self._reports.setdefault(facility_id, [])
		feed.insert(0, report)
		del feed[_MAX_REPORTS:]
		return report

	def recent_reports(self, facility_id: str, limit: int = 5) -> list[FacilityReport]:
		assert limit >= 1, 'limit must be positive'
		return list(self._reports.get(facility_id, []))[:limit]

	def offline_bundle(self, lat: float, lon: float, home_county: str | None = None) -> list[OfflineFacility]:
		"""§FND-001's "Offline mode: caches facilities within 50 km of the user's home area".

		The radius is the section's own 50 km, and the county is included as a second clause because
		the section's Offline note adds "Full offline bundle for user's home county available on first
		sync" — a person near a county border has facilities in their county farther than 50 km that
		the bundle still owes them.
		"""
		assert -5 <= lat <= 6 and 33 <= lon <= 43, 'home coordinate outside Kenya'
		rows: list[OfflineFacility] = []
		for f in self._facilities.values():
			km = haversine_km(lat, lon, f.lat, f.lon)
			if km <= _OFFLINE_RADIUS_KM or (home_county and f.county == home_county):
				rows.append(OfflineFacility(facility=f, km=round(km, 2)))
		rows.sort(key=lambda row: row.km)
		self._log_info('offline bundle', rows=len(rows))
		return rows

	@staticmethod
	def _kind(value: object) -> FacilityKind:
		return FacilityKind(str(value))

	@staticmethod
	def _num(value: object) -> float:
		assert isinstance(value, (int, float, str)), 'numeric facility coord required'
		return float(value)

	async def ingest_mohf(self, rows: list[dict[str, object]]) -> int:
		"""Import MoH Facility List rows (§18.5); skips invalid rows, returns accepted count."""
		accepted = 0
		for row in rows:
			try:
				fac = Facility(
					facility_id=str(row['facility_id']), name=str(row['name']),
					kind=self._kind(row['kind']), county=str(row['county']),
					lat=self._num(row['lat']), lon=self._num(row['lon']),
				)
				await self.upsert(fac)
				accepted += 1
			except (KeyError, ValueError, TypeError):
				self._log_warn('skipped invalid facility row')
		assert accepted <= len(rows), 'accepted cannot exceed offered'
		return accepted

	def nearest24h(self, req: NearestRequest) -> list[tuple[Facility, float]]:
		req.kind = None if req.kind is None else req.kind
		pool = [f for f in self._facilities.values() if f.hours24 and (req.kind is None or f.kind is req.kind)]
		assert pool, 'no 24h facilities registered'
		return sorted(((f, haversine_km(req.lat, req.lon, f.lat, f.lon)) for f in pool), key=lambda p: p[1])[: req.limit]

	async def report_wait(self, facility_id: str, minutes: int) -> int:
		assert 0 <= minutes <= 600, 'wait bounds'
		fac = self._facilities[facility_id]
		self._waits.setdefault(facility_id, []).append(minutes)
		fac.wait_minutes = round(sum(self._waits[facility_id]) / len(self._waits[facility_id]))
		return fac.wait_minutes

	def ed_status(self, facility_id: str) -> str:
		fac = self._facilities[facility_id]
		assert fac.kind is FacilityKind.ed, 'only ED facilities expose status'
		return fac.ed_status or 'unknown'

	async def book(self, facility_id: str, slot_iso: str, booking_id: str) -> Booking:
		fac = self._facilities[facility_id]
		pos = self._queue_counts.get(facility_id, 0) + 1
		self._queue_counts[facility_id] = pos
		booking = Booking(booking_id=booking_id, facility_id=facility_id, slot_iso=slot_iso, queue_position=pos)
		self._bookings[booking.booking_id] = booking
		assert booking.queue_position >= 1
		return booking

	def all_facilities(self) -> list[Facility]:
		return list(self._facilities.values())