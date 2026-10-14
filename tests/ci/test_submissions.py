"""§CHAN-004's two user-content bullets, held open: "User-generated content from satisfied users
(with consent)" and '"Day in the life" CHW content'.

The section prints them as content the social channel carries and the tree carried neither half —
no submission path, no consent for publishing a person's words, no moderation. These tests are about
the failures rather than the happy path, because the happy path is the easy part and every way this
path can be wrong is a way a person's words get published without their agreement:

* **The consent check can silently never fire.** `PrivacyService.has_consent` matches on
  `subject_ref`, and a story carries a §SEC-004 *handle* as well. A submission whose consent is filed
  under the subject but whose author is the handle has to still match — and the test that proves it
  is the one worth reading, because the opposite arrangement (comparing the handle) is a check that
  is always False and never fails a run.
* **Approval can look like publication.** An approved story must be a `draft` in §6.5's workflow,
  invisible to a reader, and carrying the `harmony_tag` `library()` asserts — a story approved with
  no tag passes approval and then 500s at serve time.
* **A consent log can show a slug.** `publish_story` is not one of §SEC-001's eight categories, so
  the person reading back what they agreed to is owed words, and `EXTRA_CONSENT_PURPOSES` is where
  they come from — asserted in both directions, the way `UNGATED_WRITES` is.
"""
from afya.info.service import InfoService
from afya.info.submissions import STORY_PURPOSE, StoryKind, StoryService, StoryStatus, StorySubmission
from afya.info.views import ContentStage
from afya.privacy.service import (
	CONSENT_CATALOGUE, EXTRA_CONSENT_PURPOSES, MANDATORY_NOTIFICATION_PURPOSES, PrivacyService,
)
from afya.privacy.views import ConsentCategory, ConsentRecord, LegalBasis

SUBJECT = 'SUBJ-1'
# A §SEC-004 handle: starts with a letter, as `PseudonymPolicy.handle` requires, and is *not* the
# subject. The whole point of the split is that these two values differ.
HANDLE = 'Tembo-a1b2'


def _services() -> tuple[PrivacyService, InfoService, StoryService]:
	privacy, info = PrivacyService(), InfoService()
	return privacy, info, StoryService(privacy, info)


def _consent(subject: str = SUBJECT, purpose: str = STORY_PURPOSE,
             withdrawn: bool = False) -> ConsentRecord:
	return ConsentRecord(
		subject_ref=subject, purpose=purpose, data_types=[purpose],
		retention_days=365, legal_basis=LegalBasis.consent, withdrawn=withdrawn,
	)


def _story(kind: StoryKind = StoryKind.testimonial, subject: str = SUBJECT, author: str = HANDLE,
           text: str = 'The app helped me find the clinic when my child had a fever.',
           consent_id: str = 'c-1', submitted_at_ms: int = 1000) -> StorySubmission:
	return StorySubmission(
		kind=kind, subject_ref=subject, author=author, author_role='parent',
		text=text, lang='en', consent_id=consent_id, submitted_at_ms=submitted_at_ms,
	)


# --- submit(): the consent it refuses without ---------------------------------------------------

async def test_submit_refuses_with_no_consent() -> None:
	"""No record handed over is a caller that did not look one up — not a person who declined."""
	_svc_privacy, _info, svc = _services()
	story = _story()
	try:
		svc.submit(story)
	except PermissionError as exc:
		assert 'without your consent' in str(exc)
	else:  # pragma: no cover - the refusal is the assertion
		raise AssertionError('a story was filed with no consent at all')
	assert svc.stories() == [], 'a refused story must not be stored'


async def test_submit_refuses_a_withdrawn_consent() -> None:
	"""§SEC-001's one-tap revocation: a withdrawn record is not consent, the same rule
	`has_category_consent` applies."""
	_svc_privacy, _info, svc = _services()
	try:
		svc.submit(_story(), _consent(withdrawn=True))
	except PermissionError as exc:
		assert 'withdrawn' in str(exc)
	else:  # pragma: no cover
		raise AssertionError('a withdrawn consent covered a story')


async def test_submit_refuses_someone_elses_consent() -> None:
	"""A consent that names a different subject is a stranger's grant, whatever it is for."""
	_svc_privacy, _info, svc = _services()
	try:
		svc.submit(_story(subject=SUBJECT), _consent(subject='SOMEONE-ELSE'))
	except PermissionError as exc:
		assert 'someone else' in str(exc)
	else:  # pragma: no cover
		raise AssertionError("a stranger's consent covered a story")


async def test_submit_refuses_a_consent_for_another_purpose() -> None:
	"""Publishing a person's words under a symptom-storage or research grant is a person told one
	thing and done another — the failure §SEC-001's purpose granularity exists to prevent."""
	_svc_privacy, _info, svc = _services()
	for purpose in (ConsentCategory.research.value, ConsentCategory.symptom_storage.value):
		try:
			svc.submit(_story(), _consent(purpose=purpose))
		except PermissionError as exc:
			assert purpose in str(exc)
		else:  # pragma: no cover
			raise AssertionError(f'a {purpose} consent published a story')


async def test_submit_accepts_a_real_consent() -> None:
	_svc_privacy, _info, svc = _services()
	story = _story()
	filed = svc.submit(story, _consent())
	assert filed.status is StoryStatus.submitted
	assert svc.pending() == [story]


async def test_a_handle_author_still_matches_a_subject_filed_consent() -> None:
	"""The critical point: `has_consent` matches on `subject_ref`, and a story carries a §SEC-004
	handle too.

	The consent is filed under `SUBJECT`; the story's `author` is the handle. The submission must
	still be accepted, because the check reads `subject_ref` — which is why the model carries both.
	The mirror case, immediately below, is the failure this guards: a consent filed under the
	*handle* does not cover a story whose subject is `SUBJECT`, so a submission carrying only a handle
	could never match its own consent and the check would be silently always False.
	"""
	_svc_privacy, _info, svc = _services()
	story = _story(subject=SUBJECT, author=HANDLE)
	assert story.author != story.subject_ref, 'the handle and the subject are different values by design'
	filed = svc.submit(story, _consent(subject=SUBJECT))
	assert filed.status is StoryStatus.submitted
	# And the consent filed under the handle — the value that reaches a screen — does not match.
	try:
		svc.submit(_story(subject=SUBJECT, author=HANDLE), _consent(subject=HANDLE))
	except PermissionError as exc:
		assert 'someone else' in str(exc)
	else:  # pragma: no cover
		raise AssertionError('a handle-keyed consent matched a subject-keyed story')


async def test_submit_refuses_a_duplicate_story_id() -> None:
	_svc_privacy, _info, svc = _services()
	story = _story()
	svc.submit(story, _consent())
	try:
		svc.submit(story, _consent())
	except AssertionError as exc:
		assert 'duplicate' in str(exc)
	else:  # pragma: no cover
		raise AssertionError('the same story id was filed twice')


# --- approve(): it writes a draft and serves nothing --------------------------------------------

async def test_approve_leaves_the_item_at_draft_and_out_of_the_library() -> None:
	"""Approval is §CHAN-004's moderation step; publication is §6.5's. The item must be a draft, and
	it must not be in what a reader can fetch."""
	_svc_privacy, info, svc = _services()
	story = _story()
	svc.submit(story, _consent())
	item = await svc.approve(story.story_id, 'mod-1', at_ms=2_000)
	assert item.stage is ContentStage.draft, 'approval published the story instead of drafting it'
	assert item.answers_rank is None, 'a testimonial is not a §6.1 life-safety answer'
	assert svc.story(story.story_id).status is StoryStatus.approved
	assert all(c.item_id != story.story_id for c in info.library('en')), \
		'an approved-but-unpublished story was visible to a reader'


async def test_approve_sets_a_harmony_tag_so_a_later_publish_cannot_500() -> None:
	"""`upsert_content` asserts only id/title and is not the publishing route, so a story written
	through it with `harmony_tag=None` passes approval and then **asserts at serve time** in
	`library()`. The tag is set on approval, and this walks the item to published to prove the serve
	path no longer raises."""
	_svc_privacy, info, svc = _services()
	story = _story(kind=StoryKind.day_in_the_life)
	svc.submit(story, _consent())
	item = await svc.approve(story.story_id, 'mod-1', at_ms=2_000)
	assert item.harmony_tag, 'an approved story carries no harmony tag, so library() will 500 on it'
	# The later publish §6.5 would perform. With no tag this raises inside library(), not here.
	published = item.model_copy(update={'stage': ContentStage.published})
	await info.upsert_content(published)
	served = info.library('en')
	assert any(c.item_id == story.story_id for c in served), \
		'a published story with a harmony tag did not reach the library'


async def test_approve_refuses_text_that_breaks_6_2() -> None:
	"""§6.2's rules apply to a story as they do to any served item. "an Ebola victim" is the
	stigmatising sentence §6.2.9 exists to stop, and it is refused at approval rather than published
	and found later."""
	_svc_privacy, info, svc = _services()
	story = _story(text='I was an Ebola victim and the app helped me.')
	svc.submit(story, _consent())
	try:
		await svc.approve(story.story_id, 'mod-1', at_ms=2_000)
	except AssertionError as exc:
		assert '§6.2' in str(exc) and 'stigmatising' in str(exc)
	else:  # pragma: no cover
		raise AssertionError('a stigmatising story was approved')
	assert all(c.item_id != story.story_id for c in info.all_items()), \
		'a refused story was written into the content library anyway'
	assert svc.story(story.story_id).status is StoryStatus.submitted, \
		'a refused story is still awaiting a decision'


async def test_an_approved_but_unpublished_story_is_invisible_to_a_reader() -> None:
	_svc_privacy, info, svc = _services()
	story = _story()
	svc.submit(story, _consent())
	await svc.approve(story.story_id, 'mod-1', at_ms=2_000)
	assert info.by_slug(story.story_id) is not None, 'the draft exists for the reviewer'
	assert all(c.item_id != story.story_id for c in info.library('en')), 'a reader could fetch it'


# --- pending() and decline() --------------------------------------------------------------------

async def test_pending_shows_only_submitted_stories() -> None:
	"""A decided story belongs in neither a queue nor a second queue."""
	_svc_privacy, _info, svc = _services()
	a, b, c = _story(submitted_at_ms=1000), _story(submitted_at_ms=2000), _story(submitted_at_ms=3000)
	for s in (a, b, c):
		svc.submit(s, _consent())
	await svc.approve(a.story_id, 'mod-1', at_ms=4000)
	svc.decline(b.story_id, 'mod-1', 'reads as a product endorsement rather than a person', at_ms=4000)
	assert [s.story_id for s in svc.pending()] == [c.story_id]


async def test_a_declined_story_carries_its_reason() -> None:
	_svc_privacy, _info, svc = _services()
	story = _story()
	svc.submit(story, _consent())
	declined = svc.decline(story.story_id, 'mod-2', 'please resubmit without the clinic name', at_ms=2000)
	assert declined.status is StoryStatus.declined
	assert declined.moderation_note == 'please resubmit without the clinic name'
	assert declined.moderator == 'mod-2'
	assert svc.pending() == [], 'a declined story stayed in the queue'


async def test_a_decline_needs_a_reason() -> None:
	_svc_privacy, _info, svc = _services()
	story = _story()
	svc.submit(story, _consent())
	try:
		svc.decline(story.story_id, 'mod-2', '   ', at_ms=2000)
	except AssertionError as exc:
		assert 'reason' in str(exc)
	else:  # pragma: no cover
		raise AssertionError('a story was declined with no reason the person could read')


async def test_a_decided_story_cannot_be_decided_again() -> None:
	_svc_privacy, _info, svc = _services()
	story = _story()
	svc.submit(story, _consent())
	svc.decline(story.story_id, 'mod-2', 'not a fit', at_ms=2000)
	try:
		await svc.approve(story.story_id, 'mod-1', at_ms=3000)
	except AssertionError as exc:
		assert 'already declined' in str(exc)
	else:  # pragma: no cover
		raise AssertionError('a declined story was approved afterwards')


# --- EXTRA_CONSENT_PURPOSES, asserted in both directions ----------------------------------------

def test_every_extra_consent_purpose_is_one_the_tree_files_and_every_filed_one_is_named() -> None:
	"""The `UNGATED_WRITES` shape: the table names purposes the tree files, and every purpose the
	tree files outside §SEC-001's eight is named.

	The set the tree files is `MANDATORY_NOTIFICATION_PURPOSES` (the four the legal-obligation path
	files) plus `STORY_PURPOSE` (what §CHAN-004's submission path files). Equality is both directions
	at once: a key here that the tree does not file is a sentence nobody is shown, and a purpose the
	tree files with no key here is a person shown a raw slug on their own consent log.
	"""
	filed = set(MANDATORY_NOTIFICATION_PURPOSES) | {STORY_PURPOSE}
	assert set(EXTRA_CONSENT_PURPOSES['en']) == filed, (
		'the extra-purpose table and the purposes the tree files disagree: '
		f'table={sorted(EXTRA_CONSENT_PURPOSES["en"])}, filed={sorted(filed)}'
	)


def test_the_extra_purposes_do_not_touch_sec_001s_eight() -> None:
	"""§SEC-001 prints eight categories and the catalogue asserts its eight. `EXTRA_CONSENT_PURPOSES`
	is a second *kind* of purpose, not a ninth category."""
	assert len(CONSENT_CATALOGUE) == 8
	assert {c.category for c in CONSENT_CATALOGUE} == set(ConsentCategory)
	assert not (set(EXTRA_CONSENT_PURPOSES['en']) & {c.value for c in ConsentCategory})


def test_every_extra_purpose_has_words_in_both_languages() -> None:
	assert set(EXTRA_CONSENT_PURPOSES['en']) == set(EXTRA_CONSENT_PURPOSES['sw'])
	for lang, table in EXTRA_CONSENT_PURPOSES.items():
		for slug, row in table.items():
			assert set(row) == {'label', 'on_withdrawal'}, f'{lang}/{slug} is incomplete'
			assert all(row.values()), f'{lang}/{slug} has an empty sentence'
			assert row['label'] != slug, f'{lang}/{slug} labels itself with its own slug'


# --- the consent log shows words, not a slug ----------------------------------------------------

async def test_the_consent_log_shows_words_not_a_slug() -> None:
	"""A person reading back what they agreed to must not be shown `publish_story`. The log copies
	the words as they stood, so the label is read off the event the grant wrote."""
	privacy, _info, _svc = _services()
	rec = await privacy.record_consent(_consent())
	history = privacy.consent_history(SUBJECT)
	granted = [e for e in history.events if e.action == 'granted']
	assert len(granted) == 1
	assert granted[0].label == 'Publish my story'
	assert STORY_PURPOSE not in granted[0].label, 'the log showed the raw purpose slug'
	assert granted[0].consequence, 'the person was told nothing about withdrawing it'
	assert STORY_PURPOSE in history.live, 'the live set carries the purpose the ledger holds'


async def test_the_label_falls_back_to_the_purpose_only_when_nothing_describes_it() -> None:
	"""A purpose with no row anywhere is returned as itself — the honest answer for a grant the
	ledger holds and no table names — while a purpose with a row is never returned raw."""
	privacy, _info, _svc = _services()
	assert privacy._label('publish_story') == 'Publish my story'
	assert privacy._label('some_unmapped_purpose') == 'some_unmapped_purpose'
	assert privacy._label('sensor_monitoring:gps') == 'sensor_monitoring:gps', \
		'a per-sensor grant keeps its slug, as it did before this table existed'
