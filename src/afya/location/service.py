"""Location & proximity services (spec §11.5 LOC-002..005, §8.6 LOC-001).

Design commitments carried in code, not policy:
  * LOC-002 stores encounter tokens, never identities, and declarations arrive through a proxy.
  * LOC-003 takes geohashes only — a coordinate cannot be passed in, so a leak is not representable.
  * LOC-004 check-ins are local unless the user flips `share_with_authority`.
  * LOC-005 pairs a pre-travel advisory with the same 21-day window as MON-009.
"""
from afya.location.views import (
	EBID_ROTATION_MINUTES, LOCATION_WINDOW_DAYS, BorderPost, CheckIn, CheckInPoint, CheckInReceipt,
	EncounterToken, EphemeralId, ExposureDeclaration, ExposureMatch, LocationHistory, LocationPoint,
	LocationReport, TravellerEnrolment, TravelerDeclaration,
)
from afya.logmixin import LogMixin

# Geofenced alert zones — county-configurable radii (§COM-102: 500 m, 1 km, 5 km).
ALLOWED_RADII_M: tuple[int, ...] = (500, 1000, 5000)


def _geohash_cell(geohash: str) -> str:
	"""Truncate to a coarse cell before any sharing (§SEC-004 structural generalisation)."""
	assert len(geohash) >= 5, 'geohash too precise to generalise'
	return geohash[:5]


class LocationService(LogMixin):
	def __init__(self) -> None:
		self._tokens: list[EncounterToken] = []
		self._declarations: list[ExposureDeclaration] = []
		self._histories: dict[str, LocationHistory] = {}
		self._points: dict[str, CheckInPoint] = {}
		self._checkins: list[CheckIn] = []
		self._borders: dict[str, BorderPost] = {}
		self._enrolled: dict[str, TravellerEnrolment] = {}
		assert self._tokens == [] and self._checkins == []

	# --- LOC-002 proximity ----------------------------------------------------------------

	@staticmethod
	def rotate_ebid(seed: str, now_ms: int) -> EphemeralId:
		"""EBID rotates every 15 minutes; the id is derived, never stored (§LOC-002)."""
		import hashlib
		slot = now_ms // (EBID_ROTATION_MINUTES * 60_000)
		ebid = hashlib.sha256(f'{seed}:{slot}'.encode()).hexdigest()[:32]
		rotated = slot * EBID_ROTATION_MINUTES * 60_000
		return EphemeralId(ebid=ebid, rotated_at_ms=rotated, rotates_every_minutes=EBID_ROTATION_MINUTES)

	async def log_encounter(self, token: EncounterToken) -> EncounterToken:
		# PET entropy is enforced by EncounterToken.pet (min_length=32) at validation time, which is
		# where a malformed token is actually stopped. Re-asserting it here would read as the
		# enforcement point while being unreachable, so this method asserts only what it owns.
		self._tokens.append(token)
		self._tokens = self._tokens[-200_000:]
		assert len(self._tokens) <= 200_000, 'token store bounded'
		return token

	async def declare_exposure(self, declaration: ExposureDeclaration) -> ExposureDeclaration:
		assert declaration.proxied, 'declarations must route through the trusted proxy'
		self._declarations.append(declaration)
		self._log_warn('exposure declared via proxy')
		return declaration

	def check_exposure(self, own_pets: list[str], window_days: int = LOCATION_WINDOW_DAYS, now_ms: int | None = None) -> ExposureMatch:
		assert window_days <= 28, 'proximity window capped at 28 days'
		declared = {d.pet for d in self._declarations}
		mine = set(own_pets)
		hits = [t for t in self._tokens if t.pet in declared and t.pet in mine]
		if now_ms is not None:
			cutoff = now_ms - window_days * 86_400_000
			hits = [t for t in hits if t.seen_at_ms >= cutoff]
		matched = bool(hits)
		return ExposureMatch(
			matched=matched, encounters=len(hits), window_days=window_days,
			message=(
				'You were near someone who has since been confirmed. Follow the exposure guidance on your screen.'
				if matched else 'No matching encounters in your window.'
			),
		)

	# --- LOC-003 location history ---------------------------------------------------------

	def enable_history(self, subject_ref: str, window_days: int = LOCATION_WINDOW_DAYS) -> LocationHistory:
		assert window_days <= 28, '21-day rolling window, 28 max'
		history = LocationHistory(subject_ref=subject_ref, consent_granted=True, window_days=window_days)
		self._histories[subject_ref] = history
		self._log_info('location history enabled with consent', sub=subject_ref, days=window_days)
		return history

	def log_location(self, subject_ref: str, point: LocationPoint) -> int:
		history = self._histories.get(subject_ref)
		assert history is not None and history.consent_granted, 'location history requires explicit consent'
		history.points.append(point)
		history.points = history.points[-5000:]
		return len(history.points)

	def build_report(self, subject_ref: str, share: bool = False) -> LocationReport:
		history = self._histories.get(subject_ref)
		assert history is not None, 'no history on file'
		places = sorted({p.place_label or _geohash_cell(p.geohash) for p in history.points})
		report = LocationReport(
			subject_ref=subject_ref, points=len(history.points), places=places,
			window_days=history.window_days,
			shared_with='county health team (geohashed)' if share else None,
			message=(
				'Report generated and shared as coarse locations only.'
				if share else 'Report generated on your phone. Nothing has been sent.'
			),
		)
		if share:
			self._log_info('location report shared', sub=subject_ref, points=len(history.points))
		return report

	def purge_history(self, subject_ref: str) -> int:
		history = self._histories.pop(subject_ref, None)
		return len(history.points) if history else 0

	# --- LOC-004 check-in -----------------------------------------------------------------

	async def register_point(self, point: CheckInPoint) -> CheckInPoint:
		self._points[point.token] = point
		return point

	GUIDANCE: dict[str, str] = {
		'border_post': 'Traveller screening applies here. Self-monitor for 21 days and report any fever to 719.',
		'health_facility': 'You are checked in at a health facility. Show this screen at triage if asked.',
		'isolation_unit': 'Restricted area. Follow staff instructions on PPE and movement.',
		'vaccination_point': 'Vaccination point. Bring your card; doses are free.',
		'school': 'School screening point. Report fever before entering.',
		'workplace': 'Workplace check-in logged for follow-up scheduling.',
		'event': 'Gathering check-in logged. Watch for symptoms for 21 days.',
	}

	async def check_in(self, checkin: CheckIn) -> CheckInReceipt:
		point = self._points.get(checkin.point_token)
		assert point is not None, 'unknown check-in point'
		self._checkins.append(checkin)
		if checkin.share_with_authority:
			self._log_info('check-in shared with authority', point=point.point_id)
		return CheckInReceipt(
			checkin_id=checkin.checkin_id, point_label=point.label,
			guidance=self.GUIDANCE[point.kind], logged_locally=True, shared=checkin.share_with_authority,
		)

	def checkins_for(self, subject_ref: str) -> list[CheckIn]:
		return [c for c in self._checkins if c.subject_ref == subject_ref]

	def points(self) -> list[CheckInPoint]:
		return list(self._points.values())

	# --- LOC-005 border module ------------------------------------------------------------

	async def register_border(self, post: BorderPost) -> BorderPost:
		self._borders[post.post_id] = post
		return post

	def border_status(self, post_id: str) -> BorderPost:
		assert post_id in self._borders, 'unknown border post'
		return self._borders[post_id]

	def advisory(self, destination: str, origin_country: str) -> str:
		"""Pre-travel advisory (§INF-005 links here). Unverified specifics are flagged, not asserted."""
		return (
			f'Travel to {destination} from {origin_country}: check the current MoH/PHEOC advisory before you go. '
			'Screening may apply at the border. If you feel unwell after arrival, call 719 and say where you travelled. '
			'Health advisories change — confirm with official channels.'
		)

	async def self_declare(self, decl: TravelerDeclaration) -> TravellerEnrolment:
		assert decl.arrival_iso, 'arrival date required'
		enrolment = TravellerEnrolment(
			subject_ref=decl.subject_ref, monitoring_days=21, enrolled=True,
			report_schedule=[1, 3, 7, 14, 21],
			message=(
				'Declaration recorded. You are enrolled for 21 days of self-monitoring — '
				'we will ask how you feel on days 1, 3, 7, 14 and 21. Call 719 sooner if you develop fever.'
			),
		)
		self._enrolled[decl.subject_ref] = enrolment
		if decl.symptoms:
			self._log_warn('traveller declared symptoms on arrival', sub=decl.subject_ref)
		return enrolment
