"""Gate: every feature the spec names must resolve in the registry.

The failure this exists to prevent is silent: a domain gets a namespace in §7 but never gets
built, and the README keeps claiming the product is complete. Reading ids out of the spec text
(rather than a hand-copied list) means a new feature added to the spec fails CI until it is
registered.
"""
import re
from pathlib import Path

from afya.registry.service import FeatureRegistry, Tier

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

# The registry's id grammar, so the gate cannot drift from what an id actually looks like.
FEATURE_ID = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

# §7.3 and Appendix B write a span of ids as `AI-004…005`, and the ellipsis form hides every id in
# the middle from a literal scan. `AI-005` appears in the spec in no other spelling, so the gate was
# blind to it: deleting it from the registry left all six tests green. Expanding the ranges is the
# fix, and `_spec_ids` is asserted to see both ends of every range so a new span cannot reintroduce
# the blind spot.
ID_RANGE = re.compile(r'\b([A-Z]{2,4})-(\d{3})…(\d{3})\b')


def _spec_ids() -> set[str]:
	"""Every feature id the spec names, in either spelling — literal or inside a range.

	The appendix tables are the authoritative index; ids elsewhere are cross-references and
	occasionally a typo, so we assert on the appendix and report the rest. The range expansion is not
	a refinement of that: a range is how the appendix itself writes a span, so an id reachable only
	through one is a feature the gate would otherwise never check.
	"""
	text = SPEC.read_text(encoding='utf-8')
	ids = set(FEATURE_ID.findall(text))
	for prefix, first, last in ID_RANGE.findall(text):
		assert int(first) <= int(last), f'§7.3 writes a backwards range: {prefix}-{first}…{last}'
		ids |= {f'{prefix}-{n:03d}' for n in range(int(first), int(last) + 1)}
	return ids


def test_gate_catches_a_missing_feature() -> None:
	"""Canary. The gate must fail on an id that is genuinely absent from the registry."""
	reg = FeatureRegistry()
	assert 'MON-001' in _spec_ids(), 'the extractor must find real spec ids'
	try:
		reg.get('ZZZ-999')
	except KeyError:
		pass
	else:
		raise AssertionError('a bogus id must not resolve — the gate would pass on anything')


def test_the_extractor_sees_an_id_written_only_as_a_range() -> None:
	"""The canary that was missing. `AI-005` is named in the spec once, inside `AI-004…005`, and
	nowhere literally — so the literal scan could not see it and deleting it from the registry left
	this file green. A gate that never checks a feature is not a gate over it, and the failure mode
	is a feature disappearing with nothing reporting it."""
	ids = _spec_ids()
	assert 'AI-005' in ids, 'a range endpoint must expand into the ids it spans'
	assert 'AI-004' in ids
	assert ID_RANGE.search(SPEC.read_text(encoding='utf-8')), \
		'the spec no longer writes any range — this test has stopped testing the range branch'
	reg = FeatureRegistry()
	assert all(_resolves(reg, fid) for fid in ('AI-004', 'AI-005')), \
		'both ends of §7.3\'s cross-cutting AI range must resolve'


def test_every_spec_id_resolves() -> None:
	reg = FeatureRegistry()
	missing = sorted(fid for fid in _spec_ids() if not _resolves(reg, fid))
	assert missing == [], f'spec features with no registry entry: {missing}'


def _resolves(reg: FeatureRegistry, fid: str) -> bool:
	"""Aliases count as resolving: the shipped id differs from the spec's spelling (§10.1)."""
	try:
		reg.get(fid)
	except KeyError:
		return False
	return True


def test_registry_ids_all_use_a_spec_namespace() -> None:
	"""Guards against a typo'd prefix creating a feature that is really a spec feature misfiled."""
	reg = FeatureRegistry()
	for spec in reg.FEATURES:
		assert FEATURE_ID.fullmatch(spec.id), f'{spec.id} is not a well-formed feature id'
		assert spec.name.strip(), f'{spec.id} has no name'
		assert spec.channels, f'{spec.id} declares no delivery channel'


def test_registry_has_no_duplicate_ids() -> None:
	reg = FeatureRegistry()
	ids = [s.id for s in reg.FEATURES]
	assert len(ids) == len(set(ids)), 'duplicate feature ids in the registry'


def test_every_tier_is_populated() -> None:
	"""A tier with no features means either the spec or the registry lost a domain."""
	reg = FeatureRegistry()
	for tier in Tier:
		assert reg.by_tier(tier), f'tier {tier.name} has no registered features'


def test_tier4_is_dormant_until_activated() -> None:
	"""§11.1: outbreak superpowers are dark until PHEOC authorises the event."""
	reg = FeatureRegistry()
	assert not reg.tier4_active(), 'Tier 4 must start dormant'
	assert reg.dormant(), 'dormant() must name the features held back'
	active = {s.id for s in reg.available()}
	assert not (active & {s.id for s in reg.dormant()}), 'dormant features must not be available'
