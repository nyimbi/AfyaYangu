"""§6.5's localisation workflow, as evidence rather than stage names.

The section's fourth bullet is an arrow: English draft → clinical review → translation →
back-translation → community validation → publish. Four of its six steps were carried. The two
between the translation and the publish were names, and `advance` walked every row through all of
them — including the English row, which would have to be translated from English.

Two things are under test here and they are different in kind. The **gate** is that a stage cannot
be entered without the evidence the step produces; the **report** is that a reviewer can see, item
by item, which steps are done, who did them, and what is missing. A gate whose gaps nobody can see
is a refusal with no route to fixing it, so both are asserted.
"""
import asyncio
import re

import httpx
import pytest
from fastapi import FastAPI

from afya.auth.service import AuthService
from afya.info.localisation import (
	BACK_TRANSLATION_STEP, COMMUNITY_VALIDATION_STEP, SOURCE_LANG, BackTranslation, CommunityValidation,
	localisation, separation_breach, workflow_for,
)
from afya.info.service import InfoService
from afya.info.views import WORKFLOW, ContentStage
from afya.privacy.views import RBACRole
from afya.service import build_services, create_app

# The spec codes must not reach anything a person reads. `INF-003-en` is a seed id and a slug is the
# code-free handle; a summary that carried the id would put a section number in front of the team
# under time pressure, which §3.3 principle 9 and §6.2.1 forbid of served text.
FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

T0 = 1_760_000_000_000


def _services() -> tuple[dict[str, object], dict[str, str]]:
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	sysadmin = auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
	auditor = auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
	return services, {'ops': sysadmin, 'auditor': auditor}


def _back(**overrides: object) -> dict[str, object]:
	body: dict[str, object] = {
		'item_id': 'INF-003-sw', 'translated_by': 'MoH translator',
		'back_translated_by': 'WHO verifier', 'back_translation': 'rendered back',
	}
	return {**body, **overrides}


def _community(**overrides: object) -> dict[str, object]:
	body: dict[str, object] = {
		'item_id': 'INF-003-sw', 'validated_by': 'Elder A', 'validator_role': 'community elder',
	}
	return {**body, **overrides}


def _app_and_headers() -> tuple[FastAPI, dict[str, str]]:
	services, tokens = _services()
	return create_app(services), {'authorization': f'Bearer {tokens["ops"]}'}


def test_the_workflow_is_one_arrow_read_across_two_rows() -> None:
	"""§6.5's arrow is one sentence and two walks.

	The code carried the arrow as a single list and walked every row through all of it, which is why
	the route accepted `advance('INF-003-en', to='back_translation')` — an English item rendered back
	into English. Read as what the section describes, the steps in the middle are steps of producing a
	translation: the source row reaches the clinical review, the translation step produces the
	translated row, and that row carries the rest. Concatenated they are the section's arrow in order,
	with `translation` standing where the two rows hand over.
	"""
	assert WORKFLOW == (
		ContentStage.draft, ContentStage.clinical_review, ContentStage.translation,
		ContentStage.back_translation, ContentStage.community_validation, ContentStage.published,
	), 'the flat list is §6.5\'s own order and stays as the section printed it'
	source = workflow_for(SOURCE_LANG)
	translated = workflow_for('sw')
	assert source == (ContentStage.draft, ContentStage.clinical_review, ContentStage.published)
	assert translated == (
		ContentStage.draft, ContentStage.translation, ContentStage.back_translation,
		ContentStage.community_validation, ContentStage.published,
	)
	# The two walks put together are the section's arrow, with `translation` at the handover. This is
	# the assertion that keeps the split honest: a stage added to §6.5 must appear in one of the two.
	merged = source[:-1] + translated[1:]
	assert merged == WORKFLOW
	assert ContentStage.archived not in source and ContentStage.archived not in translated, (
		'retirement is reachable from anywhere, so it is not a step of the walk'
	)


def test_a_source_item_cannot_be_translated_or_rendered_back() -> None:
	"""The English row has no translation step, and the refusal says so.

	This is the defect the section's own test carried: it walked `x` — an English item — through
	`translation` and `back_translation` and asserted 200 for both, which is an item translated from
	English and rendered back into it. The step is a check on a translation; with no translation there
	is nothing to check.
	"""
	services, tokens = _services()
	info: InfoService = services['info']  # type: ignore[assignment]
	item = info.by_slug('ebola-basics')
	assert item is not None and item.lang == SOURCE_LANG
	state = info.localisation_of(item, at_stage=ContentStage.translation)
	assert state.blocked, 'a source item at a translation stage is structurally blocked'
	assert state.missing == [], 'blocked is not the same gap as missing evidence'
	assert 'source text' in state.blocked
	assert not FEATURE_CODE.search(state.summary), 'the summary carries no spec code'
	# And the route refuses it, naming the stage that *is* next rather than the stage that is not.
	app, h = _app_and_headers()

	async def walk() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			bad = await c.post('/info/content/INF-003-en/advance?to=translation', headers=h)
			assert bad.status_code == 422, bad.text
			assert 'published' in bad.text, 'the refusal names the stage this row does advance to'

	asyncio.run(walk())


def test_back_translation_is_gated_on_the_record_and_the_record_names_a_second_person() -> None:
	"""§6.5's back-translation step: the rendered text and who produced it, and not the translator.

	The method's content is that someone who has not seen the source renders the translation back. A
	record naming the translator as the renderer is the step's name without the step — the same person
	reading their own work and calling it a check — so it is refused at construction rather than
	reported as a gap.
	"""
	# The English row cannot carry a back-translation at all: there is no translation to render back.
	bad_item = BackTranslation(item_id='INF-003-en', translated_by='A', back_translated_by='B', back_translation='x')
	state = localisation(
		InfoService().by_slug('ebola-basics'), bad_item, None, 'source body', T0,  # type: ignore[arg-type]
	)
	assert not state.is_translation and state.blocked is None, 'the record is inert on a source row; the service refuses it'
	# The renderer and the translator must be two people.
	with pytest.raises(ValueError, match='not a back-translation'):
		BackTranslation(item_id='INF-003-sw', translated_by='A', back_translated_by='A', back_translation='x')
	# Nothing has a default: a record that could be built without a name is one nobody is accountable for.
	for missing in ('item_id', 'translated_by', 'back_translated_by', 'back_translation'):
		body = _back()
		del body[missing]
		with pytest.raises(Exception):
			BackTranslation(**body)  # type: ignore[arg-type]
	# The route refuses the record before the stage can be entered.
	services, tokens = _services()
	app = create_app(services)
	h = {'authorization': f'Bearer {tokens["ops"]}'}
	auditor = {'authorization': f'Bearer {tokens["auditor"]}'}

	async def walk() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			assert (await c.post('/info/content/back-translation', json=_back(), headers=h)).status_code == 200
			rows = (await c.get('/info/content/localisation', headers=auditor)).json()
			row = next(r for r in rows if r['item_id'] == 'INF-003-sw')
			assert row['recorded'] and row['back_translated_by'] == 'WHO verifier'
			assert row['missing'] == [COMMUNITY_VALIDATION_STEP], 'the back-translation is done, the community step is not'

	asyncio.run(walk())


def test_the_back_translation_must_be_the_translated_row_past_its_translation() -> None:
	"""Two structural refusals, both about the step being performed on the right object.

	An English item rendered back into English is the check run on the wrong text, and a translation
	still at `draft` has not been produced yet, so there is nothing for a back-translation to verify.
	Both are refused by the service rather than reported as gaps: neither is a missing check, each is
	a check that could not have happened.
	"""
	services, _ = _services()
	info: InfoService = services['info']  # type: ignore[assignment]

	async def run() -> None:
		with pytest.raises(AssertionError, match='source text'):
			info.record_back_translation(BackTranslation(
				item_id='INF-003-en', translated_by='A', back_translated_by='B', back_translation='x',
			))
		await info.upsert_content(
			info.by_slug('ebola-basics').model_copy(  # type: ignore[union-attr]
				update={'item_id': 'new-sw', 'lang': 'sw', 'slug': 'new-message', 'stage': ContentStage.draft},
			),
		)
		with pytest.raises(AssertionError, match='before the translation'):
			info.record_back_translation(BackTranslation(
				item_id='new-sw', translated_by='A', back_translated_by='B', back_translation='x',
			))

	asyncio.run(run())


def test_community_validation_cannot_precede_the_text_the_community_sees() -> None:
	"""§6.5's community validation: the community is shown what the back-translation produced.

	Validating before it exists is validating nothing, so the record is refused until the
	back-translation is on file — not reported as a gap, because there is no step to be missing: the
	step's own input does not exist yet.
	"""
	services, _ = _services()
	info: InfoService = services['info']  # type: ignore[assignment]

	async def run() -> None:
		with pytest.raises(AssertionError, match='no back-translation on file'):
			info.record_community_validation(CommunityValidation(
				item_id='INF-003-sw', validated_by='Elder A', validator_role='community elder',
			))

	asyncio.run(run())


def test_the_validator_is_neither_the_translator_nor_the_renderer() -> None:
	"""The rule that spans both steps, checked where both are finally visible.

	A step authored by the person whose work it checks is the step's name without the step: a
	translator who renders their own text back and then validates it has signed the same work three
	times. Neither record can see the other, so the check lives where the two meet — on the write that
	makes it checkable.
	"""
	back = BackTranslation(item_id='INF-003-sw', translated_by='Translator', back_translated_by='Verifier',
	                       back_translation='x')
	assert separation_breach(back, CommunityValidation(
		item_id='INF-003-sw', validated_by='Elder A', validator_role='community elder')) is None
	for who in ('Translator', 'Verifier'):
		breach = separation_breach(back, CommunityValidation(
			item_id='INF-003-sw', validated_by=who, validator_role='community elder'))
		assert breach is not None and 'neither the translator nor the back-translator' in breach
	# And the service refuses it, which is where a caller actually meets the rule.
	services, _ = _services()
	info: InfoService = services['info']  # type: ignore[assignment]

	async def run() -> None:
		info.record_back_translation(back)
		with pytest.raises(AssertionError, match='neither the translator'):
			info.record_community_validation(CommunityValidation(
				item_id='INF-003-sw', validated_by='Translator', validator_role='community elder'))

	asyncio.run(run())


def test_a_stage_cannot_be_entered_without_its_evidence() -> None:
	"""The gate itself: `advance` refuses `back_translation` and `community_validation` without it.

	Without this the two stages are names. The walk is the section's own order, so the item *can*
	reach `translation` — that is the step that produces the translated row — and stops there until
	the evidence behind each following step is on file.
	"""
	services, tokens = _services()
	info: InfoService = services['info']  # type: ignore[assignment]
	app = create_app(services)
	h = {'authorization': f'Bearer {tokens["ops"]}'}
	auditor = {'authorization': f'Bearer {tokens["auditor"]}'}

	async def run() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			# A fresh translated row is created at `translation` and walks from there.
			seed = info.by_slug('ebola-basics')
			assert seed is not None
			body = seed.model_copy(update={
				'item_id': 'gate-sw', 'lang': 'sw', 'slug': 'gate-message', 'stage': ContentStage.translation,
			}).model_dump(mode='json')
			assert (await c.post('/info/content', json=body, headers=h)).status_code == 200
			# No back-translation on file: the stage is refused, and the refusal names the step.
			blocked = await c.post('/info/content/gate-sw/advance?to=back_translation', headers=h)
			assert blocked.status_code == 422, blocked.text
			assert BACK_TRANSLATION_STEP in blocked.text
			# The record is written, and now the stage is reachable.
			assert (await c.post('/info/content/back-translation', json=_back(item_id='gate-sw'), headers=h)).status_code == 200
			assert (await c.post('/info/content/gate-sw/advance?to=back_translation', headers=h)).status_code == 200
			# The community stage is still refused: the second step's evidence is not on file.
			blocked = await c.post('/info/content/gate-sw/advance?to=community_validation', headers=h)
			assert blocked.status_code == 422, blocked.text
			assert COMMUNITY_VALIDATION_STEP in blocked.text
			assert (await c.post('/info/content/community-validation', json=_community(item_id='gate-sw'), headers=h)).status_code == 200
			assert (await c.post('/info/content/gate-sw/advance?to=community_validation', headers=h)).status_code == 200
			# The review names both steps done and neither missing.
			rows = (await c.get('/info/content/localisation', headers=auditor)).json()
			row = next(r for r in rows if r['item_id'] == 'gate-sw')
			assert row['missing'] == [] and row['validated_by'] == 'Elder A'
			assert row['validator_role'] == 'community elder'

	asyncio.run(run())


def test_the_review_is_auditor_scoped_and_names_what_is_missing() -> None:
	"""The report is the other half of the gate: a refusal with no way to see the gap is a dead end.

	Auditor-scoped for the same reason the escalation log is — the person who walked an item through
	the workflow is not the person who checks it was walked, and a reviewer who can move the item can
	make their own evidence look complete.
	"""
	services, tokens = _services()
	info: InfoService = services['info']  # type: ignore[assignment]
	app = create_app(services)
	ops = {'authorization': f'Bearer {tokens["ops"]}'}
	auditor = {'authorization': f'Bearer {tokens["auditor"]}'}

	async def run() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			assert (await c.get('/info/content/localisation', headers=ops)).status_code == 403, (
				'the writer of the workflow is not its reader'
			)
			rows = (await c.get('/info/content/localisation', headers=auditor)).json()
			# Every translated item is listed, and each carries its own gap rather than a shared verdict.
			sw = [r for r in rows if r['lang'] == 'sw']
			assert sw, 'the seed corpus has Swahili rows'
			assert all(r['is_translation'] for r in sw)
			# The seed is published with no localisation record, which is the honest state of a corpus
			# that was never walked through the two steps — and the report says so rather than assuming
			# the stages imply the checks.
			published = next(r for r in sw if r['stage'] == 'published')
			assert published['recorded'] is False
			assert published['missing'] == [BACK_TRANSLATION_STEP, COMMUNITY_VALIDATION_STEP]
			assert 'no back-translation on file' in published['summary']
			assert not FEATURE_CODE.search(published['summary'])
			# The source rows are absent: the report is about translations, plus any source row sitting
			# at a translation stage, which is the workflow's own failure mode.
			assert not any(r['lang'] == SOURCE_LANG and r['stage'] == 'published' for r in rows)

	asyncio.run(run())


def test_the_review_surfaces_a_source_row_stranded_at_a_translation_stage() -> None:
	"""The one way a source row can be at a translation stage is by having been walked there.

	Nothing writes one there through the route any more, so the state is constructed directly — and it
	is exactly what the review has to catch: an English item at `back_translation` is the defect the
	split fixes, and a report scoped to translations alone would not list it.
	"""
	services, tokens = _services()
	info: InfoService = services['info']  # type: ignore[assignment]
	seed = info.by_slug('health-tips')
	assert seed is not None and seed.lang == SOURCE_LANG
	info._replace(seed, stage=ContentStage.back_translation)  # type: ignore[attr-defined]
	app = create_app(services)
	auditor = {'authorization': f'Bearer {tokens["auditor"]}'}

	async def run() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			rows = (await c.get('/info/content/localisation', headers=auditor)).json()
			stranded = next(r for r in rows if r['item_id'] == 'INF-008-en')
			assert stranded['blocked'], 'a source row at a translation stage is blocked, not merely missing'
			assert stranded['missing'] == []
			assert not FEATURE_CODE.search(stranded['summary'])

	asyncio.run(run())


def test_a_back_translation_that_came_back_identical_is_reported_not_trusted() -> None:
	"""The method's premise is that a faithful render returns in different words.

	An identical render means either the renderer read the source or the "translation" is the source.
	That is a signal and not a proof — a two-word string can match by chance — so it is reported
	beside the record and not gated: refusing it would block a legitimate short item, and the whole
	point of recording the text is that a reviewer can see it.
	"""
	services, tokens = _services()
	info: InfoService = services['info']  # type: ignore[assignment]
	source = info.by_slug('ebola-basics')
	assert source is not None
	app = create_app(services)
	ops = {'authorization': f'Bearer {tokens["ops"]}'}
	auditor = {'authorization': f'Bearer {tokens["auditor"]}'}

	async def run() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			# The English text rendered back word for word, and the same record with real differences.
			identical = await c.post('/info/content/back-translation', json=_back(back_translation=source.body), headers=ops)
			assert identical.status_code == 200
			row = next(r for r in (await c.get('/info/content/localisation', headers=auditor)).json()
			           if r['item_id'] == 'INF-003-sw')
			assert row['back_translation_matches_source'] is True
			assert 'identical' in row['summary']
			# Whitespace and case are not differences: the comparison is about the words.
			shuffled = _back(back_translation='  ' + source.body.upper() + ' ')
			state = info.record_back_translation(BackTranslation(**shuffled))  # type: ignore[arg-type]
			assert state.back_translation_matches_source is True
			# A genuinely different render is the normal case and is not flagged.
			info.record_back_translation(BackTranslation(**_back(back_translation='a different rendering')))  # type: ignore[arg-type]
			row = next(r for r in (await c.get('/info/content/localisation', headers=auditor)).json()
			           if r['item_id'] == 'INF-003-sw')
			assert row['back_translation_matches_source'] is False
			assert 'identical' not in row['summary']

	asyncio.run(run())


def test_the_gate_and_the_report_agree_on_whether_a_step_is_done() -> None:
	"""One predicate, two callers. A step reported present by the review and absent by the gate — or
	the reverse — is two definitions of the same fact, which is how a gate becomes decorative.

	The service's `advance` reads `localisation()`, the same function the review route serves, so the
	assertion here is that the *state* is the only input to the decision: with the record on file the
	stage is legal and the review says nothing is missing; with it removed both flip together.
	"""
	services, tokens = _services()
	info: InfoService = services['info']  # type: ignore[assignment]
	app = create_app(services)
	ops = {'authorization': f'Bearer {tokens["ops"]}'}

	async def run() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			seed = info.by_slug('safe-burial')
			assert seed is not None
			body = seed.model_copy(update={
				'item_id': 'agree-sw', 'lang': 'sw', 'slug': 'agree-message', 'stage': ContentStage.translation,
			}).model_dump(mode='json')
			await c.post('/info/content', json=body, headers=ops)
			info.record_back_translation(BackTranslation(**_back(item_id='agree-sw')))  # type: ignore[arg-type]
			state = info.localisation_of(info._content['agree-sw'])  # type: ignore[attr-defined]
			assert state.missing == [] and not state.blocked
			assert (await c.post('/info/content/agree-sw/advance?to=back_translation', headers=ops)).status_code == 200
			# Remove the record and both flip: the stage is no longer legal from here, and the review
			# reports the gap. The item is left where it is, so this is the same fact read twice.
			del info._back_translations['agree-sw']  # type: ignore[attr-defined]
			state = info.localisation_of(info._content['agree-sw'])  # type: ignore[attr-defined]
			assert state.missing == [BACK_TRANSLATION_STEP]
			assert (await c.post('/info/content/agree-sw/advance?to=community_validation', headers=ops)).status_code == 422

	asyncio.run(run())


def test_no_localisation_surface_leaks_a_spec_code() -> None:
	"""§3.3 principle 9 and §6.2.1: the team reading this is under time pressure, and a section number
	in front of them is noise where a sentence would be an instruction.

	The internal log keeps the item id, which embeds `INF-003`; nothing served does. This is the same
	rule the escalation row follows for the same reason.
	"""
	services, tokens = _services()
	info: InfoService = services['info']  # type: ignore[assignment]
	app = create_app(services)
	ops = {'authorization': f'Bearer {tokens["ops"]}'}
	auditor = {'authorization': f'Bearer {tokens["auditor"]}'}

	async def run() -> None:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			written = (await c.post('/info/content/back-translation', json=_back(), headers=ops)).json()
			# The record's own `item_id` is the reference a client posted and needs back; the *prose*
			# is where a code must not appear.
			for field in ('summary', 'blocked'):
				value = written.get(field)
				assert value is None or not FEATURE_CODE.search(value), f'{field} carries a spec code'
			for row in (await c.get('/info/content/localisation', headers=auditor)).json():
				assert not FEATURE_CODE.search(row['summary']), row['summary']
				assert not row['blocked'] or not FEATURE_CODE.search(row['blocked'])
				# The slug is the code-free handle and is what a person reads.
				assert not row['slug'].startswith('INF-')

	asyncio.run(run())
