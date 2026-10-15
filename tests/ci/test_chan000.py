"""§CHAN-000's drama vignette: the script's shape, and the §6.2 gate that refuses a bad one.

The audit row for "Pre-recorded drama vignettes on prevention, care-seeking, and stigma" is
`deferred`, not `carried`, and this file is written to hold that line. What is deferred is the
RECORDING — a produced audio asset in a local language, which §ACC-001 and §ACC-002 both refuse to
synthesise without a validated speaker. What is buildable, and what these tests exercise, is the
SCRIPT: the cast, the numbered scenes, the attributed dialogue, and the §6.2 review that runs
before a station ever sees it.

The tests that matter are the ones about the *refusals*. A model that only ever accepts a
well-formed vignette would pass every happy-path assertion here and catch nothing: the two defects
this file exists to refuse are a line spoken by somebody who is not in the cast, and a vignette
about stigma that stigmatises. Both are written as known-bad input rather than described.
"""
import pytest
from pydantic import ValidationError

from afya.channels.service import ChannelService
from afya.channels.views import (
	RadioVignette, VignetteLine, VignetteScene, VignetteTheme,
)


def _svc() -> ChannelService:
	"""The channel service with no SMS port. `schedule_vignette` never touches it."""
	return ChannelService(sms=_NoSms())


class _NoSms:
	async def send(self, msg: object) -> str:
		raise AssertionError('a vignette is not an SMS')


def _vignette(**overrides: object) -> RadioVignette:
	"""A well-formed prevention vignette: two characters, two numbered scenes, every line cast.

	The dialogue is deliberately free of every §6.2 marker — no stigma word, no calm-down
	instruction, no spec reference — so a test that wants a failure has to write the failing line
	itself rather than inherit one from this fixture.
	"""
	data: dict[str, object] = {
		'vignette_id': 'VIG-TEST',
		'station': 'KBC',
		'air_date': '2026-10-14',
		'duration_s': 60,
		'theme': VignetteTheme.prevention,
		'lang': 'sw',
		'roles': {'Mama Achieng', 'Juma'},
		'scenes': [
			VignetteScene(number=1, setting='a homestead in the evening', lines=[
				VignetteLine(speaker='Mama Achieng', text='Wash your hands with soap before you cook.'),
				VignetteLine(speaker='Juma', text='I will keep a bucket by the door.'),
			]),
			VignetteScene(number=2, setting='the same homestead, next morning', lines=[
				VignetteLine(speaker='Juma', text='The bucket is full and the soap is beside it.'),
				VignetteLine(speaker='Mama Achieng', text='Good. Tell your brother to do the same.'),
			]),
		],
		'script': 'A short drama about washing hands before cooking.',
	}
	data.update(overrides)
	return RadioVignette(**data)  # type: ignore[arg-type]


# --- the three themes ---------------------------------------------------------------------------

def test_the_theme_list_is_the_sections_three_and_only_three() -> None:
	"""§CHAN-000 names three themes in a closed list. The enum is that list, pinned as a set.

	Pinned by name rather than by length, because "the enum has three members" passes the moment
	somebody adds a fourth and deletes one — the count is not the claim, the three words are.
	"""
	assert {t.value for t in VignetteTheme} == {'prevention', 'care-seeking', 'stigma'}


@pytest.mark.parametrize('theme', list(VignetteTheme))
def test_a_vignette_is_constructible_for_every_theme(theme: VignetteTheme) -> None:
	"""One vignette per theme. A theme the model cannot be built under is a theme on paper."""
	assert _vignette(theme=theme).theme is theme


# --- the shape a vignette is --------------------------------------------------------------------

def test_a_vignette_has_a_cast_and_numbered_scenes() -> None:
	assert _vignette().cast == ['Juma', 'Mama Achieng']


def test_every_line_is_spoken_by_somebody_in_the_cast() -> None:
	"""The check a vignette model exists for: no voice without a character behind it."""
	v = _vignette()
	assert all(
		line.speaker in v.roles for scene in v.scenes for line in scene.lines
	)


def test_a_line_spoken_by_somebody_outside_the_cast_is_refused() -> None:
	"""The known-bad input. A third voice appears in scene 2 and is in nobody's cast.

	This is the defect the model exists to catch: a line attributed to a character who is not in
	`roles` is a script that cannot be recorded as written — somebody at the station would have to
	invent a character the writer never wrote.
	"""
	bad = _vignette()
	with pytest.raises(ValidationError, match='not in its cast'):
		RadioVignette(**{
			**bad.model_dump(),
			'scenes': [
				bad.scenes[0].model_dump(),
				{
					'number': 2,
					'setting': bad.scenes[1].setting,
					'lines': [{'speaker': 'A stranger', 'text': 'Do not come near this house.'}],
				},
			],
		})


def test_scenes_are_numbered_from_one_without_gaps() -> None:
	"""A director calls "scene 3" off the page, so the numbers are the running order.

	A vignette whose only scene is numbered 2 is the missing-scene case: the list is the script and
	the numbers are what the station reads, so a gap is a scene that was written and dropped.
	"""
	with pytest.raises(ValidationError, match='numbered from 1 without gaps'):
		_vignette(roles={'Juma'}, scenes=[
			VignetteScene(number=2, setting='a homestead', lines=[
				VignetteLine(speaker='Juma', text='I am here.'),
			]),
		])


def test_a_language_outside_the_sections_coverage_is_refused() -> None:
	"""§CHAN-000 lists the languages it broadcasts in. A code outside the registry is not one.

	The message is asserted as the sentence a caller reads, not as the section id: this refusal is
	served verbatim in a 422, and a spec code in it is the leak the vocabulary gate now catches.
	"""
	with pytest.raises(ValidationError, match='not a language this station broadcasts in'):
		_vignette(lang='fr')


# --- the runtime fits the slot ------------------------------------------------------------------

def test_the_script_fits_the_slot_and_a_long_one_does_not() -> None:
	"""The same `300 chars/sec` bound `schedule_bulletin` asserts, on the same slot.

	The long script is a literal multiple of the bound rather than computed from it: an input
	derived from the constant under test moves with it, so a bound loosened to fit would loosen the
	test that is supposed to catch it.
	"""
	assert _vignette(duration_s=15, script='x' * 4500).duration_s == 15
	with pytest.raises(ValidationError, match='script too long for slot'):
		_vignette(duration_s=15, script='x' * 4501)


# --- §6.2 runs over the script, and refuses a bad one -------------------------------------------

async def test_a_clean_vignette_is_scheduled() -> None:
	assert (await _svc().schedule_vignette(_vignette())).vignette_id == 'VIG-TEST'


async def test_a_stigmatising_line_is_refused_by_the_gate() -> None:
	"""The failure this row's own theme list invites: a vignette about stigma that stigmatises.

	The known-bad line is written out in full — it is the exact wording §6.2.9 forbids ("an Ebola
	victim" for "a person who is sick"). A gate that only ever saw the clean fixture above would
	pass forever; this is the input that proves it bites.
	"""
	bad = _vignette(theme=VignetteTheme.stigma, scenes=[
		VignetteScene(number=1, setting='a market', lines=[
			VignetteLine(speaker='Juma', text='Do not buy from her, she is an Ebola victim.'),
		]),
	])
	with pytest.raises(AssertionError, match='stigmatising_language'):
		await _svc().schedule_vignette(bad)


async def test_a_calm_down_instruction_is_refused_by_the_gate() -> None:
	"""§6.2.5's ban, on the second wording that is not the stigma table."""
	bad = _vignette(scenes=[
		VignetteScene(number=1, setting='a market', lines=[
			VignetteLine(speaker='Juma', text='Do not panic, the clinic is open.'),
		]),
	])
	with pytest.raises(AssertionError, match='banned_directive'):
		await _svc().schedule_vignette(bad)


async def test_the_gate_reads_the_dialogue_and_not_only_the_script_field() -> None:
	"""A stigmatising word spoken by a character is stigmatising wherever it is typed.

	The `script` field here is clean; the offending word is in a line of dialogue. A gate that
	judged only the free-text field would pass this, which is why the gate assembles the dialogue.
	"""
	bad = _vignette(
		script='A short drama about what to do when a neighbour is unwell.',
		scenes=[VignetteScene(number=1, setting='a market', lines=[
			VignetteLine(speaker='Juma', text='That family lives in the Ebola zone.'),
		])],
	)
	assert 'Ebola zone' not in bad.script
	with pytest.raises(AssertionError, match='stigmatising_language'):
		await _svc().schedule_vignette(bad)


async def test_a_long_line_of_dialogue_is_a_review_and_not_a_refusal() -> None:
	"""§6.2.10 is a design intent, so `_low_literacy` flags rather than fails — and the vignette
	gate must carry that distinction rather than turn every review flag into a refusal."""
	long_line = ' '.join(['word'] * 30) + '.'
	v = _vignette(scenes=[
		VignetteScene(number=1, setting='a homestead', lines=[
			VignetteLine(speaker='Juma', text=long_line),
		]),
	])
	assert (await _svc().schedule_vignette(v)).vignette_id == 'VIG-TEST'


# --- the audit rows this unit moved ------------------------------------------------------------
# The five §CHAN-0 / §CHAN-4 rows are pinned here as well as in `test_content_audit.py`, and for a
# different reason: that file asserts the *counts*, and this one asserts the *carriers* — a row that
# says `carried` while naming a module that does not exist is a bullet someone thinks is done. The
# two are read off `content_report()` rather than restated, so a row that moves fails here.

def test_the_callin_and_the_clinician_qa_are_carried_by_one_mechanism() -> None:
	"""§CHAN-000's call-in and §CHAN-004's clinician Q&A were the same absence on two channels.

	They close together because they *are* one thing — a clinician answering questions from people
	who are listening — and the two entries differ in which platform carries the programme. A fix
	that closed one and left the other would be a queue the radio has and the social channel does
	not, which is the same programme described twice.
	"""
	from afya.content_audit.service import FEATURE_CONTENT
	by_bullet = {(f, b): (k, ref) for f, _, b, k, ref, _ in FEATURE_CONTENT}
	kind, ref = by_bullet[('CHAN-000', 'Call-in Q&A with a health worker')]
	assert kind == 'carried' and ref == 'afya.live.service:LiveService', (kind, ref)
	kind, ref = by_bullet[('CHAN-004', 'Live Q&A with clinicians')]
	assert kind == 'carried' and ref == 'afya.live.service:LiveService.schedule', (kind, ref)


def test_the_vignette_is_deferred_and_the_recording_is_what_is_deferred() -> None:
	"""The row is `deferred` rather than `carried`, and the reason is the master tape, not the script.

	This is the line the module docstring draws and the one most easily crossed: the script is here,
	a station records it, and a person voices it. A future change that marked this `carried` would be
	claiming an audio asset this tree does not hold — and §ACC-001 and §ACC-002 both refuse synthetic
	narration in a local language no speaker has validated, so the tree cannot produce one either.
	"""
	from afya.content_audit.service import FEATURE_CONTENT
	by_bullet = {(f, b): (k, ref, n) for f, _, b, k, ref, n in FEATURE_CONTENT}
	kind, ref, note = by_bullet[(
		'CHAN-000', 'Pre-recorded drama vignettes on prevention, care-seeking, and stigma')]
	assert kind == 'deferred' and ref is None
	assert note is not None and 'fact about the world' in note, note


def test_the_three_rows_that_stay_open_are_the_ones_this_unit_does_not_change() -> None:
	"""§ACC-001, §ACC-002 and §CHAN-005 are the residue, and each is open for a reason of its own.

	§ACC-001's video tutorials in a local language are *new clinical copy* — a generator may not
	author one, because §6.5 has to clear it. §ACC-002's six-language ASR needs a corpus nobody has
	recorded. §CHAN-005's flip chart is a printed artefact. None of the three is closed by adding
	code, and a unit that closed one by reclassifying it would be making a gap disappear rather than
	closing it — which is what this assertion exists to catch.
	"""
	from afya.content_audit.service import content_report
	missing = {m.split(':')[0] for m in content_report().missing}
	assert missing == {'§ACC-001', '§ACC-002', '§CHAN-005'}, missing
