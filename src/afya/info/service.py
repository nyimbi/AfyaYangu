"""Information service — content library, county dashboard, decision tree (INF-002), hotline directory."""
from typing import Any

from afya.info.content_seed import seed_rows
from afya.info.views import ContentItem, CountyRisk, DecisionNode, HotlineInfo
from afya.logmixin import LogMixin

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
		out = [c for c in self._content.values() if c.lang == lang]
		assert all(c.harmony_tag for c in out), 'unharmonised content must be tagged before serving'
		return out

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