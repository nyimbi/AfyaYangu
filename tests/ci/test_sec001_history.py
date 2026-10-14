"""§SEC-001's "consent audit log visible to the user", held open.

The section asked for a log a person can read, and the repo had the *state* and not the *history*.
`ConsentRecord.withdrawn` is a boolean, so a grant that was later revoked and a grant that never
happened were the same object with a different flag: "what did I agree to, and when" had no answer.
`ConsentToggle`'s own docstring claimed it carried "the audit entry that set it" and it carried no
such field — the claim was in the docstring and nowhere else.

So the tests come in four parts: the log is written where consent moves, it carries the words the
person was actually shown, it is the caller's own and nobody else's, and its `live` set agrees with
the toggles. The last one is the one worth reading: two surfaces answering "is this on" from two
predicates is how a person withdraws something and still sees the switch on.
"""
import re

import pytest
from fastapi.testclient import TestClient

from afya.privacy.service import CONSENT_CATALOGUE, PrivacyService
from afya.privacy.views import (
	ConsentCategory,
	ConsentEvent,
	ConsentRecord,
	LegalBasis,
)
from afya.strings import CONSENT_HISTORY_STRINGS, answerable, consent_history_note

FEATURE_CODE = re.compile(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b')


def _rewind(svc: PrivacyService, index: int) -> None:
	"""Push one event back by a second so the log's ordering is a fact and not a tie.

	Events written inside one millisecond share an `at_ms`, and `sorted(..., reverse=True)` on equal
	keys is stable — so a test written against three same-millisecond events holds whether the sort
	is reversed or not.
	"""
	svc._consent_events[index] = svc._consent_events[index].model_copy(
		update={'at_ms': svc._consent_events[index].at_ms - 1000})


def _grant(subject: str = 'U-1', purpose: str = 'symptom_storage',
           days: int = 365, **kw: object) -> ConsentRecord:
	return ConsentRecord(subject_ref=subject, purpose=purpose, data_types=[purpose],
	                     retention_days=days, legal_basis=LegalBasis.consent, **kw)  # type: ignore[arg-type]


async def _svc_with(*records: ConsentRecord) -> PrivacyService:
	svc = PrivacyService()
	for r in records:
		await svc.record_consent(r)
	return svc


# --- the log is written where consent moves ---------------------------------------------------

async def test_a_grant_is_logged() -> None:
	"""The event exists at all. Before this the ledger was a `dict` and the only trace of a grant was
	the record it produced, which a withdrawal then overwrote the meaning of."""
	svc = await _svc_with(_grant())
	history = svc.consent_history('U-1')
	assert len(history.events) == 1
	event = history.events[0]
	assert event.action == 'granted' and event.category == 'symptom_storage'
	assert event.subject_ref == 'U-1' and event.at_ms > 0
	assert event.retention_days == 365 and event.legal_basis is LegalBasis.consent


async def test_a_grant_and_its_withdrawal_are_two_events() -> None:
	"""The whole reason the log is a list and not a mapping. A dict keyed by consent id would keep
	whichever was written last, so the person would see a withdrawal with no grant behind it."""
	svc = PrivacyService()
	rec = await svc.record_consent(_grant())
	await svc.withdraw(rec.consent_id)
	actions = [e.action for e in svc.consent_history('U-1').events]
	assert actions == ['withdrawn', 'granted'], 'newest first, and both of them'


async def test_the_log_is_newest_first() -> None:
	"""A history read from the wrong end is a different history, and the entry a person is looking
	for is the one they just made.

	The timestamps are spaced by hand. Three events written inside one millisecond give the sort
	nothing to order by, so `reverse=True` and `reverse=False` produce the same list and the test
	would hold either way — which is exactly how the oldest-first canary first went MISSED.
	"""
	svc = PrivacyService()
	first = await svc.record_consent(_grant(purpose='symptom_storage'))
	_rewind(svc, 0)
	second = await svc.record_consent(_grant(purpose='location_tracking'))
	_rewind(svc, 1)
	await svc.withdraw(first.consent_id)
	categories = [e.category for e in svc.consent_history('U-1').events]
	assert categories == ['symptom_storage', 'location_tracking', 'symptom_storage'], (
		'the withdrawal, then the later grant, then the grant the withdrawal ended')
	assert [e.at_ms for e in svc.consent_history('U-1').events] == sorted(
		[e.at_ms for e in svc.consent_history('U-1').events], reverse=True)
	assert second.consent_id != first.consent_id


async def test_a_purge_is_logged_and_survives_the_record_it_was_about() -> None:
	"""`purge_expired` deletes the record. The event carries its own `subject_ref` for this reason: a
	log that resolved ownership from the record would lose its last line at the first clean-up, which
	is exactly when the person would go looking for it."""
	svc = PrivacyService()
	rec = await svc.record_consent(_grant())
	await svc.withdraw(rec.consent_id)
	assert await svc.purge_expired() == 1
	events = svc.consent_history('U-1').events
	assert [e.action for e in events] == ['purged', 'withdrawn', 'granted']
	assert svc.consent_history('U-1').live == []


async def test_another_subjects_purge_does_not_enter_this_log() -> None:
	"""A log is per person. One service instance holds everyone's records, so the filter is what
	makes the answer a history rather than a dump."""
	svc = PrivacyService()
	mine = await svc.record_consent(_grant(subject='U-1'))
	theirs = await svc.record_consent(_grant(subject='U-2'))
	await svc.withdraw(theirs.consent_id)
	await svc.purge_expired()
	assert [e.subject_ref for e in svc.consent_history('U-1').events] == ['U-1']
	assert len(svc.consent_history('U-2').events) == 3
	assert mine.subject_ref == 'U-1'


# --- the log carries the words the person was shown -------------------------------------------

async def test_the_event_carries_the_catalogue_words_not_a_reference() -> None:
	"""A person reading back a grant made six months ago is owed what they were told *then*. A log
	that looked its sentences up at read time would silently rewrite their history the first time the
	catalogue was reworded."""
	svc = await _svc_with(_grant(purpose='location_tracking'))
	event = svc.consent_history('U-1').events[0]
	scope = next(c for c in CONSENT_CATALOGUE if c.category is ConsentCategory.location_tracking)
	assert event.label == scope.label
	assert event.consequence == scope.on_withdrawal
	assert 'alerts will be less precise' in event.consequence, 'the cost, not a summary of it'


async def test_a_sensor_grant_is_logged_as_that_sensor() -> None:
	"""§SEC-001 asks for each sensor separately. A log line that said "Phone sensors" for both a gps
	grant and a microphone grant would tell the person nothing about which one they switched on."""
	svc = await _svc_with(_grant(purpose='sensor_monitoring:gps'))
	event = svc.consent_history('U-1').events[0]
	assert event.category == 'sensor_monitoring:gps' and event.label == 'sensor_monitoring:gps'
	assert event.consequence, 'the sensor still inherits the category consequence it was granted under'


async def test_every_catalogue_category_produces_a_usable_log_line() -> None:
	"""A category whose event had no label or no consequence would render as a blank row, and the
	only way to find that is to walk the catalogue rather than the one category a test picked."""
	svc = PrivacyService()
	for scope in CONSENT_CATALOGUE:
		await svc.record_consent(_grant(purpose=scope.category.value))
	for event in svc.consent_history('U-1').events:
		assert event.label and event.consequence, event.category
		assert not FEATURE_CODE.search(event.label + event.consequence)


async def test_a_purpose_that_is_not_a_category_is_logged_as_itself() -> None:
	"""Not every purpose is one of §SEC-001's eight — `health_companion` and `identity_linkage` are
	lawful purposes the app records consent for. Falling back to the purpose is honest; falling back
	to an empty label would be a row with nothing in it."""
	svc = await _svc_with(_grant(purpose='health_companion'))
	event = svc.consent_history('U-1').events[0]
	assert event.label == 'health_companion' and event.consequence == ''


async def test_a_grant_made_on_a_channel_is_logged_as_that_channel() -> None:
	"""The carrier door writes through the same `record_consent`, and the log has to say which session
	the line came from — a USSD grant is one the person may not remember making, and a line that
	guessed "app" would describe a session they have no memory of."""
	from afya.identity.service import IdentityService
	identity = IdentityService()
	svc = PrivacyService(None, identity)
	await svc.record_consent_for_phone('0712345678', ConsentCategory.symptom_storage, channel='ussd')
	subject = identity.resolve('0712345678')
	event = svc.consent_history(subject).events[0]
	assert event.channel == 'ussd' and event.action == 'granted'
	assert event.label == 'Keep my symptom history', 'the catalogue words travel through this door too'

	# The default is `unknown`, never `app`: a caller that does not say must not be recorded as one
	# that did.
	await svc.record_consent_for_phone('0712345678', ConsentCategory.research)
	assert svc.consent_history(subject).events[0].channel == 'unknown'


# --- the log and the toggles cannot disagree --------------------------------------------------

async def test_live_is_the_same_predicate_the_toggles_use() -> None:
	"""Two surfaces answering "is this on" from two predicates is how a person withdraws something
	and still sees the switch on. `live` is `has_category_consent`, read off the same records."""
	svc = PrivacyService()
	kept = await svc.record_consent(_grant(purpose='symptom_storage'))
	gone = await svc.record_consent(_grant(purpose='location_tracking'))
	await svc.withdraw(gone.consent_id)
	history = svc.consent_history('U-1')
	assert history.live == ['symptom_storage']
	for category in ConsentCategory:
		assert (category.value in history.live) == svc.has_category_consent('U-1', category), category
	assert svc.has_category_consent('U-1', ConsentCategory.symptom_storage)
	assert kept.consent_id


async def test_a_subject_with_nothing_is_told_so() -> None:
	"""`none` and `all_off` are different facts about the same blank screen, and only one of them is
	true for a person who has never made a choice."""
	svc = PrivacyService()
	empty = svc.consent_history('U-nobody')
	assert empty.events == [] and empty.live == []
	assert empty.note == CONSENT_HISTORY_STRINGS['en']['none']

	rec = await svc.record_consent(_grant(subject='U-nobody'))
	await svc.withdraw(rec.consent_id)
	withdrawn = svc.consent_history('U-nobody')
	assert withdrawn.events and withdrawn.live == []
	assert withdrawn.note == CONSENT_HISTORY_STRINGS['en']['all_off']
	assert withdrawn.note != empty.note

	# And a second person's live grant does not leak into either of them. The two canaries that
	# missed on the first run were both this: with one subject, `live` filtered by subject and
	# `live` unfiltered are the same list.
	await svc.record_consent(_grant(subject='U-someone-else', purpose='research'))
	assert svc.consent_history('U-nobody').live == []
	assert svc.consent_history('U-someone-else').live == ['research']


def test_the_note_is_served_in_the_language_asked_for() -> None:
	"""The note is prose a person reads on the screen where they check whether a withdrawal took."""
	assert consent_history_note(True, True, 'sw') == CONSENT_HISTORY_STRINGS['sw']['live']
	assert consent_history_note(False, False, 'sw') == CONSENT_HISTORY_STRINGS['sw']['none']
	assert consent_history_note(True, False, 'luo') == CONSENT_HISTORY_STRINGS['en']['all_off']
	assert answerable('luo') == 'en', 'the documented fallback'
	for lang, table in CONSENT_HISTORY_STRINGS.items():
		assert set(table) == {'none', 'live', 'all_off'}, lang
		assert all(text.strip() for text in table.values()), lang


async def test_the_history_carries_no_spec_feature_code() -> None:
	svc = await _svc_with(_grant(purpose='location_tracking'))
	blob = repr(svc.consent_history('U-1').model_dump(mode='json'))
	assert not FEATURE_CODE.search(blob), blob


def test_an_unknown_action_is_refused_by_the_model() -> None:
	"""`action` is a closed set because an open string would let a new code path write an event
	nobody wrote a sentence for."""
	with pytest.raises(Exception, match='action'):
		ConsentEvent(subject_ref='U-1', at_ms=1, action='revoked_by_admin',
		             category='research', label='x', consequence='y')


# --- the route --------------------------------------------------------------------------------

def _client() -> TestClient:
	from afya.service import build_services, create_app
	return TestClient(create_app(build_services()))


def _citizen(c: TestClient, subject: str) -> dict[str, str]:
	r = c.post('/auth/anonymous', json={'subject_ref': subject})
	assert r.status_code == 200, r.text
	return {'authorization': f'Bearer {r.json()["token"]}'}


def test_the_route_serves_the_callers_own_log() -> None:
	"""The front door, through the guards a client goes through. The route takes no subject, so the
	only way to read a log is to hold the token it belongs to."""
	c = _client()
	h = _citizen(c, 'probe-1')
	granted = c.post('/privacy/consent', headers=h, json={
		'subject_ref': 'probe-1', 'purpose': 'symptom_storage', 'data_types': ['symptom_storage'],
		'retention_days': 365, 'legal_basis': 'consent',
	})
	assert granted.status_code == 200, granted.text
	served = c.get('/privacy/consent/history', headers=h)
	assert served.status_code == 200, served.text
	body = served.json()
	assert body['subject_ref'] == 'probe-1'
	assert [e['action'] for e in body['events']] == ['granted']
	assert body['live'] == ['symptom_storage']
	assert body['note'] and not FEATURE_CODE.search(served.text), served.text


def test_the_route_refuses_a_caller_with_no_token() -> None:
	"""A log is personal data. The catalogue route beside it is public and this one is not, because
	the toggles describe the app and the log describes the person."""
	assert _client().get('/privacy/consent/history').status_code in (401, 403)


def test_the_route_takes_a_language() -> None:
	c = _client()
	h = _citizen(c, 'probe-1')
	c.post('/privacy/consent', headers=h, json={
		'subject_ref': 'probe-1', 'purpose': 'research', 'data_types': ['research'],
		'retention_days': 365, 'legal_basis': 'consent',
	})
	sw = c.get('/privacy/consent/history', headers=h, params={'lang': 'sw'})
	assert sw.status_code == 200, sw.text
	assert sw.json()['note'] == CONSENT_HISTORY_STRINGS['sw']['live']


def _grant_via_route(c: TestClient, h: dict[str, str], subject: str, purpose: str = 'symptom_storage') -> str:
	r = c.post('/privacy/consent', headers=h, json={
		'subject_ref': subject, 'purpose': purpose, 'data_types': [purpose],
		'retention_days': 365, 'legal_basis': 'consent',
	})
	assert r.status_code == 200, r.text
	return str(r.json()['consent_id'])


def test_the_route_withdraws_the_callers_own_consent() -> None:
	"""§SEC-001's one-tap revocation as a door. `withdraw` was audited as carried and reached by
	nothing: a person could grant at `POST /privacy/consent` and had no HTTP way to end it, so the
	log's own `withdrawn` line was a state no caller could produce."""
	c = _client()
	h = _citizen(c, 'probe-1')
	cid = _grant_via_route(c, h, 'probe-1')
	assert c.get('/privacy/consent/history', headers=h).json()['live'] == ['symptom_storage']

	gone = c.post(f'/privacy/consent/{cid}/withdraw', headers=h)
	assert gone.status_code == 200, gone.text
	assert gone.json() == {'consent_id': cid, 'withdrawn': True}

	body = c.get('/privacy/consent/history', headers=h).json()
	assert [e['action'] for e in body['events']] == ['withdrawn', 'granted']
	assert body['live'] == [], 'the log and the toggles must not disagree about whether it is on'


def test_the_route_refuses_a_consent_id_that_is_not_the_callers() -> None:
	"""A revocation that only needed a guessed id would let anyone switch off a grant they are not
	party to — a denial of care wearing §SEC-001's label. The stranger gets a 404 and the grant
	survives, because a 403 would confirm the id names something real.

	The two 404s must also be *indistinguishable*: if a real-but-not-mine id answered differently
	from an id that names nothing, the guard itself becomes an oracle a stranger can walk to learn
	whose grants exist. The first draft leaked exactly that — the ownership assertion's message went
	straight into the response."""
	c = _client()
	mine = _citizen(c, 'probe-1')
	cid = _grant_via_route(c, mine, 'probe-1')

	stranger = _citizen(c, 'probe-2')
	stolen = c.post(f'/privacy/consent/{cid}/withdraw', headers=stranger)
	assert stolen.status_code == 404, stolen.text
	assert c.get('/privacy/consent/history', headers=mine).json()['live'] == ['symptom_storage']

	absent = '01a00000-0000-7000-8000-000000000000'
	nowhere = c.post(f'/privacy/consent/{absent}/withdraw', headers=stranger)
	assert nowhere.status_code == 404
	# Same status, same shape, and the message is a pure function of the id the caller supplied —
	# so nothing in the answer distinguishes "someone else's" from "no such thing". Echoing back the
	# caller's own input tells them nothing they did not already send.
	assert nowhere.json() == {'detail': f'no consent {absent!r}'}
	assert stolen.json() == {'detail': f'no consent {cid!r}'}


def test_the_withdraw_route_refuses_a_caller_with_no_token() -> None:
	c = _client()
	h = _citizen(c, 'probe-1')
	cid = _grant_via_route(c, h, 'probe-1')
	assert c.post(f'/privacy/consent/{cid}/withdraw').status_code in (401, 403)


def test_an_unknown_consent_id_is_not_found() -> None:
	"""A route that answered 200 for an id it never held would tell a person their consent was taken
	back when nothing was touched — the one lie a revocation screen must not tell."""
	c = _client()
	h = _citizen(c, 'probe-1')
	assert c.post('/privacy/consent/01a00000-0000-7000-8000-000000000000/withdraw', headers=h).status_code == 404


def test_the_withdraw_action_is_in_the_catalogue_and_reaches_the_route() -> None:
	from afya.mobile.actions import catalogue
	act = next(a for a in catalogue() if a.id == 'withdraw_consent')
	assert act.method == 'POST' and act.path == '/privacy/consent/{consent_id}/withdraw'
	assert [f.name for f in act.fields] == ['consent_id'], act.fields
	assert FEATURE_CODE.search(act.model_dump_json()) is None, act.model_dump(mode='json')


def test_the_route_names_no_subject_and_so_the_catalogue_offers_no_field() -> None:
	"""The route binds the subject to the token (`names_subject=False`), so a catalogue action
	drawing a `subject_ref` form would be offering a control that names a stranger. Checked here as
	well as in `test_mobile_catalogue.py` because this is the route the claim is about."""
	from afya.mobile.actions import catalogue
	act = next(a for a in catalogue() if a.id == 'consent_history')
	assert not any(f.name == 'subject_ref' for f in act.fields), act.fields
	assert act.method == 'GET' and act.path == '/privacy/consent/history'


def test_the_audit_row_is_carried_and_its_ref_resolves() -> None:
	from afya.content_audit.service import FEATURE_CONTENT
	from afya.refs import resolves

	rows = [r for r in FEATURE_CONTENT if r[0] == 'SEC-001' and r[2].startswith('Consent audit log')]
	assert len(rows) == 1
	row = rows[0]
	assert row[3] == 'carried' and resolves(row[4]), row
