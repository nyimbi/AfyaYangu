"""PHEOC dashboard feeds (§18.3) — the six feeds the national operations centre is meant to receive.

The spec fixes a granularity per feed, and two of them carry a suppression rule that is a privacy
control rather than a formatting choice: geofence events are "aggregated, min cell 10". A feed that
emits a cell of three is not an aggregated feed, it is a location trace with a county label on it,
so `build_geofence_feed` refuses rather than rounding down.

Every builder is pure: it takes what the services hold and returns the wire payload plus the number
of cells it withheld. Suppression is counted in *cells*, never in rows — rows folded into an
aggregate were merged, not dropped, and a count that conflates the two tells an operator records
were withheld when they were actually included.
"""
from typing import Any

from afya.ai.views import AggregateCell
from afya.community.views import MisinfoCluster

# §19.3 / §17.2: no aggregate may describe fewer than this many people. The AI module enforces the
# same floor on hotspot cells; it is restated here because this is a second egress path and a rule
# enforced at one exit is not enforced.
MIN_CELL = 10

FEED_GRANULARITY: dict[str, str] = {
	'symptom_reports': 'sub_county',
	'case_reports': 'facility',
	'geofence_events': 'aggregated_min_cell_10',
	'misinformation_flags': 'topic_and_county',
	'early_warning': 'sub_county',
	'resource_deployment': 'county',
}

FEED_CADENCE: dict[str, str] = {
	'symptom_reports': 'hourly',
	'case_reports': 'realtime',
	'geofence_events': 'hourly',
	'misinformation_flags': 'hourly',
	'early_warning': 'daily',
	'resource_deployment': 'daily',
}


def build_symptom_feed(cells: list[AggregateCell]) -> tuple[list[dict[str, Any]], int]:
	"""App → PHEOC, sub-county, hourly. Counts only; a cell is a denominator, never a person."""
	rows: list[dict[str, Any]] = []
	dropped = 0
	for c in cells:
		if c.population < MIN_CELL:
			dropped += 1  # too small to describe without describing an individual
			continue
		rows.append({
			'cell_id': c.cell_id, 'county': c.county, 'granularity': FEED_GRANULARITY['symptom_reports'],
			'fever_reports': c.fever_reports, 'cough_events': c.cough_events,
			'facility_reports': c.facility_reports, 'population': c.population,
		})
	return rows, dropped


def build_case_feed(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
	"""App → PHEOC, facility, real-time. A case report is identified by its reference, never by the
	patient: `patient_ref` is dropped here, so the feed cannot become a second copy of the case file."""
	assert all('report_id' in c and 'county' in c for c in cases), 'a case feed row needs an id and a county'
	rows = [
		{
			'report_id': c['report_id'], 'county': c['county'], 'facility': c.get('facility', c.get('community', 'unknown')),
			'suspected_disease': c.get('suspected_disease', 'unknown'), 'status': c.get('status', 'reported'),
			'granularity': FEED_GRANULARITY['case_reports'],
		}
		for c in cases
	]
	return rows, 0


def build_geofence_feed(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
	"""App → PHEOC, hourly, suppressed below 10 people per cell.

	An entry/exit event is the closest thing in the product to a movement trace. Emitting them
	individually would hand the national dashboard a stream of who-went-where, which is why the
	spec requires aggregation and why this refuses a cell that is too small instead of emitting it
	with a caveat.

	The floor is on distinct subjects, not events: ten visits by four people is a cell of four, and
	counting events would clear the floor with a cell that describes those four.
	"""
	by_cell: dict[str, dict[str, Any]] = {}
	for e in events:
		cell = str(e['cell_id'])
		row = by_cell.setdefault(cell, {'cell_id': cell, 'county': e['county'], 'entries': 0, 'exits': 0, 'distinct_subjects': set()})
		row['entries'] += int(e.get('direction') == 'entry')
		row['exits'] += int(e.get('direction') == 'exit')
		if e.get('subject_ref'):
			row['distinct_subjects'].add(e['subject_ref'])
	out: list[dict[str, Any]] = []
	dropped = 0
	for row in by_cell.values():
		subjects = row.pop('distinct_subjects')
		if len(subjects) < MIN_CELL:
			dropped += 1
			continue
		out.append({**row, 'distinct_subjects': len(subjects), 'granularity': FEED_GRANULARITY['geofence_events']})
	return out, dropped


def build_misinformation_feed(clusters: list[MisinfoCluster]) -> tuple[list[dict[str, Any]], int]:
	"""App → PHEOC, topic and county, hourly. The cluster is already a topic, so no per-person data
	can appear here; the correction text is included because the dashboard is also a publishing surface."""
	rows = [
		{
			'topic': c.topic, 'reports': c.reports, 'velocity': c.velocity, 'counties': c.counties,
			'status': c.status, 'correction': c.correction, 'granularity': FEED_GRANULARITY['misinformation_flags'],
		}
		for c in clusters
	]
	return rows, 0


def build_early_warning_feed(assessments: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
	"""AI → PHEOC, sub-county, daily. Never auto-publishes (§19.3): the feed carries the assessment
	and its reasons, and a human decides what becomes an alert."""
	assert all('county' in a for a in assessments), 'an early-warning row needs a county'
	rows = [
		{
			'county': a['county'], 'disease': a.get('disease', 'evd'), 'z_score': a.get('z_score'),
			'band': a.get('band'), 'reasons': a.get('reasons', []), 'public_alert': False,
			'granularity': FEED_GRANULARITY['early_warning'],
		}
		for a in assessments
	]
	return rows, 0


def build_resource_feed(recommendations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
	"""AI → PHEOC, county, daily. A recommendation is advice to a human, so it is never marked
	actioned by this system."""
	assert all('county' in r for r in recommendations), 'a resource row needs a county'
	rows = [
		{
			'county': r['county'], 'resource': r['resource'], 'quantity': r.get('quantity'),
			'rationale': r.get('rationale', ''), 'auto_actioned': False,
			'granularity': FEED_GRANULARITY['resource_deployment'],
		}
		for r in recommendations
	]
	return rows, 0


BUILDERS: dict[str, Any] = {
	'symptom_reports': build_symptom_feed,
	'case_reports': build_case_feed,
	'geofence_events': build_geofence_feed,
	'misinformation_flags': build_misinformation_feed,
	'early_warning': build_early_warning_feed,
	'resource_deployment': build_resource_feed,
}

# Two feeds take a typed model rather than a loose dict, because their builders read attributes
# rather than keys. Naming the model per feed keeps one dispatch point (`build`) instead of a
# branch inside the route, which is where a feed would eventually be added without its coercion.
SOURCE_MODEL: dict[str, Any] = {
	'symptom_reports': AggregateCell,
	'misinformation_flags': MisinfoCluster,
	'case_reports': None,
	'geofence_events': None,
	'early_warning': None,
	'resource_deployment': None,
}


def build(feed: str, rows: list[Any]) -> tuple[list[dict[str, Any]], int]:
	"""Build one feed from its raw source rows. The single entry point the route calls.

	Returns the wire rows and the number of *cells withheld* by the min-cell floor. An empty list is
	a quiet hour, not an error — the push refuses an empty batch on its own, so the distinction
	stays at the transport rather than being pre-empted here.
	"""
	assert feed in BUILDERS, f'unknown PHEOC feed {feed}'
	model = SOURCE_MODEL[feed]
	parsed = [model(**r) for r in rows] if model is not None else rows
	out, dropped = BUILDERS[feed](parsed)
	wire = [dict(r) for r in out]
	assert all(isinstance(r, dict) for r in wire), 'a built feed row must be plain data'
	assert dropped <= len(parsed), 'cannot withhold more cells than were offered'
	return wire, dropped


assert set(BUILDERS) == set(FEED_GRANULARITY) == set(FEED_CADENCE) == set(SOURCE_MODEL), 'every §18.3 feed needs a builder, a granularity, a cadence and a declared source model'

