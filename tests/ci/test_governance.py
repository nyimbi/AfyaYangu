"""§15.3 residency, §17.7 sharing agreements, §15.4 capacity — the three sections that were prose.

Each had zero code: every outbound client posted wherever it was configured, nothing knew whether
any agreement existed, and nothing measured a single target. These tests are written so that the
failure mode they guard against — a document claiming compliance nothing enforces — is a red test.
"""
import httpx
import pytest
from pydantic import ValidationError
from typing import Any

from afya.auth.service import AuthService
from afya.governance.service import SCALE_TARGETS, GovernanceService
from afya.governance.views import AgreementParty, DataClass, DataSharingAgreement, Jurisdiction
from afya.privacy.views import RBACRole
from afya.service import build_services, create_app


def _agreement(party: AgreementParty, signed: bool = True) -> DataSharingAgreement:
	return DataSharingAgreement(
		party=party, purpose='national outbreak response', scope=['case_reports'],
		retention_days=365, security='AES-256-GCM, TLS 1.3', audit_rights='MoH may audit on demand',
		signed=signed, signed_on_iso='2026-01-15' if signed else None,
		legal_review_ref='ODPC-2026-0042' if signed else None,
	)


# --- §15.3 residency -------------------------------------------------------------------------

def test_unknown_host_is_not_assumed_safe() -> None:
	"""The default must fail closed: a host nobody classified is outside Africa until a rule says
	otherwise, because the other default ships a transfer nobody reviewed."""
	svc = GovernanceService()
	assert svc.jurisdiction_of('https://api.example.com/v1') is Jurisdiction.outside_africa
	assert svc.jurisdiction_of('https://jali.health.go.ke/api') is Jurisdiction.kenya
	# Longest suffix wins, so a future `.africastalking.com` rule cannot be shadowed by `.ke`.
	assert svc.jurisdiction_of('https://api.africastalking.com') is Jurisdiction.kenya


def test_case_management_may_not_leave_kenya() -> None:
	svc = GovernanceService()
	refused = svc.residency_decision('ministry_of_health', 'https://eu.example.com', DataClass.case_management)
	assert not refused.allowed and 'may not leave' in refused.reason
	allowed = svc.residency_decision('ministry_of_health', 'https://adam.health.go.ke', DataClass.case_management)
	assert allowed.allowed and allowed.jurisdiction is Jurisdiction.kenya


def test_assert_egress_raises_on_a_forbidden_transfer() -> None:
	svc = GovernanceService()
	with pytest.raises(AssertionError, match='may not leave'):
		svc.assert_egress_allowed('ministry_of_health', 'https://graph.facebook.com', DataClass.contact_tracing)
	# The permitted path returns rather than raising, so a caller can log the decision it made.
	assert svc.assert_egress_allowed('telco', 'https://api.africastalking.com', DataClass.citizen_personal).allowed


def test_outside_africa_needs_a_signed_agreement_not_merely_a_class() -> None:
	"""§15.3's "without explicit legal review" is a gate, and the §17.7 agreement is the review.
	The canary: with no agreement the same transfer that is allowed once signed must be refused."""
	svc = GovernanceService()
	host = 'https://graph.facebook.com'
	refused = svc.residency_decision(AgreementParty.meta_whatsapp.value, host, DataClass.citizen_personal)
	assert not refused.allowed, 'no agreement means no exception'

	svc.register(_agreement(AgreementParty.meta_whatsapp))
	allowed = svc.residency_decision(AgreementParty.meta_whatsapp.value, host, DataClass.citizen_personal)
	assert allowed.allowed and 'signed §17.7 agreement' in allowed.reason

	# An unsigned agreement is not a review either.
	svc2 = GovernanceService()
	svc2.register(_agreement(AgreementParty.meta_whatsapp, signed=False))
	assert not svc2.residency_decision(AgreementParty.meta_whatsapp.value, host, DataClass.citizen_personal).allowed


def test_a_free_text_party_name_clears_nothing() -> None:
	"""The exception keys on a §17.7 party, so an arbitrary string cannot invoke it."""
	svc = GovernanceService()
	svc.register(_agreement(AgreementParty.meta_whatsapp))
	dec = svc.residency_decision('definitely-not-a-party', 'https://graph.facebook.com', DataClass.citizen_personal)
	assert not dec.allowed


def test_anonymised_analytics_may_leave_africa_without_an_agreement() -> None:
	"""The spec permits it outright for anonymised data, so this must not depend on the exception."""
	svc = GovernanceService()
	assert svc.residency_decision('cloud_provider', 'https://s3.amazonaws.com', DataClass.anonymised_analytics).allowed


# --- §17.7 agreements ------------------------------------------------------------------------

def test_agreement_needs_every_clause_the_spec_names() -> None:
	"""§17.7 names five clauses. Each is refused when missing — the model is the gate, so an
	agreement cannot be constructed incomplete and then read as one that permits sharing."""
	base: dict[str, Any] = dict(party=AgreementParty.telco, purpose='zero-rating', scope=['msisdn'],
	                            retention_days=30, security='TLS 1.3', audit_rights='annual')
	DataSharingAgreement(**base)  # the complete one constructs
	for field, empty in (('purpose', ''), ('security', ''), ('audit_rights', ''), ('scope', [])):
		with pytest.raises(ValidationError):
			DataSharingAgreement(**{**base, field: empty})


def test_absent_and_unsigned_are_both_a_refusal() -> None:
	svc = GovernanceService()
	assert not svc.may_share(AgreementParty.county_health), 'an absent agreement is a refusal'
	svc.register(_agreement(AgreementParty.county_health, signed=False))
	assert not svc.may_share(AgreementParty.county_health), 'an unsigned agreement is a refusal'
	svc.register(_agreement(AgreementParty.county_health))
	assert svc.may_share(AgreementParty.county_health)


def test_posture_names_the_seven_parties_and_the_unsigned_ones() -> None:
	svc = GovernanceService()
	posture = svc.sharing_posture()
	assert len(posture['parties']) == 7, '§17.7 names seven parties'  # type: ignore[arg-type]
	assert posture['cleared_to_share'] == []
	assert posture['unsigned'] == sorted(p.value for p in AgreementParty)
	svc.register(_agreement(AgreementParty.ministry_of_health))
	assert svc.sharing_posture()['cleared_to_share'] == ['ministry_of_health']


# --- egress audit ----------------------------------------------------------------------------

def test_egress_audit_flags_a_misconfigured_host() -> None:
	"""A deployment whose ADaM URL points outside Kenya is the failure this reports: the client
	would happily post case data there, and only the config decides."""
	svc = GovernanceService()
	clean = svc.egress_violations({'adam': 'https://adam.health.go.ke/api', 'ppb': 'https://ppb.health.go.ke/api'})
	assert clean == [], 'in-jurisdiction wires are not violations'
	dirty = svc.egress_violations({'adam': 'https://adam.example.com/api'})
	assert len(dirty) == 1 and dirty[0].party == AgreementParty.ministry_of_health.value


def test_egress_audit_skips_unconfigured_wires() -> None:
	svc = GovernanceService()
	assert svc.audit_egress({}) == [], 'no URL means the wire is not configured, not that it passed'


# --- §15.4 capacity --------------------------------------------------------------------------

def test_capacity_report_does_not_count_silence_as_compliance() -> None:
	svc = GovernanceService()
	report = svc.capacity_report()
	assert len(report.checks) == len(SCALE_TARGETS)
	assert len(report.unmeasured) == len(SCALE_TARGETS)
	assert report.all_measured_targets_met is False, 'an unmeasured target is not a met one'


def test_latency_and_recovery_targets_are_upper_bounds() -> None:
	"""The direction matters: a p95 of 250 ms meets a 300 ms target, and 3 hours does not meet a
	1-hour RTO. A report that got this backwards would pass a failing deployment."""
	svc = GovernanceService()
	report = svc.capacity_report({'api_latency_p95_ms': 250, 'recovery_time_hours': 3})
	by = {c.metric: c for c in report.checks}
	assert by['api_latency_p95_ms'].within_target is True
	assert by['recovery_time_hours'].within_target is False
	assert report.all_measured_targets_met is False


def test_capacity_targets_match_the_spec_table() -> None:
	assert len(SCALE_TARGETS) == 13, '§15.4 lists thirteen metrics'
	assert all(row[3] == '§15.4' for row in SCALE_TARGETS)
	assert {row[0] for row in SCALE_TARGETS} >= {'api_latency_p95_ms', 'uptime_pct', 'registered_users'}


# --- the routes ------------------------------------------------------------------------------

async def _client() -> httpx.AsyncClient:
	services = build_services()
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t')


def _sysadmin(services: dict[str, object]) -> str:
	auth: AuthService = services['auth']  # type: ignore[assignment]
	return auth.provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops').access_token


async def test_residency_and_capacity_routes_require_the_infrastructure_scope() -> None:
	async with await _client() as c:
		for path in ('/governance/residency', '/governance/capacity', '/governance/egress'):
			assert (await c.get(path)).status_code in (401, 403), f'{path} must be guarded'
		anon = (await c.post('/auth/anonymous', json={'subject_ref': 'U1'})).json()['token']
		assert (await c.get('/governance/egress', headers={'authorization': f'Bearer {anon}'})).status_code == 403


async def test_agreements_route_is_auditor_scoped_and_registers() -> None:
	services = build_services()
	auth: AuthService = services['auth']  # type: ignore[assignment]
	sysadmin = _sysadmin(services)
	auditor = auth.provision_staff('ops-1', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		# The auditor may read the posture but not change it: reading which parties we share with is
		# the audit question; recording an agreement is an operator action.
		assert (await c.get('/governance/agreements', headers={'authorization': f'Bearer {auditor}'})).status_code == 200
		body = _agreement(AgreementParty.telco).model_dump(mode='json')
		assert (await c.post('/governance/agreements', json=body, headers={'authorization': f'Bearer {auditor}'})).status_code == 403
		ok = await c.post('/governance/agreements', json=body, headers={'authorization': f'Bearer {sysadmin}'})
		assert ok.status_code == 200 and 'telco' in ok.json()['cleared_to_share']
		# An incomplete agreement is refused, not registered as one that permits sharing.
		bad = {**body, 'purpose': ''}
		assert (await c.post('/governance/agreements', json=bad, headers={'authorization': f'Bearer {sysadmin}'})).status_code == 422


async def test_capacity_route_refuses_an_unknown_metric() -> None:
	services = build_services()
	sysadmin = _sysadmin(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		good = await c.post('/governance/capacity', json={'api_latency_p95_ms': 120.0},
		                    headers={'authorization': f'Bearer {sysadmin}'})
		assert good.status_code == 200
		report = good.json()
		assert {c_['metric'] for c_ in report['checks'] if c_['observed'] is not None} == {'api_latency_p95_ms'}
		assert report['all_measured_targets_met'] is True
		bad = await c.post('/governance/capacity', json={'vibes': 10.0}, headers={'authorization': f'Bearer {sysadmin}'})
		assert bad.status_code == 422 and 'vibes' in bad.json()['detail']


async def test_egress_route_reports_the_deployments_own_hosts() -> None:
	services = build_services()
	sysadmin = _sysadmin(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		out = (await c.get('/governance/egress', headers={'authorization': f'Bearer {sysadmin}'})).json()
		# Default config points every national wire at a .go.ke host and the SMS gateway at
		# Africa's Talking (Kenya), so nothing is in violation; WhatsApp is unconfigured and so
		# produces no decision at all.
		assert out['violations'] == [], out['violations']
		assert {d['party'] for d in out['decisions']} == {
			AgreementParty.ministry_of_health.value, AgreementParty.telco.value,
		}, out['decisions']


# --- §15.2 the stack, and §15.1 the architecture -------------------------------------------------

def _spec_stack_rows() -> list[list[str]]:
	"""§15.2's table, read out of the spec so a revision fails here rather than passing."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('### 15.2 Technology Stack', 1)[1].split('\n### ', 1)[0]
	rows: list[list[str]] = []
	for line in section.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if len(cells) != 3 or cells[0] == 'Layer':
			continue
		rows.append([c.replace('**', '') for c in cells])
	return rows


def test_the_stack_table_is_the_sections_rows() -> None:
	"""§15.2 is a claim about what runs, and every row of it is carried — a row dropped from the
	table is a layer nothing compares against what the build contains."""
	from afya.governance.service import GovernanceService
	spec = _spec_stack_rows()
	report = GovernanceService().stack_report()
	assert len(spec) == 18, f'the section names {len(spec)} layers'
	assert [l.layer for l in report.layers] == [r[0] for r in spec]
	assert [l.specified for l in report.layers] == [r[1] for r in spec]
	assert [l.rationale for l in report.layers] == [r[2] for r in spec]


def test_a_shipped_layer_points_at_something_in_the_repo() -> None:
	"""The finding: a layer reported as shipped with nothing backing it is the stack table making
	exactly the claim it exists to check. Both evidence spellings are walked — a `module:attr`
	reference for a layer that is code and a repo path for one that is configuration — because a
	checker that knew only the import form would pass every configuration layer for free."""
	from afya.governance.service import GovernanceService
	report = GovernanceService().stack_report()
	assert report.unbacked_layers == [], f'layers claiming to ship with no evidence: {report.unbacked_layers}'
	shipped = [l for l in report.layers if l.status.value == 'shipped']
	assert shipped, 'the table must claim something ships, or the check is vacuous'
	assert all(l.evidence for l in shipped)


def test_the_three_findings_are_different_questions() -> None:
	"""A deferred layer is not a divergence and neither is an unbacked one. Collapsing them would let
	a layer the programme has not stood up read as one running something else — and the divergences
	are what every "we run the spec's stack" sentence depends on being visible."""
	from afya.governance.service import GovernanceService
	report = GovernanceService().stack_report()
	by_layer = {l.layer: l for l in report.layers}
	for name in report.deferred_layers:
		assert by_layer[name].actual is None and by_layer[name].evidence is None
	for name in report.diverged_layers:
		assert by_layer[name].actual and by_layer[name].evidence
	assert not (set(report.deferred_layers) & set(report.diverged_layers))
	assert not (set(report.unbacked_layers) & set(report.deferred_layers))
	# The four the memory records as deliberate divergences are among them, so the table agrees
	# with the recorded position rather than quietly reporting compliance.
	for layer in ('Mobile framework', 'Backend runtime'):
		assert layer in report.diverged_layers, f'{layer} should read as diverged'


def test_every_architecture_box_has_a_module_behind_it() -> None:
	"""§15.1 is a picture, so the checkable part is whether each box has a module: a box drawn and
	not built is an architecture claim with nothing under it. The two client-side boxes are the
	exception and say so through `note` rather than being given a fabricated module."""
	from afya.governance.service import GovernanceService
	report = GovernanceService().stack_report()
	assert report.unresolved_components == [], f'boxes with no module: {report.unresolved_components}'
	without = [c.name for c in report.components if c.module is None]
	assert without, 'the client-side boxes must be the ones with no module'
	for c in report.components:
		if c.module is None:
			assert c.note, f'{c.name} has no module and no note saying why'
	# Every band the diagram draws is represented, so a band cannot be dropped silently.
	assert {c.band for c in report.components} == {'backend', 'integration', 'sync', 'local'}


def test_the_canary_watches_a_phantom_module_fire() -> None:
	"""The gate is the resolver walk, and the silent change to the table is a module path that no
	longer lands — a renamed class, a moved module. Everything else still passes, because the other
	boxes still resolve and the count is unchanged."""
	from afya.governance import service as governance_service
	from afya.governance.service import GovernanceService
	original = governance_service.GovernanceService.ARCHITECTURE
	assert original[0][2] == 'afya.service:create_app', 'canary target moved'
	patched = (('API Gateway (rate limiting, auth, routing, audit)', 'backend', 'afya.nothing.service:Missing', None),
		*original[1:])
	try:
		governance_service.GovernanceService.ARCHITECTURE = patched
		report = GovernanceService().stack_report()
		assert report.unresolved_components == ['API Gateway (rate limiting, auth, routing, audit)'], \
			'the canary did not fire: a phantom module resolved'
	finally:
		governance_service.GovernanceService.ARCHITECTURE = original
	assert GovernanceService().stack_report().unresolved_components == [], 'restore failed'


# --- Appendix D: the open questions --------------------------------------------------------------

def _appendix_d_rows() -> list[list[str]]:
	"""Appendix D's table, read from the spec rather than restated, so a row reworded there fails
	here instead of silently detaching the register from the text it claims to carry."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	body = text.split('## Appendix D: Open Questions and Decisions Required', 1)[1].split('\n## ', 1)[0]
	rows = []
	for line in body.splitlines():
		if not line.startswith('|') or set(line) <= set('|-: '):
			continue
		cells = [c.strip() for c in line.strip('|').split('|')]
		if cells[0] == '#':
			continue
		rows.append(cells)
	return rows


def test_the_open_questions_are_the_appendix_rows_in_its_own_words() -> None:
	"""Appendix D's seven rows, verbatim. The block was cited in prose three times and carried as
	data nowhere, so the list of decisions the spec says are *required* was itself a thing a reader
	had to remember — and a row whose `Blocks` cell was paraphrased could name a section that does
	not exist without anything noticing."""
	from afya.governance.service import GovernanceService
	rows = _appendix_d_rows()
	assert len(rows) == 7, f'Appendix D lists seven open questions, found {len(rows)}'
	assert [q.number for q in GovernanceService.OPEN_QUESTIONS] == [int(r[0]) for r in rows]
	for row, question in zip(rows, GovernanceService.OPEN_QUESTIONS):
		assert question.question == row[1], f'Q{row[0]} question: {question.question!r} != {row[1]!r}'
		assert question.blocks == row[2], f'Q{row[0]} blocks: {question.blocks!r} != {row[2]!r}'


def test_every_question_that_bites_names_a_place_that_resolves() -> None:
	"""`live_at` is the checkable half of the row, and `unresolved` is the finding: a row naming a
	`module:attr` that no longer resolves is a blocker someone will believe is tracked after the
	code it names is gone. Question 1 is the one row with nothing in this tree to attach to — it is
	about an entity, not a value — and a `live_at` invented for it would be the fabrication the
	field exists to avoid."""
	from afya.refs import resolves
	from afya.governance.service import GovernanceService
	assert GovernanceService().unresolved_questions() == []
	assert GovernanceService.unresolved_questions() == []
	without = [q.number for q in GovernanceService.OPEN_QUESTIONS if q.live_at is None]
	assert without == [1], 'only the product-owner entity has no artefact in this tree'
	for q in GovernanceService.OPEN_QUESTIONS:
		if q.live_at is not None:
			assert resolves(q.live_at), f'Q{q.number} names {q.live_at}, which does not resolve'


def test_the_assumed_values_are_the_ones_the_code_actually_carries() -> None:
	"""An open question is not a blank: a deployment is already running on an answer to five of the
	seven, and each `assumed` names what that answer is. Each is checked against the code rather
	than trusted, because a register of assumptions that drifted from the assumptions would be
	worse than none — it would read as the inventory of what is undecided."""
	from afya.channels.cost import zero_rating_gaps
	from afya.governance.service import GovernanceService
	from afya.governance.views import DataClass, Jurisdiction
	from afya.info.service import HOTLINES
	from afya.privacy.service import RETENTION_CAP_DAYS
	from afya.registry.service import FeatureRegistry, Tier4Activation
	by_number = {q.number: q for q in GovernanceService.OPEN_QUESTIONS}

	def assumed(n: int) -> str:
		"""The `assumed` text for one row, refusing None.

		`assumed` is optional because one row genuinely has nothing in this tree to assume from —
		question 1 is about which entity owns the product, and no value in the code answers it. Every
		other row is already running on an answer, so a None there is a defect in the register
		rather than a fact about the world.
		"""
		text = by_number[n].assumed
		assert text is not None, f'Q{n} carries no assumption, and only Q1 legitimately has none'
		return text

	# Q2: the hotline codes are the spec's own example and neither row is verified.
	assert [h.number for h in HOTLINES][0] == '719'
	assert not any(h.verified for h in HOTLINES)
	assert '719' in assumed(2) and 'unverified' in assumed(2)
	# Q3: the gate records that the three keys were held, never by whom — which is the protocol
	# the row asks for and the one thing `Tier4Activation` cannot state. The check names the
	# *holder* fields a protocol would need, not the substring "by": `authorized_by_pheoc` contains
	# it, so a `'by' in field` guard passes on the very field it is meant to exclude.
	assert 'authorized_by_pheoc' in Tier4Activation.model_fields
	holder_fields = [f for f in Tier4Activation.model_fields
	                 if f in ('holder', 'holders', 'authorized_by', 'signed_off_by', 'flag_authority')]
	assert not holder_fields, f'a key holder is recorded now ({holder_fields}), so Q3 has moved'
	assert 'by whom' in assumed(3)
	# Q4: the negative answer. Every AWS and Azure host is outside_africa, so §15.3's own example
	# option is refused for the classes §15.3 protects, and no host is classified african_union.
	from afya.governance.views import HOST_JURISDICTIONS
	assert not [h for h, j in HOST_JURISDICTIONS if j is Jurisdiction.african_union], \
		'an AU host rule exists now, so Q4\'s assumption has changed and this test must change'
	svc = GovernanceService()
	assert not svc.residency_decision('ministry_of_health', 's3.af-south-1.amazonaws.com',
		DataClass.case_management).allowed, 'AWS Africa must be refused for case management'
	assert 'african_union' in assumed(4)
	# Q5: internal flags, and §15.2's own stack row records the divergence.
	assert FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1',
		flag_enabled=True)).tier4_active()
	assert 'internal' in assumed(5)
	# Q6: with no rules pulled the two zero-rating channels report unverified rather than free.
	assert zero_rating_gaps(None) == [], 'no rules means unverified, not a gap and not a pass'
	assert 'unagreed' in assumed(6)
	# Q7: the cap the appendix names, and the constant that now carries its provenance.
	assert RETENTION_CAP_DAYS == 730 and '24-month cap' in by_number[7].question
	assert str(RETENTION_CAP_DAYS) in assumed(7)
	# Exactly one row has nothing to assume from, and it is the one about an entity.
	assert [q.number for q in GovernanceService.OPEN_QUESTIONS if q.assumed is None] == [1]


def test_the_retention_cap_is_named_and_refuses_over_it() -> None:
	"""Appendix D question 7 says the cap is "assumed in code". It was a bare `730` at the assert
	that applied it — the same number the appendix states, in a second place, with no link between
	them. `RETENTION_CAP_DAYS` is that number named once, so the appendix row can point at it.

	The first cut of this test did not await the call, so the coroutine was never run, the assert
	never fired and `DID NOT RAISE` was the result — the shape CLAUDE.md records as twenty minutes
	lost to a fixture nobody awaited. A refusal test that cannot reach the refusal is not evidence
	the refusal exists.
	"""
	import asyncio
	import pytest as _pytest
	from afya.privacy.service import RETENTION_CAP_DAYS, PrivacyService
	from afya.privacy.views import ConsentRecord, LegalBasis

	async def _over_the_cap() -> None:
		svc = PrivacyService()
		await svc.record_consent(ConsentRecord(subject_ref='U1', purpose='symptom_storage',
			data_types=['symptom_logs'], retention_days=RETENTION_CAP_DAYS + 1,
			legal_basis=LegalBasis.consent))

	with _pytest.raises(AssertionError, match=str(RETENTION_CAP_DAYS)):
		asyncio.run(_over_the_cap())

	async def _at_the_cap() -> None:
		svc = PrivacyService()
		await svc.record_consent(ConsentRecord(subject_ref='U1', purpose='symptom_storage',
			data_types=['symptom_logs'], retention_days=RETENTION_CAP_DAYS,
			legal_basis=LegalBasis.consent))

	asyncio.run(_at_the_cap())  # the cap itself is permitted; only over it is refused


async def test_the_open_questions_route_is_infrastructure_scoped() -> None:
	"""The report names the retention cap, the residency table and the activation gate as
	undecided, which is a deployment fact rather than something a citizen endpoint should assert."""
	from afya.governance.service import GovernanceService
	services = build_services()
	sysadmin = _sysadmin(services)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(services)), base_url='http://t') as c:
		assert (await c.get('/governance/open-questions')).status_code in (401, 403)
		out = (await c.get('/governance/open-questions',
			headers={'authorization': f'Bearer {sysadmin}'})).json()
		assert len(out['questions']) == 7 and out['unresolved'] == []
		assert [q['number'] for q in out['questions']] == [1, 2, 3, 4, 5, 6, 7]
		assert out['questions'] == [q.model_dump(mode='json') for q in GovernanceService.OPEN_QUESTIONS]
