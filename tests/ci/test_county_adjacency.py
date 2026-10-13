"""§INF-001's "and neighbouring counties" — the table re-derived from the archived boundaries.

The table in `afya.info.counties` is *derived*, and a derived table nobody re-derives is a list of
strings someone once typed. These tests recompute it from `sources/county-adjacency/` with the same
rule and compare, so the module cannot be edited by hand without a test naming the pair that moved.

The rule, stated once so the test and the source cannot drift: two counties are adjacent when their
simplified polygons share a boundary **segment** at least 1 km long, with coordinates rounded to 3
decimal places (about 110 m at Kenya's latitudes). The threshold is what makes the answer a *border*
rather than a meeting point — four counties meet at one vertex in western Kenya, and a shared vertex
is not a shared border. The rounding is what makes the shared segment *findable*: the two sides of a
border are stored as separate rings, and without rounding their vertices differ in the last decimals
and no edge ever compares equal.
"""
import json
import math
import pathlib

from afya.info.counties import ADJACENCY, COUNTIES, neighbours

GEOJSON = pathlib.Path(__file__).resolve().parents[2] / 'sources/county-adjacency/geoBoundaries-KEN-ADM1_simplified.geojson'
TXT = pathlib.Path(__file__).resolve().parents[2] / 'sources/county-adjacency/county-adjacency.txt'
SHARED_KM = 1.0


def _rings(geometry: dict[str, object]) -> list[list[list[float]]]:
	kind = geometry['type']
	coords = geometry['coordinates']
	if kind == 'Polygon':
		return list(coords)  # type: ignore[arg-type]
	if kind == 'MultiPolygon':
		return [ring for poly in coords for ring in poly]  # type: ignore[union-attr]
	return []


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
	"""Flat-earth distance, which is the right approximation at a county's scale.

	A haversine would be more correct and change no verdict: the threshold is 1 km against segments
	that are either shared (0 km) or not (tens of km), and the two formulas differ by well under a
	percent over a few kilometres. The flat form is used so the derivation is legible beside its
	threshold.
	"""
	(x1, y1), (x2, y2) = a, b
	dy = (y2 - y1) * 111.32
	dx = (x2 - x1) * 111.32 * math.cos(math.radians((y1 + y2) / 2))
	return math.hypot(dx, dy)


def _edges(feature: dict[str, object]) -> dict[frozenset[tuple[float, float]], float]:
	out: dict[frozenset[tuple[float, float]], float] = {}
	for ring in _rings(feature['geometry']):  # type: ignore[arg-type]
		for i in range(len(ring) - 1):
			a = (round(ring[i][0], 3), round(ring[i][1], 3))
			b = (round(ring[i + 1][0], 3), round(ring[i + 1][1], 3))
			if a == b:
				continue
			out[frozenset((a, b))] = _km(a, b)
	return out


def _derive() -> dict[str, list[str]]:
	"""The table, recomputed from the archived file with the rule above."""
	features = json.loads(GEOJSON.read_text())['features']
	edges = {f['properties']['shapeName']: _edges(f) for f in features}
	names = sorted(edges)
	adj: dict[str, list[str]] = {n: [] for n in names}
	for i, a in enumerate(names):
		for b in names[i + 1:]:
			shared = sum(edges[a][e] for e in set(edges[a]) & set(edges[b]))
			if shared >= SHARED_KM:
				adj[a].append(b)
				adj[b].append(a)
	return {n: sorted(v) for n, v in adj.items()}


async def test_the_derivation_reproduces_the_module() -> None:
	"""The whole point of archiving the boundary file: the table can be re-derived, and is.

	Compared as a whole rather than by count. A count survives a swap — if Bungoma gained Busia and
	lost Kakamega the pair total would be unchanged — and the swap is exactly the defect a hand edit
	produces.
	"""
	derived = _derive()
	assert sorted(derived) == list(COUNTIES), 'the module and the source name different counties'
	mismatched = {c: (ADJACENCY[c], tuple(derived[c])) for c in COUNTIES if list(ADJACENCY[c]) != derived[c]}
	assert mismatched == {}, f'the adjacency table no longer matches its source: {mismatched}'


async def test_the_table_has_the_properties_a_border_table_must_have() -> None:
	"""Symmetry, no self-edge, no isolated county — the three a corruption breaks first.

	An asymmetric row is the nastiest of the three: a dashboard would list Bungoma as a neighbour of
	Busia while Busia's own dashboard omitted Bungoma, and both screens would look right in
	isolation.
	"""
	assert len(COUNTIES) == 47, f'Kenya has 47 counties, the table has {len(COUNTIES)}'
	assert all(c not in ADJACENCY[c] for c in COUNTIES), 'a county borders itself'
	asymmetric = [c for c in COUNTIES for n in ADJACENCY[c] if c not in ADJACENCY.get(n, ())]
	assert asymmetric == [], f'adjacency is not symmetric for: {asymmetric}'
	assert all(ADJACENCY[c] for c in COUNTIES), 'a county with no neighbour at all'
	assert sum(len(v) for v in ADJACENCY.values()) // 2 == 113, 'the pair count moved'


async def test_the_counties_whose_geography_is_least_forgiving_are_pinned() -> None:
	"""A per-county check, because the totals above survive a swap between two counties.

	Mandera has exactly one neighbour — it is the corner where Ethiopia and Somalia meet, and a
	table that gave it a second would be inventing a border. Mombasa is a coastal island county with
	two. Nairobi's three are the ones a reader would check by hand.
	"""
	assert neighbours('Mandera') == ('Wajir',), 'Mandera borders Wajir and nothing else'
	assert neighbours('Mombasa') == ('Kilifi', 'Kwale'), 'Mombasa is reached through Kilifi and Kwale'
	assert neighbours('Nairobi') == ('Kajiado', 'Kiambu', 'Machakos'), 'the capital county'
	assert neighbours('Busia') == ('Bungoma', 'Kakamega', 'Siaya'), 'the western border county'
	assert neighbours('Turkana') == ('Baringo', 'Marsabit', 'Samburu', 'West Pokot'), 'the largest county'


async def test_an_unknown_county_answers_with_nothing_rather_than_raising() -> None:
	"""The dashboard is served for a county the caller named, and the risk read already answers an
	unknown name with a defaulted row. A neighbour lookup that raised would 500 the one input the
	rest of the route handles, and the empty tuple is distinguishable from a real county because no
	real county has none (asserted above)."""
	assert neighbours('Atlantis') == ()
	assert neighbours('') == ()
	# And the names are the boundary file's spellings, apostrophe included — the dashboard matches on
	# these strings, so a lookup that missed one would silently drop a neighbour rather than fail.
	assert neighbours("Murang'a") == ('Kiambu', 'Kirinyaga', 'Machakos', 'Nyandarua', 'Nyeri')


async def test_the_archived_text_copy_agrees_with_the_module() -> None:
	"""`sources/INDEX.md` records two artefacts per source: the published file and a text copy. The
	text copy is the one a person reads, so it must not be a stale rendering of an older table."""
	rows: dict[str, list[str]] = {}
	for line in TXT.read_text().splitlines():
		if line.startswith('#') or not line.strip():
			continue
		name, _, rest = line.partition('\t')
		rows[name] = [x.strip() for x in rest.split(',') if x.strip()]
	assert sorted(rows) == list(COUNTIES), 'the text copy names different counties'
	off = {c: (rows[c], list(ADJACENCY[c])) for c in COUNTIES if rows[c] != list(ADJACENCY[c])}
	assert off == {}, f'the archived text copy has drifted from the module: {off}'
	assert '113 adjacent pairs' in TXT.read_text(), 'the text copy no longer states its own count'
