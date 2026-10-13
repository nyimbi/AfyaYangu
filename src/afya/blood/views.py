"""Blood donor matching — blood-group compatibility + 90-day eligibility + county radius (chronic shortages)."""
from datetime import date, timedelta

from afya.logmixin import LogMixin
from afya.places.views import PlaceKind, PlacesService
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

COMPATIBILITY: dict[str, tuple[str, ...]] = {  # recipient -> compatible donor groups
	'O-': ('O-',), 'O+': ('O-', 'O+'), 'A-': ('O-', 'A-'), 'A+': ('O-', 'O+', 'A-', 'A+'),
	'B-': ('O-', 'B-'), 'B+': ('O-', 'O+', 'B-', 'B+'), 'AB-': ('O-', 'A-', 'B-', 'AB-'),
	'AB+': ('O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+'),
}

# §REC-006's "Receive alerts when your blood type is urgently needed nearby": the request's urgency,
# as the reach it earns, in **county hops** over §INF-001's adjacency table. 0 is the requesting
# county alone, 1 adds the counties that touch it, 2 adds theirs. A *critical* request is the one
# where the units are needed before a donor can travel, so it is worth a donor two counties out; a
# routine need is met from the stock list. Three distinct values, three distinct behaviours — a
# table whose top two rows did the same thing would be a field that decides nothing.
URGENCY_REACH: dict[str, int] = {'routine': 0, 'urgent': 1, 'critical': 2}
# How far down the ranking a donor is reached, by urgency. Rank 0 is the donor whose own group is the
# one requested; ranks 1 and 2 are the groups that can give to it. A `routine` request notifies the
# exact group in its own county and nobody else, because a routine need is met from the stock list
# rather than by waking donors.
URGENCY_DEPTH: dict[str, int] = {'routine': 0, 'urgent': 2, 'critical': 2}

# The two kinds of site §REC-006's "Find donation centres" can mean, and they are not synonyms. The
# source is the OpenStreetMap wiki's own definitions, archived at `sources/osm-healthcare-tags/`:
# `healthcare=blood_donation` is "a facility where you can donate blood, plasma and/or platelets",
# `healthcare=blood_bank` is "a facility where blood gathered as a result of blood donation is stored
# and preserved for later use in blood transfusion". A person asking where to give blood is asking
# the first question, so the finder answers it by default and offers the second separately — a
# storage site is somewhere the blood already is, not somewhere a donor can go.
DONATION_SITE_KINDS: dict[str, str] = {
	'blood_donation': 'Where you can give blood',
	'blood_bank': 'Where donated blood is stored',
}


class Donor(BaseModel):
	model_config = MODEL_CONFIG
	donor_ref: str
	blood_group: str = Field(pattern=r'^(O-|O\+|A-|A\+|B-|B\+|AB-|AB\+)$')
	county: str
	last_donation_iso: str | None = None


class BloodRequest(BaseModel):
	model_config = MODEL_CONFIG
	request_id: str
	blood_group: str = Field(pattern=r'^(O-|O\+|A-|A\+|B-|B\+|AB-|AB\+)$')
	county: str
	urgency: str = Field(pattern=r'^(routine|urgent|critical)$')


class DonorMatch(BaseModel):
	model_config = MODEL_CONFIG
	donor_ref: str
	blood_group: str
	county: str
	eligible: bool
	compatible: bool


class DonorAlert(BaseModel):
	"""§REC-006's "Receive alerts when your blood type is urgently needed nearby", as the alert.

	The bullet's three words each decide a field. *Your blood type* is `donor_group` and
	`requested_group`, kept apart because they are usually different groups — a B+ patient can be
	given O- blood, and the donor is being told their group is *usable* rather than that it is the one
	written on the request. *Nearby* is `county` plus `distance_counties`, which is how the request
	reached them: 0 is their own county, 1 a county that touches it. *Urgently* is `urgency`, carried
	through from the request rather than recomputed, because the person reading the alert is deciding
	whether to travel now.

	`message` is written here rather than by a client: it is the one string a donor acts on, and the
	two facts it must carry — which group, and how far — are the two a generic template gets wrong.
	"""

	model_config = MODEL_CONFIG
	alert_id: str
	request_id: str
	donor_ref: str
	requested_group: str
	donor_group: str
	county: str
	distance_counties: int = Field(ge=0, le=2)
	urgency: str = Field(pattern=r'^(routine|urgent|critical)$')
	message: str


class DonationCentre(BaseModel):
	"""§REC-006's "Find donation centres" — a site, and which of the two questions it answers.

	`kind` is `DONATION_SITE_KINDS`'s key and `label` is its value, so the screen never has to hold a
	second copy of the vocabulary. A place's own `name` is separate from the label: the label says
	what the kind of site is for, the name says which one it is.
	"""

	model_config = MODEL_CONFIG
	place_id: str
	name: str
	kind: str = Field(pattern=r'^(blood_donation|blood_bank)$')
	label: str
	county: str | None = None
	distance_km: float = Field(ge=0)
	phone: str | None = None
	walk_in: bool = True


DONATION_INTERVAL_DAYS = 90


class BloodService(LogMixin):
	def __init__(self) -> None:
		self._donors: dict[str, Donor] = {}
		assert self._donors == {}

	async def register(self, d: Donor) -> Donor:
		assert d.donor_ref, 'donor ref'
		self._donors[d.donor_ref] = d
		return d

	def _eligible(self, d: Donor, today_iso: str) -> bool:
		if d.last_donation_iso is None:
			return True
		return date.fromisoformat(d.last_donation_iso) + timedelta(days=DONATION_INTERVAL_DAYS) <= date.fromisoformat(today_iso)

	def match(self, req: BloodRequest, today_iso: str, limit: int = 10) -> list[DonorMatch]:
		assert req.urgency in ('routine', 'urgent', 'critical'), 'urgency bounds'
		compatible_groups = COMPATIBILITY[req.blood_group]
		out = [
			DonorMatch(donor_ref=d.donor_ref, blood_group=d.blood_group, county=d.county, eligible=self._eligible(d, today_iso), compatible=d.blood_group in compatible_groups)
			for d in self._donors.values()
		]
		ranked = sorted(
			[m for m in out if m.compatible and m.eligible and m.county == req.county],
			key=lambda m: {'O-': 0, 'AB-': 1}.get(m.blood_group, 2),
		) or [m for m in out if m.compatible and m.eligible]
		assert all(m.compatible for m in ranked[:limit]), 'compatibility invariant'
		return ranked[:limit]

	async def record_donation(self, donor_ref: str, today_iso: str) -> Donor:
		d = self._donors[donor_ref]
		assert self._eligible(d, today_iso), 'donor not yet eligible'
		d.last_donation_iso = today_iso
		return d

	# --- §REC-006 "Receive alerts when your blood type is urgently needed nearby" -------------

	@staticmethod
	def _reach(county: str, hops: int, adjacency: dict[str, tuple[str, ...]] | None) -> dict[str, int]:
		"""Every county within `hops` of `county`, mapped to its distance — a breadth-first walk.

		`ADJACENCY` is symmetric, so this is the honest reading of "nearby": at one hop the counties
		that touch this one, at two the counties that touch *those*. The distance is what the walk
		already computed, so it is returned rather than re-derived — a second `if d.county == req.county`
		would be a second definition of distance, and the two would eventually disagree.

		An unknown county is its own answer rather than an error: `neighbours` returns `()` for one,
		and a request from a county nobody has a row for still alerts the donors in that county.
		"""
		seen = {county: 0}
		frontier = [county]
		for step in range(1, hops + 1):
			nxt = [n for c in frontier for n in (adjacency or {}).get(c, ()) if n not in seen]
			if not nxt:
				break
			seen.update(dict.fromkeys(nxt, step))
			frontier = nxt
		return seen

	def _rank(self, group: str, requested: str) -> int | None:
		"""How good a donor of `group` is for a `requested` recipient, or `None` if unusable.

		Rank 0 is the group the request names, 1 is O-negative (the universal donor, and the group a
		critical request falls back on when the exact one is not on the list), 2 is any other
		compatible group. `None` is not a rank of zero — it is a donor whose blood cannot be given to
		this patient at all, and the distinction is the same one `DonorMatch.compatible` draws.
		"""
		if group not in COMPATIBILITY[requested]:
			return None
		if group == requested:
			return 0
		return 1 if group == 'O-' else 2

	def donor_alerts(self, req: BloodRequest, now_iso: str,
	                 adjacency: dict[str, tuple[str, ...]] | None = None) -> list[DonorAlert]:
		"""§REC-006's donor alerts: who is told, and how far away they may be.

		`match` answers the *requester's* question — who can I call — and returns a ranked list of
		names. This answers the *donor's* question, which the bullet is about: my group is needed,
		and it is needed here. The two are not the same read of the same table, which is why the
		audit row said "no path notifies a donor" while `match` was fully implemented.

		Three things decide who is reached, and each is a decision rather than a filter:

		* **Urgency sets the reach and the depth.** `URGENCY_REACH` widens the counties in *hops*
		  (0 = the request's own, 1 = the counties that touch it, 2 = the counties that touch
		  those) and `URGENCY_DEPTH` widens the groups. A `routine` request notifies the exact group
		  in its own county and nobody else: a routine need is met from the stock list, and waking
		  donors for it spends their goodwill for nothing. A `critical` request reaches every
		  compatible group two counties out.
		* **A donor who is not yet eligible is not notified.** The 90-day interval is a safety rule
		  about the donor, not a supply rule, and an alert is an invitation to donate — sending it to
		  somebody inside the window invites them to break it.
		* **The donor's own county is what "nearby" is measured from**, and `distance_counties` says
		  how the alert reached them rather than leaving them to infer it from a county name they may
		  not know the neighbours of.

		`adjacency` is the §INF-001 table, injected rather than imported so this module keeps its one
		dependency and so a test can hand it a four-county world where two hops is not the whole map.
		"""
		assert req.urgency in URGENCY_REACH, f'unknown urgency {req.urgency}'
		assert now_iso, 'an eligibility decision needs a date'
		reach, depth = URGENCY_REACH[req.urgency], URGENCY_DEPTH[req.urgency]
		counties = self._reach(req.county, reach, adjacency)
		alerts: list[DonorAlert] = []
		for d in sorted(self._donors.values(), key=lambda x: x.donor_ref):
			if d.county not in counties or not self._eligible(d, now_iso):
				continue
			rank = self._rank(d.blood_group, req.blood_group)
			if rank is None or rank > depth:
				continue
			away = counties[d.county]
			where = 'your county' if away == 0 else f'{d.county}, {away} count{"y" if away == 1 else "ies"} from {req.county}'
			alerts.append(DonorAlert(
				alert_id=f'{req.request_id}-{d.donor_ref}',
				request_id=req.request_id, donor_ref=d.donor_ref,
				requested_group=req.blood_group, donor_group=d.blood_group,
				county=d.county, distance_counties=away, urgency=req.urgency,
				message=(f'{req.urgency.capitalize()} need for {req.blood_group} blood in {where}. '
				         f'Your {d.blood_group} can be given to a {req.blood_group} patient. '
				         'Call the requesting facility before you travel.'),
			))
		self._log_info('donor alerts raised', request=req.request_id, urgency=req.urgency,
		               counties=len(counties), alerted=len(alerts))
		return alerts

	# --- §REC-006 "Find donation centres" ----------------------------------------------------

	def donation_centres(self, places: PlacesService, lat: float, lon: float, limit: int = 5,
	                     kinds: tuple[str, ...] = ('blood_donation',)) -> list[DonationCentre]:
		"""§REC-006's "Find donation centres", over whatever §FND-001's place store holds.

		`kinds` defaults to `blood_donation` alone, and the default is the point. The OpenStreetMap
		vocabulary separates a site where a person gives blood from one where donated blood is stored
		(`sources/osm-healthcare-tags/`), and a caller who asks for "donation centres" is asking the
		first question. A storage site in that list would be a result a donor cannot use, so
		`blood_bank` is offered only when it is named — the same reasoning §FND-003's `test_type`
		filter applies to a test a facility does not offer.

		The label comes from `DONATION_SITE_KINDS` rather than from the caller, so the two kinds
		cannot be presented as one.

		A deployment whose OSM import has not run has no answer, and the honest one is an empty list.
		`nearest` asserts a non-empty pool, so the assert is caught here rather than surfacing as a
		500 on the screen a person opens when they are unwell — the same read `info.service`'s
		nearest-facility lookup gives it, and for the same reason.
		"""
		assert kinds, 'a donation-centre search with no kind asks for nothing'
		unknown = [k for k in kinds if k not in DONATION_SITE_KINDS]
		assert not unknown, f'not a donation-site kind: {unknown}'
		try:
			rows = places.nearest(lat, lon, {PlaceKind(k) for k in kinds}, limit)
		except AssertionError:
			return []  # nothing imported: no donation site, reported absent rather than invented
		return [
			DonationCentre(
				place_id=p.osm_id, name=p.name, kind=p.kind.value,
				label=DONATION_SITE_KINDS[p.kind.value], county=p.county,
				distance_km=round(km, 1), phone=p.phone,
			)
			for p, km in rows
		]