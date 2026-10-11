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


def test_the_four_sensor_ids_the_summary_flattens_are_recorded_not_reported() -> None:
	"""§7.3 lists `SENS-001…008` under Tier 4; §14 gives each sensor its own tier, and the registry
	follows §14. The four that differ are recorded as divergences, and both crossings must exclude
	them — a gate that re-reported a resolved divergence on every run is one whose real findings get
	ignored."""
	from afya.registry.taxonomy import DIVERGENCES
	from afya.registry.service import FeatureRegistry
	reg = FeatureRegistry()
	assert sorted(DIVERGENCES) == ['SENS-003', 'SENS-005', 'SENS-006', 'SENS-007']
	assert reg.ebola_specific_mismatches() == [], 'the recorded divergences are not findings'
	assert reg.spec_tier_mismatches() == {}
	# The registry follows §14: these four are available before an outbreak.
	assert all(reg.get(i).tier is not Tier.tier4 for i in DIVERGENCES)


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
	§7.3 is a summary and these are features the sections define without the summary catching up —
	the channel ids are §5's, and the extended INF/REC/SENS ids come from §8–§14."""
	from afya.registry.service import FeatureRegistry
	unmapped = FeatureRegistry().unmapped_features()
	assert 'CHAN-001' in unmapped, '§7.3 names no CHAN id at all'
	assert 'GTM-001' not in unmapped, 'no GTM feature exists; the prefix is declared, not populated'
	assert len(unmapped) == 18


async def test_the_taxonomy_route_serves_the_scheme_and_its_crossings() -> None:
	from afya.service import build_services, create_app
	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		out = (await c.get('/features/taxonomy')).json()
		assert len(out['tiers']) == 4 and len(out['prefixes']) == 16
		assert len(out['tier_map']) == 5
		assert out['ebola_specific_mismatches'] == [] and out['spec_tier_mismatches'] == {}
		assert out['divergences'] and out['strategic_logic']
