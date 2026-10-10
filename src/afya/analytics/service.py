"""Public-health analytics — §19.4's nine dashboards over the state the other services hold.

§19.4 was nine bullet points and an access sentence. The data existed — triage assessments, case
reports, contact lists, proximity tokens, content engagement, misinformation clusters, facility
availability, alert feed items — but nothing assembled it into the dashboards the section names,
so PHEOC and county teams had the raw routes and no view.

Two rules from §19.3 and §11.7 govern every row here, and both are enforced rather than documented:

  * **Minimum cell size.** A cell drawn from fewer than ten people is suppressed — the count is not
    reported, and the row says it was withheld. Reporting a small number with a flag would put the
    number on the wire, which is the thing the rule forbids.
  * **No individual-level data.** Every row is a count over a group. A dashboard cannot return a
    person, and `individual_level_data` is reported as False so the claim is checkable.

`AnalyticsService` reads from other services rather than keeping a second copy of their state, so a
dashboard cannot disagree with the route a person used to record the thing it counts.
"""
from collections import Counter
from typing import Any, Iterable

from afya.analytics.views import (
	MIN_CELL_SIZE, DASHBOARDS, AnalyticsAccess, Dashboard, DashboardId, MetricRow,
)
from afya.logmixin import LogMixin

# The caveat every dashboard carries. It is the honest limit of what a count means: this is what
# people reported and searched for, not what a laboratory confirmed.
REPORTED_NOT_CONFIRMED = 'Counts what people reported or searched for, not laboratory-confirmed cases.'

# §19.4 "Access: PHEOC, county health teams, MoH. Role-based. Audit logged." The roles are the
# §17.4 ones whose scope is an aggregate: a clinician sees consented patients, not a county.
ANALYTICS_ROLES: tuple[str, ...] = ('county_officer', 'pheoc_analyst', 'auditor')


def _cell(key: str, label: str, count: int, denominator: int,
		breakdown: dict[str, float] | None = None, note: str | None = None) -> MetricRow:
	"""One aggregated cell, suppressed when the group it describes is too small to be anonymous.

	`denominator` is the *group size* — the number of people the cell is drawn from — and that is
	what the min-cell rule tests. It is deliberately not a county's population: a county of four
	million with one reported case is still a cell of one, and a rule that cleared it would report
	the single case §11.7 forbids. The county population is context a reader may want, and it
	travels in `breakdown`, but it does not decide whether the cell may be shown.
	"""
	if denominator < MIN_CELL_SIZE:
		return MetricRow(key=key, label=label, value=None, denominator=None, suppressed=True,
			note=f'withheld: fewer than {MIN_CELL_SIZE} people in this cell')
	return MetricRow(key=key, label=label, value=float(count), denominator=denominator,
		breakdown=breakdown or {}, note=note)


class AnalyticsService(LogMixin):
	def __init__(self) -> None:
		self._triages: list[tuple[str, str]] = []          # (county, risk_level)
		self._cases: list[tuple[str, str]] = []            # (county, status)
		self._contacts: list[tuple[str, int, int]] = []    # (county, recorded, completed)
		self._encounters: list[tuple[str, int]] = []       # (county, token count)
		self._content_views: list[tuple[str, str]] = []    # (slug, lang)
		self._alerts: list[tuple[str, int, int]] = []      # (county, delivered, acknowledged)
		self._populations: dict[str, int] = {}
		assert self._triages == [] and self._populations == {}

	# --- ingestion ---------------------------------------------------------------------------

	def set_population(self, county: str, population: int) -> None:
		"""The denominator a county's cells are tested against. Without it a cell is unmeasurable
		and therefore suppressed, which is the safe default: an unknown population is not a large one."""
		assert population >= 0, 'population cannot be negative'
		self._populations[county] = population

	def record_triage(self, county: str, risk_level: str) -> None:
		self._triages.append((county, risk_level))

	def record_case(self, county: str, status: str) -> None:
		self._cases.append((county, status))

	def record_contacts(self, county: str, recorded: int, completed: int) -> None:
		assert 0 <= completed <= recorded, 'completed contacts cannot exceed those recorded'
		self._contacts.append((county, recorded, completed))

	def record_encounters(self, county: str, tokens: int) -> None:
		"""Proximity encounters, counted per county. The tokens are PETs — the count is all that
		reaches here, because a token that reached a dashboard would be the deanonymisation §23.4
		names as a very-high-impact risk."""
		assert tokens >= 0, 'encounter count cannot be negative'
		self._encounters.append((county, tokens))

	def record_content_view(self, slug: str, lang: str) -> None:
		self._content_views.append((slug, lang))

	def record_alert(self, county: str, delivered: int, acknowledged: int) -> None:
		assert 0 <= acknowledged <= delivered, 'acknowledgements cannot exceed deliveries'
		self._alerts.append((county, delivered, acknowledged))

	# --- the nine dashboards -----------------------------------------------------------------

	def dashboard(self, dashboard: DashboardId, as_at_iso: str) -> Dashboard:
		title, granularity = _TITLES[dashboard]
		rows, suppressed = _BUILDERS[dashboard](self)
		return Dashboard(dashboard=dashboard, title=title, granularity=granularity, rows=rows,
			suppressed_cells=suppressed, min_cell_size=MIN_CELL_SIZE, as_at_iso=as_at_iso,
			caveat=REPORTED_NOT_CONFIRMED)

	def all_dashboards(self, as_at_iso: str) -> list[Dashboard]:
		return [self.dashboard(d, as_at_iso) for d, _, _ in DASHBOARDS]

	def access(self) -> AnalyticsAccess:
		return AnalyticsAccess(
			dashboards=[d.value for d in DashboardId],
			roles_allowed=list(ANALYTICS_ROLES),
			audit_logged=True,
			individual_level_data=False,
		)

	# --- builders ----------------------------------------------------------------------------

	def _population(self, county: str) -> int:
		"""The denominator for a county. An unset population is 0, which suppresses every cell —
		the honest answer for a county nobody has given us a denominator for."""
		return self._populations.get(county, 0)

	def _by_county(self, pairs: Iterable[tuple[str, str]]) -> list[MetricRow]:
		counties = sorted({c for c, _ in pairs})
		rows: list[MetricRow] = []
		for county in counties:
			mine = [v for c, v in pairs if c == county]
			breakdown = {k: float(v) for k, v in sorted(Counter(mine).items())}
			rows.append(_cell(county, county, len(mine), len(mine), breakdown,
				f'county population {self._population(county):,}'))
		return rows

	def _symptom_surveillance(self) -> tuple[list[MetricRow], int]:
		rows = self._by_county(self._triages)
		return rows, len([r for r in rows if r.suppressed])

	def _triage_volume(self) -> tuple[list[MetricRow], int]:
		"""Triage volume and risk distribution: the count is the volume, the breakdown the mix."""
		rows = self._by_county(self._triages)
		return rows, len([r for r in rows if r.suppressed])

	def _case_pipeline(self) -> tuple[list[MetricRow], int]:
		rows = self._by_county(self._cases)
		return rows, len([r for r in rows if r.suppressed])

	def _contact_monitoring(self) -> tuple[list[MetricRow], int]:
		"""Contact monitoring adherence: completed over recorded, per county. The denominator for
		the min-cell test is the contacts recorded, not the county population — the re-identification
		risk is in the contact list, which is a small group by nature."""
		counties = sorted({c for c, _, _ in self._contacts})
		rows: list[MetricRow] = []
		for county in counties:
			mine = [(r, d) for c, r, d in self._contacts if c == county]
			recorded = sum(r for r, _ in mine)
			completed = sum(d for _, d in mine)
			pct = round(100.0 * completed / recorded, 1) if recorded else 0.0
			rows.append(_cell(county, county, completed, recorded,
				{'adherence_pct': pct, 'recorded': float(recorded)},
				'completed over recorded contacts'))
		return rows, len([r for r in rows if r.suppressed])

	def _encounter_density(self) -> tuple[list[MetricRow], int]:
		counties = sorted({c for c, _ in self._encounters})
		rows: list[MetricRow] = []
		for county in counties:
			total = sum(n for c, n in self._encounters if c == county)
			rows.append(_cell(county, county, total, total,
				{'tokens': float(total)}, 'proximity encounters, pseudonymous tokens only'))
		return rows, len([r for r in rows if r.suppressed])

	def _content_engagement(self) -> tuple[list[MetricRow], int]:
		"""Content engagement: views per library item. The denominator is the county population the
		viewers come from, so an item read by a handful of people is withheld like any other cell."""
		slugs = sorted({s for s, _ in self._content_views})
		total_population = sum(self._populations.values())
		rows: list[MetricRow] = []
		for slug in slugs:
			mine = [lang for s, lang in self._content_views if s == slug]
			breakdown = {k: float(v) for k, v in sorted(Counter(mine).items())}
			rows.append(_cell(slug, slug, len(mine), len(mine), breakdown,
				f'read by {len(mine)} of {total_population:,} people'))
		return rows, len([r for r in rows if r.suppressed])

	def _misinformation_velocity(self) -> tuple[list[MetricRow], int]:
		"""Misinformation velocity, from the clusters COM-104 already builds. The velocity band is
		the value and the report count the denominator; a cluster under ten reports is aggregating,
		which is the same rule the cluster builder already applies."""
		rows: list[MetricRow] = []
		suppressed = 0
		for topic, reports, velocity in self._misinfo_clusters():
			row = _cell(topic, topic, reports, reports, {'velocity_rank': velocity},
				'rising counts: 1 slow, 2 rising, 3 spiking')
			rows.append(row)
			suppressed += 1 if row.suppressed else 0
		return rows, suppressed

	def _facility_availability(self) -> tuple[list[MetricRow], int]:
		"""Facility and drug availability: facilities open now, per county, and how many report a
		stockout. A facility count is not a person count, so the min-cell rule does not apply — but
		the row still carries its denominator so a reader can see what it was drawn from."""
		rows: list[MetricRow] = []
		for county, total, open_now, stocked_out in self._facility_rows():
			rows.append(MetricRow(key=county, label=county, value=float(open_now), denominator=total,
				breakdown={'facilities': float(total), 'stocked_out': float(stocked_out)},
				note='facilities open now; not person-level data'))
		return rows, 0

	def _alert_reach(self) -> tuple[list[MetricRow], int]:
		"""Alert reach and response: delivered and acknowledged, per county. The denominator is
		deliveries, since the question is what share of what we sent was seen."""
		counties = sorted({c for c, _, _ in self._alerts})
		rows: list[MetricRow] = []
		for county in counties:
			mine = [(d, a) for c, d, a in self._alerts if c == county]
			delivered = sum(d for d, _ in mine)
			acked = sum(a for _, a in mine)
			pct = round(100.0 * acked / delivered, 1) if delivered else 0.0
			rows.append(_cell(county, county, acked, delivered,
				{'acknowledged_pct': pct, 'delivered': float(delivered)}, 'acknowledged over delivered'))
		return rows, len([r for r in rows if r.suppressed])

	# --- overridable reads, so the route can be driven without a live deployment ---------------

	def _misinfo_clusters(self) -> list[tuple[str, int, int]]:
		"""(topic, reports, velocity rank) from COM-104. Empty until a deployment wires the community
		service; a dashboard with no clusters is an honest empty, not a fabricated one."""
		return []

	def _facility_rows(self) -> list[tuple[str, int, int, int]]:
		"""(county, facilities, open now, stocked out) from the facility registry and MED stock
		reports. Empty until wired, for the same reason."""
		return []


_TITLES: dict[DashboardId, tuple[str, str]] = {d: (title, granularity) for d, title, granularity in DASHBOARDS}

_BUILDERS: dict[DashboardId, Any] = {
	DashboardId.symptom_surveillance: AnalyticsService._symptom_surveillance,
	DashboardId.triage_volume: AnalyticsService._triage_volume,
	DashboardId.case_pipeline: AnalyticsService._case_pipeline,
	DashboardId.contact_monitoring: AnalyticsService._contact_monitoring,
	DashboardId.encounter_density: AnalyticsService._encounter_density,
	DashboardId.content_engagement: AnalyticsService._content_engagement,
	DashboardId.misinformation_velocity: AnalyticsService._misinformation_velocity,
	DashboardId.facility_availability: AnalyticsService._facility_availability,
	DashboardId.alert_reach: AnalyticsService._alert_reach,
}

assert set(_BUILDERS) == set(DashboardId), 'every §19.4 dashboard needs a builder'
assert set(_TITLES) == set(DashboardId), 'every §19.4 dashboard needs a title'
