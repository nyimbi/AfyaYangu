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
from urllib.parse import quote

from afya.auth.views import now_ms
from afya.info.content_seed import rendition_rows, seed_rows
from afya.info.escalation import ContentError, ContentEscalation, escalate
from afya.info.localisation import (
	SOURCE_LANG, BackTranslation, CommunityValidation, LocalisationState, localisation, next_stage,
	separation_breach, workflow_for,
)
from afya.info.principles import Finding, Subject, Verdict, judge, judge_corpus, library_texts, tree_texts
from afya.info.questions import (
	QUESTION_BY_RANK, REQUIRED_LANGS, RANKED_QUESTIONS, RankedQuestion, is_life_safety,
)
from afya.info.recency import UNDATED_MS, ServedFreshness, freshness, freshness_line, midnight_ms
from afya.info.views import (
	ContactDirectory, ContactKind, ContentItem, ContentStage, CountyRisk, DecisionNode, HotlineActions,
	HotlineInfo,
)
from afya.logmixin import LogMixin
from afya.places.views import PlaceKind, PlacesService

# §6.5 review cycle: clinical content is reviewed weekly during an outbreak and monthly otherwise.
# Which regime applies is the caller's fact, so both are named and the staleness check takes one.
REVIEW_CADENCE_DAYS = {'outbreak': 7, 'steady': 30}


def _days_since(iso: str, today_iso: str) -> int:
	"""Whole days from a review date to today. Parsed here so an unparseable date is a loud error
	rather than a silently never-stale item."""
	return (date.fromisoformat(today_iso) - date.fromisoformat(iso)).days


HOTLINES: tuple[HotlineInfo, ...] = (
	HotlineInfo(name='Ministry of Health Hotline', number='719', hours='24/7', verified=False,
		kind=ContactKind.emergency_hotline),
	HotlineInfo(name='ODPC Complaints Desk', number='+254-20-4226849', hours='business hours',
		verified=False, kind=ContactKind.complaints_desk),
)

# §INF-006 prints eight Contents and the two rows above cover one of them plus a desk the section
# does not name. The mental-health, substance-abuse and ambulance numbers *do* exist in the tree —
# `mental.COUNSELLING_LINES` holds all three — and the directory route never read that table, so
# three of the eight were in the repo and off the screen. They are folded in here rather than
# duplicated: the mental-health module keeps the table (it owns the counselling surface) and this
# reads it, which is why the numbers cannot drift between the two.
COUNSELLING_KINDS: tuple[tuple[str, ContactKind], ...] = (
	('Befrienders Kenya (emotional support)', ContactKind.mental_health_helpline),
	('NACADA helpline (substance abuse)', ContactKind.substance_abuse_helpline),
	('Emergency', ContactKind.ambulance),
)


def _dialable(number: str) -> str:
	"""The one number a dialler can use, out of what a row was written with.

	§INF-006's rows are prose: the ODPC desk is `+254-20-4226849` and the tree's own emergency row is
	`1199 (ambulance) / 719 (MoH)`, which names *two* numbers. Stripping non-digits from the second
	concatenates them into `1199719` — a number that dials nothing — so a row that names more than one
	is cut to its first and the rest are dropped, because a directory entry is one destination. The
	`/` is the tell and the assert is on it: a row written some other way that still carries two
	numbers would otherwise pass silently into a `tel:` URI, which is the failure `hotline_actions`
	exists to prevent.
	"""
	first = number.split('/')[0]
	digits = ''.join(ch for ch in first if ch.isdigit() or ch == '+')
	assert digits, f'{number!r} has no dialable number'
	return digits


def _directory_rows() -> tuple[HotlineInfo, ...]:
	"""§INF-006's directory: `HOTLINES` plus the `mental.COUNSELLING_LINES` rows the route never read.

	The ambulance row is the section's own "ambulance" and the counselling rows are its "mental
	health helpline"; NACADA is filed under the substance-abuse kind because the section names no
	such entry and inventing a row the spec does not ask for would be worse than filing the number
	under the kind it actually answers. Each keeps `mental`'s own `verified` flag, which is False on
	every row, so a number folded in here does not arrive looking checked.
	"""
	from afya.mental.views import COUNSELLING_LINES
	by_name = {row['name']: row for row in COUNSELLING_LINES}
	out: list[HotlineInfo] = list(HOTLINES)
	for name, kind in COUNSELLING_KINDS:
		row = by_name.get(name)
		assert row is not None, f'{name} is no longer in mental.COUNSELLING_LINES'
		out.append(HotlineInfo(
			name=name, number=row['number'], hours=row['hours'] or 'not stated',
			verified=row['verified'] == 'True', kind=kind,
		))
	return tuple(out)



class InfoService(LogMixin):
	def __init__(self) -> None:
		self._content: dict[str, ContentItem] = {}
		self._risk: dict[str, CountyRisk] = {}
		self._errors: dict[str, ContentError] = {}
		self._withdrawn: dict[str, list[str]] = {}
		self._back_translations: dict[str, BackTranslation] = {}
		self._community_validations: dict[str, CommunityValidation] = {}
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
		for item in seed_rows() + rendition_rows():
			self._content[item.item_id] = item.model_copy(update={'updated_at_ms': midnight_ms(item.reviewed_on_iso)})
			n += 1
		assert n >= 8, 'seed corpus must load'
		# §INF-003's and §INF-008's Format cells are delivered by renditions rather than by prose, and
		# a corpus that dropped them would satisfy every topic while serving none of the audio and
		# video the sections ask for. Asserted here rather than only in the audit view because the
		# seed is where the corpus is loaded, and an empty rendition set is a silent regression.
		assert any(i.media_ref for i in self._content.values()), \
			'the corpus carries no rendition, so §INF-003 and §INF-008 print formats nothing delivers'
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

		A rendition is withheld too, and for a different reason: it is not an item a reader opens. Its
		body is empty by construction — the content is the file at `media_ref` — so serving it here
		would put a blank card in the list beside the article it illustrates. It travels *with* its
		parent instead, which is what `renditions_of()` is for.
		"""
		out = [
			c for c in self._content.values()
			if c.lang == lang and c.stage is ContentStage.published and c.rendition_of is None
			and c.updated_at_ms > UNDATED_MS and self.translated(c)
		]
		assert all(c.harmony_tag for c in out), 'unharmonised content must be tagged before serving'
		return out

	def renditions_of(self, slug: str) -> list[ContentItem]:
		"""Every rendition of the item with this slug: its illustrations, audio versions, videos.

		§INF-003 and §INF-008 print these as *formats of an item* rather than as items, which is what
		makes this a lookup rather than a second list. A client renders the article and offers what is
		beside it; a client that listed renditions separately would show the same subject twice, once
		as text and once as a blank entry pointing at a file.

		Published and stamped, the same gate `library()` applies — a draft audio version of a
		published article is not servable, and the parent's own withholding (a missing translation, an
		absent stamp) is not re-derived here because the caller only reaches this for an item it has
		already been allowed to serve.
		"""
		assert slug, 'a rendition is looked up by its parent slug'
		return sorted(
			(
				c for c in self._content.values()
				if c.rendition_of == slug and c.stage is ContentStage.published
				and c.updated_at_ms > UNDATED_MS
			),
			key=lambda c: (c.format.value, c.item_id),
		)

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

		**The two verification stages are gated on their evidence.** Without that, `back_translation`
		and `community_validation` are names: the item moves and nothing records that anyone rendered
		the translation back or took it to a community. The check is on the stage being *entered*, and
		it reads the same `localisation()` the review view serves, so the gate and the report cannot
		disagree about whether a step is done.

		The move is stamped (§6.2.3): the version a reader holds is the one that last changed, and a
		translation published an hour ago is not an English draft written in September.
		"""
		assert item_id in self._content, f'no content item {item_id}'
		item = self._content[item_id]
		stamp = at_ms if at_ms is not None else now_ms()
		if to is ContentStage.archived:
			return self._replace(item, stage=ContentStage.archived, updated_at_ms=stamp)
		assert item.stage is not ContentStage.archived, 'an archived item is retired, not revived'
		nxt = next_stage(item)
		assert nxt is to, (
			f'{item.stage.value} advances to {nxt.value}, not {to.value}'
			if nxt is not None else f'{item.stage.value} is the end of the walk, so it does not advance'
		)
		state = self.localisation_of(item, at_stage=to)
		assert not state.blocked, state.blocked
		assert not state.missing, (
			f'{item.slug or item.item_id} cannot reach {to.value} with no evidence for '
			f'{", ".join(state.missing)} (§6.5)'
		)
		return self._replace(item, stage=to, updated_at_ms=stamp)

	def _source_body(self, item: ContentItem) -> str | None:
		"""The source-language text of this item's message, or None when there is no such row.

		The back-translation is rendered into the *source language*, so the text it is compared against
		is the source row of the same slug. §6.5's arrow drafts in English, so that is `SOURCE_LANG`;
		the row is looked up by slug rather than by a naming convention on the id, which is how the
		rest of the module matches two translations of one message.
		"""
		if item.lang == SOURCE_LANG:
			return item.body
		for other in self._content.values():
			if other.slug and other.slug == item.slug and other.lang == SOURCE_LANG:
				return other.body
		return None

	def localisation_of(self, item: ContentItem, at_stage: ContentStage | None = None) -> LocalisationState:
		"""§6.5's localisation for one item, with this shelf's records behind it."""
		return localisation(
			item, self._back_translations.get(item.item_id), self._community_validations.get(item.item_id),
			self._source_body(item), now_ms(), at_stage=at_stage,
		)

	def record_back_translation(self, record: BackTranslation, at_ms: int | None = None) -> LocalisationState:
		"""Write §6.5's back-translation step for one item.

		The item must be the translated row, because the step is rendering a translation back: an
		English item rendered into English is the check performed on the wrong object. It must also
		have reached `translation`, since a back-translation of a translation that does not exist is
		a record of a step that could not have happened.
		"""
		assert record.item_id in self._content, f'no content item {record.item_id}'
		item = self._content[record.item_id]
		assert item.lang != SOURCE_LANG, (
			f'{record.item_id} is the source text ({item.lang}), so there is no translation to render back'
		)
		order = workflow_for(item.lang)
		assert order.index(item.stage) >= order.index(ContentStage.translation), (
			f'{record.item_id} is at {item.stage.value}, before the translation this step verifies'
		)
		stamp = at_ms if at_ms is not None else now_ms()
		self._back_translations[record.item_id] = record.model_copy(update={'at_ms': stamp})
		self._log_info('back-translation recorded', item_id=record.item_id, by=record.back_translated_by)
		return self.localisation_of(item)

	def record_community_validation(self, record: CommunityValidation, at_ms: int | None = None) -> LocalisationState:
		"""Write §6.5's community validation step for one item.

		The back-translation must already be on file: the community is shown the text the
		back-translation produced, so validating before it exists is validating nothing. The separation
		rule spans both records and is checked here, where both are finally visible.
		"""
		assert record.item_id in self._content, f'no content item {record.item_id}'
		item = self._content[record.item_id]
		back = self._back_translations.get(record.item_id)
		assert back is not None, (
			f'{record.item_id} has no back-translation on file, so there is nothing the community can have seen'
		)
		breach = separation_breach(back, record)
		assert breach is None, breach
		stamp = at_ms if at_ms is not None else now_ms()
		self._community_validations[record.item_id] = record.model_copy(update={'at_ms': stamp})
		self._log_info('community validation recorded', item_id=record.item_id, by=record.validated_by)
		return self.localisation_of(item)

	def localisation_review(self) -> list[LocalisationState]:
		"""Every translated item's localisation, and every source item sitting at a translation stage.

		The second set is the one a shelf-scoped view would miss: an English item walked into
		`back_translation` is the workflow's own failure mode, and it is invisible to a report that
		only lists translations.
		"""
		return [
			self.localisation_of(c) for c in sorted(self._content.values(), key=lambda c: c.item_id)
			if c.lang != SOURCE_LANG or c.stage in (
				ContentStage.translation, ContentStage.back_translation, ContentStage.community_validation,
			)
		]


	def _replace(self, item: ContentItem, **updates: object) -> ContentItem:
		updated = item.model_copy(update=updates)
		self._content[updated.item_id] = updated
		return updated

	async def report_error(self, error: ContentError, at_ms: int | None = None) -> ContentEscalation:
		"""§6.5's escalation: an item found wrong is retired, and its translations go with it.

		**Every published item sharing the slug is withdrawn, not just the one named.** A correction
		is per-message, not per-language: a wrong English item and its Swahili translation are one
		claim in two languages, and archiving only the one somebody happened to open leaves the other
		being served to the audience §3.3 principle 8 puts first. That is the failure this method
		exists to prevent, and it is invisible from the item the error was reported against.

		Retiring is immediate and unconditional. §6.5's clause says the error *triggers* review, and a
		wrong life-safety item left published while its correction is drafted is the harm the clause
		is about — the correction is what makes the shelf right again, and `superseded` says whether
		it has arrived.
		"""
		assert error.item_id in self._content, f'no content item {error.item_id}'
		item = self._content[error.item_id]
		assert item.stage is ContentStage.published, f'{error.item_id} is {item.stage.value}, not published'
		assert error.error_id not in self._errors, f'duplicate error id {error.error_id}'
		stamp = at_ms if at_ms is not None else now_ms()
		withdrawn = sorted(
			c.lang for c in self._content.values()
			if c.slug and c.slug == item.slug and c.stage is ContentStage.published
		)
		for other in list(self._content.values()):
			if other.slug and other.slug == item.slug and other.stage is ContentStage.published:
				self._replace(other, stage=ContentStage.archived, updated_at_ms=stamp)
		recorded = error.model_copy(update={'found_at_ms': stamp})
		self._errors[recorded.error_id] = recorded
		self._withdrawn[recorded.error_id] = withdrawn
		self._log_warn('content error escalated', error=recorded.error_id, slug=item.slug,
			safety=is_life_safety(item.answers_rank), withdrawn=len(withdrawn))
		return self.escalation(recorded.error_id, stamp)

	def escalation(self, error_id: str, at_ms: int | None = None) -> ContentEscalation:
		"""§6.5's escalation for a recorded error, recomputed against the clock it is asked at.

		The clock is the caller's and may be absent, like every other freshness call here: the
		service resolves None to now rather than making the route reach for a clock of its own,
		which is what keeps `review_overdue` a fact about the moment asked.
		"""
		assert error_id in self._errors, f'no content error {error_id}'
		error = self._errors[error_id]
		item = self._content[error.item_id]
		# A replacement is a published item under the same slug stamped after the error was found.
		# Asking "is there a corrected item" rather than "was one posted" is what makes `superseded`
		# a fact about the shelf a reader sees, which is the only thing the clause is about.
		superseded = any(
			c.slug and c.slug == item.slug and c.stage is ContentStage.published
			and c.updated_at_ms > error.found_at_ms
			for c in self._content.values()
		)
		return escalate(item, error, at_ms if at_ms is not None else now_ms(),
			self._withdrawn.get(error_id, []), superseded)

	def errors(self) -> list[ContentError]:
		"""Every recorded content error, oldest first — §6.5's escalation log for the reviewer."""
		return [self._errors[k] for k in sorted(self._errors)]

	def by_slug(self, slug: str) -> ContentItem | None:
		"""The item a slug names, at whatever stage it now sits, or None.

		Stage-agnostic on purpose. §6.5's escalation corrects a *message*, and the correction goes out
		under that message's title — but the message has just been retired by the act of reporting it,
		so a published-only lookup would find nothing at exactly the moment it is needed and every
		correction would be headlined by a slug. The title of a retired item is still the title of the
		thing that was wrong.
		"""
		assert slug, 'a slug is not empty'
		named = [c for c in self._content.values() if c.slug == slug]
		return max(named, key=lambda c: (c.updated_at_ms, c.version)) if named else None

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

	@staticmethod
	def hotline_actions(row: HotlineInfo, lang: str = 'en') -> HotlineActions:
		"""§INF-006's four Features for one entry: call, SMS, save, share.

		Rendered here rather than left to each client, the way `PlacesService.directions` renders its
		two maps URLs — a directory of life-safety numbers whose four Features are a client's
		obligation is a directory where two clients disagree about whether "one-tap call" works. The
		digits are stripped of everything a dialler cannot use, because the section's own rows are
		written `+254-20-4226849` and a `tel:` URI carrying the hyphens may not dial.

		`share_url` is a `wa.me` deep link rather than a bare number, because §3.3 principle 10 says
		every output must be shareable as a WhatsApp card and a card needs a link to carry.
		"""
		dialable = _dialable(row.number)
		label = row.name.replace("'", '')
		body = f'You can reach {row.name} on {row.number}' + (f' ({row.hours})' if row.hours else '')
		return HotlineActions(
			tel_uri=f'tel:{dialable}',
			sms_uri=f'sms:{dialable}',
			vcard=f'BEGIN:VCARD\nVERSION:3.0\nN:{label}\nFN:{label}\nTEL;TYPE=VOICE:{dialable}\nEND:VCARD',
			share_url=f'https://wa.me/?text={quote(body)}',
		)

	def hotline_directory(
		self, at_ms: int | None = None, lang: str = 'en',
		lat: float | None = None, lon: float | None = None, places: PlacesService | None = None,
	) -> ContactDirectory:
		"""§INF-006's "single screen with all relevant contacts", with the ones this deployment lacks.

		`absent` is coverage of the section's own eight Contents (`SPEC_CONTENTS`), not of every enum
		member: the ODPC complaints desk and NACADA's line are rows this deployment has and the section
		does not name, and a gap list that counted them would report the directory incomplete for
		holding more than asked. A kind the section names appears in `absent` the moment a row for it
		is not there, which is what makes "GBV helpline: not in this deployment" a fact a screen can
		print rather than a blank.

		`nearest_facility` is the one Content that is not a fixed row — it is whichever facility is
		closest to the caller, so it is only answerable with a position. Given one, the nearest place
		of any clinical kind is folded in and carries its own `phone` when OSM had one; without one
		the kind is reported absent, because a directory cannot name a nearest facility to nobody.
		"""
		rows = [
			row.model_copy(update={
				'actions': self.hotline_actions(row, lang),
				'updated_line': self.hotline_freshness(row, at_ms, lang),
			})
			for row in _directory_rows()
		]
		rows.extend(self._nearest_facility_rows(lat, lon, places, lang))
		return ContactDirectory(contacts=rows)

	def _nearest_facility_rows(
		self, lat: float | None, lon: float | None,
		places: PlacesService | None, lang: str,
	) -> list[HotlineInfo]:
		"""§INF-006's "nearest facility", as a directory row rather than a map pin.

		A facility with no `phone` in OSM is still the nearest facility and is listed without one: the
		row is the answer to "where do I go", and dropping it for want of a number would hide the
		destination because the number is missing. `actions` is None on such a row for the same reason
		`HotlineActions` requires a dialable number — there is nothing to dial, and a `tel:` URI built
		from an empty string is the failure the assert in `hotline_actions` exists to catch.
		"""
		if lat is None or lon is None or places is None:
			return []
		clinical = {
			PlaceKind.clinic, PlaceKind.hospital, PlaceKind.treatment_unit, PlaceKind.testing_site,
		}
		try:
			found = places.nearest(lat, lon, clinical, limit=1)
		except AssertionError:
			return []  # nothing imported: no nearest facility, reported absent rather than invented
		place, km = found[0]
		row = HotlineInfo(
			name=place.name,
			number=place.phone or 'no number published',
			hours=place.opening_hours or 'hours not published',
			kind=ContactKind.nearest_facility,
			updated_line=f'{km:.1f} km away',
		)
		return [row.model_copy(update={'actions': self.hotline_actions(row, lang)})] if place.phone else [row]