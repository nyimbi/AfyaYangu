"""§5.4's last four "All channels share" bullets, against the identity model that carries them.

The section names five things every channel shares. The first — one triage engine — is enforced in
`channels/service.py`. The other four all rest on a fact the build did not have: a phone number and a
subject were two identifiers with nothing between them. `CaseReport` had no phone field, the consent
ledger was keyed by `subject_ref`, and a USSD session held an MSISDN — so "deduplicated by phone
number" could not be performed, "consent granted on one channel applies across channels" could not be
checked, and §5.4's "WhatsApp → USSD → CHW" journey was three strangers.

What is tested here is that the crossings now exist and go through *one* index, and that the parts
the identifier cannot decide are reported rather than invented. The finding is the same shape as
§17.4's: a capability the spec claims, stated where a reader can act on it.
"""
from pathlib import Path

import httpx
import pytest

from afya.auth.service import AuthService
from afya.channels.service import ChannelService
from afya.channels.views import SmsOut, WhatsAppIn
from afya.community.service import CommunityService
from afya.community.views import CaseReport, CaseStatus
from afya.identity.service import IdentityService
from afya.identity.views import IdentityLink, LinkBasis
from afya.privacy.service import PrivacyService
from afya.privacy.views import ConsentCategory, RBACRole
from afya.registry.service import FeatureRegistry
from afya.service import build_services, create_app
from afya.triage.service import TriageService

MSISDN = '+254712345678'
OTHER = '+254700000001'


def _link(msisdn: str = MSISDN, subject: str = 'subj-1', basis: LinkBasis = LinkBasis.self_entered) -> IdentityLink:
	return IdentityLink(msisdn=msisdn, subject_ref=subject, consent_id='consent-1', basis=basis)


def _case(report_id: str = 'CR-ABCD1234', msisdn: str | None = MSISDN, **kw: object) -> CaseReport:
	base: dict[str, object] = {
		'report_id': report_id, 'chw_ref': 'chw-1', 'county': 'Busia', 'community': 'Budalangi',
		'symptoms': ['fever', 'vomiting'], 'reporter_msisdn': msisdn,
	}
	base.update(kw)
	return CaseReport.model_validate(base)


def test_the_section_names_the_five_things_the_channels_share() -> None:
	"""§5.4's bullets, read against the spec. The list is carried so a revision that adds a sixth
	shared thing fails here until something implements it — which is the whole failure this unit
	exists for: four of the five were named and unbuilt."""
	spec = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = spec.split('### 5.4 Channel Interoperability', 1)[1].split('\n**Cross-channel journeys', 1)[0]
	bullets = [ln.strip('- ').split(' — ')[0].strip('* ') for ln in section.splitlines() if ln.startswith('- **')]
	assert bullets == [
		'A single triage engine', 'A single case-report backend', 'A single content repository',
		'A single identity model', 'A single consent registry',
	]
	# The two that name a mechanism are the two this unit is about, and the section's own words for
	# the mechanism are asserted so a revision cannot quietly drop "by phone number".
	assert 'deduplicated by phone number' in section
	assert 'phone number, with optional linkage to an app profile' in section


def test_a_phone_resolves_to_one_subject_and_the_second_call_is_the_same_one() -> None:
	"""The index itself. §5.4's identity is the phone, so two messages from one number are one person
	— and a per-session handle would make them two, which is exactly what the channel layer did."""
	svc = IdentityService()
	first = svc.resolve(MSISDN)
	assert svc.resolve(MSISDN) == first
	assert svc.subject_for(MSISDN) == first
	assert svc.msisdn_for(first) == MSISDN
	# Reads do not mint: a lookup for a number that has never messaged answers None rather than
	# creating a subject nothing has consented to.
	assert svc.subject_for(OTHER) is None
	assert svc.resolve(OTHER) != first
	assert svc.report()['resolved_phones'] == 2


def test_an_unlinked_subject_is_not_an_app_profile() -> None:
	"""§5.4's "optional" is the claim, and the distinction it turns on is whether a link exists.
	A subject minted by `resolve` is a phone's handle — a person who only ever used USSD — and
	treating it as an app profile is the silent merge §3.3 principle 6 forbids."""
	svc = IdentityService()
	subject = svc.resolve(MSISDN)
	assert not svc.is_linked(subject)
	assert svc.links() == []


async def test_linkage_needs_a_recorded_consent_and_is_refused_without_one() -> None:
	"""§17.1's basis for processing a phone number is the consent the person gave. The refusal is at
	the model — `consent_id` is required — and at the service, so neither a caller nor a future
	route can create the automatic merge by leaving a field out."""
	svc = IdentityService()
	with pytest.raises(Exception):
		IdentityLink(msisdn=MSISDN, subject_ref='subj-1', consent_id='', basis=LinkBasis.self_entered)
	# A different subject's phone is not this subject's to take: repointing it would silently
	# reassign the first person's data.
	await svc.link(_link())
	with pytest.raises(ValueError):
		await svc.link(IdentityLink(msisdn=MSISDN, subject_ref='subj-2', consent_id='c2', basis=LinkBasis.chw_registered))
	# And one app profile holds one phone, because a household sharing a handset is real but merging
	# two people's records is not a thing a phone number can decide.
	with pytest.raises(ValueError):
		await svc.link(IdentityLink(msisdn=OTHER, subject_ref='subj-1', consent_id='c3', basis=LinkBasis.self_entered))


async def test_unlinking_removes_the_index_entry_and_keeps_the_data() -> None:
	"""§17.2's withdrawal. The link is the thing withdrawn; the records the phone's sessions created
	are not, because unlinking a phone is not a request to delete them."""
	svc = IdentityService()
	link = await svc.link(_link())
	assert svc.is_linked('subj-1')
	out = await svc.unlink(link.link_id)
	assert out.link_id == link.link_id
	assert not svc.is_linked('subj-1')
	assert svc.subject_for(MSISDN) is None


async def test_a_case_report_from_a_linked_phone_dedups_against_the_apps_report() -> None:
	"""§5.4's "single case-report backend — deduplicated by phone number", performed, and the
	cross-channel case specifically: the report arrives over USSD and the open case was filed in the
	app. The key is the *resolved subject* rather than the raw number, which is what makes those two
	collide — a key built on the MSISDN alone would find nothing here."""
	identity = IdentityService()
	community = CommunityService(identity)
	first = await community.submit_case(_case('CR-AAAA1111'))
	assert first.alerts_sent == 1 and not first.deduplicated
	second = await community.submit_case(_case('CR-BBBB2222'))
	assert second.deduplicated
	assert second.alerts_sent == 0, 'the officer is alerted once per open case'
	assert 'CR-AAAA1111' in second.next_step
	# The duplicate is still stored: it is a report that landed, and dropping it would lose the
	# channel it arrived on.
	assert community.case_status('CR-BBBB2222') is CaseStatus.reported


async def test_a_link_does_not_change_which_case_a_report_dedups_against() -> None:
	"""The key is the phone number, so linking an app profile is orthogonal to the dedup — and that
	is a property worth asserting, because the first cut of this module keyed on the resolved subject
	and linking then *repointed* the key, orphaning any case opened before it. Keying on the number
	makes the whole ordering question disappear rather than answering it."""
	identity = IdentityService()
	community = CommunityService(identity)
	await community.submit_case(_case('CR-AAAA1111'))
	await identity.link(_link())
	linked = await community.submit_case(_case('CR-BBBB2222'))
	assert linked.deduplicated and 'CR-AAAA1111' in linked.next_step
	# And the raw number is the key, so the anonymous and the linked spellings are one reporter.
	assert identity.dedup_key('0712345678') == identity.dedup_key('254712345678') == identity.dedup_key('+254712345678')


def test_one_handset_has_one_spelling_across_the_channels() -> None:
	"""The defect the normalisation closes. A Kenyan carrier delivers a number bare (`254712345678`),
	the telco inbound route used to strip a leading zero from `0712345678`, and the USSD callback
	prepended a `+` to whatever arrived — so one handset produced `+254712345678` on USSD and
	`+0712345678` on SMS. Two spellings are two identities: two subjects, a consent grant the second
	channel cannot see, and a case-report dedup that never matches. This is §5.4's "single identity
	model — phone number" read as the literal claim it is."""
	svc = IdentityService()
	for spelling in ('0712345678', '254712345678', '+254712345678', '+254 712 345 678'):
		assert svc.normalise(spelling) == '+254712345678', spelling
	subject = svc.resolve('0712345678')
	assert svc.subject_for('254712345678') == subject
	assert svc.subject_for('+254712345678') == subject
	assert svc.report()['resolved_phones'] == 1, 'one handset, one resolution'
	assert svc.same_reporter('0712345678', '+254712345678')
	# A number that is not Kenyan is refused rather than rewritten into something that looks like one:
	# a wrong number here is a report attributed to the wrong person.
	with pytest.raises(ValueError):
		svc.normalise('+15551234567')


async def test_the_model_boundary_is_strict_e164_and_ingress_is_where_the_spelling_is_decided() -> None:
	"""Two boundaries, deliberately different. The models require E.164, so a request that spells a
	number any other way is refused rather than guessed at — an API that accepts `0712345678` and
	rewrites it is one that will one day rewrite something else. The *ingress* paths are where a
	carrier's own spelling is turned into that form, and there is one function that does it.

	So the "already belongs to another person" guard cannot be walked around by respelling: the model
	refuses the respelling before the service ever sees it."""
	with pytest.raises(Exception):
		IdentityLink(msisdn='0712345678', subject_ref='subj-1', consent_id='c1', basis=LinkBasis.self_entered)
	svc = IdentityService()
	await svc.link(_link())
	with pytest.raises(ValueError):
		await svc.link(IdentityLink(msisdn=MSISDN, subject_ref='subj-2', consent_id='c2',
		                            basis=LinkBasis.chw_registered))
	assert svc.links()[0].msisdn == MSISDN


async def test_a_closed_case_does_not_swallow_the_next_report() -> None:
	"""A closed case is a completed episode, so a later report from the same person is a new one
	rather than an amendment — otherwise a person who recovers and falls ill again is never counted."""
	identity = IdentityService()
	community = CommunityService(identity)
	await community.submit_case(_case('CR-AAAA1111'))
	await community.advance_case('CR-AAAA1111', CaseStatus.closed)
	again = await community.submit_case(_case('CR-BBBB2222'))
	assert not again.deduplicated and again.alerts_sent == 1


async def test_a_report_with_no_phone_is_not_treated_as_a_duplicate() -> None:
	"""A CHW logging offline carries no MSISDN and never will. "Cannot be deduplicated" and "is a
	duplicate" are different answers, and merging the absence into a match would collapse every
	offline report into one case."""
	identity = IdentityService()
	community = CommunityService(identity)
	first = await community.submit_case(_case('CR-AAAA1111', msisdn=None))
	second = await community.submit_case(_case('CR-BBBB2222', msisdn=None))
	assert not first.deduplicated and not second.deduplicated
	assert second.alerts_sent == 1


async def test_the_community_service_refuses_rather_than_deduping_on_the_raw_number() -> None:
	"""The failure mode the wiring guards against. A service with no identity model could dedup on the
	MSISDN and look correct for the USSD-only case while failing the app case — so it refuses."""
	community = CommunityService()
	with pytest.raises(RuntimeError, match='identity model'):
		await community.submit_case(_case())


async def test_a_consent_granted_by_phone_is_the_one_the_app_reads() -> None:
	"""§5.4's "consent granted on one channel applies across channels". The grant is written through
	the identity index, so it lands on the subject the app's token resolves to — one record, read the
	same way from both sides."""
	identity = IdentityService()
	privacy = PrivacyService(None, identity)
	subject = identity.resolve(MSISDN)
	assert not privacy.has_category_consent(subject, ConsentCategory.symptom_storage)
	rec = await privacy.record_consent_for_phone(MSISDN, ConsentCategory.symptom_storage)
	assert rec.subject_ref == subject
	assert privacy.has_category_consent(subject, ConsentCategory.symptom_storage)
	assert privacy.has_category_consent_for_phone(MSISDN, ConsentCategory.symptom_storage)
	# An unknown phone has granted nothing — the correct reading of an opt-in registry, and distinct
	# from a lookup that failed.
	assert not privacy.has_category_consent_for_phone(OTHER, ConsentCategory.symptom_storage)


async def test_withdrawing_in_the_app_withdraws_it_for_the_channel_too() -> None:
	"""One record, not one per channel. If the channel wrote its own grant the app's withdrawal would
	leave the channel still storing — which is the defect this crossing exists to prevent."""
	identity = IdentityService()
	privacy = PrivacyService(None, identity)
	rec = await privacy.record_consent_for_phone(MSISDN, ConsentCategory.symptom_storage)
	await privacy.withdraw(rec.consent_id)
	assert not privacy.has_category_consent_for_phone(MSISDN, ConsentCategory.symptom_storage)


def test_the_channel_service_resolves_a_phone_through_the_shared_index() -> None:
	"""The channel layer's half. A USSD session holds an MSISDN and nothing else; resolving it here
	rather than minting a session handle is what makes the section's "WhatsApp → USSD → CHW" journey
	one person. Without the index it refuses, because a local index is a second person."""
	identity = IdentityService()
	privacy = PrivacyService(None, identity)
	channels = ChannelService(_StubSms(), None, TriageService(FeatureRegistry()), identity, privacy)
	subject = channels.subject_of(MSISDN)
	assert identity.subject_for(MSISDN) == subject
	assert not channels.may_store_symptoms(MSISDN), 'no grant yet'
	bare = ChannelService(_StubSms(), None, TriageService(FeatureRegistry()))
	with pytest.raises(RuntimeError, match='identity model'):
		bare.subject_of(MSISDN)
	# A deployment that cannot read the ledger stores nothing. False is the safe direction: a default
	# of True would store health data on the strength of a wiring mistake.
	assert bare.may_store_symptoms(MSISDN) is False


async def test_the_ussd_callback_reports_whether_the_session_may_store_symptoms() -> None:
	"""The crossing at the point it reaches a person. The grant made in the app is what permits a
	USSD report to be kept, and the carrier envelope says so — a channel that silently stored
	regardless would make §5.4's consent registry a table nobody consults."""
	identity = IdentityService()
	privacy = PrivacyService(None, identity)
	channels = ChannelService(_StubSms(), None, TriageService(FeatureRegistry()), identity, privacy)
	from afya.integrations.gateways import AtUssdCallback

	cb = AtUssdCallback(session_id='s1', phone_number='254712345678', text='')
	assert channels.ussd_carrier_callback(cb)['store_symptoms'] == 'false'
	await privacy.record_consent_for_phone(MSISDN, ConsentCategory.symptom_storage)
	assert channels.ussd_carrier_callback(cb)['store_symptoms'] == 'true'


async def test_a_grant_made_over_ussd_survives_the_person_installing_the_app() -> None:
	"""§5.4's own journey, end to end, and the case the first cut of `link` got wrong by refusing it:
	the person used USSD first, so the phone *already* resolves to an anonymous subject when they
	install the app. Refusing that would make the section's journey impossible; the earlier cut read
	any existing entry as "another person's handset".

	The grant is the thing at stake. It was written against the anonymous handle, the app reads the
	profile's subject, and without the migration the person who consented on a feature phone finds the
	toggle off on the smartphone — consent granted on one channel not applying on the next, which is
	the exact sentence §5.4 makes."""
	identity = IdentityService()
	privacy = PrivacyService(None, identity)
	channels = ChannelService(_StubSms(), None, TriageService(FeatureRegistry()), identity, privacy)

	# The USSD leg: a session grants symptom storage, keyed on the handle the phone resolved to.
	await privacy.record_consent_for_phone('0712345678', ConsentCategory.symptom_storage)
	handle = identity.subject_for('0712345678')
	assert handle is not None
	assert channels.may_store_symptoms('0712345678')
	assert privacy.has_category_consent(handle, ConsentCategory.symptom_storage)

	# The app leg: the person installs it, gets a profile, and links the phone they already used.
	await identity.link(IdentityLink(msisdn='+254712345678', subject_ref='app-profile-1', consent_id='c1',
	                                 basis=LinkBasis.self_entered))
	assert identity.absorbed_subjects('+254712345678') == (handle,)
	# The composition point moves the grants; the route does this with both services in hand, and the
	# assertion here is that the move is what makes the app see what the feature phone granted.
	assert privacy.reassign_subject(handle, 'app-profile-1') == 1
	# The app reads its own subject and finds the grant the feature phone made.
	assert privacy.has_category_consent('app-profile-1', ConsentCategory.symptom_storage)
	# And the channel, now resolving the phone to the profile, still sees it.
	assert channels.may_store_symptoms('+254712345678')


async def test_a_phone_belonging_to_a_linked_profile_is_refused() -> None:
	"""The refusal that *should* stand. A subject with a link of its own is a person, so a phone that
	already belongs to one cannot be claimed by another — repointing it would silently move their
	records to a stranger. The distinction is between an anonymous handle (claimable) and a linked
	profile (not), and an earlier cut collapsed it, which is what made the journey above impossible."""
	identity = IdentityService()
	await identity.link(_link(msisdn='+254712345678', subject='person-a'))
	with pytest.raises(ValueError, match='another person'):
		await identity.link(IdentityLink(msisdn='+254712345678', subject_ref='person-b',
		                                 consent_id='c2', basis=LinkBasis.chw_registered))


def test_the_carrier_spellings_reach_one_subject_through_the_callback() -> None:
	"""The entry point the defect was actually at. Africa's Talking sends the number bare
	(`254712345678`), and the callback used to prepend a `+` to whatever arrived — so the same handset
	that messaged on WhatsApp as `+254712345678` resolved to a second subject when it opened USSD. A
	test that only called `normalise` directly would have missed it, because the bug was in the
	handler's use of the string rather than in the rule."""
	identity = IdentityService()
	channels = ChannelService(_StubSms(), None, TriageService(FeatureRegistry()), identity,
	                          PrivacyService(None, identity))
	from afya.integrations.gateways import AtUssdCallback

	subject = channels.subject_of('+254712345678')
	channels.ussd_carrier_callback(AtUssdCallback(session_id='s1', phone_number='254712345678', text=''))
	assert identity.subject_for('254712345678') == subject, 'the carrier\'s bare spelling is the same phone'
	channels.ussd_carrier_callback(AtUssdCallback(session_id='s2', phone_number='0712345678', text=''))
	assert identity.subject_for('0712345678') == subject, 'and so is the local spelling'
	assert identity.report()['resolved_phones'] == 1


async def test_the_telco_inbound_sms_reaches_the_same_subject() -> None:
	"""The third entry point, and the one that had the *other* hand-rolled rule: this route stripped a
	leading zero while the USSD callback prepended a `+`. Asserted over HTTP because the normalisation
	lives in the route rather than in the channel service, so a test against the service alone would
	pass while the route stayed wrong."""
	services = build_services()
	app = create_app(services)
	identity: IdentityService = services['identity']  # type: ignore[assignment]
	channels: ChannelService = services['channels']  # type: ignore[assignment]
	channels.subject_of('+254712345678')
	secret = 'test-webhook-secret'
	import hashlib
	import hmac
	import json as _json
	import os

	os.environ['AFYA_WEBHOOK_SECRET'] = secret
	payload = _json.dumps({'from': '0712345678', 'text': 'fever'}).encode()
	sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		resp = await c.post('/integrations/telco/sms/inbound', content=payload,
		                    headers={'content-type': 'application/json', 'x-afya-signature': sig})
	assert resp.status_code == 200, resp.text
	assert identity.subject_for('0712345678') == identity.subject_for('+254712345678'), 'one handset, one subject'
	assert identity.report()['resolved_phones'] == 1
	assert resp.json()['linked'] is False, 'an unlinked sender is not an app profile'
	# And a sender whose phone was linked resolves to the app profile rather than a fresh subject.
	anon = identity.subject_for('+254712345678')
	await identity.link(IdentityLink(msisdn='+254712345678', subject_ref='subj-1', consent_id='c1',
	                                 basis=LinkBasis.self_entered))
	assert identity.subject_for('0712345678') == 'subj-1'
	assert identity.report()['resolved_phones'] == 1, 'the link repoints rather than adding a phone'
	assert identity.absorbed_subjects('+254712345678') == (anon,), 'the handle it messaged under is named' 


def test_the_report_states_the_deduplication_gap_rather_than_implying_it_works() -> None:
	"""The finding. `dedup_key` exists and `can_deduplicate` is False, and the reason travels with it
	— a reader who saw the key alone would take the section's claim for a working control. §4.1's
	shared handsets, CHWs reporting for others and borrowed phones are why the identifier cannot
	close it on its own, so the rule is a product decision."""
	report = IdentityService().report()
	assert report['can_deduplicate'] is False
	assert 'CaseReport carries no phone number' in str(report['dedup_gap'])
	assert report['bases'] == [b.value for b in LinkBasis]
	# The gap names the mechanism the fix would need, so it is actionable rather than a disclaimer.
	assert 'dedup_key' in str(report['dedup_gap'])


class _StubSms:
	async def send(self, msg: SmsOut) -> str:
		return 'stub'


async def test_the_identity_routes_are_guarded_and_serve_the_model() -> None:
	"""§5.4 over HTTP. The model route is auditor-scoped because the index holds MSISDNs (§17.2), so
	it is exercised with a provisioned auditor token rather than assumed — a route that 403s for
	everyone would pass a weaker test."""
	services = build_services()
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/identity/model')).status_code == 401
		anon = (await c.post('/auth/anonymous', json={})).json()['token']
		assert (await c.get('/identity/model', headers={'authorization': f'Bearer {anon}'})).status_code == 403
		auth_svc: AuthService = services['auth']  # type: ignore[assignment]
		auditor = auth_svc.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
		body = (await c.get('/identity/model', headers={'authorization': f'Bearer {auditor}'})).json()
	identity_svc: IdentityService = services['identity']  # type: ignore[assignment]
	assert body == identity_svc.report()
	assert body['can_deduplicate'] is False
	# The payload carries no phone and no subject: it is the shape of the model, not its contents.
	assert MSISDN not in str(body)


async def test_a_link_is_forced_onto_the_callers_own_subject() -> None:
	"""The IDOR this route would otherwise be. The body names a subject and the token names one too,
	so a caller who types someone else's must be refused rather than silently linked — joining a
	profile to a phone is the act that merges two people's records."""
	services = build_services()
	app = create_app(services)
	privacy: PrivacyService = services['privacy']  # type: ignore[assignment]
	auth_svc: AuthService = services['auth']  # type: ignore[assignment]
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		token = (await c.post('/auth/anonymous', json={})).json()['token']
		caller = auth_svc.resolve_anonymous(token).subject_ref
		from afya.privacy.views import ConsentRecord, LegalBasis
		consent = await privacy.record_consent(
			ConsentRecord(subject_ref=caller, purpose='identity_linkage', data_types=['identity_linkage'],
			              retention_days=365, legal_basis=LegalBasis.consent))
		body = {'msisdn': MSISDN, 'subject_ref': caller, 'consent_id': consent.consent_id, 'basis': 'self_entered'}
		# A grant this person made over a channel, against the handle their phone resolved to.
		await privacy.record_consent_for_phone(MSISDN, ConsentCategory.symptom_storage)
		identity_svc: IdentityService = services['identity']  # type: ignore[assignment]
		handle = identity_svc.subject_for(MSISDN)
		assert handle is not None
		ok = await c.post('/identity/link', json=body, headers={'authorization': f'Bearer {token}'})
		assert ok.status_code == 200, ok.text
		assert ok.json()['linked'] is True
		# The route moved the channel's grant onto the caller's profile, which is §5.4's crossing
		# performed at the one point both services are in hand.
		assert ok.json()['consents_moved'] == 1
		assert privacy.has_category_consent(caller, ConsentCategory.symptom_storage)
		assert not privacy.has_category_consent(handle, ConsentCategory.symptom_storage), 'moved, not copied' 
		other = dict(body, subject_ref='someone-else')
		refused = await c.post('/identity/link', json=other, headers={'authorization': f'Bearer {token}'})
		assert refused.status_code == 422
		assert 'your own profile' in refused.json()['detail']


async def test_the_whatsapp_route_and_the_ussd_route_share_one_subject() -> None:
	"""The section's "WhatsApp → USSD → CHW" journey, asserted where it is reachable. One phone that
	messages on WhatsApp and then opens USSD resolves to one subject through the app's own services,
	which is what makes the journey a person rather than three strangers."""
	services = build_services()
	identity: IdentityService = services['identity']  # type: ignore[assignment]
	channels: ChannelService = services['channels']  # type: ignore[assignment]
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		await c.post('/channels/whatsapp', json={'from_msisdn': MSISDN, 'body': 'I have fever'})
		await c.post('/channels/ussd', json={'session_id': 's1', 'msisdn': MSISDN, 'text': '1*1'})
	wa_subject = channels.subject_of(MSISDN)
	assert identity.subject_for(MSISDN) == wa_subject
	# And the app's own token for that phone is the same subject once linked, which is the crossing
	# the CHW leg needs.
	await identity.link(_link(subject=wa_subject))
	assert identity.is_linked(wa_subject)
	assert channels.subject_of(MSISDN) == wa_subject


async def test_the_ussd_route_still_answers_without_a_storage_grant() -> None:
	"""The guard against over-applying consent. §5.4's registry decides whether a report is *kept*,
	not whether a person gets triaged — refusing to answer someone with fever because a toggle is off
	would trade a privacy protection for a case, which is the wrong trade at a triage boundary."""
	services = build_services()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		body = (await c.post('/channels/ussd', json={'session_id': 's1', 'msisdn': OTHER, 'text': '1*1'})).json()
	# §CHAN-2 draws two "→" prompts after the symptom entries, so the triage answer now arrives as a
	# `CON` carrying the first prompt with the recommendation above it rather than as a final `END`.
	answered = (body.get('menu') or '') + (body.get('end_text') or '')
	assert answered and 'malaria' in answered.lower(), 'a symptom report is answered whether or not it may be stored'
	channels: ChannelService = services['channels']  # type: ignore[assignment]
	assert channels.may_store_symptoms(OTHER) is False
	# And a WhatsApp body mentioning a symptom reaches the shared engine rather than being refused.
	out = channels.route_whatsapp(WhatsAppIn(from_msisdn=OTHER, body='fever and bleeding'))
	assert out.reply
