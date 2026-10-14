"""Gate: §CHAN-5's intermediary programme — seven kinds, five tools, and the verification gate.

§CHAN-5 is the section §20.2 lever 4 rests on — "CHWs, chemists, faith leaders drive adoption, not
app stores", answered by "Structured intermediary programme (CHAN-5)" — and its own rationale is the
mechanism: "These people, not app stores, drive adoption in Kenya. Trust transfers through
relationships." Nothing carried it, and the gap was load-bearing: §4.1's Persona B arrives through
"SOS feature recommended by his SACCO chairman", §CHAN-5 names the SACCO chairmen as a target
intermediary who gets a code, and the only thing in the tree called `referral` was a CHW activity
label.

What is tested is the transcription (a revision to §CHAN-5 must fail here), the attribution
mechanism (a code resolves to exactly one intermediary), and the one decision the section forces but
does not state: what makes a referral *verified*, given that §18.8 puts the disbursement on a weekly
run and money is real.
"""
import re
from pathlib import Path
from typing import Any

import httpx

from afya.auth.views import PKCETokenRequest, PKCEStart, s256
from afya.intermediaries.service import CODE_ALPHABET, IntermediaryService, _KIND_PREFIX
from afya.intermediaries.views import (
	CODE_CARRIED_TOOLS, TOOLS_PROVIDED, Incentive, Intermediary, IntermediaryKind, Referral,
)
from afya.privacy.views import RBACRole
from afya.service import build_services, create_app

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'

# The PKCE verifier for the CHW token below. Any 43–128 character string will do; this one is
# fixed rather than random so a failure reproduces.
VERIFIER = 'afya-intermediaries-test-verifier-000000000000000000000000'


def _section(start: str) -> list[str]:
	lines = SPEC.read_text(encoding='utf-8').splitlines()
	i = next(n for n, ln in enumerate(lines) if ln.startswith(start))
	out: list[str] = []
	for ln in lines[i:]:
		if out and ln.startswith(('## ', '### ', '#### ')) and not ln.startswith(start):
			break
		out.append(ln)
	return out


def _spec_bullets(start: str, after: str) -> list[str]:
	"""The `- ` bullets of one §CHAN-5 sub-list, located by its bold label."""
	lines = _section(start)
	i = next(n for n, ln in enumerate(lines) if ln.strip() == after)
	out: list[str] = []
	for ln in lines[i + 1:]:
		if ln.startswith('**'):
			break
		if ln.startswith('- '):
			out.append(ln[2:].strip())
	return out


def _intermediary(kind: IntermediaryKind, code: str, **kw: object) -> Intermediary:
	base: dict[str, Any] = {
		'code': code, 'name': 'Test Intermediary', 'kind': kind, 'county': 'Kisumu',
		'community': 'Nyalenda', 'enrolled_iso': '2026-10-11T09:00:00+00:00', 'trained': True,
	}
	return Intermediary(**{**base, **kw})  # type: ignore[arg-type]


def _referral(code: str, rid: str, completed: bool = True) -> Referral:
	return Referral(
		referral_id=rid, code=code, arrived_subject_ref='subj-1',
		at_iso='2026-10-11T10:00:00+00:00', profile_completed=completed,
	)


# What the fake carrier was asked to do. A module-level list rather than an attribute on the
# function: the point of the assertions below is that a refused payment never reaches the carrier,
# so the call log is the evidence and it has to be readable from the test.
PAID_CALLS: list[tuple[str, int, str]] = []


async def _paid(msisdn: str, kes: int, reason: str) -> str:
	PAID_CALLS.append((msisdn, kes, reason))
	return f'TELCO-{len(PAID_CALLS)}'


# --- §CHAN-5's lists, verbatim ----------------------------------------------------------------

def test_the_seven_kinds_are_the_sections_seven_bullets() -> None:
	"""§CHAN-5's "Target intermediaries", in the section's order. A kind lost from the list would
	still sort and still print; the seven and their wording are what make the omission visible."""
	bullets = _spec_bullets('#### CHAN-5', '**Target intermediaries:**')
	assert len(bullets) == 7, bullets
	assert [k.name for k in IntermediaryKind] == bullets


def test_the_five_tools_are_the_sections_five_bullets() -> None:
	"""§CHAN-5's "Tools provided", verbatim. Transcribed whole — including the three that are not
	code — because a list holding only what this repo implements would describe a programme the
	section does not."""
	bullets = _spec_bullets('#### CHAN-5', '**Tools provided:**')
	assert len(bullets) == 5, bullets
	assert list(TOOLS_PROVIDED) == bullets


def test_the_rationale_is_the_sections_own_sentence() -> None:
	"""The rationale is the mechanism, not decoration: "These people, not app stores, drive adoption
	in Kenya. Trust transfers through relationships." It is what makes §20.2 lever 4 a programme
	rather than a channel."""
	text = '\n'.join(_section('#### CHAN-5'))
	assert 'These people, not app stores, drive adoption in Kenya.' in text
	assert 'Trust transfers through relationships.' in text


def test_the_carried_tools_are_a_subset_of_the_sections() -> None:
	"""`CODE_CARRIED_TOOLS` marks which of the five this repo carries. A tool marked carried that
	§CHAN-5 does not list would be a claim about a programme the section never describes."""
	assert CODE_CARRIED_TOOLS <= set(TOOLS_PROVIDED), CODE_CARRIED_TOOLS - set(TOOLS_PROVIDED)
	assert len(CODE_CARRIED_TOOLS) < len(TOOLS_PROVIDED), (
		'a printed flip chart and a two-hour training are not code; a report claiming all five '
		'would be describing something this repository does not ship'
	)


# --- the attribution code ---------------------------------------------------------------------

def test_a_code_carries_the_kind_and_no_ambiguous_character() -> None:
	"""The prefix says what the intermediary is without a lookup, and the alphabet excludes I, O, 0
	and 1 — a code is read aloud to a person standing next to the intermediary and copied onto a flip
	chart by hand, so the characters that are ambiguous in speech or in handwriting are not in it."""
	for kind in IntermediaryKind:
		code = IntermediaryService.issue_code(kind)
		assert code.startswith(f'{_KIND_PREFIX[kind]}-'), code
		assert re.fullmatch(r'^[A-Z]{3}-[A-Z2-9]{4}$', code), code
	assert not set('IO01') & set(CODE_ALPHABET), 'the ambiguous characters must not be in the alphabet'


def test_issue_code_avoids_one_already_taken() -> None:
	"""Uniqueness is the caller's to enforce through `taken`, and `enrol` is the caller that does.
	Without it a code could resolve to two people, which attributes a referral to neither."""
	taken = {IntermediaryService.issue_code(IntermediaryKind.chw) for _ in range(20)}
	fresh = IntermediaryService.issue_code(IntermediaryKind.chw, taken)
	assert fresh not in taken


async def test_a_duplicate_code_is_refused_rather_than_overwriting() -> None:
	"""The second enrolment would silently reattribute every referral the first one earned, and
	nothing downstream could tell that it had happened."""
	svc = IntermediaryService()
	await svc.enrol(_intermediary(IntermediaryKind.chw, 'CHW-AAAA', name='First'))
	try:
		await svc.enrol(_intermediary(IntermediaryKind.chw, 'CHW-AAAA', name='Second'))
	except AssertionError as exc:
		assert 'already issued' in str(exc)
	else:
		raise AssertionError('a duplicate code must be refused')
	assert svc.intermediary('CHW-AAAA').name == 'First', 'the first enrolment must survive'


# --- the verification gate --------------------------------------------------------------------

async def test_an_incentive_is_refused_for_an_incomplete_profile() -> None:
	"""§20.2 lever 6 is "Airtime or data bundles for health profile completion", so the completion is
	the qualifying event. Paying an arrival pays for a click."""
	PAID_CALLS.clear()
	svc = IntermediaryService()
	await svc.enrol(_intermediary(IntermediaryKind.boda_sacco, 'BOD-AAAA'))
	await svc.record_referral(_referral('BOD-AAAA', 'REF-00000001', completed=False))
	assert svc.payable('BOD-AAAA') == []
	inc = Incentive(referral_id='REF-00000001', code='BOD-AAAA', msisdn='+254700000001',
	                kes=50, paid_iso='2026-10-11T11:00:00+00:00', reference='')
	try:
		await svc.pay_incentive(inc, _paid)
	except AssertionError as exc:
		assert 'profile completion' in str(exc)
	else:
		raise AssertionError('an incomplete profile must not be payable')
	assert PAID_CALLS == [], 'nothing must reach the carrier'


async def test_a_referral_cannot_be_paid_twice() -> None:
	"""The gate that matters. §18.8 puts the disbursement on a *weekly* run, so the same request
	arriving twice is the failure mode a programme with real money in it actually has — and the
	second payment is money already gone, which is why it is refused rather than reported."""
	PAID_CALLS.clear()
	svc = IntermediaryService()
	await svc.enrol(_intermediary(IntermediaryKind.pharmacy, 'PHA-AAAA'))
	await svc.record_referral(_referral('PHA-AAAA', 'REF-00000002'))
	inc = Incentive(referral_id='REF-00000002', code='PHA-AAAA', msisdn='+254700000002',
	                kes=50, paid_iso='2026-10-11T11:00:00+00:00', reference='')
	first = await svc.pay_incentive(inc, _paid)
	assert first.reference == 'TELCO-1'
	assert svc.is_paid('REF-00000002')
	assert svc.payable('PHA-AAAA') == [], 'a paid referral is no longer payable'
	try:
		await svc.pay_incentive(inc, _paid)
	except AssertionError as exc:
		assert 'already been paid' in str(exc)
	else:
		raise AssertionError('a replay must be refused')
	assert len(PAID_CALLS) == 1, 'the carrier must have been called exactly once'


async def test_an_incentive_must_be_attributed_to_its_referrals_code() -> None:
	"""A payment pointing at one referral and another code would pay the wrong intermediary — and
	the code is the whole attribution mechanism, so a mismatch makes the payment unattributable."""
	PAID_CALLS.clear()
	svc = IntermediaryService()
	await svc.enrol(_intermediary(IntermediaryKind.faith_leader, 'FTH-AAAA'))
	await svc.enrol(_intermediary(IntermediaryKind.market_leader, 'MKT-AAAA'))
	await svc.record_referral(_referral('FTH-AAAA', 'REF-00000003'))
	inc = Incentive(referral_id='REF-00000003', code='MKT-AAAA', msisdn='+254700000003',
	                kes=50, paid_iso='2026-10-11T11:00:00+00:00', reference='')
	try:
		await svc.pay_incentive(inc, _paid)
	except AssertionError as exc:
		assert 'attributed to the referral code' in str(exc)
	else:
		raise AssertionError('a mismatched code must be refused')
	assert PAID_CALLS == []


async def test_an_unattributable_referral_is_refused() -> None:
	"""A referral whose code is not enrolled is not a referral — there is nobody to attribute it to,
	and recording it would put a row in the table that no attribution report can ever show."""
	svc = IntermediaryService()
	try:
		await svc.record_referral(_referral('XXX-AAAA', 'REF-00000004'))
	except AssertionError as exc:
		assert 'unknown intermediary code' in str(exc)
	else:
		raise AssertionError('an unknown code must be refused')


async def test_the_amount_is_the_callers_and_the_carrier_bound_still_holds() -> None:
	"""§CHAN-5 states no amount, so none is written in this module — `kes` has no default. §18.8's
	telco client keeps its own 500 KES bound, which is the last place the figure is checkable."""
	import inspect
	field = Incentive.model_fields['kes']
	assert field.is_required(), '§CHAN-5 gives no amount; a default would be this module inventing one'
	from afya.integrations.service import TelcoGatewayClient
	src = inspect.getsource(TelcoGatewayClient.disburse_airtime)
	assert '500' in src, 'the carrier bound must still be there'


# --- the programme report ---------------------------------------------------------------------

def test_the_programme_reports_the_tools_it_does_not_carry() -> None:
	"""`uncarried_tools` is the finding. A printed flip chart and a two-hour training are not code;
	a report listing only what is implemented would describe a programme §CHAN-5 does not.

	The airtime incentive is *not* uncarried. It was, until this test was corrected: `pay_incentive`
	gates a verified referral and disburses through §18.8's bounded telco client, so the mechanism
	exists and an unconfigured deployment refusing the payment is a different fact. The audit filed
	the bullet `carried` while this set omitted it, and the programme report understated the section.
	"""
	svc = IntermediaryService()
	prog = svc.programme()
	assert len(prog.kinds) == 7 and len(prog.tools) == 5
	assert len(prog.carried_tools) + len(prog.uncarried_tools) == 5
	assert len(prog.uncarried_tools) == 2, prog.uncarried_tools
	assert 'Air time / data bundle incentives for verified referrals' in prog.carried_tools
	assert prog.intermediaries == 0
	assert 'no intermediary is enrolled yet' in prog.note
	assert set(prog.by_kind) == {k.value for k in IntermediaryKind}, 'every kind is counted, at zero'


async def test_the_attribution_report_reads_the_intermediarys_own_referrals() -> None:
	"""Arrivals, completions and payments for one code, and the unpaid completions are what a weekly
	run picks up."""
	PAID_CALLS.clear()
	svc = IntermediaryService()
	await svc.enrol(_intermediary(IntermediaryKind.chama_leader, 'CHA-AAAA'))
	await svc.record_referral(_referral('CHA-AAAA', 'REF-00000005'))
	await svc.record_referral(_referral('CHA-AAAA', 'REF-00000006', completed=False))
	await svc.record_referral(_referral('CHA-AAAA', 'REF-00000007'))
	await svc.pay_incentive(Incentive(referral_id='REF-00000005', code='CHA-AAAA',
		msisdn='+254700000005', kes=25, paid_iso='2026-10-11T12:00:00+00:00', reference=''), _paid)
	att = svc.attribution('CHA-AAAA')
	assert (att.referrals, att.completed) == (3, 2)
	assert att.paid_referrals == ['REF-00000005']
	assert att.unpaid_completed == ['REF-00000007'], 'the incomplete one is not payable'
	assert att.kes_paid == 25


# --- what the app serves ----------------------------------------------------------------------

def _app_and_tokens():  # type: ignore[no-untyped-def]
	"""A CHW token is *issued* through the PKCE flow, not provisioned: `provision_staff` is for the
	two operational roles (§17.4's sysadmin and auditor), and asserting `assigned` scope against a
	provisioned token would have failed at provisioning rather than at the route under test."""
	svc = build_services()
	auth: Any = svc['auth']
	code = auth.start_pkce(PKCEStart(
		client_id='chw-app', redirect_uri='afya://cb', code_challenge=s256(VERIFIER), state='state-1234',
	)).authorization_code
	chw_token = auth.exchange_pkce(PKCETokenRequest(
		authorization_code=code, client_id='chw-app', redirect_uri='afya://cb', code_verifier=VERIFIER,
	), RBACRole.chw)
	return create_app(svc), {
		'sysadmin': {'authorization': f"Bearer {auth.provision_staff('int-sys', RBACRole.sysadmin, registrar='MoH').access_token}"},
		'chw': {'authorization': f'Bearer {chw_token.access_token}'},
		'auditor': {'authorization': f"Bearer {auth.provision_staff('int-aud', RBACRole.auditor, registrar='MoH').access_token}"},
	}


async def test_the_programme_and_kinds_are_open_and_the_writes_are_not() -> None:
	"""The programme description names no person and is open, like `/personas`; enrolment spends the
	right to issue a payable code, so it is the operator's. A sysadmin holds `infrastructure` and a
	CHW holds `assigned`, which is what proves the two write routes are scoped to different roles."""
	app, tok = _app_and_tokens()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		prog = await c.get('/intermediaries/programme')
		assert prog.status_code == 200 and len(prog.json()['tools']) == 5
		kinds = await c.get('/intermediaries/kinds')
		assert kinds.status_code == 200 and len(kinds.json()['kinds']) == 7
		enrol = await c.post('/intermediaries/enrol', json={
			'code': 'CHW-ZZZZ', 'name': 'Open Caller', 'kind': 'chw', 'county': 'Kisumu',
			'community': 'Nyalenda', 'enrolled_iso': '2026-10-11T09:00:00+00:00',
		})
		assert enrol.status_code in (401, 403), 'issuing a payable code is not anonymous'
		assert (await c.post('/intermediaries/enrol', json={
			'code': 'CHW-ZZZZ', 'name': 'CHW Caller', 'kind': 'chw', 'county': 'Kisumu',
			'community': 'Nyalenda', 'enrolled_iso': '2026-10-11T09:00:00+00:00',
		}, headers=tok['chw'])).status_code == 403, 'a CHW does not issue codes'
		ok = await c.post('/intermediaries/enrol', json={
			'code': 'CHW-ZZZZ', 'name': 'Operator', 'kind': 'chw', 'county': 'Kisumu',
			'community': 'Nyalenda', 'enrolled_iso': '2026-10-11T09:00:00+00:00',
		}, headers=tok['sysadmin'])
		assert ok.status_code == 200, ok.text[:200]
		assert ok.json()['code'] == 'CHW-ZZZZ'


async def test_a_paid_code_cannot_be_reissued_through_the_route() -> None:
	"""The duplicate refusal is a 409 rather than a 500 — the operator can act on it, and the second
	enrolment must not have overwritten the first."""
	app, tok = _app_and_tokens()
	body = {'code': 'BOD-ZZZZ', 'name': 'SACCO Chair', 'kind': 'boda_sacco', 'county': 'Kisumu',
	        'community': 'Nyalenda', 'enrolled_iso': '2026-10-11T09:00:00+00:00'}
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		assert (await c.post('/intermediaries/enrol', json=body, headers=tok['sysadmin'])).status_code == 200
		again = await c.post('/intermediaries/enrol', json={**body, 'name': 'Someone Else'}, headers=tok['sysadmin'])
		assert again.status_code == 409, again.text[:200]
		att = await c.get('/intermediaries/BOD-ZZZZ/attribution', headers=tok['chw'])
	assert att.status_code == 200 and att.json()['intermediary']['name'] == 'SACCO Chair'


async def test_the_incentive_route_refuses_when_no_carrier_is_configured() -> None:
	"""A dev deployment has no airtime agreement. The refusal is 503 — "this deployment cannot pay" —
	rather than 422, which would say the *request* was wrong. The two are different facts and a
	caller can act on one of them."""
	app, tok = _app_and_tokens()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as c:
		await c.post('/intermediaries/enrol', json={
			'code': 'CHW-YYYY', 'name': 'Op', 'kind': 'chw', 'county': 'Kisumu',
			'community': 'Nyalenda', 'enrolled_iso': '2026-10-11T09:00:00+00:00',
		}, headers=tok['sysadmin'])
		await c.post('/intermediaries/referrals', json={
			'referral_id': 'REF-00000009', 'code': 'CHW-YYYY', 'arrived_subject_ref': 'subj-1',
			'at_iso': '2026-10-11T10:00:00+00:00', 'profile_completed': True,
		}, headers=tok['chw'])
		resp = await c.post('/intermediaries/incentives', json={
			'referral_id': 'REF-00000009', 'code': 'CHW-YYYY', 'msisdn': '+254700000009',
			'kes': 50, 'paid_iso': '2026-10-11T11:00:00+00:00', 'reference': '',
		}, headers=tok['sysadmin'])
		assert resp.status_code == 503, resp.text[:200]
		assert 'not configured' in resp.json()['detail']
		# The referral is untouched, so a later run with a carrier configured can still pay it.
		att = await c.get('/intermediaries/CHW-YYYY/attribution', headers=tok['chw'])
	assert att.json()['unpaid_completed'] == ['REF-00000009']


def test_no_served_sentence_carries_a_spec_code() -> None:
	"""§3.3 principle 9's rule. §CHAN-5 is an internal identifier; a served field saying "CHAN-005"
	would be the feature code percolating into a surface the app serves."""
	code = re.compile(r'\b(CHAN|INF|REC|MON|SENS|ACC)-\d{3}\b')
	svc = IntermediaryService()
	prog = svc.programme()
	for value in (*prog.kinds, *prog.tools, *prog.carried_tools, *prog.uncarried_tools, prog.note):
		assert not code.search(value), value
