"""Gate: §6.2's ten content principles, as checks over the text a person actually reads.

§6.2 is titled "Content Principles" and all ten of its rules were prose. A library item, a triage
recommendation, a myth correction, a peer alert or a USSD menu could stigmatise the person it
described, carry a spec section number, or promise a certainty nobody can promise, and nothing
failed. The only tone check anywhere was a four-word alarmist list inside one service.

The rule this file is written under, learned the expensive way: a check that fails correct content
is worse than no check, because it trains its reader to skip the line. So every rule here was run
against the live corpus *before* it was trusted, and the two that failed correct content were
rescoped rather than the content changed — §6.2.1 does not govern a form label, and §6.2.6's "every
answer" does not reach a tree question. Two genuine findings did come out of it: two differential
answers carried an em dash, which is outside GSM-7 and so could not be sent as the SMS §6.2.6
promises, and three served strings named the spec section they were implementing.
"""
from pathlib import Path

import pytest

from afya.community.service import CORRECTION_LIBRARY, CommunityService
from afya.community.views import PeerAlert
from afya.info.principles import (
	BANNED_DIRECTIVES,
	ALARMIST_PHRASES,
	STIGMA_SUBSTITUTIONS,
	Subject,
	judge,
	judge_corpus,
	library_texts,
	tree_texts,
)
from afya.info.service import InfoService
from afya.mobile.actions import FRIENDLY_COPY, catalogue
from afya.strings import TRIAGE_RECS, USSD_MENU
from afya.triage.service import RECMAP
from afya.triage.views import RECOMMENDATIONS

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'


# --- the canaries. Each rule is pointed at a known-bad text and watched to fire. ----------------

def test_the_stigma_rule_fires_on_the_sections_own_examples() -> None:
	"""§6.2.9 gives two substitutions verbatim. Both must be caught, in the words it uses."""
	victim = judge('c', 'An Ebola victim should be isolated at once.', Subject.content)
	assert [v.rule for v in victim.failures()] == ['stigmatising_language']
	assert 'a person who is sick' in victim.failures()[0].detail
	zone = judge('c', 'People travelling from the Ebola zone must report.', Subject.content)
	assert [v.rule for v in zone.failures()] == ['stigmatising_language']
	assert 'the area where a case was reported' in zone.failures()[0].detail


def test_the_stigma_rule_does_not_fire_on_the_replacement() -> None:
	"""The canary that matters. A rule that also rejects its own remedy is a rule nobody can obey:
	§6.2.9 tells the writer to say "a person who is sick", so that sentence must pass."""
	for good in (
		'A person who is sick with Ebola should be isolated at once.',
		'Anyone travelling from the area where a case was reported must report.',
		'Traditional washing of EVD bodies spreads the virus.',
	):
		assert judge('c', good, Subject.content).clean(), f'false positive on {good!r}'


def test_the_panic_rule_fires_on_both_the_forbidden_and_the_prescribed_sentence() -> None:
	"""§6.2.5 bans "don't panic" *and* tells the writer to give a concrete action instead. Both are
	calm-down instructions, so both are caught — a single scan for the word "panic" would fail the
	section's own remedy while passing the sentence it forbids."""
	for bad in ("Don't panic. Wash your hands.", 'Do not panic, but stay home.', 'Usiogope, osha mikono.'):
		f = judge('i', bad, Subject.content)
		assert not f.clean(), f'the calm-down instruction must be caught: {bad!r}'


def test_the_action_rule_fires_on_an_answer_that_says_nothing_to_do() -> None:
	"""§6.2.1: 'Information without action is noise.' The section's own bad example."""
	f = judge('a', 'Ebola is a viral haemorrhagic fever.', Subject.answer)
	assert [v.rule for v in f.failures()] == ['no_action']


def test_the_action_rule_accepts_the_sections_own_good_example() -> None:
	"""§6.3 prints the sentence it wants: 'You have fever and no travel history. In Kenya this is
	most often malaria. Please get a malaria test at a clinic today.'"""
	good = ('You have fever and no travel history. In Kenya this is most often malaria. '
	        'Please get a malaria test at a clinic today. Call 719 if you develop bleeding.')
	assert judge('a', good, Subject.answer).clean()
	# And a disposition is an action. Telling someone there is nothing to do answers the question.
	assert judge('a', 'No action needed.', Subject.answer).clean()


def test_the_spec_reference_rule_fires_and_the_seed_is_clean_of_it() -> None:
	"""A section number read aloud by §ACC-001's read-aloud interface is the same failure as a
	feature code on a screen. It reached three served strings before this gate existed."""
	assert not judge('a', 'Test and treat for malaria first (spec 6.3).', Subject.answer).clean()
	assert not judge('c', 'See Tier 4 for details.', Subject.content).clean()


def test_the_forwardable_rule_fires_on_a_character_outside_gsm7() -> None:
	"""§6.2.6's SMS half is a hard constraint: an em dash doubles the segment count and can arrive
	as mojibake. Two differential answers carried one."""
	f = judge('a', 'Go to a facility — the danger is dehydration. Call 719.', Subject.answer)
	assert [v.rule for v in f.failures()] == ['not_forwardable']


def test_the_low_literacy_rule_reviews_rather_than_fails() -> None:
	"""§6.2.10 is a design intent, and a burial protocol may legitimately run long. The flag is for
	a person; it must not block publication."""
	long_text = 'This sentence ' + 'runs on and on ' * 12 + 'to the end.'
	f = judge('c', long_text, Subject.content)
	assert f.failures() == [] and [v.rule for v in f.reviews()] == ['long_sentence']


def test_a_decimal_point_is_not_a_sentence_break() -> None:
	"""'38.5 °C' is one sentence. Splitting on the point would count a two-word fragment as long."""
	f = judge('a', 'A temperature of 38.5 is a fever. Call 719 if it stays high.', Subject.answer)
	assert [v.rule for v in f.reviews()] == []


# --- the tables cannot drift from the section they enforce -------------------------------------

def test_every_banned_phrase_is_the_specs_own_words() -> None:
	"""The tables are transcribed from §6.2, not paraphrased. If the section is revised, this fails
	until the table moves with it — otherwise the gate keeps enforcing a rule that no longer exists."""
	spec = SPEC.read_text(encoding='utf-8')
	assert 'Never say "don\'t panic."' in spec, 'the §6.2.5 rule this table enforces'
	assert 'Say "a person who is sick," not "an Ebola victim."' in spec, 'the §6.2.9 rule this table enforces'
	assert 'Say "the area where a case was reported," not "the Ebola zone."' in spec
	# §6.2.9's *rule* is "avoid stigmatising language" and its two substitutions are examples of it,
	# so the table may hold more instances than the section prints — but every substitution the
	# section does print must be in the table, in its own words, and nothing else may claim to be one.
	stated = {(r, rejected) for _, _, r, rejected in STIGMA_SUBSTITUTIONS if rejected in spec}
	assert stated == {
		('a person who is sick', 'an Ebola victim'),
		('the area where a case was reported', 'the Ebola zone'),
	}, stated
	# The one row the section does not print is the generalisation, and it is named as such here so
	# a reader can tell a transcribed rule from a derived one.
	derived = {(r, rejected) for _, _, r, rejected in STIGMA_SUBSTITUTIONS if rejected not in spec}
	assert derived == {('a person who passed the infection to others', 'a superspreader')}, derived


def test_the_tables_are_not_vacuous() -> None:
	"""A canary for the canaries: an empty table would make every rule above pass while proving
	nothing."""
	assert len(BANNED_DIRECTIVES) >= 2 and len(ALARMIST_PHRASES) >= 3 and len(STIGMA_SUBSTITUTIONS) >= 3


# --- the corpus, judged in full ----------------------------------------------------------------

def _corpus() -> list[tuple[str, str, Subject]]:
	"""Every surface §6.2 governs, as `(name, text, genre)`.

	The genre is per surface and it is the whole reason this gate does not produce false positives:
	a form label is not an answer, and a question asked of the reader is not an answer either.
	"""
	svc = InfoService()
	items = list(library_texts(svc.all_items()))
	items += tree_texts(svc.TREE)
	# A correction answers "is this true", not "what should I do" — `cure_claim` is a factual
	# correction with no disposition in it, and §6.2.1 does not govern it. Judging these as answers
	# failed nine correct strings, which is the failure mode this file exists to avoid.
	items += [(f'corr:{k}:{lang}', v, Subject.content) for k, texts in CORRECTION_LIBRARY.items() for lang, v in texts.items()]
	items += [(f'rec:{lang}:{k}', v, Subject.answer) for lang, d in TRIAGE_RECS.items() for k, v in d.items()]
	items += [(f'recmap:{k}', v, Subject.answer) for k, v in RECMAP.items()]
	items += [(f'risk:{k.value}', v, Subject.answer) for k, v in RECOMMENDATIONS.items()]
	items += [(f'ussd:{k}', v, Subject.content) for k, v in USSD_MENU.items()]
	items += [(f'copy:{k}', f'{t} {d}', Subject.content) for k, (t, d) in FRIENDLY_COPY.items()]
	# Catalogue titles, labels and placeholders are read by a person filling a form. Each is judged
	# on its own — concatenating a form's labels into one string would invent a sentence nobody ever
	# reads, and the long-sentence rule would fire on the join rather than on any real text.
	for act in catalogue():
		items.append((f'act:{act.id}', act.title, Subject.content))
		for fl in act.fields:
			items.append((f'field:{act.id}.{fl.name}', f'{fl.label} {fl.placeholder or ""}', Subject.content))
	return items


def test_the_whole_corpus_obeys_six_two() -> None:
	"""The gate. Every served string in the corpus, judged by the genre it is."""
	findings = [f for f in judge_corpus(_corpus()) if not f.clean()]
	report = [(f.surface, [(v.rule, v.detail) for v in f.verdicts]) for f in findings]
	assert report == [], f'§6.2 violations in the served corpus: {report}'


def test_the_corpus_is_not_empty() -> None:
	"""Canary for the gate above: if `_corpus()` ever returned nothing, it would pass while checking
	nothing at all."""
	corpus = _corpus()
	assert len(corpus) >= 80, f'the corpus collapsed to {len(corpus)} surfaces'
	assert {s for _, _, s in corpus} == {Subject.answer, Subject.content}, 'every genre must be exercised'


def test_the_gate_catches_a_planted_violation_in_the_real_corpus() -> None:
	"""The gate is only evidence if it fails on a corpus that contains the thing it looks for. This
	plants one violation into the real list and asserts the same comparison the gate makes."""
	corpus = _corpus() + [('planted', 'An Ebola victim must be isolated.', Subject.content)]
	findings = [f.surface for f in judge_corpus(corpus) if not f.clean()]
	assert findings == ['planted'], 'the corpus gate must catch a stigmatising sentence planted in it'


# --- the two call sites, so the rules are applied and not merely available ----------------------

async def test_publishing_refuses_a_stigmatising_item() -> None:
	"""The rule is enforced where content is written, not only in CI. A gate that exists is not a
	gate that is applied.

	This goes through the route rather than calling `content_verdicts` directly. The first version of
	this test called the service method, and a canary that deleted the route's refusal still passed —
	a test of the method is not a test of the call site, and the whole point is that the call site
	exists.
	"""
	import httpx

	from afya.auth.service import AuthService
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	sysadmin = auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token
	h = {'authorization': f'Bearer {sysadmin}'}
	body: dict[str, object] = {
		'item_id': 'x', 'title': 'Guidance', 'body': 'An Ebola victim must be isolated.',
		'lang': 'en', 'harmony_tag': 'official', 'slug': 'guidance',
		'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1,
	}
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		refused = await c.post('/info/content', json=body, headers=h)
		assert refused.status_code == 422, refused.text
		assert 'stigmatising_language' in refused.text, 'the refusal must say which rule was broken'
		# And the corrected sentence is accepted by the same route.
		body['body'] = 'A person who is sick with Ebola must be isolated.'
		assert (await c.post('/info/content', json=body, headers=h)).status_code == 200


async def test_a_peer_alert_is_refused_on_the_sections_rules_not_a_local_list() -> None:
	"""The peer-alert gate carried its own four-word list, which would not have moved if §6.2 did.
	It now runs the same table — and this is the surface that showed the table must apply to a
	broadcast as well as to reference material, since a peer alert is read by a whole village."""
	svc = CommunityService()
	alert = PeerAlert(alert_id='PA-1', headline='Panic: outbreak spreads', verified_by='PHEOC',
	                  county='Busia', lat=0.5, lon=34.1, radius_m=1000, location='Budalangi market',
	                  issued_iso='2026-10-10')
	with pytest.raises(AssertionError, match='tone rejected'):
		await svc.send_peer_alert(alert)
	# The case the old local list missed. "Panic" was one of its four words; "an Ebola victim" was
	# not, and a broadcast that names a neighbour that way is the harm §6.2.9 exists to prevent.
	# A canary that reverted this call site to its own list passed until this text was added. The
	# sentence around it is now the section's own template, so the location is where the words go.
	stigmatising = PeerAlert(alert_id='PA-3', headline='Ebola in Busia',
	                         location='An Ebola victim was found at the market',
	                         verified_by='PHEOC', county='Busia', lat=0.5, lon=34.1, radius_m=1000,
	                         issued_iso='2026-10-10')
	with pytest.raises(AssertionError, match='tone rejected'):
		await svc.send_peer_alert(stigmatising)
	# A calm, actionable alert passes, and the section's own prescribed shape is not itself refused.
	ok = PeerAlert(alert_id='PA-2', headline='Ebola in Busia', location='Busia market',
	               verified_by='PHEOC', county='Busia', lat=0.5, lon=34.1, radius_m=1000,
	               issued_iso='2026-10-10')
	await svc.send_peer_alert(ok)
	assert len(svc.peer_alerts('Busia')) == 1


async def test_the_governance_view_reports_the_audit() -> None:
	"""§6.5's governance view is where a reviewer looks; the §6.2 audit belongs on it, so a finding
	that predates the check is visible rather than assumed absent."""
	import httpx

	from afya.auth.service import AuthService
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	auditor = auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		gov = (await c.get('/info/content/governance', headers={'authorization': f'Bearer {auditor}'})).json()
	assert 'content_principles' in gov
	assert gov['content_principles'] == [], f'the served corpus must be clean: {gov["content_principles"]}'
