"""Location & proximity services (spec §11.5 LOC-002..005, §8.6 LOC-001).

Design commitments carried in code, not policy:
  * LOC-002 stores encounter tokens, never identities, and declarations arrive through a proxy.
  * LOC-003 takes geohashes only — a coordinate cannot be passed in, so a leak is not representable.
  * LOC-004 check-ins are local unless the user flips `share_with_authority`.
  * LOC-005 pairs a pre-travel advisory with the same 21-day window as MON-009.
"""
from typing import Protocol

from afya.info.counties import COUNTIES
from afya.info.recency import UNDATED_MS, instant_iso
# §INF-005's county half reads §INF-001's risk rows rather than keeping a second table. The import is
# a plain one and not a `TYPE_CHECKING`-guarded name, because the protocol below has to name the
# return type at class-creation time; it is safe because `afya.info.service` reaches nothing in
# `afya.location` (asserted in `test_inf005.py`), so the edge is one-way and always will be.
from afya.info.views import CountyRisk
from afya.location.advisories import (
	ASSESSED_ON_ISO, BAND_LABELS, NOT_ASSESSED_CAVEAT, SOURCE_LABEL, STEP_SOURCES,
	TRAVELLER_RISK_NOTE, WHO_BORDER_NOTE, WHO_CONFIDENCE, WHO_RISK_TABLE, WHO_TRAVEL_ADVICE,
	CountryRow, POST_TRAVEL_STEPS, row_for,
)
from afya.location.views import (
	ALERT_ZONE_RADII_M, EBID_ROTATION_MINUTES, LOCATION_WINDOW_DAYS, BorderPost, CheckIn,
	CheckInPoint, CheckInReceipt, EncounterToken, EphemeralId, ExposureDeclaration, ExposureMatch,
	LocationHistory, LocationPoint, LocationReport, PlaceAdvisory, PostArrivalReport,
	PostArrivalVerdict, PostTravelStep, RiskBand, TravellerEnrolment, TravelerDeclaration,
	TravelAdvisoryReport,
)
from afya.logmixin import LogMixin
from afya.monitoring.service import MONITORING_ALERT_SYMPTOMS
from afya.strings import traveller


# Geofenced alert zones — county-configurable radii (§COM-102: 500 m, 1 km, 5 km). Re-exported
# rather than written again: the peer-alert model validates a radius against the same three, and a
# second tuple is a second answer to "which zones exist" the moment one of them moves.
ALLOWED_RADII_M: tuple[int, ...] = ALERT_ZONE_RADII_M
assert ALLOWED_RADII_M is ALERT_ZONE_RADII_M, 'the zone set is one tuple, not two that agree today'


def _geohash_cell(geohash: str) -> str:
	"""Truncate to a coarse cell before any sharing (§SEC-004 structural generalisation)."""
	assert len(geohash) >= 5, 'geohash too precise to generalise'
	return geohash[:5]


class DiaryLink(Protocol):
	"""The one thing §INF-005's fifth Feature needs from §MON-009: the enrolment.

	A protocol and not the class, because the coupling is one method. `MonitoringService.enrol` is
	synchronous and returns the household, which this caller has no use for — the traveller's diary
	is read through `/monitoring/contact/{ref}/diary`, so what this path owes the monitoring service
	is the enrolment and nothing else.
	"""
	def enrol(self, subject_ref: str, officer: str | None = None,
	          officer_number: str | None = None) -> object: ...


def _assessed_on_iso(updated_at_ms: int) -> str:
	"""A risk row's stamp as a date, or an empty string when nobody has assessed the county.

	`CountyRisk` answers an unknown county with a defaulted low-risk row carrying `UNDATED_MS`, and
	§6.2.3 is explicit that an undated assessment "destroys trust" — so the empty string is the
	honest reading of that row and a client renders it as "never assessed" rather than inferring a
	date from a default. Same distinction `instant_iso` refuses to make for a stamp of zero.
	"""
	return instant_iso(updated_at_ms) if updated_at_ms > UNDATED_MS else ''


class CountyRiskRead(Protocol):
	"""The one thing §INF-005's county half needs from §INF-001: a county's current risk row.

	A protocol and not `InfoService`, so this module depends on one method rather than on a service.
	"""
	def __call__(self, county: str) -> CountyRisk: ...


class LocationService(LogMixin):
	def __init__(self, county_risk: CountyRiskRead | None = None,
	             monitoring: DiaryLink | None = None) -> None:
		# §INF-005's county half is §INF-001's dashboard read, and the traveller enrolment's diary
		# is §MON-009's. Both are collaborators rather than imports, so this service owns no second
		# copy of a risk table or a 21-day window — and so a test can construct it with neither.
		self._county_risk = county_risk
		self._monitoring = monitoring
		self._tokens: list[EncounterToken] = []
		self._declarations: list[ExposureDeclaration] = []
		self._histories: dict[str, LocationHistory] = {}
		self._points: dict[str, CheckInPoint] = {}
		self._checkins: list[CheckIn] = []
		self._borders: dict[str, BorderPost] = {}
		self._enrolled: dict[str, TravellerEnrolment] = {}
		self._reports: list[PostArrivalReport] = []
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

	def place_advisory(self, place: str) -> PlaceAdvisory:
		"""One place, resolved to the authority's row for it — country, Kenyan county, or neither.

		The two halves read from different tables and are tried in that order, because a place name
		is the only thing the caller gives and "Busia" is both a Kenyan county and the Ugandan town
		the county is named for. The county table wins: a traveller asking from Kenya is asking about
		the Kenyan side, and the Ugandan side is reached by naming Uganda.
		"""
		assert isinstance(place, str) and place.strip(), 'a place is required'
		county = self._county_advisory(place)
		if county is not None:
			return county
		row = row_for(place)
		if row is None:
			return PlaceAdvisory(
				place=place, kind='unknown', band='unknown',
				stated=(
					f'No country row matches “{place}”. This may be a city, a spelling this table '
					'does not carry, or a country WHO has not named in this assessment.'
				),
				source=SOURCE_LABEL,
			)
		return self._country_advisory(row)

	@staticmethod
	def _country_advisory(row: CountryRow) -> PlaceAdvisory:
		"""WHO's row for a country, with the assessment's date and the band the source printed.

		`assessed_on_iso` is the v4 assessment's date and not today's: a risk band is a statement
		about a moment, and a payload that stamped it at serve time would present an August
		assessment as this morning's.
		"""
		return PlaceAdvisory(
			place=row.iso2, kind='country', name=row.name, band=row.band, stated=row.stated,
			assessed_on_iso=ASSESSED_ON_ISO, source=SOURCE_LABEL,
		)

	def _county_advisory(self, county: str) -> PlaceAdvisory | None:
		"""§INF-005's county half, read from §INF-001's dashboard rather than kept a second time.

		The row said the county half "has no carrier at all", and it had one the whole time — just
		not in this module. `CountyRisk` already holds a per-county band with a stamp and a source,
		and the dashboard route already serves it; a second table here would be the copy that goes
		stale the first time a county office publishes a risk level. `None` when the deployment has
		no risk source wired or the name is not a Kenyan county, so the caller falls through to the
		country table.
		"""
		if self._county_risk is None or county not in COUNTIES:
			return None
		risk = self._county_risk(county)
		return PlaceAdvisory(
			place=county, kind='county', name=county, band=risk.risk_level,
			stated=risk.bulletin, assessed_on_iso=_assessed_on_iso(risk.updated_at_ms),
			source=risk.source or 'County dashboard (§INF-001); no source line published',
		)

	def travel_advisory(self, destination: str, origin_country: str, lang: str = 'en') -> TravelAdvisoryReport:
		"""§INF-005's first and fourth Features: both places, the paragraph, and the five steps.

		**The paragraph is composed, not fixed.** It used to interpolate the caller's two arguments
		into one sentence that said the same thing about every pair, so a traveller asking about
		Kinshasa and one asking about Kampala were answered identically — the audit row's "the
		country half is a constant rather than a table". It now leads with the destination's own
		band and the source's own words for it, and says plainly when there is no row.

		The localised strings stay the frame — §LOC-005's "multi-language support for cross-border
		travellers" — because the band names are read by a person at a border and the fallback rule
		is `answerable`, not a second one. `not_assessed` is never rendered as reassurance: WHO's own
		caveat is served with it, the same shape as §MED-002's pregnancy caveat.
		"""
		assert isinstance(destination, str) and destination.strip(), 'a destination is required'
		assert isinstance(origin_country, str) and origin_country.strip(), 'an origin is required'
		dest = self.place_advisory(destination)
		origin = self.place_advisory(origin_country)
		return TravelAdvisoryReport(
			destination=dest,
			origin=origin,
			advisory=self.advisory(destination, origin_country, lang, dest),
			steps=[PostTravelStep(step_id=sid, instruction=text, source=STEP_SOURCES[src])
			       for sid, text, src in POST_TRAVEL_STEPS],
			risk_table=[RiskBand(label=label, band=band, printed=printed,
			                     confidence=dict(WHO_CONFIDENCE)[label])
			            for label, band, printed in WHO_RISK_TABLE],
			who_travel_advice=WHO_TRAVEL_ADVICE,
			border_note=WHO_BORDER_NOTE,
			traveller_risk_note=TRAVELLER_RISK_NOTE,
			not_assessed_caveat=NOT_ASSESSED_CAVEAT,
			lang=lang,
			source=SOURCE_LABEL,
		)

	def advisory(self, destination: str, origin_country: str, lang: str = 'en',
	             dest: PlaceAdvisory | None = None) -> str:
		"""Pre-travel advisory (§INF-005 links here), in the traveller's own language.

		§LOC-005's "multi-language support for cross-border travellers": the string was an English
		literal and the route took no language, so a traveller crossing at Busia who reads Kiswahili
		was served English on the one screen where getting it wrong means arriving unwell and not
		knowing to call 719. The strings live in `afya.strings` beside the triage tables so the
		fallback rule is `answerable` and not a second one that agrees today.

		`dest` is the resolved destination row, and passing it is what stops this being a constant:
		the caller that already resolved the place does not resolve it twice, and the sentence gains
		the band and the source's own words for the destination. Called without one — as
		`§INF-002`'s entry answer and the route's own default do — it resolves from the name.
		"""
		row = dest if dest is not None else self.place_advisory(destination)
		return traveller(lang, 'advisory', destination=destination, origin_country=origin_country,
		                 band=BAND_LABELS[row.band], stated=row.stated)

	async def self_declare(self, decl: TravelerDeclaration) -> TravellerEnrolment:
		"""Record the declaration and enrol the traveller for §MON-009's diary.

		§INF-005's fifth Feature is "21-day self-monitoring enrolment for travellers (**links to
		MON-009**)" and the link was a message: `TravellerEnrolment.message` told the traveller they
		would be asked on days 1, 3, 7, 14 and 21 while `MonitoringService` had never heard of them,
		so `/monitoring/contact/{ref}/diary` answered an empty list and no day was ever logged. The
		enrolment now reaches the monitoring service, and `diary_linked` says whether it did — a
		deployment with no monitoring service wired reports `False` rather than promising a diary.

		The officer is not passed. A traveller is not a contact of a named officer, and inventing one
		would put a stranger's name on a 21-day record; §MON-009's escalation falls back to 719,
		which is the line the advisory already names.
		"""
		assert decl.arrival_iso, 'arrival date required'
		linked = False
		if self._monitoring is not None:
			self._monitoring.enrol(decl.subject_ref)
			linked = True
		else:
			self._log_warn('traveller enrolled with no monitoring service wired',
			               sub=decl.subject_ref)
		enrolment = TravellerEnrolment(
			subject_ref=decl.subject_ref, monitoring_days=21, enrolled=True,
			report_schedule=[1, 3, 7, 14, 21],
			message=traveller(decl.lang, 'enrolled'), lang=decl.lang, diary_linked=linked,
		)
		self._enrolled[decl.subject_ref] = enrolment
		if decl.symptoms:
			self._log_warn('traveller declared symptoms on arrival', sub=decl.subject_ref)
		return enrolment

	def enrolment(self, subject_ref: str) -> TravellerEnrolment:
		"""The traveller's own enrolment, or a refusal. A report is filed against a window that has to
		exist: accepting one from a person who never declared would enrol them by the back door and
		give them a schedule nobody recorded."""
		enrolment = self._enrolled.get(subject_ref)
		assert enrolment is not None, f'{subject_ref} is not enrolled for post-arrival monitoring'
		return enrolment

	async def report_arrival_day(self, report: PostArrivalReport) -> PostArrivalVerdict:
		"""§LOC-005's "post-arrival symptom reporting": one day of the 21-day window, answered.

		The escalation rule is §MON-009's own — fever at 38.0, or a warning sign — and it is read off
		`MONITORING_ALERT_SYMPTOMS` rather than written again, because a traveller and a contact are
		the same person under the same criteria and two lists would drift apart on the day one of
		them was edited. The day must be one the schedule actually asks about: a report on day 5 is a
		day nobody will read, and accepting it would tell the traveller they had been checked on.
		"""
		enrolment = self.enrolment(report.subject_ref)
		assert report.day in enrolment.report_schedule, (
			f'day {report.day} is not one of the days this traveller is asked about '
			f'({enrolment.report_schedule})'
		)
		flagged = sorted(set(report.symptoms) & MONITORING_ALERT_SYMPTOMS)
		fever = report.temperature_c is not None and report.temperature_c >= 38.0
		escalate = fever or bool(flagged)
		remaining = max(0, enrolment.monitoring_days - report.day)
		if escalate:
			reason = 'fever' if fever else ', '.join(flagged)
			message = traveller(enrolment.lang, 'warned', day=report.day, reason=reason)
			self._log_warn('traveller reported warning signs', sub=report.subject_ref, day=report.day)
		else:
			message = traveller(enrolment.lang, 'well', day=report.day, remaining=remaining)
		self._reports.append(report)
		return PostArrivalVerdict(
			subject_ref=report.subject_ref, day=report.day, days_remaining=remaining,
			escalate=escalate, notify_border_health=escalate, message=message, lang=enrolment.lang,
		)

	def arrival_prompt(self, subject_ref: str, day: int) -> str:
		"""What the traveller is asked on a scheduled day, in their own language. The client has no
		other source for it: the enrolment names the schedule and this names the question."""
		enrolment = self.enrolment(subject_ref)
		assert day in enrolment.report_schedule, f'day {day} is not a scheduled report day'
		return traveller(enrolment.lang, 'prompt', day=day)

	def reports_for(self, subject_ref: str) -> list[PostArrivalReport]:
		return [r for r in self._reports if r.subject_ref == subject_ref]

	def border_status(self, post_id: str) -> BorderPost:
		assert post_id in self._borders, 'unknown border post'
		return self._borders[post_id]
