"""Kenya's 47 counties and which of them touch — §INF-001's "and neighbouring counties".

§INF-001 asks for a dashboard of "health risks in the user's county **and neighbouring counties**",
and the repo had no adjacency at all: `CountyRisk` is keyed by a county name and nothing anywhere
recorded that Busia is next to Bungoma. A dashboard scoped to the caller's own county answers a
narrower question than the section asks, and there is no way to widen it without knowing which
counties share a border.

**The table is derived from a boundary file, not typed from memory.** `sources/county-adjacency/`
holds geoBoundaries' `KEN-ADM1` (47 features, 2020 boundaries, public domain), and
`sources/county-adjacency/county-adjacency.txt` is the derivation: two counties are adjacent when
their simplified polygons share a boundary segment at least 1 km long. The threshold is what makes
the answer a border rather than a point — at the four-corner meeting of Kajiado, Narok, Kisii and
Migori a shared *vertex* is not adjacency, and rounding the simplified geometry to 3 decimal places
(about 110 m) is what keeps the shared segments findable on both sides.

**A derived table drifts unless something re-derives it.** `test_county_adjacency.py` recomputes the
pairs from the archived GeoJSON with the same rule and compares them to this module, so the table
cannot be edited by hand without the test saying which pair moved. It also asserts the properties a
border table has to have: symmetry, no self-edge, all 47 counties present, and the two facts that
catch a wholesale corruption — every county has at least one neighbour, and the pair count is 113.

**`Mandera` has exactly one neighbour and that is correct.** It is the county at the Ethiopian and
Somali corner; a table that gave it a second would be inventing a border. The test pins the degree
of the counties whose geography is least forgiving rather than only the total, because a total
survives a swap between two counties that a per-county check does not.
"""
# Derived from `sources/county-adjacency/geoBoundaries-KEN-ADM1_simplified.geojson` by shared
# boundary segment >= 1 km. Regenerate with the rule in `county-adjacency.txt`'s header; do not
# hand-edit a row.
ADJACENCY: dict[str, tuple[str, ...]] = {
	'Baringo': ('Elgeyo-Marakwet', 'Kericho', 'Laikipia', 'Nakuru', 'Samburu', 'Turkana', 'Uasin Gishu', 'West Pokot',),
	'Bomet': ('Kericho', 'Nakuru', 'Narok', 'Nyamira',),
	'Bungoma': ('Busia', 'Kakamega', 'Trans Nzoia',),
	'Busia': ('Bungoma', 'Kakamega', 'Siaya',),
	'Elgeyo-Marakwet': ('Baringo', 'Trans Nzoia', 'Uasin Gishu', 'West Pokot',),
	'Embu': ('Kirinyaga', 'Kitui', 'Machakos', 'Tharaka',),
	'Garissa': ('Isiolo', 'Lamu', 'Tana River', 'Wajir',),
	'Homa Bay': ('Kericho', 'Kisii', 'Kisumu', 'Migori', 'Nyamira', 'Siaya',),
	'Isiolo': ('Garissa', 'Kitui', 'Laikipia', 'Marsabit', 'Meru', 'Samburu', 'Tana River', 'Wajir',),
	'Kajiado': ('Kiambu', 'Machakos', 'Makueni', 'Nairobi', 'Nakuru', 'Narok', 'Taita Taveta',),
	'Kakamega': ('Bungoma', 'Busia', 'Nandi', 'Siaya', 'Trans Nzoia', 'Uasin Gishu', 'Vihiga',),
	'Kericho': ('Baringo', 'Bomet', 'Homa Bay', 'Kisumu', 'Nakuru', 'Nandi', 'Nyamira', 'Uasin Gishu',),
	'Kiambu': ('Kajiado', 'Machakos', "Murang'a", 'Nairobi', 'Nakuru', 'Nyandarua',),
	'Kilifi': ('Kwale', 'Mombasa', 'Taita Taveta', 'Tana River',),
	'Kirinyaga': ('Embu', "Murang'a", 'Nyeri',),
	'Kisii': ('Homa Bay', 'Migori', 'Narok', 'Nyamira',),
	'Kisumu': ('Homa Bay', 'Kericho', 'Nandi', 'Siaya', 'Vihiga',),
	'Kitui': ('Embu', 'Isiolo', 'Machakos', 'Makueni', 'Meru', 'Taita Taveta', 'Tana River', 'Tharaka',),
	'Kwale': ('Kilifi', 'Mombasa', 'Taita Taveta',),
	'Laikipia': ('Baringo', 'Isiolo', 'Meru', 'Nakuru', 'Nyandarua', 'Nyeri', 'Samburu',),
	'Lamu': ('Garissa', 'Tana River',),
	'Machakos': ('Embu', 'Kajiado', 'Kiambu', 'Kitui', 'Makueni', "Murang'a", 'Nairobi',),
	'Makueni': ('Kajiado', 'Kitui', 'Machakos', 'Taita Taveta',),
	'Mandera': ('Wajir',),
	'Marsabit': ('Isiolo', 'Samburu', 'Turkana', 'Wajir',),
	'Meru': ('Isiolo', 'Kitui', 'Laikipia', 'Nyeri', 'Tharaka',),
	'Migori': ('Homa Bay', 'Kisii', 'Narok',),
	'Mombasa': ('Kilifi', 'Kwale',),
	"Murang'a": ('Kiambu', 'Kirinyaga', 'Machakos', 'Nyandarua', 'Nyeri',),
	'Nairobi': ('Kajiado', 'Kiambu', 'Machakos',),
	'Nakuru': ('Baringo', 'Bomet', 'Kajiado', 'Kericho', 'Kiambu', 'Laikipia', 'Narok', 'Nyandarua',),
	'Nandi': ('Kakamega', 'Kericho', 'Kisumu', 'Uasin Gishu', 'Vihiga',),
	'Narok': ('Bomet', 'Kajiado', 'Kisii', 'Migori', 'Nakuru',),
	'Nyamira': ('Bomet', 'Homa Bay', 'Kericho', 'Kisii',),
	'Nyandarua': ('Kiambu', 'Laikipia', "Murang'a", 'Nakuru', 'Nyeri',),
	'Nyeri': ('Kirinyaga', 'Laikipia', 'Meru', "Murang'a", 'Nyandarua',),
	'Samburu': ('Baringo', 'Isiolo', 'Laikipia', 'Marsabit', 'Turkana',),
	'Siaya': ('Busia', 'Homa Bay', 'Kakamega', 'Kisumu', 'Vihiga',),
	'Taita Taveta': ('Kajiado', 'Kilifi', 'Kitui', 'Kwale', 'Makueni', 'Tana River',),
	'Tana River': ('Garissa', 'Isiolo', 'Kilifi', 'Kitui', 'Lamu', 'Taita Taveta',),
	'Tharaka': ('Embu', 'Kitui', 'Meru',),
	'Trans Nzoia': ('Bungoma', 'Elgeyo-Marakwet', 'Kakamega', 'Uasin Gishu', 'West Pokot',),
	'Turkana': ('Baringo', 'Marsabit', 'Samburu', 'West Pokot',),
	'Uasin Gishu': ('Baringo', 'Elgeyo-Marakwet', 'Kakamega', 'Kericho', 'Nandi', 'Trans Nzoia',),
	'Vihiga': ('Kakamega', 'Kisumu', 'Nandi', 'Siaya',),
	'Wajir': ('Garissa', 'Isiolo', 'Mandera', 'Marsabit',),
	'West Pokot': ('Baringo', 'Elgeyo-Marakwet', 'Trans Nzoia', 'Turkana',),
}

COUNTIES: tuple[str, ...] = tuple(sorted(ADJACENCY))

assert len(COUNTIES) == 47, f'Kenya has 47 counties, this table has {len(COUNTIES)}'
assert all(sorted(ADJACENCY[c]) == list(ADJACENCY[c]) for c in COUNTIES), \
	'each row is sorted, so a diff of the table is a diff of the borders'
assert all(c not in ADJACENCY[c] for c in COUNTIES), 'a county is not its own neighbour'
assert all(c in ADJACENCY[n] for c in COUNTIES for n in ADJACENCY[c]), \
	'adjacency is symmetric: if A borders B then B borders A'
assert all(ADJACENCY[c] for c in COUNTIES), 'every county touches at least one other'


def neighbours(county: str) -> tuple[str, ...]:
	"""The counties sharing a border with `county`, in the table's order.

	An unknown county answers with an empty tuple rather than raising. §INF-001's dashboard route is
	served for a county the caller named, and the risk read already answers an unknown name with a
	defaulted row — a neighbour lookup that raised would make the dashboard 500 on the one input the
	rest of the route handles. The empty tuple is the honest answer: this table knows nothing about
	that place, and it is distinguishable from a real county with no neighbours, of which there are
	none (asserted above).
	"""
	return ADJACENCY.get(county, ())
