"""Information service — content library, county dashboard, decision tree (INF-002), hotline directory.

The library serves only what §6.5's workflow has published, and every item carries the owner,
reviewer, review date and version that section requires. Content is the one thing this app says on
the Ministry's behalf, so an item nobody reviewed must not be servable — `library()` filters on the
stage rather than trusting the caller to have advanced it.
"""
from datetime import date
from typing import Any

from afya.info.content_seed import seed_rows
from afya.info.views import WORKFLOW, ContentItem, ContentStage, CountyRisk, DecisionNode, HotlineInfo
from afya.logmixin import LogMixin

# §6.5 review cycle: clinical content is reviewed weekly during an outbreak and monthly otherwise.
# Which regime applies is the caller's fact, so both are named and the staleness check takes one.
REVIEW_CADENCE_DAYS = {'outbreak': 7, 'steady': 30}


def _days_since(iso: str, today_iso: str) -> int:
	"""Whole days from a review date to today. Parsed here so an unparseable date is a loud error
	rather than a silently never-stale item."""
	return (date.fromisoformat(today_iso) - date.fromisoformat(iso)).days

HOTLINES: tuple[HotlineInfo, ...] = (
	HotlineInfo(name='Ministry of Health Hotline', number='719', hours='24/7', verified=False),
	HotlineInfo(name='ODPC Complaints Desk', number='+254-20-4226849', hours='business hours', verified=False),
)


class InfoService(LogMixin):
	def __init__(self) -> None:
		self._content: dict[str, ContentItem] = {}
		self._risk: dict[str, CountyRisk] = {}
		self.seed()
		assert self._content and self._risk == {}

	def seed(self) -> int:
		"""Load harmonised en/sw corpus; idempotent."""
		n = 0
		for item in seed_rows():
			self._content[item.item_id] = item
			n += 1
		assert n >= 8, 'seed corpus must load'
		return n

	async def upsert_content(self, item: ContentItem) -> None:
		assert item.item_id and item.title, 'id/title required'
		self._content[item.item_id] = item

	def library(self, lang: str = 'en') -> list[ContentItem]:
		"""What a client may read: published items in this language, and nothing else.

		The stage filter is the whole point of §6.5. A draft, a translation awaiting back-translation
		or an item retired for being wrong must not be servable, and a caller cannot be trusted to
		remember that — so the filter is here, at the one place the route reads from.
		"""
		out = [c for c in self._content.values() if c.lang == lang and c.stage is ContentStage.published]
		assert all(c.harmony_tag for c in out), 'unharmonised content must be tagged before serving'
		return out

	def advance(self, item_id: str, to: ContentStage) -> ContentItem:
		"""Move an item one step along §6.5's workflow, or retire it.

		One step, never a jump: the spec's order is draft → clinical review → translation →
		back-translation → community validation → publish, and a route that let a draft be marked
		published directly would make every stage before it decorative. `archived` is reachable from
		any stage, because retiring something wrong should not require walking it forward first.
		"""
		assert item_id in self._content, f'no content item {item_id}'
		item = self._content[item_id]
		if to is ContentStage.archived:
			return self._replace(item, stage=ContentStage.archived)
		assert item.stage is not ContentStage.archived, 'an archived item is retired, not revived'
		current = WORKFLOW.index(item.stage)
		nxt = WORKFLOW.index(to)
		assert nxt == current + 1, f'{item.stage.value} advances to {WORKFLOW[current + 1].value}, not {to.value}'
		return self._replace(item, stage=to)

	def _replace(self, item: ContentItem, **updates: object) -> ContentItem:
		updated = item.model_copy(update=updates)
		self._content[updated.item_id] = updated
		return updated

	def all_items(self) -> list[ContentItem]:
		"""Every item at every stage, drafts and retirements included. The governance view reads
		this; the client-facing `library()` never does."""
		return list(self._content.values())

	@staticmethod
	def cadence_days(regime: str) -> int:
		assert regime in REVIEW_CADENCE_DAYS, f'unknown review regime {regime!r}'
		return REVIEW_CADENCE_DAYS[regime]

	def stale(self, today_iso: str, regime: str = 'steady') -> list[str]:
		"""§6.5's staleness audit: published items whose clinical review has come due.

		A review date is the only thing that makes the cycle real. Without it "reviewed monthly" is
		an intention, and the item served longest ago is the one nobody has looked at since."""
		assert regime in REVIEW_CADENCE_DAYS, f'unknown review regime {regime!r}'
		cadence = REVIEW_CADENCE_DAYS[regime]
		return sorted(
			c.item_id for c in self._content.values()
			if c.stage is ContentStage.published and _days_since(c.reviewed_on_iso, today_iso) > cadence
		)

	async def set_county_risk(self, risk: CountyRisk) -> None:
		self._risk[risk.county] = risk

	def dashboard(self, county: str) -> CountyRisk:
		return self._risk.get(county, CountyRisk(county=county, risk_level='low', active_signals=0, bulletin='No official signal.'))

	# INF-002: explicit decision tree — node_id -> node
	TREE: dict[str, DecisionNode] = {
		'root': DecisionNode(question='Do you have fever (≥38.0 °C)?', yes_next='fever', no_next='no_fever', leaf_recommendation=None),
		'fever': DecisionNode(question='Recent contact with an Ebola patient or travel to an affected area in 21 days?', yes_next='leaf_hotline', no_next='leaf_malaria', leaf_recommendation=None),
		'no_fever': DecisionNode(question='Any other symptoms?', yes_next='leaf_monitor', no_next='leaf_ok', leaf_recommendation=None),
		'leaf_hotline': DecisionNode(question='(leaf)', yes_next=None, no_next=None, leaf_recommendation='Isolate and call 719 immediately.'),
		'leaf_malaria': DecisionNode(question='(leaf)', yes_next=None, no_next=None, leaf_recommendation='Test and treat for malaria first; call 719 if no improvement in 48h.'),
		'leaf_monitor': DecisionNode(question='(leaf)', yes_next=None, no_next=None, leaf_recommendation='Monitor; standard hygiene; call 719 if worsening.'),
		'leaf_ok': DecisionNode(question='(leaf)', yes_next=None, no_next=None, leaf_recommendation='No action needed.'),
	}

	def decide(self, county: str, answers: list[bool]) -> str:
		assert len(answers) <= 3, 'tree depth bounded'
		node = self.TREE['root']
		for ans in answers:
			assert node.leaf_recommendation is None, 'walked past leaf'
			nxt = node.yes_next if ans else node.no_next
			assert nxt, 'interior node must reference next'
			node = self.TREE[nxt]
		assert node.leaf_recommendation, 'must terminate at leaf'
		return node.leaf_recommendation

	def hotlines(self) -> list[HotlineInfo]:
		return list(HOTLINES)