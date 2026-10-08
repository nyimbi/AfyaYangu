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
	assert not FeatureRegistry(Tier4Activation(authorized_by_pheoc=False, dpia_reviewed=True, flag_enabled=True)).tier4_active()
	assert not FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_reviewed=False, flag_enabled=True)).tier4_active()
	assert not FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_reviewed=True, flag_enabled=False)).tier4_active()
	assert FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_reviewed=True, flag_enabled=True)).tier4_active()


def test_get_raises_unknown() -> None:
	with pytest.raises(KeyError):
		FeatureRegistry().get('TRI-003')  # exists but dormant -> still gettable
		FeatureRegistry().get('FAKE-001')