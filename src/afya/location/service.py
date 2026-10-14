"""Location & proximity services (spec §11.5 LOC-002..005, §8.6 LOC-001).

Design commitments carried in code, not policy:
  * LOC-002 stores encounter tokens, never identities, and declarations arrive through a proxy.
  * LOC-003 takes geohashes only — a coordinate cannot be passed in, so a leak is not representable.
  * LOC-004 check-ins are local unless the user flips `share_with_authority`.
  * LOC-005 pairs a pre-travel advisory with the same 21-day window as MON-009.
"""
from datetime import datetime, timezone
from typing import Protocol

from afya.info.counties import COUNTIES
from afya.info.recency import DAY_MS, UNDATED_MS, instant_iso, iso_add_days, midnight_ms
# §INF-005's county half reads §INF-001's risk rows rather than keeping a second table. The import is
# a plain one and not a `TYPE_CHECKING`-guarded name, because the protocol below has to name the
# return type at class-creation time; it is safe because `afya.info.service` reaches nothing in
# `afya.location` (asserted in `test_inf005.py`), so the edge is one-way and always will be.
from afya.info.views import CountyRisk
# §LOC-001's entry/exit reads §11.1's zone registry rather than keeping its own list of zones — the
# copy that goes stale the first time a county health authority draws a new one. Plain import for the
# same class-creation reason as `CountyRisk` above, and safe for the same reason: `afya.surveillance`
# reaches nothing in `afya.location` (asserted in `test_loc001.py`), so the edge is one-way.
from afya.surveillance.views import Geofence
from afya.location.advisories import (
	ASSESSED_ON_ISO, BAND_LABELS, NOT_ASSESSED_CAVEAT, SOURCE_LABEL, STEP_SOURCES,
	TRAVELLER_RISK_NOTE, WHO_BORDER_NOTE, WHO_CONFIDENCE, WHO_RISK_TABLE, WHO_TRAVEL_ADVICE,
	CountryRow, POST_TRAVEL_STEPS, row_for,
)
from afya.location.views import (
	ALERT_ZONE_RADII_M, EBID_ROTATION_MINUTES, EXPOSURE_FOLLOWUP_DAYS, LOCATION_WINDOW_DAYS,
	WATCH_KINDS, BorderPost, CheckIn, CheckInAttendance, CheckInFollowUp, CheckInPoint,
	CheckInReceipt, EncounterToken, EphemeralId, ExposureDeclaration, ExposureMatch, ExposureWindow,
	FollowUpStep, LocationHistory, LocationPoint, LocationReport, PlaceAdvisory, PostArrivalReport,
	PostArrivalVerdict, PostTravelStep, RiskBand, TravellerEnrolment, TravelerDeclaration,
	TravelAdvisoryReport, ZoneEvent, ZoneWatch,
)
from afya.logmixin import LogMixin
from afya.monitoring.service import MONITORING_ALERT_SYMPTOMS
from afya.strings import (
	answerable, checkin, geofence_alert, traveller, zone_privacy_note, zone_transition,
)


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


class ZoneRead(Protocol):
	"""The one thing §LOC-001's entry/exit needs from §11.1's surveillance registry: the zones
	covering a point.

	`SurveillanceService.geofences_at` already answers exactly this and is the only place a zone is
	stored, so the entry/exit derivation reads it rather than keeping a second list of zones — the
	copy that goes stale the first time a county health authority draws a new one.
	"""
	def __call__(self, lat: float, lon: float) -> list[Geofence]: ...


class LocationService(LogMixin):
	def __init__(self, county_risk: CountyRiskRead | None = None,
	             monitoring: DiaryLink | None = None,
	             zones: ZoneRead | None = None) -> None:
		# §INF-005's county half is §INF-001's dashboard read, the traveller enrolment's diary is
		# §MON-009's, and §LOC-001's entry/exit is §11.1's zone registry. All three are collaborators
		# rather than imports, so this service owns no second copy of a risk table, a 21-day window
		# or a list of zones — and so a test can construct it with none of them.
		self._county_risk = county_risk
		self._monitoring = monitoring
		self._zones = zones
		self._tokens: list[EncounterToken] = []
		self._declarations: list[ExposureDeclaration] = []
		self._histories: dict[str, LocationHistory] = {}
		self._points: dict[str, CheckInPoint] = {}
		self._checkins: list[CheckIn] = []
		self._borders: dict[str, BorderPost] = {}
		self._enrolled: dict[str, TravellerEnrolment] = {}
		self._reports: list[PostArrivalReport] = []
		# §LOC-001's opt-in switch and the zones each person was last seen inside. Per-subject, and
		# never coordinates: the Privacy line is that location is processed on-device, so what is
		# stored is which zones were crossed and not where the person was when they crossed them.
		self._watches: dict[str, ZoneWatch] = {}
		# The fences this device has announced, by id, so that leaving one can name it. `inside` holds
		# ids because that is all a crossing is; an exit event has to say *which* place was left, and
		# a zone the person has walked out of is by definition not in the registry's answer for the
		# current point. What is kept is the zone the device itself showed, never the position it was
		# at when it showed it.
		self._seen_fences: dict[str, Geofence] = {}
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

	# The guidance is where a person is told what their check-in means, so it is where the watch is
	# stated to them. `follow_up` opens a window only for `WATCH_KINDS`, and these are one claim
	# rather than two: a point whose guidance promises 21 days must open one, and a point that opens
	# one must have said so. Asserted here because both facts are this class's, and because the
	# alternative — a kind added to `WATCH_KINDS` with a guidance line that mentions no window — is
	# the app starting a clock it never told the person about.
	assert {k for k, text in GUIDANCE.items() if '21 days' in text} == set(WATCH_KINDS), (
		'the kinds whose guidance names a 21-day watch and the kinds that open one are one set'
	)

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

	def follow_up(self, subject_ref: str, now_ms: int | None = None,
	              lang: str = 'en') -> CheckInFollowUp:
		"""§LOC-004's fourth Behaviour bullet: what the check-ins on file are *for*.

		Three derivations, because the bullet names three uses, and each was a join nothing made:

		* **Attendance.** `CheckIn.point_token` is stored and `CheckInPoint` is stored, and nothing
		  put them together — so "where was this person on the 3rd" was a question the record could
		  not answer. `check_in` joins them once, for the receipt, and the receipt is not kept.
		* **Follow-up scheduling.** The window opens on the check-in instant and the asks fall on
		  `EXPOSURE_FOLLOWUP_DAYS`, which is the same set §LOC-005's enrolment states and §COM-102's
		  peer alert carries. Nothing read any of them for a check-in.
		* **Exposure window.** `CheckIn.at_iso` is the timestamp and no code did arithmetic on it.

		**The window is opened only by a point that puts someone on watch.** A workplace check-in
		logs a visit and starts no 21-day clock, because §LOC-004's own guidance for it says the
		check-in is "logged for follow-up scheduling" and says nothing about symptoms — so a window
		derived from every check-in would be this code inventing a watch the app never told the
		person about, and the guidance and the schedule would disagree about the same scan.

		**A refusal is reported, not returned as an empty list.** A subject with no check-ins gets
		`attendance=None`, `window=None` and a `note` saying so: a clean empty record and a person
		nothing is being followed up for read identically on a screen, and only one of them is true.
		"""
		assert subject_ref, 'a subject is required to derive a follow-up'
		mine = self.checkins_for(subject_ref)
		now = now_ms if now_ms is not None else int(datetime.now(tz=timezone.utc).timestamp() * 1000)
		today = instant_iso(now)[:10]
		if not mine:
			return CheckInFollowUp(
				subject_ref=subject_ref, attendance=None, schedule=[], window=None,
				points_attended=0, checkins=0, next_due_iso=None, served_in=answerable(lang),
				note=checkin(lang, 'no_checkins'),
			)

		attendance = self._attendance(mine)
		# The most recent watch-opening check-in is the one the window runs from. A later scan at a
		# school does not close a border post's window, and an earlier one does not reopen it.
		watching = [c for c in mine if self._opens_watch(c)]
		window = self._window(max(watching, key=lambda c: c.at_iso), now, lang) if watching else None
		schedule = self._schedule(window, today, lang)
		next_due = next((s.due_iso for s in schedule if not s.past), None)
		assert len(attendance) == len(mine), 'every check-in is attended to, none invented'
		return CheckInFollowUp(
			subject_ref=subject_ref, attendance=attendance, schedule=schedule, window=window,
			points_attended=len({a.point_id for a in attendance}), checkins=len(mine),
			next_due_iso=next_due, served_in=answerable(lang),
			note=window.note if window is not None else checkin(lang, 'no_watch'),
		)

	def _opens_watch(self, checkin: CheckIn) -> bool:
		"""Whether this check-in's point is one §LOC-004's guidance already puts a window around."""
		point = self._points.get(checkin.point_token)
		return point is not None and point.kind in WATCH_KINDS

	def _attendance(self, mine: list[CheckIn]) -> list[CheckInAttendance]:
		"""Every check-in joined to its point, in time order, numbered per point."""
		seen: dict[str, int] = {}
		rows: list[CheckInAttendance] = []
		for c in sorted(mine, key=lambda c: (c.at_iso, c.checkin_id)):
			point = self._points.get(c.point_token)
			# `check_in` refuses an unknown token, so a stored check-in always resolves. Asserted
			# rather than skipped: a `continue` here would drop a visit from the attendance count
			# and report the person had attended fewer places than they had.
			assert point is not None, f'check-in {c.checkin_id} names an unregistered point'
			seen[point.point_id] = seen.get(point.point_id, 0) + 1
			rows.append(CheckInAttendance(
				checkin_id=c.checkin_id, point_id=point.point_id, point_label=point.label,
				kind=point.kind, county=point.county, at_iso=c.at_iso, day=c.at_iso[:10],
				visit_no=seen[point.point_id], method=c.method, shared=c.share_with_authority,
			))
		return rows

	def _window(self, opened: CheckIn, now_ms: int, lang: str) -> ExposureWindow:
		"""The 21-day window a watch-opening check-in opens, and how far into it the caller is."""
		point = self._points[opened.point_token]
		start_ms = midnight_ms(opened.at_iso)
		closes_ms = start_ms + LOCATION_WINDOW_DAYS * DAY_MS
		elapsed = max(0, (now_ms - start_ms) // DAY_MS)
		remaining = max(0, LOCATION_WINDOW_DAYS - elapsed)
		open_ = now_ms < closes_ms
		note = checkin(lang, 'window_open' if open_ else 'window_closed', place=point.label,
		               day=opened.at_iso[:10], remaining=remaining, closes=instant_iso(closes_ms)[:10])
		assert (remaining == 0) == (not open_), 'an open window with nothing left is not a state'
		return ExposureWindow(
			opened_iso=opened.at_iso, closes_iso=instant_iso(closes_ms)[:10],
			window_days=LOCATION_WINDOW_DAYS, elapsed_days=min(elapsed, LOCATION_WINDOW_DAYS),
			remaining_days=remaining, open=open_, note=note,
		)

	def _schedule(self, window: ExposureWindow | None, today: str,
	              lang: str) -> list[FollowUpStep]:
		"""The asks the window owes, each with the day it falls on and whether it has passed.

		No answer is read, because none is stored on this path: §LOC-005's traveller route is where a
		report is filed against a day. So a step is `due` when its day is today and `past` when the
		day is behind the clock — and neither of those is "missed", which would be this code
		reporting a prompt nobody sent as a prompt somebody ignored.
		"""
		if window is None:
			return []
		start = window.opened_iso[:10]
		steps: list[FollowUpStep] = []
		for day in EXPOSURE_FOLLOWUP_DAYS:
			due = iso_add_days(start, day - 1)
			steps.append(FollowUpStep(
				day=day, due_iso=due, due=due == today, past=due < today,
				question=checkin(lang, 'prompt', day=day),
			))
		assert len(steps) == len(EXPOSURE_FOLLOWUP_DAYS), 'one step per scheduled day'
		return steps

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

	# --- §8.6 LOC-001 zone entry and exit -------------------------------------------------------

	def set_zone_alerts(self, subject_ref: str, enabled: bool) -> ZoneWatch:
		"""The opt-in §LOC-001's Tier 1 behaviour names, stored rather than passed per request.

		"Static advisory zones ... with opt-in alerts" and "Fully disableable" are two statements about
		one switch, and a switch a caller sends with each request is not one: the client would be
		choosing on the person's behalf, which is the failure §MON-009's location consent names.
		Turning alerts off does not erase the zones already crossed — `inside` is kept so that turning
		them back on does not re-announce a zone the person is standing in.
		"""
		assert isinstance(subject_ref, str) and subject_ref, 'a subject is required'
		watch = self._watches.get(subject_ref) or ZoneWatch(subject_ref=subject_ref)
		watch = watch.model_copy(update={'alerts_enabled': enabled})
		self._watches[subject_ref] = watch
		self._log_info('zone alerts set', sub=subject_ref, enabled=enabled)
		return watch

	def zone_watch(self, subject_ref: str) -> ZoneWatch:
		"""The person's own switch and zone set, defaulted off. Absent means off, not unknown: an
		alerts-on default would alert every device in Kenya the first time a zone was drawn."""
		assert isinstance(subject_ref, str) and subject_ref, 'a subject is required'
		return self._watches.get(subject_ref) or ZoneWatch(subject_ref=subject_ref)

	def zones_at(self, lat: float, lon: float, subject_ref: str | None = None,
	             lang: str = 'en') -> list[ZoneEvent]:
		"""§LOC-001's entry and exit, derived from the position and the person's own switch.

		**A zone is an event, not a reading.** `inside` records which zones the last check found this
		person in, so a person walking across a 5 km zone is told once on the way in and once on the
		way out rather than on every GPS fix — which is how an alert becomes something people turn
		off, and a turned-off alert is the whole feature gone.

		`logged` is the Privacy line — "Only entry/exit events logged, and only with consent" — made
		checkable rather than asserted in a docstring: with alerts off, `inside` is not written and the
		events are served with `logged=False`. The **crossing is still reported**, because a person who
		turned alerts off still benefits from knowing they are in a zone; what they are not owed is a
		record of it. Serving nothing at all would make "fully disableable" mean "blind", and a person
		who disabled alerts to protect their privacy would lose the one warning the feature exists for.

		An anonymous caller is treated as a person who has never opted in: every zone is an entry,
		nothing is remembered, and `logged` is False. Nothing about the caller is recorded, which is
		§LOC-001's Privacy line and the reason this route is open.
		"""
		assert isinstance(lat, (int, float)) and isinstance(lon, (int, float)), 'a position is required'
		assert isinstance(lang, str) and lang, 'lang required'
		watch = self._watches.get(subject_ref) if subject_ref else None
		now_inside = self._fences_at(lat, lon)
		now_ids = {f.geofence_id for f in now_inside}
		for fence in now_inside:
			self._seen_fences[fence.geofence_id] = fence
		was_inside = set(watch.inside) if watch is not None else set()
		logging = bool(watch is not None and watch.alerts_enabled)
		events: list[ZoneEvent] = []
		for fence in now_inside:
			if fence.geofence_id not in was_inside:
				events.append(self._zone_event(fence, 'entry', logging, lang))
		for fence_id in sorted(was_inside - now_ids):
			left = self._seen_fences.get(fence_id)
			if left is not None:
				events.append(self._zone_event(left, 'exit', logging, lang))
		if logging and watch is not None:
			self._watches[watch.subject_ref] = watch.model_copy(
				update={'inside': sorted(f.geofence_id for f in now_inside)})
		return events

	@staticmethod
	def _zone_event(fence: Geofence, event: str, logging: bool, lang: str) -> ZoneEvent:
		# `county` is passed to both string calls, not just the alert: an exit names the place it left
		# too, and a zone whose label nobody set has only its county to be named by.
		# `lang` on the event is the language the sentence was actually composed in, not the one that
		# was asked for: §ACC-002's rule is that a caller answered in English *knows* it was English,
		# and an event carrying `luo` beside an English alert tells the person the opposite.
		alert = geofence_alert(lang, fence.place_label, fence.county)
		return ZoneEvent(
			event=event, geofence_id=fence.geofence_id, place_label=fence.place_label or '',
			county=fence.county, risk_type=fence.risk_type, alert_level=fence.alert_level,
			alert=alert, message=zone_transition(lang, event, fence.place_label, alert, fence.county),
			privacy_note=zone_privacy_note(lang, logging),
			logged=logging, lang=answerable(lang),
		)

	def _fences_at(self, lat: float, lon: float) -> list[Geofence]:
		"""§LOC-001's zones covering a point, read from the surveillance registry.

		A protocol and not `SurveillanceService`, so this module depends on one method rather than on
		a service — the same shape as `CountyRiskRead`. `[]` when no read is wired, because a
		deployment with no zone registry has no zones and that is not an error.
		"""
		return self._zones(lat, lon) if self._zones is not None else []
