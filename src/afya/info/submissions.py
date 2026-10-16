"""§CHAN-004's two user-content bullets: "User-generated content from satisfied users (with
consent)" and '"Day in the life" CHW content'.

Both were `missing` for the same shape of reason: the section prints them as content the social
channel carries, and this tree had no way for a person to submit one, no consent that covers
*publishing a person's words*, and nothing that moderates what arrives. §SEC-004's per-item consent
is for a photo attached to an evidence record and is not this — a testimonial is a person's own
speech put on a public channel, which is a different decision from handing over a picture of a rash.

**Two identifiers, and the split is the whole design.** `subject_ref` is the subject the consent is
filed under; `author` is §SEC-004's rotating handle, the only one of the two that ever reaches a
screen. They have to be *different* — a public story that carried the subject reference would put a
person's ledger key on a feed — and that difference is exactly what makes the consent check easy to
get wrong. `PrivacyService.has_consent` matches on `subject_ref`, so a submission carrying only a
handle could never match its own consent and the check would silently never fire: `submit` would
refuse every real story, or — worse, in the other arrangement — a handle compared against a subject
would be the thing nobody notices is always False. The model therefore carries both, and the tests
prove a submission whose consent is filed under the subject but whose author is the handle still
matches.

**Approval is not publication.** `approve` constructs a `ContentItem` at `ContentStage.draft` and
writes it through `InfoService.upsert_content`, so a story must walk §6.5's existing workflow like
every other item. It is deliberately *not* served by `approve`, and it is deliberately not placed at
`published`: a moderator approving a story is a §CHAN-004 act, and publishing clinical content is
§6.5's, which has a clinical review, a translation, a back-translation and a community validation
this module does not perform.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.auth.views import now_ms
from afya.ids import ref8
from afya.info.service import InfoService
from afya.info.views import CONTENT_LANG_PATTERN, ContentItem, ContentStage
from afya.logmixin import LogMixin
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentRecord

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# The purpose a §CHAN-004 testimonial is filed under. It lives here rather than in §SEC-001's
# catalogue because it is not one of that section's eight categories: filing a story to publish
# under "research" or "share with health authorities" would be a person told one thing and done
# another, which is the failure a consent ledger exists to make impossible. `PrivacyService` labels
# it from `EXTRA_CONSENT_PURPOSES`, and `tests/ci/test_submissions.py` asserts the two key sets agree
# in both directions — the module cannot import this constant without cycling, so the test is where
# the join is checked.
STORY_PURPOSE = 'publish_story'

# The unit accountable for a published story, as §6.5's `owner`. A name rather than a spec
# reference: `owner` is not served to a reader today, but it is the field a reviewer reads on the
# governance screen and the one §6.5 makes every item carry, so it follows the corpus's own
# convention (`SEED_OWNER` is "MoH Health Promotion Unit") rather than naming a section.
STORY_OWNER = 'MoH Health Promotion Unit'

# The moderation statuses a submission moves through. `submitted` is the only state `pending()`
# serves and the only one a moderator has not acted on; `declined` is terminal, and the reason it
# carries is what the person is told.
STORY_KINDS = ('testimonial', 'day_in_the_life')


class StoryKind(str, Enum):
	"""§CHAN-004's two user-content bullets as the two things they are.

	`testimonial` is "user-generated content from satisfied users (with consent)" — a person saying
	the product helped them. `day_in_the_life` is '"Day in the life" CHW content' — a community
	health worker describing their own day. Both are first-person material the channel publishes, so
	they share one path; the kind is what a moderator and a reader are told they are looking at.
	"""

	testimonial = 'testimonial'
	day_in_the_life = 'day_in_the_life'


class StoryStatus(str, Enum):
	submitted = 'submitted'
	approved = 'approved'
	declined = 'declined'


class StorySubmission(BaseModel):
	"""One submitted story, with the two identifiers kept apart and the consent it rests on named.

	`author_role` is the person's own description of who they are (a CHW, a patient, a parent) and is
	not the handle: a §CHW-004 "day in the life" is worth publishing *because* the author is a
	community health worker, and the handle deliberately hides that. The role is the thing the
	section asks for; the handle is the thing §SEC-004 requires.

	`media_ref` is optional because a testimonial may be text alone. When present it is a reference
	to an asset produced through §6.5 — the same `media_ref` a `ContentItem` rendition carries — and
	is not uploaded here: this module holds a story's words and the *name* of any recording, not the
	recording.
	"""

	model_config = MODEL_CONFIG
	# `ref8()` and not a truncation of a UUID7: a UUID7's leading hex *is* its millisecond
	# timestamp, so `uuid7str()[:10]` is constant across a 256 ms window and two stories submitted in
	# the same breath took one id — the collision `afya.ids` documents for diary entries, which the
	# first draft of this model reproduced and this test caught.
	story_id: str = Field(default_factory=lambda: 'ST-' + ref8())
	kind: StoryKind
	# The subject the consent is filed under. Never served, never on a screen — it is what
	# `has_consent` matches, and the tests exist because comparing a handle against it would be
	# silently always False.
	subject_ref: str = Field(min_length=1)
	# §SEC-004's rotating handle, and the only identifier a reader sees. Kept distinct from
	# `subject_ref` on purpose: a public story carrying the ledger key would put a person's consent
	# reference on a feed.
	author: str = Field(min_length=1, description='§SEC-004 rotating handle, never a subject reference')
	author_role: str = Field(min_length=1)
	text: str = Field(min_length=1)
	lang: str = Field(default='en', pattern=CONTENT_LANG_PATTERN)
	# The consent this story rests on, by id. Required at the model: a story with no consent to point
	# at is a story nobody agreed to have published, and the default that let one exist was the shape
	# the audit row described.
	consent_id: str = Field(min_length=1)
	media_ref: str | None = None
	status: StoryStatus = StoryStatus.submitted
	moderator: str | None = None
	moderation_note: str | None = None
	submitted_at_ms: int = Field(default_factory=now_ms, ge=0)


class StoryIn(BaseModel):
	"""What a submitter sends. The **author handle is not here**, for the reason `QuestionIn` gives.

	A handle in the body is a handle a caller can choose, and a story filed under someone else's
	name is one the moderation queue cannot attribute. The route derives it from the token's own
	subject — the same rule §SEC-004's rotating handle rests on, that it is derived rather than
	claimed. `author_role` *is* here, because it is the person's own description of who they are and
	nothing else can supply it.
	"""

	model_config = MODEL_CONFIG
	subject_ref: str = Field(min_length=1)
	kind: StoryKind
	author_role: str = Field(min_length=1)
	text: str = Field(min_length=1)
	lang: str = Field(default='en', pattern=CONTENT_LANG_PATTERN)
	consent_id: str = Field(min_length=1)
	media_ref: str | None = None

	def as_submission(self, author: str) -> StorySubmission:
		"""The stored model, with the handle the route derived rather than one the caller sent."""
		return StorySubmission(
			kind=self.kind, subject_ref=self.subject_ref, author=author, author_role=self.author_role,
			text=self.text, lang=self.lang, consent_id=self.consent_id, media_ref=self.media_ref,
		)


class StoryModerationIn(BaseModel):
	"""What a moderator sends: the decision and the note. Who moderated is the token, not a field.

	`decision` is a word rather than a bool because it is what the moderation screen offers and
	because `False` does not say *why* — a declined story carries a reason, and a bool body has
	nowhere to put one without a second field that is meaningless on the approve path.
	"""

	model_config = MODEL_CONFIG
	decision: str = Field(pattern='^(approve|decline)$')
	note: str | None = None
	at_ms: int | None = None


class StoryService(LogMixin):
	"""The submission, moderation and approval path for §CHAN-004's user content.

	It holds the `PrivacyService` (for the consent it refuses without) and the `InfoService` (for the
	`ContentItem` it writes on approval) rather than reimplementing either: the consent ledger has one
	reader, and the content library has one writer.
	"""

	def __init__(self, privacy: PrivacyService, info: InfoService) -> None:
		self._privacy = privacy
		self._info = info
		self._stories: dict[str, StorySubmission] = {}
		assert self._stories == {}

	def submit(self, story: StorySubmission, consent: ConsentRecord | None = None) -> StorySubmission:
		"""File a story, and refuse it without a real consent behind it.

		Four things must hold, and each is a distinct way a submission is not consented to:

		* a `ConsentRecord` is supplied at all — `None` is a caller that did not look one up;
		* it is **the story's own subject's** — matched on `subject_ref`, which is why the model
		  carries the subject and not only the handle;
		* it is not withdrawn — §SEC-001's one-tap revocation, so a withdrawn record is not consent;
		* it is filed under `STORY_PURPOSE` — a symptom-storage or research grant is consent to
		  something else, and publishing a person's words under it is a person told one thing and
		  done another.

		The check is here rather than only at the route because there is more than one way in — the
		route, a moderation queue replay, a future importer — and a control fitted to one door is a
		control the others walk past, which is the rule §SEC-002's photo pipeline states one module
		over. `has_consent` is deliberately not the check: it reads the ledger by id-less predicate
		and would answer True for a *different* record under the same subject and purpose, so the
		refusals name the record the caller handed over rather than a matching one in the store.
		"""
		assert story.story_id not in self._stories, f'duplicate story id {story.story_id}'
		if consent is None:
			raise PermissionError('this story cannot be published without your consent')
		if consent.subject_ref != story.subject_ref:
			raise PermissionError('this consent belongs to someone else, so it does not cover this story')
		if consent.withdrawn:
			raise PermissionError('this consent was withdrawn, so the story cannot be published')
		if consent.purpose != STORY_PURPOSE:
			raise PermissionError(
				f'this consent is for {consent.purpose!r}, not for publishing a story; '
				'a person who agreed to one thing has not agreed to another'
			)
		self._stories[story.story_id] = story
		self._log_info('story submitted', story_id=story.story_id, kind=story.kind.value)
		return story

	def pending(self) -> list[StorySubmission]:
		"""The moderation queue: stories submitted and not yet acted on, oldest first.

		Only `submitted`. An approved or declined story has been decided and belongs in neither a
		queue nor a second queue — a moderator reading it again would be reading something already
		answered.
		"""
		return sorted(
			(s for s in self._stories.values() if s.status is StoryStatus.submitted),
			key=lambda s: (s.submitted_at_ms, s.story_id),
		)

	async def approve(self, story_id: str, moderator: str, at_ms: int | None = None) -> ContentItem:
		"""Approve a story into §6.5's workflow at `draft`, and return the item it became.

		**It does not serve anything.** The item is written through `InfoService.upsert_content` at
		`ContentStage.draft`, so a story must then walk §6.5's clinical review, translation,
		back-translation and community validation like every other item before `library()` will serve
		it. Approval is §CHAN-004's moderation step; publication is §6.5's, and this module does not
		perform it.

		**It sets `harmony_tag` and runs `content_verdicts` itself.** `upsert_content` asserts only
		`item_id` and `title` and is not the publishing route — a story written through it with
		`harmony_tag=None` would pass approval and then **assert at serve time** in `library()`, which
		is a 500 rather than a refusal, and a story whose text breaks §6.2 would reach the shelf. So
		the tag is set here (a testimonial is content, and §6.2 requires every served item carry a
		tag), and the verdicts are read here and refused here — the same §6.2 rules the library
		applies, at the one moment the text can still be sent back.

		`answers_rank` stays `None` deliberately: a testimonial is not an answer to one of §6.1's ten
		life-safety questions, and §6.2.4's "never publish English-only for a life-safety message"
		must not withhold a story for a missing translation it never needed.
		"""
		story = self._stories[story_id]
		assert story.status is StoryStatus.submitted, f'{story_id} is already {story.status.value}'
		item = ContentItem(
			item_id=story.story_id,
			title=self._title(story),
			body=story.text,
			lang=story.lang,
			harmony_tag=self._tag(story),
			slug=story.story_id,
			owner=STORY_OWNER,
			reviewer=moderator,
			reviewed_on_iso=self._iso_day(at_ms if at_ms is not None else now_ms()),
			version=1,
			stage=ContentStage.draft,
			media_ref=story.media_ref,
		)
		failures = self._info.content_verdicts(item)
		assert not failures, (
			f'{story_id} breaks §6.2 and cannot be approved: '
			f'{"; ".join(f"{v.rule}: {v.detail}" for v in failures)}'
		)
		self._stories[story_id] = story.model_copy(update={
			'status': StoryStatus.approved, 'moderator': moderator,
		})
		self._log_info('story approved', story_id=story_id, moderator=moderator)
		return await self._info.upsert_content(item, at_ms=at_ms)

	def decline(self, story_id: str, moderator: str, reason: str, at_ms: int | None = None) -> StorySubmission:
		"""Decline a story, and record why.

		The reason is required — a decline with no note is a decision a person cannot learn from, and
		the section's whole point is that the contributor is a member of the audience. `at_ms` is
		accepted for symmetry with `approve` and is deliberately unused: a declined story is terminal
		and carries no timestamp of its own, the same shape `record_sub_county` states for its own
		unused clock.
		"""
		story = self._stories[story_id]
		assert story.status is StoryStatus.submitted, f'{story_id} is already {story.status.value}'
		assert reason.strip(), 'a decline carries the reason the person is told'
		declined = story.model_copy(update={
			'status': StoryStatus.declined, 'moderator': moderator, 'moderation_note': reason,
		})
		self._stories[story_id] = declined
		self._log_warn('story declined', story_id=story_id, moderator=moderator)
		return declined

	def story(self, story_id: str) -> StorySubmission:
		return self._stories[story_id]

	def stories(self) -> list[StorySubmission]:
		"""Every story at every status, oldest first. The moderation view reads this; `pending()` is
		the queue."""
		return sorted(self._stories.values(), key=lambda s: (s.submitted_at_ms, s.story_id))

	@staticmethod
	def _tag(story: StorySubmission) -> str:
		"""The harmony tag a story is published under, derived from its kind.

		A `day_in_the_life` story is CHW material and is browsed under `chw`; a testimonial is filed
		under `testimonial`. Neither is `MYTH_TAG` — a story is not a rumour and its correction, and
		`ContentItem` asserts that pairing — so the tags are named here rather than left to the
		writer, which is what stops a story reaching `library()` with a tag of `None` and asserting
		at serve time.
		"""
		return 'chw' if story.kind is StoryKind.day_in_the_life else 'testimonial'

	@staticmethod
	def _title(story: StorySubmission) -> str:
		"""A title a reader can place, without naming the person.

		The kind and the role, not the text: a title cut from the body would be the first sentence of
		a story used as its heading, which reads as an editorial claim rather than as the person's own
		words. `author_role` is safe here where `author` is not the point — a story is worth
		publishing because its author is a CHW, and the handle is what hides which CHW.
		"""
		kind = 'A day in the life' if story.kind is StoryKind.day_in_the_life else 'In their own words'
		return f'{kind}: {story.author_role}'

	@staticmethod
	def _iso_day(at_ms: int) -> str:
		"""The calendar day of an instant, as §6.5's `reviewed_on_iso` requires.

		§6.5 dates a review by the day it happened, and this is the moderator's decision day rather
		than the submitter's — an item approved today is reviewed today.
		"""
		from datetime import datetime, timezone
		return datetime.fromtimestamp(at_ms / 1000, tz=timezone.utc).date().isoformat()


assert STORY_KINDS == tuple(k.value for k in StoryKind), 'every §CHAN-004 user-content bullet is a kind'
