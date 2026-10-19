"""§COM-102 — the peer alert that had a body a caller wrote and a follow-up list nothing read.

The section prints five Features and one Verification clause. Two were implemented — the geofenced
zones and the tone gate — and the four below had no carrier, each in its own way:

- **"Alert content: 'A suspected case has been reported in your area. Avoid [specific location].
  Monitor for symptoms for 21 days. Call 719 if you feel unwell.'"** — `PeerAlert` carried a
  caller-supplied `headline` and `body` and nothing drafted the section's sentence. A free-text body
  is a body that can be alarmist, that can name a person, and that cannot be reviewed before it
  reaches a whole village. `ALERT_TEMPLATE` is now the sentence, `body` is a computed field, and the
  only slot is the location.
- **"No personally identifiable information about the case"** — nothing rejected one. There was no
  field to put one in, which is not the same as a rule: `body` was free text and could carry a name.
  The template has nowhere to put one, and `location` refuses the shapes that *are* a person.
- **"Users acknowledge alerts and receive follow-up guidance"** — `PeerAlertReceipt` reported
  recipients and tone and there was no acknowledgement model, no route and nothing returned after
  one. `PeerAlertAck` and `PeerAlertGuidance` are both, and the receipt now counts them.
- **"Follow-up prompts on days 3, 7, 14, and 21"** — `PeerAlert.followup_days` defaulted to exactly
  those four and no code path read it. `followup_prompt` reads it, on a day passed in rather than
  read from a clock.

Each gate below is canaried against a planted defect in `canary_com102.py`.
"""
import httpx
import pytest
from pydantic import ValidationError

from afya.community.service import CommunityService
from afya.community.views import (
	ALERT_TEMPLATE, ALERT_WINDOW_DAYS, FOLLOWUP_DAYS, PeerAlert, PeerAlertAck,
)
from afya.location.views import ALERT_ZONE_RADII_M


def _alert(alert_id: str = 'PA-1', **kw: object) -> PeerAlert:
	base: dict[str, object] = {
		'alert_id': alert_id, 'county': 'Busia', 'lat': -0.5, 'lon': 34.0, 'radius_m': 1000,
		'headline': 'Suspected case reported nearby',
		'location': 'Budalangi market',
		'issued_iso': '2026-10-10',
		'verified_by': 'County',
	}
	base.update(kw)
	return PeerAlert.model_validate(base)


# --- the alert content --------------------------------------------------------------------------

def test_the_body_is_the_sections_sentence_and_the_location_is_the_only_slot() -> None:
	"""§COM-102 prints the sentence. A caller cannot write a different one.

	The section says the wording was "tested with community representatives before deployment", and
	a body a CHW types at 3am is not that wording. `body` is computed, so it is not a field a request
	can carry at all — `DerivedFields` drops it on the way in, which is why the model mixes it in.
	"""
	alert = _alert()
	assert alert.body == ALERT_TEMPLATE.format(location='Budalangi market')
	assert 'A suspected case has been reported in your area' in alert.body
	assert 'Budalangi market' in alert.body
	assert '21 days' in alert.body, 'the window is in the section sentence'
	assert '719' in alert.body
	# And a caller cannot substitute one: the key is dropped, not honoured.
	assert PeerAlert.model_validate({**_alert().model_dump(), 'body': 'Everyone will die'}).body == \
		ALERT_TEMPLATE.format(location='Budalangi market')
	with pytest.raises(ValidationError):
		PeerAlert.model_validate({**_alert().model_dump(), 'location': ''})


def test_the_alert_body_has_nowhere_to_put_a_case_identifier() -> None:
	"""§COM-102's "No personally identifiable information about the case", enforced by construction.

	The section's own rule, and the defect was that it was unenforced rather than absent: `body` was
	free text, so a CHW could write "the case in House 14" and the only thing standing between that
	and a village was the tone judge, which reads words and not reference. The template has one slot
	and it is a place.
	"""
	for leak in ('House 14, near the market', 'the patient from Budalangi', 'plot 22, next to the market',
	             'the victim was found at the market', 'Room 3, Budalangi'):
		with pytest.raises(ValidationError, match='not a place'):
			_alert(location=leak)
	# "the case" is deliberately *not* refused: it names nobody, it is the section's own anonymised
	# phrasing, and a rule that banned it would refuse "The Case Hotel, Nairobi" — the shape of rule
	# people route around rather than use.
	assert _alert(location='the case hotel, Nairobi').body
	assert _alert(location='Budalangi market').body


def test_a_radius_outside_the_sections_zones_is_refused() -> None:
	"""§COM-102 offers three zones, and the set is the set — not a 500–5000 range.

	`radius_m` was bounded `ge=500, le=5000`, which admits 3000: a radius the section does not offer
	and a county cannot configure, since the zones are a choice from three and not a slider. The
	three are §LOC-001's `ALERT_ZONE_RADII_M`, which is where the number lives — one tuple, so the
	alert model and the location service cannot disagree about which zones exist.
	"""
	assert ALERT_ZONE_RADII_M == (500, 1000, 5000)
	for r in ALERT_ZONE_RADII_M:
		assert _alert(radius_m=r).radius_m == r
	with pytest.raises(ValidationError, match='not a §COM-102 alert zone'):
		_alert(radius_m=3000)


def test_the_followup_days_are_the_sections_four_and_not_a_callers_choice() -> None:
	"""The section names four days. A caller cannot add a fifth.

	`followup_days` was a settable list defaulting to the right four, so a caller could send
	`[1, 2, 3, 4, ..., 21]` and every recipient would get a prompt a day — which is the daily nag the
	section avoids precisely by naming four.
	"""
	assert FOLLOWUP_DAYS == (3, 7, 14, 21)
	assert _alert().followup_days == [3, 7, 14, 21]
	with pytest.raises(ValidationError, match='follow-up prompts on days'):
		_alert(followup_days=[1, 2, 3])


# --- the follow-up prompts ----------------------------------------------------------------------

async def test_a_prompt_goes_on_the_four_days_and_on_no_other() -> None:
	"""§COM-102's fourth bullet, from the scheduler's side.

	The scheduler asks for every day of the window and sends what comes back, so a day the section
	does not name returns `None` rather than an error. A prompt on day 22 is a prompt about a window
	that has closed, and the section's window is the WHO fact sheet's 21 days.
	"""
	svc = CommunityService()
	await svc.send_peer_alert(_alert())
	prompts = {day: svc.followup_prompt('PA-1', day) for day in range(1, ALERT_WINDOW_DAYS + 1)}
	fired = sorted(d for d, p in prompts.items() if p is not None)
	assert fired == [3, 7, 14, 21], fired
	last = prompts[21]
	assert last is not None and 'Day 21 of 21' in last
	# The prompt is a question about the person, not a restatement of the alert.
	third = prompts[3]
	assert third is not None and '719' in third and 'fever' in third.lower()
	assert svc.followup_prompt('PA-1', 22) is None
	with pytest.raises(AssertionError, match='unknown alert'):
		svc.followup_prompt('PA-NOPE', 3)


# --- acknowledgement and the guidance it returns -------------------------------------------------

async def test_an_acknowledgement_returns_guidance_and_names_the_next_prompt() -> None:
	"""§COM-102's third bullet is two things and both have to be there.

	"Users acknowledge alerts and receive follow-up guidance" — an acknowledgement that returned
	nothing would leave the person with the alert and no next step, and the guidance is the four
	actions that resolve a concern inside an alert zone.
	"""
	svc = CommunityService()
	await svc.send_peer_alert(_alert())
	guidance = await svc.acknowledge_peer_alert(PeerAlertAck(
		alert_id='PA-1', subject_ref='s1', acknowledged_iso='2026-10-13T08:00:00Z'))
	assert guidance.day == 4, 'issued 2026-10-10, read 2026-10-13 — day 4 of the window'
	assert guidance.next_followup_day == 7, 'the next prompt after day 4 is day 7'
	assert len(guidance.guidance) >= 4
	assert any('719' in g for g in guidance.guidance), 'the guidance has to name the action'
	assert 'day 4 of 21' in guidance.message
	# Worried is a state the person can report, and it earns one more line — the action that
	# resolves it rather than reassurance.
	worried = await svc.acknowledge_peer_alert(PeerAlertAck(
		alert_id='PA-1', subject_ref='s2', acknowledged_iso='2026-10-13', concerned=True))
	assert len(worried.guidance) == len(guidance.guidance) + 1
	assert 'worried' in worried.guidance[-1].lower()


async def test_the_day_is_derived_from_the_alert_not_from_the_client() -> None:
	"""A client's clock decides which prompt a person reads, so the server does not ask it.

	The window opens when the alert was issued, not when the person happened to open the app. A
	phone with a wrong clock would read the day-21 prompt on day 1, and a person who reads the alert
	late is told they are late rather than told they are on day 1.
	"""
	svc = CommunityService()
	await svc.send_peer_alert(_alert(issued_iso='2026-10-10'))
	first = await svc.acknowledge_peer_alert(PeerAlertAck(
		alert_id='PA-1', subject_ref='s1', acknowledged_iso='2026-10-10T09:00:00Z'))
	assert first.day == 1 and first.next_followup_day == 3
	late = await svc.acknowledge_peer_alert(PeerAlertAck(
		alert_id='PA-1', subject_ref='s2', acknowledged_iso='2026-10-31T09:00:00Z'))
	assert late.day == ALERT_WINDOW_DAYS, 'past the window is clamped to the last day, not refused'
	assert late.next_followup_day is None, 'there is no prompt after day 21'


async def test_one_person_acknowledging_twice_is_one_acknowledgement() -> None:
	"""The receipt reports how many people answered, so a double tap is not two people.

	§COM-102's receipt is what a CHW reads to decide whether anyone heard the alert. A count that
	moved on a repeated tap would be a count of taps, and the number would stop meaning "people who
	read this".
	"""
	svc = CommunityService()
	await svc.send_peer_alert(_alert())
	for _ in range(3):
		await svc.acknowledge_peer_alert(PeerAlertAck(
			alert_id='PA-1', subject_ref='s1', acknowledged_iso='2026-10-13'))
	assert svc.acknowledged_count('PA-1') == 1
	await svc.acknowledge_peer_alert(PeerAlertAck(
		alert_id='PA-1', subject_ref='s2', acknowledged_iso='2026-10-13'))
	assert svc.acknowledged_count('PA-1') == 2
	with pytest.raises(AssertionError, match='unknown alert'):
		svc.acknowledged_count('PA-NOPE')


async def test_the_receipt_carries_the_body_it_sent_and_the_days_it_will_prompt() -> None:
	"""The sender's receipt is the review surface: what went out, and when it will come back."""
	svc = CommunityService()
	receipt = await svc.send_peer_alert(_alert())
	assert receipt.body == _alert().body, 'the receipt shows the sentence that was dispatched'
	assert receipt.followup_days == [3, 7, 14, 21]
	assert receipt.acknowledged == 0


# --- end to end through the real app ------------------------------------------------------------

async def _token(c: httpx.AsyncClient, subject: str = 's1') -> dict[str, str]:
	tok = (await c.post('/auth/anonymous', json={'subject_ref': subject})).json()['token']
	return {'authorization': f'Bearer {tok}'}


def _worker_token(auth: object, ref: str) -> dict[str, str]:
	"""A CHW token through the app's own PKCE flow — `provision_staff` refuses a role the app issues."""
	import secrets

	from afya.auth.views import PKCETokenRequest, PKCEStart, s256
	from afya.privacy.views import RBACRole
	verifier = secrets.token_urlsafe(64)[:64]
	code = auth.start_pkce(PKCEStart(  # type: ignore[attr-defined]
		client_id='chw-app', redirect_uri='afya://cb', code_challenge=s256(verifier),
		state=ref + '-state', role='chw')).authorization_code
	token = auth.exchange_pkce(  # type: ignore[attr-defined]
		PKCETokenRequest(authorization_code=code, client_id='chw-app', redirect_uri='afya://cb',
		                 code_verifier=verifier), RBACRole.chw)
	return {'authorization': f'Bearer {token.access_token}'}


async def test_the_route_refuses_a_body_and_the_acknowledgement_binds_the_token() -> None:
	"""The wiring, both halves. A caller cannot write the sentence, and cannot acknowledge as someone else.

	The second half is §17's rule and it matters more here than usual: the acknowledgement is what
	§COM-102's receipt counts, so a caller who could name another person could inflate the number a
	CHW reads as "how many people heard this".
	"""
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		chw = _worker_token(services['auth'], 'chw-1')
		body = _alert().model_dump()
		# A body the caller wrote is dropped rather than honoured — `DerivedFields` removes a computed
		# key on the way in, which is the supported way for a request to carry back what it was served.
		# The sentence that goes out is the section's, whatever the caller sent in that slot.
		overridden = await c.post('/community/peer-alert', headers=chw,
		                          json={**body, 'body': 'Everyone will die unless you act now'})
		assert overridden.status_code == 200, overridden.text
		assert overridden.json()['body'] == ALERT_TEMPLATE.format(location='Budalangi market')
		assert 'die' not in overridden.json()['body']
		sent = await c.post('/community/peer-alert', headers=chw, json=body)
		assert sent.status_code == 200, sent.text
		assert sent.json()['body'] == ALERT_TEMPLATE.format(location='Budalangi market')

		citizen = await _token(c, 's1')
		# A caller who names someone else is *refused*, not silently rewritten: `require_self()` is
		# the gate, and a silent rewrite would let a caller discover the binding only by reading the
		# response. The refusal is the stronger behaviour and it is what the route relies on.
		ack = {'alert_id': 'PA-1', 'subject_ref': 'someone_else', 'acknowledged_iso': '2026-10-13'}
		refused = await c.post('/community/peer-alert/ack', headers=citizen, json=ack)
		assert refused.status_code == 403, refused.text
		assert 'its own subject' in refused.json()['detail']
		told = await c.post('/community/peer-alert/ack', headers=citizen,
		                    json={**ack, 'subject_ref': 's1'})
		assert told.status_code == 200, told.text
		assert told.json()['subject_ref'] == 's1', 'the token names the person, not the body'
		assert told.json()['day'] == 4
		assert (await c.get('/community/peer-alert/PA-1/followup/3')).json()['prompt']
		assert (await c.get('/community/peer-alert/PA-1/followup/4')).json()['prompt'] is None
		assert (await c.get('/community/peer-alert/PA-NOPE/followup/3')).status_code == 404
		# The receipt a CHW reads counts the acknowledgement the citizen just made.
		again = await c.post('/community/peer-alert', headers=chw, json=body)
		assert again.status_code == 200, again.text
		assert again.json()['acknowledged'] == 1, 'the receipt counts who answered, not who was sent to'
