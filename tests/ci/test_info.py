import pytest

from afya.info.service import InfoService
from afya.info.views import ContentItem, CountyRisk


async def test_dashboard_defaults_low() -> None:
	svc = InfoService()
	assert svc.dashboard('Turkana').risk_level == 'low'
	await svc.set_county_risk(CountyRisk(county='Nairobi', risk_level='high', active_signals=12, bulletin='Stay alert.'))
	assert svc.dashboard('Nairobi').risk_level == 'high'


async def test_content_must_be_harmonised() -> None:
	svc = InfoService()
	base = len(svc.library())
	await svc.upsert_content(ContentItem(item_id='INF-003-1', title='EVD basics', body='...', lang='en'))
	with pytest.raises(AssertionError):
		svc.library()
	await svc.upsert_content(ContentItem(item_id='INF-003-1', title='EVD basics', body='...', lang='en', harmony_tag='official'))
	ids = [c.item_id for c in svc.library()]
	assert 'INF-003-1' in ids and len(ids) == base + 1


def test_decision_tree_malaria_path() -> None:
	svc = InfoService()
	assert 'malaria' in svc.decide('Nairobi', [True, False]).lower()


def test_decision_tree_hotline_path() -> None:
	svc = InfoService()
	assert '719' in svc.decide('Kisumu', [True, True])


def test_decision_tree_healthy() -> None:
	svc = InfoService()
	assert svc.decide('Kisumu', [False, False]) == 'No action needed.'


def test_tree_depth_bounded() -> None:
	svc = InfoService()
	with pytest.raises(AssertionError):
		svc.decide('Kisumu', [True, False, True, False])


def test_hotline_directory_includes_719() -> None:
	svc = InfoService()
	numbers = [h.number for h in svc.hotlines()]
	assert '719' in numbers and len(numbers) == 2


def test_seed_corpus_en_and_sw() -> None:
	from afya.info.service import InfoService as IS
	svc = IS()
	en = svc.library('en')
	sw = svc.library('sw')
	assert len(en) >= 5 and len(sw) >= 5
	assert all(c.harmony_tag for c in en + sw)
	assert svc.seed() == svc.seed()  # idempotent