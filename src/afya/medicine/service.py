"""Medicine service — PPB verification port + client, interactions, dosing, stock crowdsourcing."""
from datetime import datetime, timezone
from typing import Protocol

from afya.facilities.service import haversine_km
from afya.logmixin import LogMixin
from afya.medicine import formulary
from afya.medicine.views import (
	BatchRecall, DoseLine, DoseRequest, DoseResult, ProductDisplay, RegistrationStatus, StockAlert,
	StockAvailability, StockReport, VerifyRequest, VerifyResult, essential_slug,
)


def _now_iso() -> str:
	return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _dose_line(form: formulary.Formulation, low_mg: float, high_mg: float) -> DoseLine:
	"""One form's share of a milligram range, in the units that form is actually given in.

	A syrup's strength is printed as "250 mg/5 ml", so the millilitres a person measures are the
	milligrams divided by the strength and multiplied by the volume the strength is stated per. A
	tablet's unit is the tablet, and a dose between two whole tablets is reported as the range it
	is rather than rounded to one of them — rounding a paediatric dose to the nearest tablet is a
	decision for a prescriber, not for a calculator.
	"""
	if form.mg_per_unit and form.ml_per_unit:
		unit, factor = 'ml', form.ml_per_unit / form.mg_per_unit
	elif form.mg_per_unit:
		unit, factor = 'tablet', 1.0 / form.mg_per_unit
	else:
		# A form with no fixed milligram content — an ORS sachet. It is dosed by volume, and the
		# volume is on the model's own fields, so there is no per-unit amount to compute here.
		return DoseLine(form=form.form, strength=form.strength, unit='unit',
		                amount_low=0.0, amount_high=0.0)
	return DoseLine(
		form=form.form, strength=form.strength, unit=unit,
		amount_low=round(low_mg * factor, 1), amount_high=round(high_mg * factor, 1),
		amount_mg_low=low_mg, amount_mg_high=high_mg,
	)


# §MED-004's Anti-gaming clause: "Require location proximity to report." Five kilometres is the
# coarsest of §COM-102's three geofence radii, and it is the right one here — a person reporting
# stock at a facility is standing in or near it, and a tighter ring would refuse the report of
# someone who walked to the next shop and remembered. It is a module constant rather than a route
# default so the number appears once and a deployment that wants it stricter changes one line.
STOCK_REPORT_MAX_KM = 5.0


def _age_hours(at_iso: str | None) -> float | None:
	"""How long ago a report was made, as a number a screen prints.

	§MED-004's Anti-gaming clause says "Show report age clearly", and "clearly" is a duration rather
	than a timestamp: a client holding an ISO string has to diff it against its own clock, which is
	wrong on a phone whose clock is wrong and impossible on one that has none. `None` for a report
	with no timestamp — which is a report from an older client, and printing "0 hours ago" for it
	would be a freshness claim nothing supports.
	"""
	if not at_iso:
		return None
	try:
		made = datetime.fromisoformat(at_iso.replace('Z', '+00:00'))
	except ValueError:
		return None
	if made.tzinfo is None:
		made = made.replace(tzinfo=timezone.utc)
	return round(max(0.0, (datetime.now(timezone.utc) - made).total_seconds() / 3600.0), 2)


_GEOHASH_BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz'


def _geohash_centre(geohash: str) -> tuple[float, float]:
	"""Decode a geohash to the centre of its cell.

	§LOC-003's rule is that raw location never crosses this boundary, so the report carries a cell
	and the proximity test decodes it here. The cell is coarse by construction (5+ characters), so
	the decode yields an area, not a position — which is exactly the precision a proximity check
	needs and the precision a leak would need to be useful.
	"""
	assert len(geohash) >= 5, 'geohash too precise to generalise'
	lat_range = [-90.0, 90.0]
	lon_range = [-180.0, 180.0]
	even = True
	for char in geohash.lower():
		idx = _GEOHASH_BASE32.find(char)
		assert idx >= 0, f'not a geohash character: {char!r}'
		for bit in (16, 8, 4, 2, 1):
			rng = lon_range if even else lat_range
			mid = (rng[0] + rng[1]) / 2
			if idx & bit:
				rng[0] = mid
			else:
				rng[1] = mid
			even = not even
	return ((lat_range[0] + lat_range[1]) / 2, (lon_range[0] + lon_range[1]) / 2)


class PPBRegistryPort(Protocol):
	async def verify(self, req: VerifyRequest) -> VerifyResult: ...


class PPBStubClient:
	"""Offline fallback registry used when PPB endpoint unreachable.

	It answers `unverified`, not `not_found`. The section's Offline clause promises a cached registry
	rather than a guess, and a stub that reported "this batch is not registered" while holding no
	registry at all would be accusing a medicine on the strength of an empty table — the one failure
	mode in this feature that can kill someone. `genuine` is False either way, so the fail-closed
	behaviour the README claims is unchanged; what changed is that the client can now tell the
	person *why*, and the answer is "we could not check", not "it is fake".
	"""

	async def verify(self, req: VerifyRequest) -> VerifyResult:
		return VerifyResult(status=RegistrationStatus.unverified, source='offline_stub',
			notes='PPB unreachable — verify manually at pharmacy')


# §MED-001's "Display" line reads from the two PPB feeds §18.7 already names: the registry (daily,
# "registered products, status") and recalls (on issue). Neither is a new wire, and `verify` is the
# only caller that needs both at once — which is why the join lives here rather than in the client,
# whose `verify` answers the single-batch question the endpoint is shaped for.
_REGISTRY_NAME_KEYS: tuple[str, ...] = ('product_name', 'name', 'brand_name')
_REGISTRY_MAKER_KEYS: tuple[str, ...] = ('manufacturer', 'marketing_authorisation_holder', 'holder')
_REGISTRY_EXPIRY_KEYS: tuple[str, ...] = ('expiry_iso', 'expiry', 'expires_on')
_REGISTRY_STATUS_KEYS: tuple[str, ...] = ('status', 'registration_status')


def _first(row: dict[str, object], keys: tuple[str, ...]) -> str | None:
	"""The first of `keys` the row carries, as a string.

	PPB's registry field names are not pinned by the spec, and a client that reads one spelling
	would render a blank the day the regulator renames a column. Reading a small set of known
	spellings and saying `None` when none is present keeps the blank honest.
	"""
	for key in keys:
		value = row.get(key)
		if isinstance(value, str) and value.strip():
			return value.strip()
	return None


def registration_outcome(row: dict[str, object] | None, *, recalled: bool) -> RegistrationStatus:
	"""§MED-001's four outcomes, decided from a registry row and the recall feed.

	A recall outranks every other status: a product can be registered, unexpired and still
	withdrawn, and the withdrawal is the fact that matters. An absent row is `not_found`, and a row
	whose status the regulator marks as lapsed is `expired`.
	"""
	if recalled:
		return RegistrationStatus.recalled
	if row is None:
		return RegistrationStatus.not_found
	stated = (_first(row, _REGISTRY_STATUS_KEYS) or '').lower()
	if stated in ('expired', 'lapsed', 'withdrawn', 'suspended'):
		return RegistrationStatus.expired
	return RegistrationStatus.registered


def display_from(row: dict[str, object] | None, status: RegistrationStatus,
	recalls: list[dict[str, object]]) -> ProductDisplay:
	"""The five display fields, assembled from the registry row and the recall rows."""
	if row is None:
		# Nothing to display about a product the registry does not hold, and the recalls list stays
		# empty: a recall row keyed on a batch nobody registered is not this person's medicine.
		return ProductDisplay()
	return ProductDisplay(
		product_name=_first(row, _REGISTRY_NAME_KEYS),
		manufacturer=_first(row, _REGISTRY_MAKER_KEYS),
		registration_status=status,
		expiry_iso=_first(row, _REGISTRY_EXPIRY_KEYS),
		batch_recalls=[_recall(r) for r in recalls],
	)


def _recall(row: dict[str, object]) -> BatchRecall:
	return BatchRecall(
		batch_number=str(row.get('batch') or row.get('batch_number') or ''),
		reason=str(row.get('reason') or 'recalled by the regulator'),
		recalled_at_iso=(str(row['recalled_at_iso']) if row.get('recalled_at_iso') else None),
	)


def _registry_row(data: dict[str, object]) -> dict[str, object] | None:
	"""The product row inside a `/verify` answer, or `None` if the answer carries no product.

	Three shapes are accepted because all three are things a registry plausibly returns and none is
	wrong: a nested `product`/`registry` object, or the fields at the top level. An answer that is
	nothing but `{"genuine": true}` yields `None`, and `None` here is what makes the caller say
	`unverified` rather than invent a product name — the difference between "the regulator confirms
	this batch" and "the regulator confirms this batch is *this medicine*".
	"""
	for key in ('product', 'registry', 'registration'):
		nested = data.get(key)
		if isinstance(nested, dict):
			return dict(nested)
	if any(k in data for k in _REGISTRY_NAME_KEYS + _REGISTRY_MAKER_KEYS + _REGISTRY_STATUS_KEYS):
		return dict(data)
	return None


def _matching_recalls(data: dict[str, object], batch_number: str) -> list[dict[str, object]]:
	"""Recall rows the answer carries for this batch, under either spelling of the key.

	A recall is filtered to the batch the person scanned. A registry that returns every recall it
	holds would otherwise put another batch's withdrawal on this person's screen, which is the kind
	of false alarm that teaches people to ignore the real one.
	"""
	rows = data.get('recalls') or data.get('batch_recalls') or []
	if not isinstance(rows, list):
		return []
	out: list[dict[str, object]] = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		row = dict(row)
		named = str(row.get('batch') or row.get('batch_number') or '')
		if named and named != batch_number:
			continue
		out.append(row)
	return out


def status_from_verify_answer(data: dict[str, object], batch_number: str) -> tuple[RegistrationStatus, dict[str, object] | None, list[dict[str, object]]]:
	"""One PPB `/verify` answer -> the status, the product row and this batch's recalls.

	The rule that matters: a `genuine: false` with no product row behind it is `not_found`, because
	the registry answered and this batch is not in it. An answer carrying *nothing* — no verdict and
	no product — is `unverified`, because a registry that returned an unrecognisable body has not
	told us the medicine is bad, only that we do not know. Folding that into `not_found` is the one
	mistake in this feature that can cost a life in the other direction: a person throws away
	medicine that was fine.
	"""
	recalls = _matching_recalls(data, batch_number)
	row = _registry_row(data)
	if row is None and 'genuine' not in data:
		return RegistrationStatus.unverified, None, []
	if row is None:
		return (RegistrationStatus.not_found if not data.get('genuine')
			else RegistrationStatus.registered), None, recalls
	return registration_outcome(row, recalled=bool(recalls)), row, recalls


class MedicineService(LogMixin):
	_INTERACTIONS: tuple[str, ...] = (
		'warfarin|aspirin:major:additive bleeding risk',
		'metronidazole|alcohol:moderate:disulfiram-like reaction',
		'artemether|ketoconazole:moderate:QT prolongation',
		'rifampicin|oral_contraceptives:major:reduced efficacy',
	)

	def __init__(self, ppb: PPBRegistryPort) -> None:
		self._ppb = ppb
		assert self._ppb is not None
		self._stock: list[StockReport] = []
		self._restock_alerts: list[StockAlert] = []

	async def verify(self, req: VerifyRequest) -> VerifyResult:
		assert req.batch_number and req.gtin, 'batch+gtin required'
		return await self._ppb.verify(req)

	def check_interactions(self, drugs: list[str]) -> list[str]:
		assert len(drugs) <= 50, 'unreasonable polypharmacy'
		found: list[str] = []
		for idx, left in enumerate(drugs):
			for right in drugs[idx + 1:]:
				for row in self._INTERACTIONS:
					pair, severity, note = row.split(':', 2)
					names = pair.split('|')
					if {left.lower(), right.lower()} == set(names):
						found.append(f'{severity.upper()} {left}+{right}: {note}')
		self._log_info('interaction check', hits=len(found))
		return found

	def dose(self, req: DoseRequest) -> DoseResult:
		"""§MED-003's calculator: the dose range for this child, from the WHO Pocket Book.

		The range is the source's own. Paracetamol is 10–15 mg/kg, so the answer is a spread and not
		a midpoint: a midpoint is a number no guideline states, and a prescriber reading one has no
		way to know which end of the range it came from.

		Refusals are answers here, not exceptions. A name not in the formulary, a weight below the
		source's own tables, a zinc lookup with no age — each returns a result carrying `unknown` or
		a warning rather than raising, because a parent who mistyped a medicine name needs to be
		told so, and a 500 tells them nothing.
		"""
		assert req.weight_kg > 0, 'a dose needs a weight'
		entry = formulary.match(req.drug)
		if entry is None:
			self._log_info('dose: unknown drug', drug=req.drug)
			return DoseResult(
				drug=req.drug, matched='', mg_per_kg_low=0.0, mg_per_kg_high=0.0,
				doses_per_day_low=0, doses_per_day_high=0, unknown=True,
				warns=[f'We do not have a paediatric dose for "{req.drug}". '
				       'Ask a pharmacist or clinician rather than estimating one.'],
			)

		warns: list[str] = []
		# The source's own lower bound. Below it the tables do not reach, and extrapolating a
		# downward dose is where a paediatric error does the most harm.
		if req.weight_kg < entry.min_kg:
			warns.append(
				f'{entry.label} doses in this reference start at {entry.min_kg:g} kg. '
				'A child below that needs a clinician to dose them.')
		if req.weight_kg > entry.max_kg:
			warns.append(
				f'{entry.label} doses in this reference stop at {entry.max_kg:g} kg, which is the '
				'range it was written for. An older or heavier patient needs an adult reference.')

		result = DoseResult(
			drug=req.drug, matched=entry.label,
			mg_per_kg_low=entry.mg_per_kg_low, mg_per_kg_high=entry.mg_per_kg_high,
			doses_per_day_low=entry.doses_per_day_low, doses_per_day_high=entry.doses_per_day_high,
			max_mg_per_dose=entry.max_mg_per_dose, max_mg_per_day=entry.max_mg_per_day,
			note=entry.note, warns=warns,
		)

		# Zinc is dosed by age, not weight: the source's rule turns on six months, so a lookup
		# without an age cannot be answered and says so rather than defaulting to either band.
		if entry.slug == 'zinc':
			if req.age_months is None:
				result.warns.append('Zinc is given by age, so we need the child\'s age to answer this.')
				return result
			daily = (formulary.ZINC_MG_UNDER if req.age_months < formulary.ZINC_MONTHS_THRESHOLD
			         else formulary.ZINC_MG_FROM)
			result.days_low = formulary.ZINC_DAYS_LOW
			result.days_high = formulary.ZINC_DAYS_HIGH
			tab = entry.formulations[0]
			result.lines = [DoseLine(form=tab.form, strength=tab.strength, unit='tablet',
			                         amount_low=daily / tab.mg_per_unit if tab.mg_per_unit else 1.0,
			                         amount_high=daily / tab.mg_per_unit if tab.mg_per_unit else 1.0,
			                         amount_mg_low=daily, amount_mg_high=daily)]
			self._log_info('dose', drug=entry.slug, band=f'age {req.age_months}m')
			return result

		# ORS is a volume, not a milligram dose: after each loose stool, plus a maintenance rate
		# while the child is rehydrating. Computing mg/kg for it would be a category error.
		if entry.slug == 'ors':
			under_two = req.age_months is not None and req.age_months < formulary.ORS_TWO_YEAR_MONTHS
			result.after_each_stool_ml_low = (formulary.ORS_ML_UNDER_2Y_LOW if under_two
			                                  else formulary.ORS_ML_FROM_2Y_LOW)
			result.after_each_stool_ml_high = (formulary.ORS_ML_UNDER_2Y_HIGH if under_two
			                                   else formulary.ORS_ML_FROM_2Y_HIGH)
			result.maintenance_ml_per_kg_per_hour = formulary.ORS_ML_PER_KG_MAINTENANCE
			if req.age_months is None:
				result.warns.append('Without the child\'s age we cannot say whether this is the under-two '
				             'or over-two amount, so the larger range is shown.')
			self._log_info('dose', drug=entry.slug, volume=True)
			return result

		# A drug the source doses by weight band: the answer is a tablet count, not a milligram
		# figure, because the formulation is a fixed-strength combined tablet.
		if entry.bands:
			band = next((b for b in entry.bands
			             if req.weight_kg >= b.min_kg and (b.max_kg is None or req.weight_kg < b.max_kg)),
			            None)
			if band is None:
				result.warns.append(f'{entry.label} has no tablet band for {req.weight_kg:g} kg in this '
				             'reference; ask a clinician.')
				return result
			tab = entry.formulations[0]
			result.lines = [DoseLine(form=tab.form, strength=tab.strength, unit='tablet',
			                         amount_low=band.units_low, amount_high=band.units_high)]
			result.days_low = 3
			result.days_high = 3
			self._log_info('dose', drug=entry.slug, band=f'{band.min_kg:g}-{band.max_kg}kg')
			return result

		# The ordinary case: a mg/kg range, rendered in each form the pharmacy stocks.
		low = round(req.weight_kg * entry.mg_per_kg_low, 1)
		high = round(req.weight_kg * entry.mg_per_kg_high, 1)
		result.mg_low = low
		result.mg_high = high

		if entry.max_mg_per_dose is not None and high > entry.max_mg_per_dose:
			result.over_max = True
			result.warns.append(
				f'The calculated dose ({high:g} mg) is above the maximum this reference states for '
				f'{entry.label} ({entry.max_mg_per_dose:g} mg per dose). Give the maximum, not the '
				'calculated figure, and check with a clinician.')
		if entry.max_mg_per_day is not None and high * entry.doses_per_day_high > entry.max_mg_per_day:
			result.over_max = True
			result.warns.append(
				f'{high * entry.doses_per_day_high:g} mg a day is above the maximum this reference '
				f'states for {entry.label} ({entry.max_mg_per_day:g} mg a day).')
		if entry.max_mg_per_dose is None:
			# Said out loud rather than left blank, because an empty maximum column reads as "no
			# limit", and the source's silence is neither a limit of zero nor of infinity.
			result.warns.append(f'This reference states no maximum dose for {entry.label}.')

		result.lines = [_dose_line(f, low, high) for f in entry.formulations]
		self._log_info('dose', drug=entry.slug, mg_low=low, mg_high=high)
		return result

	async def report_stock(self, report: StockReport) -> StockAlert | None:
		"""Record a stock report and raise §MED-004's restock alert on the transition.

		The alert fires on out-of-stock -> in-stock, not on in-stock: a report that a medicine is
		available is not news unless the last thing anyone said about it was that it had run out.
		"""
		previous = self._latest(report.drug, report.facility_id)
		self._stock.append(report)
		assert len(self._stock) < 10_000, 'unbounded stock store'
		if previous is None or previous.in_stock or not report.in_stock:
			return None
		alert = StockAlert(
			alert_id='RESTOCK-' + report.report_id.removeprefix('STOCK-'),
			drug=report.drug, facility_id=report.facility_id,
			became_available_at_iso=report.at_iso or _now_iso(),
			out_of_stock_since_iso=previous.at_iso,
		)
		self._restock_alerts.append(alert)
		self._log_info('restock', drug=report.drug, facility=report.facility_id)
		return alert

	def _latest(self, drug: str, facility_id: str) -> StockReport | None:
		"""The newest report for one drug at one facility, by the time it was made.

		Ordered by `at_iso` rather than by arrival, because a report queued offline and flushed
		later is older than one filed after it — reading arrival order would make an offline report
		look like the newest thing anyone knows.
		"""
		rows = [r for r in self._stock
			if r.drug.lower() == drug.lower() and r.facility_id == facility_id]
		if not rows:
			return None
		return max(rows, key=lambda r: r.at_iso or '')

	def stock_for(self, drug: str, facility_id: str) -> list[StockReport]:
		return [r for r in self._stock if r.drug == drug and r.facility_id == facility_id]

	# --- §MED-004 crowdsourced stock: search, recency, weighting, restock alerts ---------------

	def search_stock(self, query: str, *, limit: int = 20) -> list[StockAvailability]:
		"""§MED-004's "Search for a medicine" — across drugs, which `stock_for` cannot do.

		`stock_for` is keyed on (drug, facility) and needs both, so it answers "is this drug at this
		place" and not "where is this drug". This is the other question, and it is the one the
		section's example asks: a person with a prescription wants a list of places, not a verdict
		on one.
		"""
		assert query.strip(), 'a search needs something to search for'
		needle = query.strip().lower()
		by_pair: dict[tuple[str, str], list[StockReport]] = {}
		for row in self._stock:
			if needle not in row.drug.lower():
				continue
			by_pair.setdefault((row.drug.lower(), row.facility_id), []).append(row)
		out: list[StockAvailability] = []
		for rows in by_pair.values():
			out.append(self._availability(rows))
		# Essential medicines first, then freshest: §MED-004 says the list is "prioritised", and a
		# person searching for insulin should not have to scroll past a vitamin.
		out.sort(key=lambda a: (not a.essential, a.age_hours if a.age_hours is not None else 1e9))
		return out[:limit]

	def availability_for(self, drug: str, facility_id: str) -> StockAvailability | None:
		"""The one pair §MED-004's example names: "available at [pharmacy], 2 hours ago"."""
		rows = [r for r in self._stock
			if r.drug.lower() == drug.lower() and r.facility_id == facility_id]
		return self._availability(rows) if rows else None

	def _availability(self, rows: list[StockReport]) -> StockAvailability:
		assert rows, 'an availability needs at least one report'
		latest = max(rows, key=lambda r: r.at_iso or '')
		age = _age_hours(latest.at_iso)
		return StockAvailability(
			drug=latest.drug, facility_id=latest.facility_id,
			in_stock=latest.in_stock, reported_at_iso=latest.at_iso, age_hours=age,
			reporter_weight=self.reporter_weight(latest.reported_by), reports=len(rows),
			essential=essential_slug(latest.drug) is not None,
		)

	def reporter_weight(self, reporter_ref: str | None) -> int:
		"""§MED-004's "Weight reports by reporter reliability" — 1 to 10, derived not supplied.

		Starts at the middle and moves on evidence: a reporter whose reports a *later* report from
		someone else contradicts loses a point, and one whose reports stand gains one. The window is
		the reporter's whole history here, which is honest for a service that holds reports in
		memory and would need a decay term the day it holds a year of them — so the cap and the
		floor are asserted rather than the rate.

		A report with no reporter has no weight to read: `None` would match every other anonymous
		report and turn "unknown" into a history, so it answers the same 5 a first-time reporter
		gets rather than pooling strangers into one person.
		"""
		if reporter_ref is None:
			return 5
		mine = [r for r in self._stock if r.reported_by == reporter_ref]
		if not mine:
			return 5
		weight = 5
		for row in mine:
			later = [r for r in self._stock
				if r.drug.lower() == row.drug.lower() and r.facility_id == row.facility_id
				and r.reported_by != reporter_ref and (r.at_iso or '') > (row.at_iso or '')]
			if not later:
				continue
			newest = max(later, key=lambda r: r.at_iso or '')
			weight += -1 if newest.in_stock != row.in_stock else 1
		return max(1, min(10, weight))

	def within_proximity(self, report: StockReport, facility: object, max_km: float) -> bool:
		"""§MED-004's "Require location proximity to report", as a predicate the caller applies.

		A missing geohash answers `False`: as a predicate on "is this report from here", an
		unplaceable report has not shown that it is, and a `True` would be the predicate asserting
		something it did not check. The §13.2 `gps` fallback is therefore the *caller's* to apply —
		the route skips the check when the client sent no cell, so a phone without a fix can still
		report, which is the accessibility failure §ACC-001 exists to prevent. `False` here is not
		a refusal; it is the absence of the evidence a refusal would rest on.
		"""
		if not report.reporter_geohash:
			return False
		lat, lon = _geohash_centre(report.reporter_geohash)
		return haversine_km(lat, lon, getattr(facility, 'lat'), getattr(facility, 'lon')) <= max_km

	def restock_alerts(self, facility_id: str | None = None) -> list[StockAlert]:
		return [a for a in self._restock_alerts if facility_id is None or a.facility_id == facility_id]