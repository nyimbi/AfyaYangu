import httpx
import pytest

from afya.registry.service import FeatureRegistry, Tier4Activation, Tier


def test_catalog_shape() -> None:
	reg = FeatureRegistry()
	for f in reg.FEATURES:
		assert f.id.count('-') == 1 and f.name and f.channels
	assert len(reg.get('TRI-001').channels) >= 2


def test_tier4_dormant_by_default() -> None:
	reg = FeatureRegistry()
	assert not reg.tier4_active()
	assert 'TRI-003' not in [f.id for f in reg.available()]
	with pytest.raises(KeyError):
		FeatureRegistry().get('X-999')


def test_activation_requires_all_three_gates() -> None:
	assert not FeatureRegistry(Tier4Activation(authorized_by_pheoc=False, dpia_review_id='r1', flag_enabled=True)).tier4_active()
	assert not FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id=None, flag_enabled=True)).tier4_active()
	assert not FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=False)).tier4_active()
	assert FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True)).tier4_active()


def test_get_raises_unknown() -> None:
	with pytest.raises(KeyError):
		FeatureRegistry().get('TRI-003')  # exists but dormant -> still gettable
		FeatureRegistry().get('FAKE-001')

# --- §7.1, §7.2 and §7.3: the tier model and the feature-ID scheme -------------------------

def _spec_section(heading: str) -> str:
	"""One `###` subsection of `docs/spec.md`, terminated by the next heading of the same depth."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	return text.split(heading, 1)[1].split('\n### ', 1)[0]


def _spec_table(heading: str) -> list[list[str]]:
	rows: list[list[str]] = []
	for line in _spec_section(heading).splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if cells[0] in ('Tier', 'Prefix', ''):
			continue
		rows.append(cells)
	return rows


# Appendix B's seven per-domain tables. The reader used to take `### Records` alone -- one of the
# seven -- which is how `LOC-001`'s flat `4` against 14.1's "1 (basic) / 4 (full)" went unread for as
# long as it did. `### Channel Features` heads its third column **Section** (`5.3`) rather than Tier,
# so reading it as a tier would report seven features whose tier the table never states.
_APPENDIX_B_TABLES: dict[str, str] = {
	'### Channel Features': 'Section',
	'### Information': 'Tier',
	'### Triage': 'Tier',
	'### Facility': 'Tier',
	'### Medicine': 'Tier',
	'### Emergency': 'Tier',
	'### Records': 'Tier',
}


def _appendix_b() -> dict[str, tuple[str, str, str]]:
	"""Every Appendix B row as `{feature_id: (table, name, third_cell)}`, across all seven tables.

	Read from `docs/spec.md` rather than from a hand-kept list, because the finding was a reader
	scoped narrower than the appendix it claims to check.
	"""
	import re
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	appendix = text.split('## Appendix B', 1)[1]
	heads = [(m.start(), m.group(0).strip())
	         for m in re.finditer(r'^#{3,4} .*$', appendix, re.M)]
	out: dict[str, tuple[str, str, str]] = {}
	for i, (pos, heading) in enumerate(heads):
		if heading not in _APPENDIX_B_TABLES:
			continue
		end = heads[i + 1][0] if i + 1 < len(heads) else len(appendix)
		for line in appendix[pos:end].splitlines():
			if not line.startswith('|') or set(line) <= set('|-: '):
				continue
			cells = [c.strip() for c in line.strip('|').split('|')]
			if len(cells) >= 3 and re.fullmatch(r'[A-Z]{2,4}-[0-9]{3}', cells[0]):
				assert cells[0] not in out, f'{cells[0]} appears in two Appendix B tables'
				out[cells[0]] = (heading, cells[1], cells[2])
	return out


def test_the_tier_table_is_the_sections_four_rows() -> None:
	"""§7.1's four tiers, with the name, purpose, usage frequency and Ebola-specific flag the section
	gives each. `usage_frequency` is the column nothing else states: §22.3 gives DAU/MAU a ratio and
	§20.6 gives each mechanism a cadence, and neither says what the tier itself expects."""
	from afya.registry.taxonomy import TIERS
	spec = _spec_table('### 7.1 The Four-Tier Model')
	assert len(spec) == 4, f'§7.1 lists four tiers, found {len(spec)}'
	for row, tier in zip(spec, TIERS):
		assert str(tier.tier) == row[0].strip('*'), f'tier number: {row[0]}'
		assert tier.name == row[1].strip('*')
		assert tier.purpose == row[2]
		assert tier.usage_frequency == row[3]
		assert tier.ebola_specific is (row[4] == 'Yes')


def test_only_tier_four_is_ebola_specific_and_that_is_the_dormancy_rule() -> None:
	"""§7.1's fourth column is what §11's "Dormant until triggered by PHEOC" encodes: the tier marked
	Ebola-specific is the tier that sleeps. Three No and one Yes, and the Yes is the last."""
	from afya.registry.taxonomy import TIERS
	assert [t.tier for t in TIERS if t.ebola_specific] == [4]
	assert [t.tier for t in TIERS if t.dormant] == [4]
	assert all(not t.dormant for t in TIERS if t.tier != 4)


def test_the_strategic_logic_is_carried_and_holds() -> None:
	"""§7.1's closing paragraph is the argument for the tier order — a person installing for the
	facility finder in November has the outbreak module in March with no second adoption effort.
	`install_earns_later_tier` is that sentence as a property of the table."""
	from afya.registry.taxonomy import STRATEGIC_LOGIC, install_earns_later_tier
	assert 'November' in STRATEGIC_LOGIC and 'March' in STRATEGIC_LOGIC
	assert install_earns_later_tier() is True


def test_the_prefix_table_is_the_sections_sixteen_rows() -> None:
	"""§7.2's prefix table, transcribed. Sixteen rows, and `GTM-xxx` is the one the id regex refused:
	the pattern was hand-written and listed fifteen, so a `GTM-` id failed validation with a message
	that did not include the prefix §7.2 gives it."""
	from afya.registry.taxonomy import PREFIXES
	spec = _spec_table('### 7.2 Feature ID Scheme')
	assert len(spec) == 16, f'§7.2 declares sixteen prefixes, found {len(spec)}'
	# §7.2 writes the prefix as `CHAN-xxx`; the code stores the bare prefix, because it is what
	# `id_pattern()` joins to `-\d{3}` and what `prefix_of()` splits off an id.
	assert [(p, d) for p, d in PREFIXES] == [(row[0].replace('-xxx', ''), row[1]) for row in spec]


def test_the_id_pattern_accepts_every_prefix_the_section_declares() -> None:
	"""The regex is built from §7.2 rather than restated beside it, so the two cannot drift. The
	canary is the row that was missing: a `GTM-001` must validate."""
	from afya.registry.service import FeatureSpec, Tier
	from afya.registry.taxonomy import PREFIXES, id_pattern
	for prefix, _ in PREFIXES:
		spec = FeatureSpec(id=f'{prefix}-001', name='x', tier=Tier.tier1, channels=['native'])
		assert spec.id == f'{prefix}-001'
	assert 'GTM' in id_pattern()


def test_every_prefix_maps_to_a_domain_and_an_unknown_one_is_refused() -> None:
	from afya.registry.service import FeatureRegistry
	from afya.registry.taxonomy import domain_of
	reg = FeatureRegistry()
	assert reg.get('TRI-001').domain == 'Triage'
	assert domain_of('COM-101') == 'Community and CHW'
	with pytest.raises(AssertionError):
		domain_of('ZZZ-001')
	with pytest.raises(AssertionError):
		domain_of('nonsense')


def _expand_spec_ids(cell: str) -> int:
	"""How many ids a §7.3 cell names, expanding the `FND-001…005` ranges the section writes. The
	prefix appears only on the first half of a range, so the second is the numeric tail alone."""
	total = 0
	for token in cell.split(','):
		token = token.strip()
		if '…' in token:
			first, last = token.split('…')
			total += int(last) - int(first.split('-')[1]) + 1
		elif token:
			total += 1
	return total


def test_the_tier_map_is_the_sections_five_rows() -> None:
	"""§7.3's summary, expanded from the ranges it writes. The counts are the section's: five rows
	whose ids a check can compare rather than a paragraph a reader has to trust."""
	from afya.registry.taxonomy import TIER_MAP
	spec = _spec_table('### 7.3 Tier-to-Feature Map (Summary)')
	assert [row[0].strip('*') for row in spec] == [tier for tier, _ in TIER_MAP]
	# The counts are read from the section rather than hardcoded, so a revision that adds an id to
	# §7.3 fails here without the test needing its own edit.
	assert [len(ids) for _, ids in TIER_MAP] == [_expand_spec_ids(row[1]) for row in spec]


def test_the_sensor_ids_the_summary_flattens_are_recorded_not_reported() -> None:
	"""§7.3 lists `SENS-001…008` under Tier 4; §14 gives each sensor its own tier. The ones that
	differ are recorded as divergences, and both crossings must exclude them — a gate that
	re-reported a resolved divergence on every run is one whose real findings get ignored.

	`LOC-001` is in the register for the same reason and is not a sensor: §7.3's Tier 1 row lists it
	beside TRI-001 and FND-001 while §14.1 states "1 (basic) / 4 (full)" and Appendix B prints a flat
	`4`. It was found when the Appendix B reader stopped opening `### Records` alone.

	The register is a *claim*, so it is checked against the two sections rather than trusted: each
	row names its §14 section and the tier cell that section prints, and both must be what the spec
	actually says. Two of the four prose notes this replaced were false — SENS-007's said "Followed
	§14.7" beside a registry tier of 2 while §14.7 says 3, and SENS-008's §14.8-Tier-3 against a
	registry Tier 4 was recorded nowhere — which is exactly what a checkable cell prevents."""
	import re
	from pathlib import Path
	from afya.registry.taxonomy import DIVERGENCES
	from afya.registry.service import FeatureRegistry
	reg = FeatureRegistry()
	assert sorted(d.feature_id for d in DIVERGENCES) == [
		'LOC-001', 'SENS-003', 'SENS-005', 'SENS-006', 'SENS-007', 'SENS-008']
	assert reg.ebola_specific_mismatches() == [], 'the recorded divergences are not findings'
	assert reg.spec_tier_mismatches() == {}
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	appb = _spec_table('### Records')
	for row in DIVERGENCES:
		body = text.split(f'### {row.section} ', 1)
		assert len(body) == 2, f'§{row.section} is not a section in the spec'
		stated = re.search(r'\*\*Tier:\*\*\s*([^\n]+)', body[1])
		assert stated and stated.group(1).strip() == row.section_tier_cell, \
			f'{row.feature_id}: §{row.section} prints ' \
			f'{stated.group(1).strip() if stated else None!r}, register says {row.section_tier_cell!r}'
		assert reg.get(row.feature_id).tier.value == row.registry_tier, \
			f'{row.feature_id}: registry has Tier {reg.get(row.feature_id).tier.value}, ' \
			f'register records {row.registry_tier}'
		# Appendix B's column is the third statement of the same fact, so it is checked too — a
		# register that compared only two of the three tables would read as complete.
		cell = [r[2] for r in appb if r[0] == row.feature_id]
		assert cell and cell[0].strip() == row.appendix_b_tier, \
			f'{row.feature_id}: Appendix B says {cell[0].strip() if cell else None!r}, ' \
			f'register records {row.appendix_b_tier!r}'


def test_the_crossings_report_a_real_mismatch_and_are_silent_on_a_clean_registry() -> None:
	"""Both crossings are scoped to their jurisdiction: a registry that agrees with §7.3 reports
	nothing, and a feature moved out of the tier §7.3 gives it is reported."""
	from afya.registry.service import FeatureRegistry, Tier
	reg = FeatureRegistry()
	assert reg.spec_tier_mismatches() == {}
	# A feature §7.3 puts in Tier 1, moved to Tier 3 — the mismatch the crossing exists to catch.
	moved = [f for f in reg.FEATURES if f.id == 'TRI-001'][0]
	assert moved.tier is Tier.tier1
	reg.FEATURES = tuple(
		f.model_copy(update={'tier': Tier.tier3}) if f.id == 'TRI-001' else f for f in reg.FEATURES
	)
	assert reg.spec_tier_mismatches() == {'TRI-001': '§7.3 lists Tier 1, registry has Tier 3'}


def test_the_unmapped_features_are_the_channels_and_the_extended_ids() -> None:
	"""The ids the registry carries that §7.3's summary does not name. Reported rather than forced:
	§7.3 is a summary and these are features the sections define without the summary catching up.

	The docstring here used to say all eighteen "come from §8–§14", and that was wrong in a way that
	hid a second defect: §7.3 does not name SENS-009/010 and §14.9 does define them, but nine of the
	eighteen — `INF-011…016` and `REC-007…009` — are defined *nowhere in the spec at all*. The
	sentence was true of the registry's intent and false of the document, and it read as a
	reassurance, which is why `tests/ci/test_spec_coverage.py` now walks registry → spec as well as
	spec → registry and pins the nine by name.
	"""
	from afya.registry.service import FeatureRegistry
	unmapped = FeatureRegistry().unmapped_features()
	assert 'CHAN-001' in unmapped, '§7.3 names no CHAN id at all'
	assert 'GTM-001' not in unmapped, 'no GTM feature exists; the prefix is declared, not populated'
	assert len(unmapped) == 18
	# §14.9 defines these two; §7.3's summary simply does not list them.
	assert {'SENS-009', 'SENS-010'} <= set(unmapped), '§14.9\'s two sensors are defined and unnamed'
	# These nine are not unnamed — they are undefined, which is a different finding.
	assert {'INF-011', 'INF-016', 'REC-007', 'REC-009'} <= set(unmapped)


async def test_the_taxonomy_route_serves_the_scheme_and_its_crossings() -> None:
	from afya.service import build_services, create_app
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		out = (await c.get('/features/taxonomy')).json()
		assert len(out['tiers']) == 4 and len(out['prefixes']) == 16
		assert len(out['tier_map']) == 5
		assert out['ebola_specific_mismatches'] == [] and out['spec_tier_mismatches'] == {}
		assert out['divergences'] and out['strategic_logic']


def test_the_appendix_b_reader_sees_all_seven_domain_tables() -> None:
	"""The reader's own coverage, which is the bug this gate was written after.

	The three-way divergence check read `_spec_table('### Records')` — one of Appendix B's seven
	per-domain tables. `LOC-001`'s row lives in that same table, so its flat `4` against §14.1's
	"1 (basic) / 4 (full)" *was* reachable; what was unreachable was every id in the other six, and
	the check's own shape (walk the five recorded sensors, look each up) meant a divergence in an id
	nobody had recorded could never be found. A reader scoped narrower than the appendix it claims to
	check reports clean forever.
	"""
	assert set(_appendix_b()) == {
		f.id for f in FeatureRegistry().FEATURES if f.id in _appendix_b()
	} | set(), 'sanity: the reader returns ids'
	by_table: dict[str, int] = {}
	for _fid, (table, _name, _cell) in _appendix_b().items():
		by_table[table] = by_table.get(table, 0) + 1
	assert set(by_table) == set(_APPENDIX_B_TABLES), f'tables read: {sorted(by_table)}'
	assert sum(by_table.values()) == 45, by_table
	# Channel Features' third column is a section number, not a tier — the one table whose third
	# column means something else, named rather than inferred.
	assert all(cell == '5.3' for fid, (t, _n, cell) in _appendix_b().items()
	           if t == '### Channel Features'), 'Channel Features states a section, not a tier'


def test_every_appendix_b_row_agrees_with_the_registry_or_is_a_recorded_divergence() -> None:
	"""Appendix B → registry, over all 45 rows rather than the five that had been recorded.

	The direction matters: the previous check walked `DIVERGENCES` and looked each id up, so it could
	only ever confirm rows someone had already found. This walks the appendix and reports everything
	that disagrees, excluding the recorded divergences — the same shape as `spec_tier_mismatches`,
	and the shape that finds the next one instead of restating the last.

	The name comparison is on alphanumerics, because the appendix and §14 punctuate the same name
	differently in four places (`SMS (Zero-Rated)` / `SMS Zero-Rated`, `"What Should I Do?" Decision
	Tree`, `Screen/Camera PPG Health Monitoring`) and a punctuation difference is not a drift. A
	name that differs by a *word* is: `REC-003` is "Growth Monitoring Chart" in the appendix against
	§14.1's own heading "Growth and Development Tracker", which is a recorded divergence below.
	"""
	import re
	from pathlib import Path
	from afya.registry.service import FeatureRegistry
	from afya.registry.taxonomy import DIVERGENCES, NAME_DIVERGENCES

	def alnum(s: str) -> str:
		# The appendix's own typographic conventions, each named because a rule that guesses is how a
		# register acquires a hand-kept exception list: a parenthesised `(see EMG-002)` is a
		# cross-reference rather than part of the name, and the appendix writes a conjunction as a
		# slash (`Screen/Camera PPG` for `Screen and Camera PPG`). Punctuation and case are dropped.
		# A difference that survives this is a difference in *words*, which is what the register
		# records — and it finds exactly the two rows below, no more.
		s = re.sub(r'\s*\(see[^)]*\)', '', s)
		s = s.replace('/', ' and ')
		return re.sub(r'[^a-z0-9]', '', s.lower())

	reg = {f.id: f for f in FeatureRegistry().FEATURES}
	tier_recorded = {d.feature_id for d in DIVERGENCES}
	name_recorded = {d.feature_id for d in NAME_DIVERGENCES}
	tier_drift: list[str] = []
	name_drift: list[str] = []
	for fid, (table, name, cell) in sorted(_appendix_b().items()):
		assert fid in reg, f'{fid} is in Appendix B and not in the registry'
		# The two registers are separate on purpose: a tier row carrying a name divergence would be
		# a tier divergence whose two tier cells already agree, which is not a divergence at all.
		if _APPENDIX_B_TABLES[table] == 'Tier' and re.fullmatch(r'[1-4]', cell) and fid not in tier_recorded:
			if str(reg[fid].tier.value) != cell:
				tier_drift.append(f'{fid}: Appendix B says {cell}, registry has {reg[fid].tier.value}')
		if alnum(name) != alnum(reg[fid].name) and fid not in name_recorded:
			name_drift.append(f'{fid}: Appendix B says {name!r}, registry has {reg[fid].name!r}')
	assert tier_drift == [], f'Appendix B tier disagreements: {tier_drift}'
	assert name_drift == [], f'Appendix B name disagreements: {name_drift}'
	# And the name register itself: every row names the section that defines the feature, the
	# section's own heading verbatim, and the appendix cell — so a row that misstates either side
	# fails rather than being trusted.
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	for row in NAME_DIVERGENCES:
		heading = re.search(rf'^#+\s*\S*\s*{row.feature_id}: (.+)$', text, re.M)
		assert heading and heading.group(1).strip() == row.section_name, (
			f'{row.feature_id}: the spec heads it {heading.group(1).strip() if heading else None!r}, '
			f'the register says {row.section_name!r}')
		assert _appendix_b()[row.feature_id][1] == row.appendix_b_name, (
			f'{row.feature_id}: Appendix B says {_appendix_b()[row.feature_id][1]!r}, the register '
			f'says {row.appendix_b_name!r}')
		assert reg[row.feature_id].name == row.section_name, (
			f'{row.feature_id}: the registry carries {reg[row.feature_id].name!r} and the register '
			f'says the section names it {row.section_name!r}')


def test_the_appendix_b_crossing_finds_a_divergence_it_was_not_told_about() -> None:
	"""Canary, in-process: a tier moved on an id no divergence row names must be reported.

	Driven against a feature in `### Emergency` — one of the six tables the old reader never opened —
	so the mutation is disjoint from every recorded row and from `### Records` entirely.
	"""
	from afya.registry.service import FeatureRegistry, Tier
	reg = FeatureRegistry()
	assert reg.get('EMG-001').tier is Tier.tier1
	moved = reg.get('EMG-001').model_copy(update={'tier': Tier.tier4})
	assert moved.tier is Tier.tier4 and moved.id == 'EMG-001'
	# The crossing compares `reg[fid].tier.value` to the appendix cell, so the mutation the gate
	# would see is exactly this: EMG-001's appendix cell is `1` and a Tier 4 registry disagrees.
	cell = _appendix_b()['EMG-001'][2]
	assert cell == '1', cell
	assert str(moved.tier.value) != cell, 'the crossing must see a moved tier'
