"""§6.5's localisation workflow — the two verification steps as evidence, not stage names.

§6.5's fourth bullet is an arrow list: "English draft → clinical review → translation →
back-translation → community validation → publish." Four of its six steps were carried. The draft
and the clinical review are `ContentItem` fields nobody can omit; `published` is the stage the
library filters on; `translation` is the step that brings a translated row into existence. The two
steps between the translation and the publish were names. `advance(item_id, to='back_translation')`
moved an item and recorded nothing about whether anyone had rendered the translation back, or taken
it to a community, or what either found — so the whole workflow could be walked by one person in a
minute with every stage behind it and no check performed at any of them.

Three things follow from taking the two steps at their word:

* **A back-translation is a text and a person.** The method's content is that someone who has not
  seen the source renders the translation back into it, so the record carries the rendered text and
  who produced it. A render that comes back identical to the source is *reported* rather than
  trusted: the method's premise is that a faithful render returns in different words, so an identical
  one means either the renderer read the source or the "translation" is the source. That is a signal
  and not a proof — a two-word string can match by chance — so it is reported and not gated.

* **Community validation is done by the community.** §1452 is explicit that the sensitive content is
  "developed with religious leaders, community elders, and anthropologists", while §6.5's own table
  puts the drafting with the Comms team, so the validator is a party outside the drafting unit and
  the record names the role. The three people are required to be distinct, because a step performed
  by the person whose work it checks is the step's name without the step: a translator who
  back-translates their own text and then validates it has signed the same work three times.

* **A source-language item has no translation step, and that is what makes the arrow one arrow.**
  `translation`, `back_translation` and `community_validation` are steps of *producing a
  translation*, so they are walked by the translated counterpart and not by the English draft it came
  from. The route accepted `advance('INF-003-en', to='back_translation')` — an English item rendered
  back into English — because the arrow list is walked per row and nothing asked what the row was.
  With the split made explicit the six steps are one sequence again, read across the two rows of a
  slug: the English row goes draft → clinical review → published, the translated row is created at
  `translation` and carries back-translation → community validation → published.

The record is written in the order the arrow is walked rather than all at once, which is why the two
steps are two models and not one. `BackTranslation` exists when the item reaches `back_translation`;
`CommunityValidation` is written when it reaches `community_validation`. A record carrying the
community's verdict at the back-translation stage would date a check to before it happened, and a
client asked to re-send the rendered text on the second write is a client that can silently change
it.
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator

from afya.info.views import ContentItem, ContentStage

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §6.5's arrow starts at the English draft, so the source language is the section's own word rather
# than a choice made here. It is also what §6.2.4 lists second in `REQUIRED_LANGS`: the section
# orders serving "local language first, English second" while the workflow still drafts in English.
SOURCE_LANG = 'en'

# The three steps that produce or verify a translation. They are the ones a source-language item has
# no business walking, and the ones whose later members claim a check has been performed.
TRANSLATION_STAGES: tuple[ContentStage, ...] = (
	ContentStage.translation, ContentStage.back_translation, ContentStage.community_validation,
)

# The two steps that produce evidence, in the order §6.5's arrow walks them. Named here so the
# service, the gate and the report use the same words for the same steps.
BACK_TRANSLATION_STEP = 'back_translation'
COMMUNITY_VALIDATION_STEP = 'community_validation'


def workflow_for(lang: str) -> tuple[ContentStage, ...]:
	"""§6.5's arrow as the stages *this* row walks, which is not one list for both rows.

	§6.5's sentence is one arrow and the code carried it as one list, so `advance` walked every row
	through `translation`, `back_translation` and `community_validation` — including the English row,
	which would have to be translated from English and rendered back into it. Reading the arrow as
	what it describes rather than as a list of stages fixes that: the steps in the middle are steps of
	*producing a translation*, so the source row skips them and the translated row is the one that
	walks them.

	The two lists concatenated are the section's arrow, in order, with `translation` standing at the
	point the two rows hand over: the source row reaches `clinical_review`, the translation step
	produces the translated row, and that row carries the rest. `archived` is on neither, because it
	is reachable from anywhere rather than being a step of the walk.
	"""
	if lang == SOURCE_LANG:
		return (ContentStage.draft, ContentStage.clinical_review, ContentStage.published)
	return (
		ContentStage.draft, ContentStage.translation, ContentStage.back_translation,
		ContentStage.community_validation, ContentStage.published,
	)


def next_stage(item: ContentItem) -> ContentStage | None:
	"""The stage §6.5's arrow moves this row to next, or None at the end of the walk.

	Returned rather than asserted so the refusal can name the stage that *is* next: "clinical_review
	advances to published, not translation" tells a caller what happened, where "illegal transition"
	does not.
	"""
	order = workflow_for(item.lang)
	assert item.stage in order, f'{item.item_id} is at {item.stage.value}, which is not a stage this row walks'
	index = order.index(item.stage)
	return order[index + 1] if index + 1 < len(order) else None


def _norm(text: str) -> str:
	"""Whitespace- and case-insensitive, because a render differing only in spacing came back the
	same and the comparison is about the words."""
	return ' '.join(text.split()).casefold()


class BackTranslation(BaseModel):
	"""§6.5's back-translation step: the rendered text and who produced it.

	Nothing has a default. A record that could be constructed without a name would be one that says a
	step happened while nobody is accountable for it, which is the failure the stage names were
	already making — the same reason §6.5's owner and reviewer have no defaults on `ContentItem`.
	"""
	model_config = MODEL_CONFIG
	item_id: str = Field(min_length=1)
	translated_by: str = Field(min_length=1, description='who produced the translation (§6.5)')
	back_translated_by: str = Field(min_length=1, description='who rendered it back, without the source')
	back_translation: str = Field(min_length=1, description='the translation rendered back into the source language')
	at_ms: int = Field(default=0, ge=0)

	@model_validator(mode='after')
	def _the_renderer_is_not_the_translator(self) -> 'BackTranslation':
		"""Refused at construction rather than reported, because a record naming one person twice is
		not a workflow with a gap in it — it is a false statement about who checked what."""
		if self.back_translated_by == self.translated_by:
			raise ValueError(
				'a back-translation rendered by the translator is not a back-translation: the method '
				'needs someone who has not seen the source'
			)
		return self


class CommunityValidation(BaseModel):
	"""§6.5's community validation step: who took it to the community, and what they said.

	`concerns` is recorded rather than resolved: a concern is the substance of the step, and whether
	it was acted on is a judgement the reviewer makes from the text, not one this model can make from
	a list. It is a list of plain sentences, not a nested structure, so the mobile catalogue's generic
	form can compose it.
	"""
	model_config = MODEL_CONFIG
	item_id: str = Field(min_length=1)
	validated_by: str = Field(min_length=1, description='who took it to the community (§6.5)')
	validator_role: str = Field(min_length=1, description='the community role they hold (§1452)')
	concerns: list[str] = Field(default_factory=list)
	at_ms: int = Field(default=0, ge=0)


def separation_breach(back: BackTranslation, community: CommunityValidation) -> str | None:
	"""The rule that spans both steps, or None.

	It lives here rather than on either model because neither model can see the other, and it is
	checked when the two meet — on the write that makes it checkable, not left for a reader to
	notice. A step authored by the person whose work it checks is the step's name without the step: a
	translator who renders their own text back and then validates it has signed the same work three
	times.
	"""
	if community.validated_by in (back.translated_by, back.back_translated_by):
		return (
			'the community validator must be neither the translator nor the back-translator: a step '
			'authored by the person whose work it checks is the step\'s name without the step'
		)
	return None


class LocalisationState(BaseModel):
	"""One item's localisation as the facts a reviewer needs.

	`blocked` and `missing` are the two different ways a stage can be a name with nothing behind it.
	A source-language item at a translation stage is blocked — the stage does not apply to it at all.
	A translation at `back_translation` with no record is missing evidence — the stage applies and the
	step was not performed. Collapsing the two would report "record the back-translation" for an item
	that has no translation to render back.
	"""
	model_config = MODEL_CONFIG
	item_id: str
	slug: str
	lang: str
	stage: str
	is_translation: bool
	recorded: bool
	translated_by: str | None
	back_translated_by: str | None
	back_translated_at_ms: int | None
	validated_by: str | None
	validator_role: str | None
	validated_at_ms: int | None
	concerns: list[str]
	back_translation_matches_source: bool
	blocked: str | None
	missing: list[str]
	summary: str


def _claims(stage: ContentStage, is_translation: bool) -> tuple[str | None, list[str]]:
	"""What `stage` claims, as (the structural objection, the evidence it requires).

	Reaching a stage means the step that produced it is done, which is the reading `published` already
	carries. So the evidence is required *at* the stage rather than after it, and each record is
	written before the item is moved past the step that produces it.

	**`translation` requires no record and the two stages after it do.** A translation arriving is the
	act that produces the thing to render back, so there is nothing yet for a record to attest; the
	record is what the *next* two steps produce. That asymmetry is the arrow's own shape rather than a
	choice: back-translation is a step of verifying a translation, and community validation is a step
	of verifying what the back-translation found.
	"""
	if not is_translation:
		if stage in (ContentStage.draft, ContentStage.clinical_review, ContentStage.published):
			return None, []
		return (
			f'{stage.value} is a step of producing a translation, and this item is the source text it '
			f'would be translated from', [],
		)
	if stage is ContentStage.back_translation:
		return None, [BACK_TRANSLATION_STEP]
	if stage in (ContentStage.community_validation, ContentStage.published):
		return None, [BACK_TRANSLATION_STEP, COMMUNITY_VALIDATION_STEP]
	return None, []


def _missing(back: BackTranslation | None, community: CommunityValidation | None,
             wanted: list[str]) -> list[str]:
	"""Which of `wanted` the records do not evidence, each named on its own.

	One predicate, so a step cannot be reported present by the gate and absent by the report. Each
	step is judged separately rather than the whole set collapsing: an item whose back-translation is
	on file and whose community step is not has *one* gap, and a report that named both would send a
	reviewer to redo a check that is already done.
	"""
	out: list[str] = []
	if BACK_TRANSLATION_STEP in wanted and back is None:
		out.append(BACK_TRANSLATION_STEP)
	if COMMUNITY_VALIDATION_STEP in wanted and community is None:
		out.append(COMMUNITY_VALIDATION_STEP)
	return out


def localisation(item: ContentItem, back: BackTranslation | None, community: CommunityValidation | None,
                 source_body: str | None, now_ms: int,
                 at_stage: ContentStage | None = None) -> LocalisationState:
	"""§6.5's localisation for one item, at its stage or at the stage it is being moved to.

	The records and `source_body` are the service's facts and are passed in rather than looked up:
	this function knows what §6.5 requires, and the service knows what the shelf holds. `at_stage`
	exists because `advance` has to ask whether the item *would* be legal at the stage it is entering,
	and asking that of the stage it is leaving is the off-by-one that would make the gate decorative.
	"""
	assert now_ms >= 0, 'a clock is not negative'
	stage = at_stage if at_stage is not None else item.stage
	is_translation = item.lang != SOURCE_LANG
	blocked, wanted = _claims(stage, is_translation)
	missing = _missing(back, community, wanted)
	matches = bool(back and source_body and _norm(back.back_translation) == _norm(source_body))
	return LocalisationState(
		item_id=item.item_id, slug=item.slug or item.item_id, lang=item.lang, stage=stage.value,
		is_translation=is_translation, recorded=back is not None or community is not None,
		translated_by=back.translated_by if back else None,
		back_translated_by=back.back_translated_by if back else None,
		back_translated_at_ms=back.at_ms if back else None,
		validated_by=community.validated_by if community else None,
		validator_role=community.validator_role if community else None,
		validated_at_ms=community.at_ms if community else None,
		concerns=list(community.concerns) if community else [],
		back_translation_matches_source=matches,
		blocked=blocked, missing=missing,
		summary=_summary(item, back, community, stage, is_translation, blocked, matches),
	)


def _summary(item: ContentItem, back: BackTranslation | None, community: CommunityValidation | None,
             stage: ContentStage, is_translation: bool, blocked: str | None,
             matches: bool) -> str:
	"""One sentence an operator can act on, in plain language and inside GSM-7.

	It names the step that is *absent*, not the list of steps that are not yet done: "no
	back-translation on file" is an instruction, "back_translation, community_validation missing" is a
	field dump. `missing` remains the machine-readable form for the same reason.

	It carries no spec code and no section reference — §6.2.1 and §3.3 principle 9 apply to anything
	a person reads, and this line is read by the team under time pressure.
	"""
	name = item.slug or item.item_id
	if blocked:
		return f'{name}: {blocked}.'
	if not is_translation:
		return f'{name} is the source text, so the translation steps do not apply to it.'
	if back is None:
		return f'{name} is at {stage.value} with no back-translation on file.'
	parts = [
		f'{name} was translated by {back.translated_by} and rendered back by {back.back_translated_by}.'
	]
	if matches:
		parts.append(
			'The back-translation came back identical to the source, so the render may not have been '
			'blind.'
		)
	if community is None:
		parts.append('It has not been taken to the community yet.')
	else:
		parts.append(f'{community.validated_by} ({community.validator_role}) validated it with the community.')
		if community.concerns:
			parts.append('The community raised: ' + '; '.join(community.concerns) + '.')
	return ' '.join(parts)

