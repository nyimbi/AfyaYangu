"""Gate: §6.5's escalation clause — a content error affecting safety, as a trigger.

§6.5's last bullet is one sentence: "**Escalation:** Any content error affecting safety triggers
immediate review and correction broadcast." It was the only bullet in the section with nothing
behind it. §6.5's *retirement* bullet was modelled — `archived` is a stage reachable from anywhere —
but retirement for being **outdated** and retirement for being **wrong** were the same state: an
item pulled because its review date passed and an item pulled because it told people to drink salt
water both read `archived`, and nothing said when the second was found, by whom, or that the
escalation had fired at all.

Four things this file is careful about, because each is a way the gate could pass while the clause
does not hold:

* **"Affecting safety" is read off §6.1, not accepted from the reporter.** The person retiring
  content under pressure is the last one to mark their own item as safety-affecting, so the trigger
  is asserted against the same `is_life_safety` set §6.2.4 keys on — including the case where the
  caller's own `langs` claim disagrees.
* **"Immediate" is a clock, not a word.** Neither §6.5 nor §24.8 prints a number, so the deadline is
  pinned to §24.3's own ladder rung for the severity §24.8 assigns, and the label beside it is
  required to move with the hours.
* **Retirement is per-message, not per-item.** A wrong English item and its Swahili translation are
  one claim in two languages; archiving only the item named leaves the other being served.
* **A broadcast that cannot be composed is not a broadcast.** The correction must carry every
  language §6.2.4 requires of a life-safety message, and the refusal must arrive *before* the feed
  is written, or the test would be asserting a 422 that already published.
"""
import re
from pathlib import Path
from typing import Any

import asyncio
import httpx
import pytest

from afya.info.escalation import (
	CORRECTION_FEED_CATEGORY, REVIEW_SLA_HOURS, REVIEW_SLA_LABEL, ContentError, escalate,
)
from afya.info.questions import REQUIRED_LANGS, is_life_safety
from afya.info.service import InfoService
from afya.info.views import ContentStage
from afya.operations.views import SUPPORT_SLA_HOURS, IncidentClass, IncidentSeverity
from afya.privacy.views import RBACRole
from afya.service import build_services, create_app

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

# The registry's own id grammar, reused so the code-free claim cannot drift from what ids look like.
FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

# A fixed instant to hang every assertion on. Nothing here reads the wall clock: a test that did
# would pass or fail depending on when it ran, and the rule is about a computed deadline.
T0 = 1_760_000_000_000

# Seeded items, by the fact that makes each one interesting rather than by id. `INF-003-en` answers
# §6.1 rank 3 ("I have a fever") and is therefore life-safety; `INF-008-en` answers no ranked
# question and is not.
SAFETY_SLUG = 'ebola-basics'
PLAIN_SLUG = 'health-tips'


def _item(slug: str):
	svc = InfoService()
	return next(c for c in svc.all_items() if c.slug == slug and c.lang == 'en')


def _made(**overrides: object):
	"""A hand-built item, for the cases the seed corpus cannot express.

	The corpus has life-safety items (ranks 3 and 4) and unranked ones, but no item answering a
	*ranked yet not life-safety* question — §6.1 ranks 9 and 10 are the case-surveillance and
	service-status questions. Without one, "the trigger is §6.1's life-safety set" and "the trigger
	is any ranked question at all" are the same claim over this data, and a gate that reads the
	wrong one passes.
	"""
	from afya.info.views import ContentItem
	body: dict[str, object] = {
		'item_id': 'x', 'title': 't', 'body': 'b', 'lang': 'en', 'harmony_tag': 'official',
		'slug': 's', 'owner': 'MoH Health Promotion Unit', 'reviewer': 'Clinical advisory group',
		'reviewed_on_iso': '2026-10-01', 'version': 1, 'stage': ContentStage.published,
		'answers_rank': 3, 'updated_at_ms': T0,
	}
	return ContentItem(**{**body, **overrides})  # type: ignore[arg-type]


def _error(**overrides: object) -> ContentError:
	body: dict[str, object] = {
		'error_id': 'E-1', 'item_id': 'INF-003-en', 'found_by': 'Nairobi PHEOC',
		'what_is_wrong': 'The salt-water line is wrong and dangerous.',
	}
	return ContentError(**{**body, **overrides})  # type: ignore[arg-type]


def _services() -> tuple[Any, dict[str, str], dict[str, Any]]:
	"""The app, an operator's token for it, and the services behind it, from one instance.

	`AuthService` holds issued tokens in memory, so a token minted against a separately built app
	reads as unauthenticated and every refusal below would be 401 for the wrong reason. The services
	are returned because a socket has to be subscribed on the *same* realtime bus the route fans out
	from, for the same reason.
	"""
	services = build_services()
	return (create_app(services),
	        {'authorization': f'Bearer {_token(RBACRole.sysadmin, "ops-0", services)}'},
	        services)


def _token(role: RBACRole, who: str, services: dict[str, Any] | None = None) -> str:
	"""A staff token from the *same* service instance the app was built with.

	`AuthService` holds issued tokens in memory, so a token minted on a fresh `build_services()` is
	unknown to a separately built app and every request reads as unauthenticated.
	"""
	auth = (services or build_services())['auth']
	return auth.provision_staff(who, role, registrar='MoH ops').access_token  # type: ignore[union-attr]


# --- the rule's own wording, and the two numbers it resolves to -----------------------------------

def test_the_clause_is_the_sections_own() -> None:
	"""Pinned to §6.5's sentence, so a spec revision that changes it fails here until the code moves.
	The bullet carries no full stop in the spec, and quoting it with one added is quoting a sentence
	the document does not contain."""
	spec = SPEC.read_text(encoding='utf-8')
	assert '- **Escalation:** Any content error affecting safety triggers immediate review and correction broadcast' in spec


def test_immediate_is_the_ladders_own_rung_not_a_figure_invented_here() -> None:
	"""§6.5 says "immediate" and prints no number; §24.8's row says "Immediate correction" and prints
	none either. The number that exists is §24.3's support ladder for the severity §24.8 assigns to
	this incident, so the deadline is read from there. If the ladder moves, this moves with it."""
	assert REVIEW_SLA_HOURS == SUPPORT_SLA_HOURS[IncidentSeverity.critical]
	assert REVIEW_SLA_HOURS == 0.25
	# The label is derived from the hours rather than carried beside them: §6.4's own SLA label and
	# `sla_hours` were two statements of one number and disagreed in a canary.
	assert REVIEW_SLA_LABEL == '15 minutes'


def test_the_incident_is_the_row_the_section_names() -> None:
	"""§24.8's own row for a content error: the kind, the severity and the two parties notified.
	Restating any of the three here would be a second definition of §24.8 that could drift."""
	assert IncidentClass.clinical_content_error.value == 'clinical_content_error'
	from afya.operations.service import INCIDENT_KINDS
	row = next(k for k in INCIDENT_KINDS if k.kind is IncidentClass.clinical_content_error)
	assert row.severity is IncidentSeverity.critical
	assert list(row.notifies) == ['clinical_advisory_group', 'affected_users']
	esc = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0), T0, [], False)
	assert esc.notifies == ['clinical_advisory_group', 'affected_users']
	assert esc.severity == 'critical'


# --- the trigger's jurisdiction is §6.1's, not the reporter's -------------------------------------

def test_affecting_safety_is_read_off_section_6_1() -> None:
	"""The whole trigger. A rank in §6.1's life-safety set escalates; a rank outside it does not, and
	the caller has no field with which to say otherwise.

	Ranks 9 and 10 are the discriminating case: they are *ranked* questions — "how many cases today"
	and "is the border open" — and §6.1 marks them `life_safety=False`. A trigger that asked "does
	this item answer a ranked question" instead of "is it life-safety" would escalate case counts to
	the clinical advisory group on every correction, and no seeded item would catch it.
	"""
	assert is_life_safety(_item(SAFETY_SLUG).answers_rank)
	assert not is_life_safety(_item(PLAIN_SLUG).answers_rank)
	assert not is_life_safety(9) and not is_life_safety(10)
	surveillance = escalate(_made(answers_rank=9), _error(found_at_ms=T0), T0, ['en'], False)
	assert not surveillance.affects_safety and not surveillance.broadcast_required, \
		'a ranked question outside the life-safety set is not the clause\'s trigger'
	safety = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0), T0, ['en', 'sw'], False)
	plain = escalate(_item(PLAIN_SLUG), _error(item_id='INF-008-en', found_at_ms=T0), T0, ['en'], False)
	assert safety.affects_safety and safety.broadcast_required
	assert not plain.affects_safety and not plain.broadcast_required
	assert 'not a life-safety item' in plain.summary


def test_a_reporter_cannot_declare_their_own_item_safe_or_unsafe() -> None:
	"""The failure the reading exists to prevent: whoever is retiring content under pressure is the
	last person to mark it life-safety. `ContentError` has no field for it — the model refuses the
	attempt rather than ignoring it, so a client that believes it is telling the server something
	finds out it is not."""
	with pytest.raises(Exception):
		_error(affects_safety=False)  # type: ignore[call-arg]


def test_a_life_safety_correction_must_carry_every_required_language() -> None:
	"""§6.2.4 forbids English-only for a life-safety message, and a correction is a message. The gap
	is *reported* rather than thrown at construction: a wrong item must be pullable the instant it is
	found wrong, even before the correction is drafted."""
	assert set(REQUIRED_LANGS) == {'en', 'sw'}
	half = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0, correction_en='Boil it.'), T0, [], False)
	assert half.missing_langs == ['sw'] and half.correction_langs == ['en']
	both = escalate(_item(SAFETY_SLUG),
	                _error(found_at_ms=T0, correction_en='Boil it.', correction_sw='Chemsha.'), T0, [], False)
	assert both.missing_langs == []
	# A non-safety item is not held to §6.2.4: a health tip in one language is a gap, not the act
	# the section forbids, so the language required is the item's own. The Swahili tip is the
	# discriminating case — under the correct rule nothing is missing, under §6.2.4's rule English
	# would be demanded of a tip the English audience was never meant to read.
	sw_tip = _made(item_id='INF-008-sw', lang='sw', slug='health-tips', answers_rank=None)
	plain = escalate(sw_tip, _error(item_id='INF-008-sw', found_at_ms=T0, correction_sw='Chemsha.'), T0, [], False)
	assert not plain.affects_safety
	assert plain.missing_langs == [], 'a Swahili-only tip is corrected in Swahili, not in both'
	assert plain.correction_langs == ['sw']


def test_the_correction_is_one_field_per_language_so_a_form_can_compose_it() -> None:
	"""The mobile catalogue's generic form has no object type, so a correction sent as a nested map
	is a correction no client can build. The two fields are the wire shape; `correction` is the
	language map the rules read, so the two spellings cannot drift."""
	esc = escalate(_item(SAFETY_SLUG),
	               _error(found_at_ms=T0, correction_en='Boil it.', correction_sw='Chemsha.'), T0, [], False)
	assert esc.correction_langs == ['en', 'sw'], 'ordered as §6.2.4 lists the languages'
	assert _error(correction_en='a').correction == {'en': 'a'}
	with pytest.raises(Exception):
		_error(correction={'en': 'a'})  # type: ignore[call-arg]


# --- the deadline ---------------------------------------------------------------------------------

def test_the_review_deadline_is_measured_from_the_finding_and_moves_with_the_clock() -> None:
	"""A deadline stored as a duration is a deadline that never expires. `review_overdue` is
	recomputed against the clock the escalation is asked at, so the same recorded error is on time
	and then late."""
	esc = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0), T0, [], False)
	assert esc.review_due_ms == T0 + int(REVIEW_SLA_HOURS * 3_600_000)
	assert not esc.review_overdue, 'overdue at the instant of finding it is a clock, not a review'
	late = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0), esc.review_due_ms + 1, [], False)
	assert late.review_overdue


def test_an_escalation_cannot_be_measured_from_nowhere() -> None:
	"""`found_at_ms` defaults to 0 because the *service* stamps it. An escalation computed off a
	zero stamp would put the deadline in 1970 and read as overdue forever, so the function refuses."""
	with pytest.raises(AssertionError):
		escalate(_item(SAFETY_SLUG), _error(), T0, [], False)
	with pytest.raises(AssertionError):
		escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0 + 1), T0, [], False)


# --- the two gaps reported rather than papered over ------------------------------------------------

def test_the_broadcast_is_reported_as_one_a_subscriber_can_switch_off() -> None:
	"""The correction lands in the `outbreak` category, which §9.6's own preference model makes
	toggleable. So the one message that must reach a person is one they may have turned off, and
	`preference_gap` says so instead of pretending the broadcast is guaranteed.

	The category is pinned by its literal *and* by the preference it must resolve to, because
	asserting `governing_preference(CORRECTION_FEED_CATEGORY) in TOGGLEABLE` alone is an assertion
	about the constant and the constant — a canary that changes `outbreak` to `service` still passes
	it, and the correction then reaches a subscriber who asked for facility alerts.
	"""
	from afya.alerting.views import TOGGLEABLE, governing_preference
	assert CORRECTION_FEED_CATEGORY == 'outbreak'
	assert governing_preference(CORRECTION_FEED_CATEGORY) == 'disease_alerts'
	assert 'disease_alerts' in TOGGLEABLE, 'the gap is real only while the preference is switchable'
	esc = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0), T0, [], False)
	assert esc.preference_gap


def test_withdrawn_guidance_with_no_replacement_says_so() -> None:
	"""Pulling a wrong item is the point, and a shelf with the guidance removed and nothing in its
	place is a reader with no answer. `superseded` asks whether the library holds a *published*
	item under the same slug stamped after the error was found — a fact about the shelf, not about
	a POST."""
	esc = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0), T0, ['en', 'sw'], False)
	assert esc.withheld_langs == ['en', 'sw'] and not esc.superseded
	assert 'withdrawn' in esc.summary
	replaced = escalate(_item(SAFETY_SLUG), _error(found_at_ms=T0), T0, ['en', 'sw'], True)
	assert replaced.superseded and 'withdrawn' not in replaced.summary


# --- the service: retirement is per-message --------------------------------------------------------

def test_reporting_an_error_withdraws_every_language_of_the_message() -> None:
	"""The failure invisible from the item the error was reported against: archiving only the item
	named leaves its translation being served to the audience §3.3 principle 8 puts first.

	Asserted on the **stored stage**, not on `library()`. §6.2.4 already withholds the English half
	of a life-safety message whose counterpart is gone, so a library-only assertion passes on a
	retirement that archived the English item and left the Swahili one published — the exact defect
	this test exists for. The stage is the fact; the shelf is a second rule that happens to hide it.
	"""
	svc = InfoService()
	assert {c.lang for c in svc.library('sw') if c.slug == SAFETY_SLUG} == {'sw'}, \
		'the fixture needs a published Swahili translation to withhold'
	esc = asyncio.run(svc.report_error(_error(item_id='INF-003-en'), T0))
	assert esc.withheld_langs == ['en', 'sw']
	stages = {c.lang: c.stage for c in svc.all_items() if c.slug == SAFETY_SLUG}
	assert stages == {'en': ContentStage.archived, 'sw': ContentStage.archived}, \
		f'the translation was left published: {stages}'
	assert not [c for c in svc.library('sw') if c.slug == SAFETY_SLUG], 'the translation is still served'
	assert not [c for c in svc.library('en') if c.slug == SAFETY_SLUG]
	assert svc.by_slug(SAFETY_SLUG) is not None, 'the retired message still has its title'


def test_a_slug_names_one_message_however_many_languages_it_has() -> None:
	"""`by_slug` is stage-agnostic on purpose: the correction goes out under the title of the message
	that was wrong, and that message has just been retired by the act of reporting it. A
	published-only lookup would find nothing at exactly the moment it is needed."""
	svc = InfoService()
	assert svc.by_slug(SAFETY_SLUG) is not None
	assert svc.by_slug('no-such-slug') is None


def test_an_error_against_an_unpublished_item_is_refused() -> None:
	"""§6.5's clause is about content that went out. Escalating a draft would page the clinical
	advisory group about a sentence nobody has read.

	A real item is advanced backwards into a draft first: naming an id that does not exist fails a
	different assertion, so a gate built on one would pass while the stage guard was absent.
	"""
	svc = InfoService()
	svc._content['INF-003-en'] = svc._content['INF-003-en'].model_copy(update={'stage': ContentStage.draft})
	with pytest.raises(AssertionError):
		asyncio.run(svc.report_error(_error(item_id='INF-003-en'), T0))
	with pytest.raises(AssertionError):
		asyncio.run(svc.report_error(_error(item_id='nope'), T0))


def test_one_error_is_recorded_once() -> None:
	"""The id is the key of the log and the handle the broadcast is named by (`COR-{error_id}`), so a
	second report under the same id would overwrite the first and re-broadcast under a name already
	in the feed."""
	svc = InfoService()
	asyncio.run(svc.report_error(_error(error_id='E-1', item_id='INF-003-en'), T0))
	with pytest.raises(AssertionError):
		asyncio.run(svc.report_error(_error(error_id='E-1', item_id='INF-008-en'), T0))
	assert len(svc.errors()) == 1


def test_the_service_asks_the_shelf_whether_the_guidance_was_replaced() -> None:
	"""`superseded` is the service's fact, not the caller's. A corrected item published under the
	same slug *after* the error was found flips it; one published before does not, because a
	correction that predates the error cannot be the correction for it."""
	svc = InfoService()
	asyncio.run(svc.report_error(_error(item_id='INF-003-en'), T0))
	assert not svc.escalation('E-1', T0).superseded, 'nothing has replaced it yet'
	svc._content['INF-003-en'] = svc._content['INF-003-en'].model_copy(
		update={'stage': ContentStage.published, 'updated_at_ms': T0 + 1})
	assert svc.escalation('E-1', T0).superseded, 'the corrected item is on the shelf'
	svc._content['INF-003-en'] = svc._content['INF-003-en'].model_copy(
		update={'stage': ContentStage.published, 'updated_at_ms': T0 - 1})
	assert not svc.escalation('E-1', T0).superseded, 'a replacement cannot predate the error'


def test_the_escalation_log_keeps_every_error_and_recomputes_its_state() -> None:
	svc = InfoService()
	asyncio.run(svc.report_error(_error(error_id='E-1', item_id='INF-003-en'), T0))
	asyncio.run(svc.report_error(_error(error_id='E-2', item_id='INF-008-en'), T0))
	assert [e.error_id for e in svc.errors()] == ['E-1', 'E-2']
	early = svc.escalation('E-1', T0)
	late = svc.escalation('E-1', early.review_due_ms + 1)
	assert not early.review_overdue and late.review_overdue, 'the same row, two clocks'


# --- the route ------------------------------------------------------------------------------------

async def test_reporting_a_life_safety_error_broadcasts_the_correction() -> None:
	"""The clause's second half. The correction reaches the alert feed §6.4's own corrections use —
	written durably first, so a client offline when it fired still finds it — and it is headlined by
	the title of the item that was wrong, not by a slug.

	A socket is subscribed before the report, because `delivered_realtime` counting zero would
	otherwise be indistinguishable from a fan-out that never ran.
	"""
	from afya.alerting.views import governing_preference
	from afya.realtime.views import SocketSubscription
	app, h, services = _services()
	services['realtime'].subscribe(SocketSubscription(categories=[governing_preference(CORRECTION_FEED_CATEGORY)]))
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = _error(item_id='INF-003-en', correction_en='Boil drinking water.',
		              correction_sw='Chemsha maji ya kunywa.').model_dump(mode='json')
		r = await c.post('/info/content/errors', json=body, headers=h)
		assert r.status_code == 200, r.text
		out = r.json()
		assert out['broadcast'] is True and out['delivered_realtime'] == 1
		assert out['affects_safety'] is True and out['review_due_label'] == '15 minutes'
		feed = (await c.get('/alerting/feed')).json()['items']
		correction = next(i for i in feed if i['item_id'] == f"COR-{out['error_id']}")
		assert correction['category'] == CORRECTION_FEED_CATEGORY
		assert correction['headline'] == _item(SAFETY_SLUG).title, 'the correction names its subject'
		assert correction['verified'] is True and correction['source'] == 'MoH Health Promotion Unit'


async def test_the_served_escalation_carries_no_spec_code() -> None:
	"""The escalation row is served twice — as the body of the language refusal and as the
	escalation log — and both are read by a person. A seed id embeds its spec code (`INF-003-en`),
	so the row names the item by slug; the internal log keeps the id, the served row does not.
	Carried by the payload rather than by a friendly string, which is why the vocabulary gate that
	scans the catalogue and the copy never saw it."""
	app, h, services = _services()
	auditor = {'authorization': f'Bearer {_token(RBACRole.auditor, "aud-0", services)}'}
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		refused = await c.post('/info/content/errors', headers=h, json=_error(
			item_id='INF-003-en', correction_en='Boil drinking water.').model_dump(mode='json'))
		assert refused.status_code == 422
		assert FEATURE_CODE.search(refused.text) is None, f'code in the refusal: {refused.text}'
		# And it is not merely absent because the payload is empty: the row is there, named by slug.
		assert refused.json()['detail']['escalation']['slug'] == SAFETY_SLUG
		rows = (await c.get('/info/content/errors', headers=auditor)).json()
		assert rows and rows[0]['slug'] == SAFETY_SLUG
		assert FEATURE_CODE.search(str(rows)) is None, f'code in the escalation log: {rows}'
	# The id is still recorded internally — the code is kept off the wire, not out of the system.
	assert services['info'].errors()[0].item_id == 'INF-003-en'


async def test_a_correction_missing_a_required_language_is_refused_before_anything_is_published() -> None:
	"""The order matters and is the assertion: a 422 that has already written the feed is not a
	refusal. §6.2.4's rule is checked before the broadcast, and the escalation is returned with the
	refusal so the operator can see what is missing rather than only that something is."""
	app, h, _ = _services()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = _error(item_id='INF-003-en', correction_en='Boil drinking water.').model_dump(mode='json')
		r = await c.post('/info/content/errors', json=body, headers=h)
		assert r.status_code == 422, r.text
		detail = r.json()['detail']
		assert detail['escalation']['missing_langs'] == ['sw']
		assert 'sw' in detail['content_language']
		assert FEATURE_CODE.search(r.text) is None, f'code in the refusal: {r.text}'
		feed = (await c.get('/alerting/feed')).json()['items']
		assert not [i for i in feed if i['item_id'].startswith('COR-')], 'refused but broadcast anyway'
		# And the item is still retired: refusing the broadcast must not un-retire the wrong text.
		assert not [i for i in (await c.get('/info/library')).json() if i['slug'] == SAFETY_SLUG]


async def test_a_non_safety_error_is_archived_quietly() -> None:
	"""§6.5 says "affecting safety", so a tip that is merely wrong escalates nothing. It is still
	retired — the shelf must not serve a wrong item — but no alert is broadcast and no clinical
	advisory group is paged."""
	app, h, _ = _services()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = _error(error_id='E-plain', item_id='INF-008-en', found_by='Kisumu CHW',
		              what_is_wrong='The salt figure is wrong.').model_dump(mode='json')
		out = (await c.post('/info/content/errors', json=body, headers=h)).json()
		assert out['broadcast'] is False and out['affects_safety'] is False
		assert 'feed_item_id' not in out
		feed = (await c.get('/alerting/feed')).json()['items']
		assert not [i for i in feed if i['item_id'].startswith('COR-')]
		assert not [i for i in (await c.get('/info/library')).json() if i['slug'] == PLAIN_SLUG]


async def test_the_escalation_log_is_auditor_scoped_and_reports_state_at_the_clock_asked() -> None:
	"""§17.4 splits the two scopes across different roles: `infrastructure` reports an error,
	`audit_logs` reads the log. The sysadmin who can retire the guidance is refused the record of
	having done it, which is the separation rather than an oversight."""
	app, h, services = _services()
	auditor = {'authorization': f'Bearer {_token(RBACRole.auditor, "aud-0", services)}'}
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = _error(item_id='INF-003-en', correction_en='a', correction_sw='b').model_dump(mode='json')
		await c.post('/info/content/errors', json=body, headers=h)
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		assert (await c.get('/info/content/errors',
		                    headers={'authorization': f'Bearer {anon}'})).status_code == 403
		assert (await c.get('/info/content/errors', headers=h)).status_code == 403, \
			'the writer of the log is not its reader'
		rows = (await c.get('/info/content/errors', headers=auditor)).json()
		assert [r['error_id'] for r in rows] == ['E-1']
		assert rows[0]['review_overdue'] is False
		late = (await c.get(f'/info/content/errors?now_ms={rows[0]["review_due_ms"] + 1}',
		                    headers=auditor)).json()
		assert late[0]['review_overdue'] is True, 'the row is recomputed against the clock asked'


async def test_a_citizen_cannot_retire_ministry_guidance() -> None:
	"""The write is an operator control, and the gate that proves it is the route's own guard. The
	operator token is minted but never used: the claim is that the same request succeeds for a
	holder of `infrastructure` and fails for everyone else, so both halves are asserted."""
	app, h, _ = _services()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = _error(item_id='INF-003-en', correction_en='Boil it.', correction_sw='Chemsha.').model_dump(mode='json')
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		r = await c.post('/info/content/errors', json=body, headers={'authorization': f'Bearer {anon}'})
		assert r.status_code == 403
		assert (await c.post('/info/content/errors', json=body)).status_code in (401, 403)
		# And the item is untouched: a refused report must not have retired anything.
		assert [i for i in (await c.get('/info/library')).json() if i['slug'] == SAFETY_SLUG]
		# The same body, by a caller holding the scope, does go through.
		assert (await c.post('/info/content/errors', json=body, headers=h)).status_code == 200
