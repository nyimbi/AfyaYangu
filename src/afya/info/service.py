"""Information service — content library, county dashboard, decision tree (INF-002), hotline directory.

The library serves only what §6.5's workflow has published, and every item carries the owner,
reviewer, review date and version that section requires. Content is the one thing this app says on
the Ministry's behalf, so an item nobody reviewed must not be servable — `library()` filters on the
stage rather than trusting the caller to have advanced it.

§6.2.3's "Timestamp everything" is stamped here rather than accepted from a writer. `ContentItem` is
`extra='forbid'`, so a posted `updated_at_ms` is refused and the service sets it on write, on advance
and at seed; `library()` withholds an item carrying no stamp, because undated content is the thing
the section calls destructive. The relative age is computed at serve time against the caller's clock
— see `afya.info.recency` for why the line is built server-side and never stored.
"""
from datetime import date

from afya.auth.views import now_ms
from afya.info.content_seed import seed_rows
from afya.info.principles import Finding, Subject, Verdict, judge, judge_corpus, library_texts, tree_texts
from afya.info.questions import (
	QUESTION_BY_RANK, REQUIRED_LANGS, RANKED_QUESTIONS, RankedQuestion, is_life_safety,
)
from afya.info.recency import UNDATED_MS, ServedFreshness, freshness, freshness_line, midnight_ms
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
		"""Load harmonised en/sw corpus; idempotent.

		The stamp comes from the row's own review date rather than from the wall clock. A corpus that
		claimed to have been updated the moment the process started would render "Updated just now"
		for text written in September, which is the failure §6.2.3 names — a freshness line nobody can
		believe is worse than no line.
		"""
		n = 0
		for item in seed_rows():
			self._content[item.item_id] = item.model_copy(update={'updated_at_ms': midnight_ms(item.reviewed_on_iso)})
			n += 1
		assert n >= 8, 'seed corpus must load'
		return n

	async def upsert_content(self, item: ContentItem, at_ms: int | None = None) -> ContentItem:
		"""Write an item, stamped with when it was written.

		§6.2.3's stamp is set here and not taken from the body: `ContentItem` forbids extra fields, so
		a writer that posts one is refused, and a freshness signal a client can choose is one it can
		lie about. `at_ms` is injectable for the same reason every other clock in this codebase is —
		a clock nobody can move is a clock nobody can test.
		"""
		assert item.item_id and item.title, 'id/title required'
		stamped = item.model_copy(update={'updated_at_ms': at_ms if at_ms is not None else now_ms()})
		self._content[stamped.item_id] = stamped
		return stamped

	def content_verdicts(self, item: ContentItem) -> list[Verdict]:
		"""§6.2's rules applied to one item, as findings rather than an exception.

		Returned rather than raised so the drafting screen can show what to fix and the publishing
		route can refuse on the same verdicts — one implementation, two callers, and the reason the
		failures are a list rather than a bool.
		"""
		return judge(f'library:{item.slug or item.item_id}', f'{item.title} {item.body}', Subject.content).failures()

	def library_audit(self) -> list[Finding]:
		"""Every §6.2 finding in the corpus, drafts included.

		Published items only would be the comfortable choice and the wrong one: the rule exists to
		stop a stigmatising sentence reaching a screen, and the cheapest place to catch it is before
		the item is published rather than after. `all_items()` is what the governance view reads.
		"""
		return [f for f in judge_corpus(library_texts(self.all_items())) if not f.clean()]

	def tree_audit(self) -> list[Finding]:
		"""§6.2 over the decision tree, which is served text too.

		The tree's questions are read aloud by the low-literacy interface (§ACC-001), so a question
		that names a group of people is a stigmatising sentence in a voice, and a leaf that names the
		spec is a section number read out to someone deciding whether to seek care.
		"""
		return [f for f in judge_corpus(tree_texts(self.TREE)) if not f.clean()]

	def library(self, lang: str = 'en') -> list[ContentItem]:
		"""What a client may read: published items in this language, and nothing else.

		The stage filter is the whole point of §6.5. A draft, a translation awaiting back-translation
		or an item retired for being wrong must not be servable, and a caller cannot be trusted to
		remember that — so the filter is here, at the one place the route reads from.

		§6.2.4's second sentence filters too: a life-safety item whose counterpart in the other
		required language is missing is *not served at all*, in either language. Withholding it is
		the point — §6.2.4 forbids publishing English-only for a life-safety message, and serving it
		is the act of publishing. The gap is not silent: `untranslated()` names it for the reviewer,
		and `/info/content` refuses to publish such an item in the first place.

		§6.2.3 filters a third way: an item with no stamp is withheld, because "undated content
		destroys trust" and a client handed one has nothing to render but the text. `undated()` names
		it for the reviewer. Both withholdings are the same shape deliberately — a gap someone can
		see beats a message that misleads.
		"""
		out = [
			c for c in self._content.values()
			if c.lang == lang and c.stage is ContentStage.published
			and c.updated_at_ms > UNDATED_MS and self.translated(c)
		]
		assert all(c.harmony_tag for c in out), 'unharmonised content must be tagged before serving'
		return out

	def undated(self) -> list[str]:
		"""§6.2.3's audit: published items held back for carrying no timestamp.

		Named by slug so a reviewer can act on it. This is the half of the rule that is easy to skip:
		serving the text with no age would satisfy every other check in this module while doing the
		one thing the section forbids.
		"""
		return sorted({
			c.slug or c.item_id for c in self._content.values()
			if c.stage is ContentStage.published and c.updated_at_ms <= UNDATED_MS
		})

	def item_freshness(self, item: ContentItem, at_ms: int | None = None, lang: str = 'en') -> ServedFreshness:
		"""§6.2.3's age line for one item, against the caller's clock.

		Computed at serve time and never stored: a phrase written into a row is wrong an hour later,
		and the whole point of the line is that a reader can believe it.
		"""
		assert item.updated_at_ms > UNDATED_MS, f'{item.slug or item.item_id} carries no timestamp (§6.2.3)'
		return freshness(item.updated_at_ms, at_ms if at_ms is not None else now_ms(), lang)

	def dashboard_freshness(self, county: str, at_ms: int | None = None, lang: str = 'en') -> str | None:
		"""§8.5's "Last updated timestamp", or None when the county has never been assessed.

		None rather than a sentence about a row that does not exist. `dashboard()` answers an unknown
		county with a defaulted low-risk row so a client always has something to draw, and with no way
		to tell the two apart that default reads as an assessment someone made. This is how a client
		tells them apart.
		"""
		risk = self._risk.get(county)
		if risk is None or risk.updated_at_ms <= UNDATED_MS:
			return None
		return freshness_line(risk.updated_at_ms, at_ms if at_ms is not None else now_ms(), lang)

	def hotline_freshness(self, hotline: HotlineInfo, at_ms: int | None = None, lang: str = 'en') -> str | None:
		"""§18.4 / §6.2.3: when a directory entry was last checked, or None when never."""
		if hotline.verified_at_ms <= UNDATED_MS:
			return None
		return freshness_line(hotline.verified_at_ms, at_ms if at_ms is not None else now_ms(), lang)

	def translated(self, item: ContentItem) -> bool:
		"""Whether a life-safety item has every language §6.2.4 requires, or is not life-safety.

		Matched on `slug` rather than on the id, because the slug is the code-free handle the corpus
		already keys on and two translations of one message share it — which is what makes "the
		counterpart exists" a question the data can answer.
		"""
		if not is_life_safety(item.answers_rank):
			return True
		present = {
			c.lang for c in self._content.values()
			if c.slug == item.slug and c.stage is ContentStage.published
		}
		return set(REQUIRED_LANGS) <= present

	def untranslated(self) -> list[str]:
		"""§6.2.4's audit: published life-safety items held back for a missing language.

		Named by slug so a reviewer can act on it. A gate that withheld content silently would be
		worse than the English-only message it prevents: the audience sees nothing and nobody is told
		why.
		"""
		return sorted({
			c.slug or c.item_id for c in self._content.values()
			if c.stage is ContentStage.published and not self.translated(c)
		})

	def life_safety_refusal(self, item: ContentItem) -> str | None:
		"""The §6.2.4 refusal for an item about to be published English-only, or None.

		Returned as a sentence rather than raised so the publishing route can put the missing
		languages in front of the person drafting, which is the only moment the gap can be closed.
		"""
		if item.stage is not ContentStage.published or not is_life_safety(item.answers_rank):
			return None
		present = {
			c.lang for c in self._content.values()
			if c.slug == item.slug and c.item_id != item.item_id and c.stage is ContentStage.published
		} | {item.lang}
		missing = [lang for lang in REQUIRED_LANGS if lang not in present]
		if not missing:
			return None
		question = QUESTION_BY_RANK[item.answers_rank]  # type: ignore[index]
		return (
			f'§6.2.4: {question.question!r} is a life-safety message, so it cannot be published in '
			f'{item.lang} alone. Missing: {", ".join(missing)}. '
			f'{question.why_life_safety}'
		)

	def advance(self, item_id: str, to: ContentStage, at_ms: int | None = None) -> ContentItem:
		"""Move an item one step along §6.5's workflow, or retire it.

		One step, never a jump: the spec's order is draft → clinical review → translation →
		back-translation → community validation → publish, and a route that let a draft be marked
		published directly would make every stage before it decorative. `archived` is reachable from
		any stage, because retiring something wrong should not require walking it forward first.

		The move is stamped (§6.2.3): the version a reader holds is the one that last changed, and a
		translation published an hour ago is not an English draft written in September.
		"""
		assert item_id in self._content, f'no content item {item_id}'
		item = self._content[item_id]
		stamp = at_ms if at_ms is not None else now_ms()
		if to is ContentStage.archived:
			return self._replace(item, stage=ContentStage.archived, updated_at_ms=stamp)
		assert item.stage is not ContentStage.archived, 'an archived item is retired, not revived'
		current = WORKFLOW.index(item.stage)
		nxt = WORKFLOW.index(to)
		assert nxt == current + 1, f'{item.stage.value} advances to {WORKFLOW[current + 1].value}, not {to.value}'
		return self._replace(item, stage=to, updated_at_ms=stamp)

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

	async def set_county_risk(self, risk: CountyRisk, at_ms: int | None = None) -> CountyRisk:
		"""Record a county's risk, stamped with when it was assessed.

		§8.5 lists "Last updated timestamp" among the dashboard's fields, and §6.2.3 gives the reason:
		a risk level with no date is indistinguishable from today's. The stamp is set here rather than
		taken from the body for the same reason a content item's is.
		"""
		stamped = risk.model_copy(update={'updated_at_ms': at_ms if at_ms is not None else now_ms()})
		self._risk[stamped.county] = stamped
		return stamped

	def dashboard(self, county: str) -> CountyRisk:
		return self._risk.get(county, CountyRisk(county=county, risk_level='low', active_signals=0, bulletin='No official signal.'))

	# INF-002: explicit decision tree — node_id -> node
	TREE: dict[str, DecisionNode] = {
		'root': DecisionNode(question='Do you have fever (≥38.0 °C)?', yes_next='fever', no_next='no_fever', leaf_recommendation=None),
		'fever': DecisionNode(question='In the last 21 days, have you been near someone who is sick with Ebola, or travelled to an area where a case was reported?', yes_next='leaf_hotline', no_next='leaf_malaria', leaf_recommendation=None),
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

	def ranked_questions(self) -> list[RankedQuestion]:
		"""§6.1's ten questions in the section's own order.

		The order is the content: §6.1 is explicit that it is "ordered by real demand, not by what
		health authorities want to publish", so a client that lists the library alphabetically or by
		route has thrown away the one thing the section contributes. Served so a client can lead with
		what people actually ask.
		"""
		return list(RANKED_QUESTIONS)

	def hotlines(self) -> list[HotlineInfo]:
		return list(HOTLINES)