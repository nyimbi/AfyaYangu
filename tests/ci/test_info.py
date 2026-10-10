import pytest

from afya.info.service import InfoService
from afya.info.views import ContentItem, ContentStage, CountyRisk


async def test_dashboard_defaults_low() -> None:
	svc = InfoService()
	assert svc.dashboard('Turkana').risk_level == 'low'
	await svc.set_county_risk(CountyRisk(county='Nairobi', risk_level='high', active_signals=12, bulletin='Stay alert.'))
	assert svc.dashboard('Nairobi').risk_level == 'high'


def _item(**overrides: object) -> ContentItem:
	"""A published, fully-governed item — the shape §6.5 requires and nothing less."""
	base: dict[str, object] = {
		'item_id': 'INF-003-1', 'title': 'EVD basics', 'body': '...', 'lang': 'en',
		'harmony_tag': 'official', 'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1, 'stage': ContentStage.published,
	}
	return ContentItem(**{**base, **overrides})  # type: ignore[arg-type]


async def test_content_must_be_harmonised() -> None:
	svc = InfoService()
	base = len(svc.library())
	await svc.upsert_content(_item(harmony_tag=None))
	with pytest.raises(AssertionError):
		svc.library()
	await svc.upsert_content(_item())
	ids = [c.item_id for c in svc.library()]
	assert 'INF-003-1' in ids and len(ids) == base + 1


def test_an_item_with_nobody_accountable_for_it_cannot_be_constructed() -> None:
	"""§6.5: every item has an owner, a reviewer, a date and a version. The model refuses an item
	without them, so an unattributed item is a construction error rather than a blank table cell."""
	from pydantic import ValidationError
	for missing in ('owner', 'reviewer', 'reviewed_on_iso', 'version'):
		fields = {
			'item_id': 'X', 'title': 't', 'body': 'b', 'lang': 'en',
			'owner': 'o', 'reviewer': 'r', 'reviewed_on_iso': '2026-10-01', 'version': 1,
		}
		del fields[missing]
		with pytest.raises(ValidationError):
			ContentItem(**fields)  # type: ignore[arg-type]


def test_only_published_content_is_served() -> None:
	"""§6.5: a draft, an item awaiting back-translation, or one retired for being wrong must not
	reach a screen. The stage filter lives in `library()`, not in the caller's memory."""
	svc = InfoService()
	svc._content['draft-1'] = _item(item_id='draft-1', stage=ContentStage.draft)
	svc._content['arch-1'] = _item(item_id='arch-1', stage=ContentStage.archived)
	svc._content['review-1'] = _item(item_id='review-1', stage=ContentStage.clinical_review)
	served = {c.item_id for c in svc.library()}
	assert not (served & {'draft-1', 'arch-1', 'review-1'}), 'only published items may be served'


def test_the_workflow_cannot_be_skipped() -> None:
	"""§6.5's order is the rule: draft → clinical review → translation → back-translation →
	community validation → publish. A jump straight to published would make every earlier stage
	decorative."""
	svc = InfoService()
	svc._content['d-1'] = _item(item_id='d-1', stage=ContentStage.draft)
	with pytest.raises(AssertionError):
		svc.advance('d-1', ContentStage.published)
	step = svc.advance('d-1', ContentStage.clinical_review)
	assert step.stage is ContentStage.clinical_review
	# And retirement is reachable from anywhere, because retiring something wrong should not
	# require walking it forward first.
	assert svc.advance('d-1', ContentStage.archived).stage is ContentStage.archived


def test_staleness_audit_reports_items_past_their_review_cycle() -> None:
	"""§6.5's staleness audit as a date: weekly in an outbreak, monthly otherwise. An item reviewed
	40 days ago is stale under both; one reviewed yesterday is stale under neither."""
	svc = InfoService()
	svc._content['old-1'] = _item(item_id='old-1', reviewed_on_iso='2026-09-01')
	svc._content['new-1'] = _item(item_id='new-1', reviewed_on_iso='2026-10-09')
	assert 'old-1' in svc.stale('2026-10-10', 'steady') and 'old-1' in svc.stale('2026-10-10', 'outbreak')
	assert 'new-1' not in svc.stale('2026-10-10', 'outbreak')


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