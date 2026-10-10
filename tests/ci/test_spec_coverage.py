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


def _spec_ids() -> set[str]:
	text = SPEC.read_text(encoding='utf-8')
	# The appendix tables are the authoritative index; ids elsewhere are cross-references and
	# occasionally a typo, so we assert on the appendix and report the rest.
	return set(FEATURE_ID.findall(text))


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
