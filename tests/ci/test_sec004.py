"""§SEC-004's "Optional pseudonymous profile".

The row was `missing` for a reason that turned out to be half a defect. `IdentityService` had no
notion of a handle at all, and the audit note read as a gap in a settings screen: "no profile model
carries a chosen pseudonym or display name". What it actually was is the shape §COM-103, §LOC-004,
§SEC-001 and §ACC-004 all had — every visible part present and the join absent — except that here
the absent join was leaking.

`POST /facilities/{facility_id}/reports` took `reporter_ref` **out of the request body** and
`GET /facilities/{facility_id}/reports` served it back on a feed the route's own docstring calls a
public screen. So the app published a raw `subject_ref` — the string that keys `/records/{ref}`,
`/maternal/{ref}`, `/wallet`, the monitoring diaries and every other personal route — to anyone who
asked, and let the caller choose whose it was. The subject reference is stable across every post a
person ever makes; it is the opposite of a pseudonym in exactly the way §SEC-004's bullet is about.

The unit is the join: a handle derived from the subject, rotating per epoch so a feed cannot follow
one person across windows, chosen by the person when they want to name themselves, and published in
place of the reference. §SEC-004's own caveat travels with it — a handle hides a name and is not
anonymity, and a screen that implied otherwise would change what a person is willing to write.
"""
import re

from afya.facilities.service import FacilityService
from afya.facilities.views import Facility, FacilityKind
from afya.identity.service import PSEUDONYM_ROTATION_DAYS, IdentityService
from afya.strings import pseudonym_note

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')

_DAY_MS = 86_400_000
_SUBJECT = 'anon-01a00000-0000-7000-8000-000000000001'
# A fixed instant rather than a clock read, so a test that runs across a rotation boundary is not a
# test that fails once a month. 2026-10-14T00:00:00Z.
_NOW_MS = 1_760_400_000_000


def _svc() -> IdentityService:
	return IdentityService()


# --- the derivation -------------------------------------------------------------------------

async def test_the_handle_is_derived_from_the_subject_and_not_from_it() -> None:
	"""Two properties at once, and they are the whole design.

	*Stable within a window* — the same subject at two instants in one epoch gets one handle, so a
	feed does not relabel a person between two requests, and the derivation survives a restart
	because it is a digest and not a counter.

	*Not the subject* — and the assertion is about **fragments**, not the whole string. A first cut
	asserted only `handle != subject`, which a handle built from the subject's last four characters
	passes: the two are unequal and the reference is still on the screen, in pieces. What must not
	happen is any run of the subject appearing in the handle, so the check is every four-character
	run of the subject against the handle.
	"""
	svc = _svc()
	a = svc.pseudonym(_SUBJECT, _NOW_MS)
	b = svc.pseudonym(_SUBJECT, _NOW_MS + _DAY_MS)
	assert a.handle == b.handle, 'one window, one handle'
	assert a.handle != _SUBJECT
	fragments = {_SUBJECT[i:i + 4] for i in range(len(_SUBJECT) - 3)}
	leaked = sorted(f for f in fragments if f in a.handle)
	assert leaked == [], f'the handle carries the reference it replaces: {leaked}'
	assert a.chosen is False and a.rotates_every_days == PSEUDONYM_ROTATION_DAYS


async def test_the_handle_rotates_with_the_epoch() -> None:
	"""The field that makes it a pseudonym rather than a relabelled identifier.

	A handle that never changed would correlate every post a person ever made, on every public feed,
	forever — which is the property the feed was leaking in the first place. The epoch is in the
	digest, so the next window gives a different handle; the cost is that a reader cannot follow one
	person's reports across a rotation, and that is the point rather than a side effect.
	"""
	svc = _svc()
	now = svc.pseudonym(_SUBJECT, _NOW_MS)
	later = svc.pseudonym(_SUBJECT, _NOW_MS + (PSEUDONYM_ROTATION_DAYS + 1) * _DAY_MS)
	assert later.epoch == now.epoch + 1
	assert later.handle != now.handle, 'a handle that survives the window is not rotating'
	# And it comes back for the same epoch, so the derivation is a function and not a counter.
	assert svc.pseudonym(_SUBJECT, _NOW_MS).handle == now.handle


async def test_two_subjects_in_one_window_do_not_share_a_handle() -> None:
	"""Collision would be worse than a leak: two people's posts would read as one person's, which
	misattributes what somebody said about a clinic. The suffix is what separates them — the word is
	a readability aid drawn from twenty entries — so this asserts the pair is distinct across more
	subjects than there are words."""
	svc = _svc()
	handles = {svc.pseudonym(f'anon-{n:040d}', _NOW_MS).handle for n in range(200)}
	assert len(handles) == 200, 'the handle must separate subjects, not just label them'


async def test_the_handle_is_a_shape_a_screen_can_show() -> None:
	"""The model's pattern is the contract, so it is asserted against the model rather than trusted:
	a handle that could never be displayed is a handle that reaches a screen and breaks it."""
	svc = _svc()
	for n in range(50):
		h = svc.pseudonym(f'anon-{n:040d}', _NOW_MS).handle
		assert re.fullmatch(r'^[A-Za-z][A-Za-z0-9 _-]{1,23}$', h), h


# --- the choice -----------------------------------------------------------------------------

async def test_a_chosen_handle_is_used_and_does_not_rotate() -> None:
	"""The "optional" half of the bullet. A person who picked a name and found it changed after a
	month would have been given a setting that does not do what it says."""
	svc = _svc()
	chosen = svc.choose_handle(_SUBJECT, 'Mama Njeri', _NOW_MS)
	assert chosen.chosen is True and chosen.handle == 'Mama Njeri'
	assert svc.pseudonym(_SUBJECT, _NOW_MS).handle == 'Mama Njeri'
	assert svc.pseudonym(_SUBJECT, _NOW_MS + 400 * _DAY_MS).handle == 'Mama Njeri', 'a choice is not a window'
	# A different subject is unaffected — the choice is one person's, not a global setting.
	assert svc.pseudonym('anon-other', _NOW_MS).chosen is False


async def test_a_person_cannot_choose_their_own_identifier_as_a_handle() -> None:
	"""The refusal that matters. A person typing their phone number or subject reference into the
	box would be publishing the key §SEC-004 keeps off the screen, and the service would be the
	thing that let them do it to themselves."""
	svc = _svc()
	for bad in ('+254712345678', '0712345678', 'anon-01a00000-0000-7000-8000-000000000001'):
		raised = False
		try:
			svc.choose_handle(_SUBJECT, bad, _NOW_MS)
		except AssertionError:
			raised = True
		assert raised, f'{bad!r} is an identifier, not a pseudonym'
	# And the ordinary case still works, so the guard is not refusing every handle.
	assert svc.choose_handle(_SUBJECT, 'Tembo', _NOW_MS).handle == 'Tembo'


async def test_an_unchosen_subject_still_has_a_handle() -> None:
	"""`missing` read as "the screen is empty". It is not: a person who never opens the setting is
	named by the derived handle, so "optional" describes the choice and not the profile."""
	svc = _svc()
	policy = svc.pseudonym(_SUBJECT, _NOW_MS)
	assert policy.handle and policy.chosen is False


# --- the join the feed was missing ----------------------------------------------------------

async def test_the_report_feed_publishes_a_handle_not_the_subject_reference() -> None:
	"""The defect, in one assertion. Before this, the feed served back the exact string that was
	posted — and that string keys every personal route in the app."""
	identity = _svc()
	facilities = FacilityService(identity)
	await facilities.upsert(Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed,
	                                 county='Nairobi', lat=-1.3, lon=36.8))
	posted = await facilities.report('F1', 'long queue', _SUBJECT, now_ms=_NOW_MS)
	assert posted.reporter_ref != _SUBJECT, 'the feed must not carry the subject reference'
	assert posted.reporter_ref == identity.pseudonym(_SUBJECT, _NOW_MS).handle
	feed = facilities.recent_reports('F1')
	assert feed[0].reporter_ref == posted.reporter_ref
	assert _SUBJECT not in feed[0].model_dump_json()


async def test_a_caller_cannot_attribute_a_report_to_someone_else() -> None:
	"""The body field is gone, and that is the fix rather than a tidy-up. While `reporter_ref` was a
	request field, a caller could file a report *as* another subject — the feed would show their
	handle next to words they never wrote. The handle is derived from the subject the token carries,
	so there is no field left to lie in."""
	from afya.facilities.views import FacilityReportRequest
	assert 'reporter_ref' not in FacilityReportRequest.model_fields, \
		'a body field for the reporter is a field a caller can lie in'


async def test_a_report_with_no_reporter_is_published_anonymously() -> None:
	"""§FND-001's ordinary case: a person with no token still gets to report the queue. The report
	is anonymous rather than refused, which is why the field stays optional."""
	identity = _svc()
	facilities = FacilityService(identity)
	await facilities.upsert(Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed,
	                                 county='Nairobi', lat=-1.3, lon=36.8))
	posted = await facilities.report('F1', 'no malaria tests today', None, now_ms=_NOW_MS)
	assert posted.reporter_ref is None
	assert facilities.recent_reports('F1')[0].text == 'no malaria tests today'


async def test_the_feed_still_works_with_no_identity_model_wired() -> None:
	"""The pseudonymiser is a protocol and optional, so the finder does not depend on the identity
	model for one call. A build without it publishes anonymously rather than raising — a facility
	finder that cannot accept a queue report because a service is missing is worse than an anonymous
	one."""
	facilities = FacilityService()
	await facilities.upsert(Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed,
	                                 county='Nairobi', lat=-1.3, lon=36.8))
	posted = await facilities.report('F1', 'long queue', _SUBJECT, now_ms=_NOW_MS)
	assert posted.reporter_ref is None, 'no identity model means no handle, not a raw reference'


# --- what the person is told ------------------------------------------------------------------

async def test_the_note_says_which_kind_of_handle_this_is() -> None:
	"""A derived handle and a chosen one are different promises and the screen must not read the
	same for both. The derived note carries the window; the chosen note says it stays."""
	derived = pseudonym_note(False, PSEUDONYM_ROTATION_DAYS, 'en')
	chosen = pseudonym_note(True, PSEUDONYM_ROTATION_DAYS, 'en')
	assert str(PSEUDONYM_ROTATION_DAYS) in derived and 'changes every' in derived
	assert derived != chosen and 'chose' in chosen
	assert pseudonym_note(False, PSEUDONYM_ROTATION_DAYS, 'sw') != derived, 'the note is served in the language asked for'


async def test_the_caveat_is_served_rather_than_paraphrased() -> None:
	"""§SEC-004's caveat is load-bearing and must travel with the handle. A handle hides a name; it
	is not anonymity, because a small enough group re-identifies regardless of the identifier used —
	the same admission the section's "minimum cell size of 10" makes one level up. A screen that
	implied otherwise would change what a person is willing to write.

	Asserted through `pseudonym_caveat` and not only against the table, because the table existing
	and nothing reading it is exactly how this module shipped its first cut: the sentence was there
	and the route served no such field.
	"""
	from afya.strings import PSEUDONYM_STRINGS, pseudonym_caveat
	for lang in ('en', 'sw'):
		caveat = PSEUDONYM_STRINGS[lang]['caveat']
		assert caveat and len(caveat) > 60, lang
		assert 'work out who you are' in caveat or 'kukutambua' in caveat, lang
		assert pseudonym_caveat(lang) == caveat
	assert pseudonym_caveat('luo') == PSEUDONYM_STRINGS['en']['caveat'], 'no table, English, and told so'


async def test_the_policy_carries_no_spec_feature_code() -> None:
	payload = _svc().pseudonym(_SUBJECT, _NOW_MS).model_dump_json()
	assert FEATURE_CODE.search(payload) is None, payload


# --- the front door ---------------------------------------------------------------------------

def _client():  # type: ignore[no-untyped-def]
	from fastapi.testclient import TestClient
	from afya.service import build_services, create_app
	services = build_services()
	return TestClient(create_app(services)), services


def _citizen(c, subject: str) -> dict[str, str]:  # type: ignore[no-untyped-def]
	r = c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'authorization': f'Bearer {r.json()["token"]}'}


def test_the_route_serves_the_callers_own_handle() -> None:
	c, _ = _client()
	h = _citizen(c, 'probe-pseudo')
	body = c.get('/identity/pseudonym', headers=h).json()
	assert body['subject_ref'] == 'probe-pseudo'
	assert body['chosen'] is False and body['handle']
	assert body['rotates_every_days'] == PSEUDONYM_ROTATION_DAYS
	assert body['note'] and str(PSEUDONYM_ROTATION_DAYS) in body['note']
	# The caveat is served, not merely tabulated. A route that answered with the handle and no
	# caveat is the first cut of this unit: the sentence existed and nothing read it.
	from afya.strings import PSEUDONYM_STRINGS
	assert body['caveat'] == PSEUDONYM_STRINGS['en']['caveat']
	assert FEATURE_CODE.search(c.get('/identity/pseudonym', headers=h).text) is None


def test_the_route_has_no_parameter_a_caller_can_name_a_stranger_with() -> None:
	"""The handle is what makes a person's posts unlinkable to their records. A route that answered
	"what is this subject called" for any caller would undo that in one request — so the route names
	no subject at all (`names_subject=False`) and reads the caller's own from the token, the same
	shape §SEC-001's consent log uses.

	The check is against **every** name a subject travels under, not just `subject_ref`. A first cut
	asserted `'subject_ref' not in params`, which a route that took `subject` — or `member_ref`, or
	`ref` — passes while being the same IDOR. That is the exact bug `test_self_scope.py`'s docstring
	records finding in its own first version, and it is cheaper to avoid here than to rediscover.
	"""
	import inspect
	from afya.service import build_services, create_app
	# The names a subject travels under, spelled out rather than imported: `tests.ci` is not an
	# importable package here, and a gate that cannot run its own comparison is not a gate.
	subject_names = {'subject_ref', 'member_ref', 'guardian_ref', 'family_ref', 'chw_ref', 'ref',
	                 'subject', 'subject_id'}
	app = create_app(build_services())
	found: list[object] = []

	def walk(routes: object) -> None:
		for r in routes:  # type: ignore[attr-defined]
			if hasattr(r, 'routes'):
				walk(r.routes)
				continue
			if getattr(r, 'path', '') == '/identity/pseudonym':
				found.append(r)

	walk(app.routes)
	assert found, 'the route must exist'
	for r in found:
		params = set(inspect.signature(r.endpoint).parameters)  # type: ignore[attr-defined]
		offenders = sorted(params & subject_names)
		assert offenders == [], f'{r.methods} takes a subject it must not take: {offenders}'  # type: ignore[attr-defined]


def test_the_route_refuses_a_caller_with_no_token() -> None:
	c, _ = _client()
	assert c.get('/identity/pseudonym').status_code in (401, 403, 422)


def test_a_chosen_handle_round_trips_through_the_route() -> None:
	c, _ = _client()
	h = _citizen(c, 'probe-pseudo')
	chosen = c.post('/identity/pseudonym', headers=h, json={'handle': 'Mama Njeri'})
	assert chosen.status_code == 200, chosen.text
	assert chosen.json()['handle'] == 'Mama Njeri' and chosen.json()['chosen'] is True
	read = c.get('/identity/pseudonym', headers=h).json()
	assert read['handle'] == 'Mama Njeri' and read['chosen'] is True


def test_the_model_refuses_a_handle_shaped_like_a_number() -> None:
	"""The *first* line of defence, and it is the model's rather than the service's.

	Two layers refuse an identifier used as a handle and they catch different things. The pattern
	refuses anything that does not start with a letter — which is every phone number, in every
	spelling a carrier sends. The service then refuses a `anon-` subject reference, which *does*
	start with a letter and so passes the pattern. A route-level test cannot see the first layer,
	because the service catches the same input one frame later and the status code is 422 either
	way; that is exactly why the pattern is asserted here against the model.
	"""
	import pytest
	from pydantic import ValidationError
	from afya.identity.views import PseudonymChoice
	for bad in ('+254712345678', '0712345678', '254712345678', '01a00000-0000-7000-8000'):
		with pytest.raises(ValidationError):
			PseudonymChoice(handle=bad)
	assert PseudonymChoice(handle='Mama Njeri').handle == 'Mama Njeri'


def test_the_route_refuses_a_handle_that_is_an_identifier() -> None:
	"""The second layer, through the door. The `anon-` case is the one only the service catches:
	it starts with a letter, so the pattern admits it and the service's own refusal is what stops a
	person publishing the reference that keys their records."""
	c, _ = _client()
	h = _citizen(c, 'probe-pseudo')
	for bad in ('+254712345678', 'anon-01a00000-0000-7000-8000-000000000001'):
		r = c.post('/identity/pseudonym', headers=h, json={'handle': bad})
		assert r.status_code == 422, (bad, r.text)


def test_the_report_route_serves_a_handle_and_not_the_token_subject() -> None:
	"""The end-to-end shape of the fix. The route reads the reporter from the token, so what lands
	on the public feed is the handle — and the subject never appears in the response."""
	from afya.facilities.views import Facility, FacilityKind
	c, services = _client()
	svc: FacilityService = services['facilities']  # type: ignore[assignment]
	svc._facilities['F1'] = Facility(facility_id='F1', name='KNH', kind=FacilityKind.ed,
	                                 county='Nairobi', lat=-1.3, lon=36.8)
	h = _citizen(c, 'probe-reporter')
	posted = c.post('/facilities/F1/reports', headers=h, json={'text': 'long queue'})
	assert posted.status_code == 200, posted.text
	assert posted.json()['reporter_ref'] != 'probe-reporter'
	assert 'probe-reporter' not in posted.text
	feed = c.get('/facilities/F1/reports').json()
	assert feed[0]['text'] == 'long queue'
	assert 'probe-reporter' not in str(feed), 'the public feed must not carry the subject reference'
	# And the reporter really is the handle that subject would be shown under, not a different one.
	handle = c.get('/identity/pseudonym', headers=h).json()['handle']
	assert feed[0]['reporter_ref'] == handle


def test_the_catalogue_offers_the_profile_and_reaches_the_routes() -> None:
	"""A handle no client can read or set is the `missing` row again, wearing the same coat."""
	from afya.mobile.actions import catalogue
	by_id = {a.id: a for a in catalogue()}
	assert by_id['my_pseudonym'].path == '/identity/pseudonym' and by_id['my_pseudonym'].method == 'GET'
	assert by_id['choose_pseudonym'].path == '/identity/pseudonym' and by_id['choose_pseudonym'].method == 'POST'
	assert 'handle' in {f.name for f in by_id['choose_pseudonym'].fields}
	for slug in ('my_pseudonym', 'choose_pseudonym'):
		assert FEATURE_CODE.search(by_id[slug].model_dump_json()) is None, slug


def test_the_audit_row_is_carried_and_its_ref_resolves() -> None:
	from afya.content_audit.service import FEATURE_CONTENT
	from afya.refs import resolves

	rows = [r for r in FEATURE_CONTENT if r[0] == 'SEC-004' and r[2] == 'Optional pseudonymous profile']
	assert len(rows) == 1
	assert rows[0][3] == 'carried' and resolves(rows[0][4]), rows[0]


def test_the_feature_is_reachable_so_it_is_no_longer_called_on_device() -> None:
	"""`test_feature_coverage.py` listed §SEC-004 as having no call to make. It has two now, and an
	entry naming a covered feature is stale — that gate asserts the staleness itself, so this
	asserts the reason it came off."""
	from afya.mobile.actions import FEATURE_OF
	from afya.registry.service import FeatureRegistry
	assert FEATURE_OF['my_pseudonym'] == 'SEC-004'
	covered = set(FEATURE_OF.values())
	assert 'SEC-004' in covered
	assert 'SEC-004' in {f.id for f in FeatureRegistry().available()}, 'and it is still an available feature'
