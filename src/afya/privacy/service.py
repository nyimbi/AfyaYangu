"""Privacy service — consent ledger, DPIA gate, RBAC, anonymization, breach notification (spec §17)."""
from typing import Any

from afya.identity.service import IdentityService
from afya.logmixin import LogMixin
from afya.privacy.views import (
	AccessRequest, BreachEvent, BreachNotification, ConsentCategory, ConsentRecord, ConsentScope,
	ConsentToggle, DPIAInput, DPIARecord, DPIAReport, InstrumentAssessment, InstrumentKind,
	InstrumentObligation,
	LegalBasis, ObligationKind, PrincipleImplementation, RBACRole, RegulatoryInstrument,
	RegulatoryReport, _SCOPE,
)
from afya.refs import resolves

# §SEC-001's eight categories. `explains` is the plain-language sentence beside the toggle and
# `on_withdrawal` is the consequence §SEC-001 requires be stated — both are data so a toggle cannot
# ship without them, and neither carries a spec code.
CONSENT_CATALOGUE: tuple[ConsentScope, ...] = (
	ConsentScope(category=ConsentCategory.symptom_storage, label='Keep my symptom history',
		explains='We store the symptoms you log so you and your health worker can see how you have been.',
		on_withdrawal='Your symptom history stops being used and is deleted on the next clean-up.'),
	ConsentScope(category=ConsentCategory.location_tracking, label='Use my location',
		explains='We use your area to find the nearest clinic and to show risk alerts where you are.',
		on_withdrawal='You can still use the app, but you will type your area by hand and alerts will be less precise.'),
	ConsentScope(category=ConsentCategory.proximity_logging, label='Nearby contact log',
		explains='The app can note when it is close to another app user, without either of you being identified.',
		on_withdrawal='Close-contact alerts cannot reach you if you are exposed.'),
	ConsentScope(category=ConsentCategory.sensor_monitoring, label='Phone sensors',
		explains='Your phone can measure things like breathing, coughing and falls. Each one is a separate choice.',
		on_withdrawal='The sensors you switch off stop measuring immediately and their readings are deleted.',
		per_sensor=True),
	ConsentScope(category=ConsentCategory.share_health_authorities, label='Share with health authorities',
		explains='Counts of illness, with no names, go to the Ministry so they can see where an outbreak is moving.',
		on_withdrawal='Your data is left out of the counts the Ministry sees.'),
	ConsentScope(category=ConsentCategory.share_chw, label='Share with my health worker',
		explains='Your community health worker can see your record so they can follow up with you.',
		on_withdrawal='Your health worker will not be able to see your record or follow up.'),
	ConsentScope(category=ConsentCategory.cloud_backup, label='Back up my data',
		explains='A copy of your record is kept so you do not lose it if you change or lose your phone.',
		on_withdrawal='Your record stays only on this phone. If you lose it, the record goes with it.'),
	ConsentScope(category=ConsentCategory.research, label='Allow research use',
		explains='De-identified data may be used to study how illness spreads. This is never required.',
		on_withdrawal='Your data is not used in research. Nothing else about the app changes.',
		separate_from_core=True),
)

_CATALOGUE_BY_CATEGORY: dict[ConsentCategory, ConsentScope] = {c.category: c for c in CONSENT_CATALOGUE}

# §17.2's lawfulness row is "Consent-based for all citizen data; legal obligation basis for mandatory
# disease notification only", and "only" is the load-bearing word: it is what stops the legal-basis
# door being a general-purpose way to process a citizen's health data without their consent. The
# purposes a case report is filed under are named here so the rule has somewhere to be applied
# rather than being a sentence in a document.
MANDATORY_NOTIFICATION_PURPOSES: frozenset[str] = frozenset({
	'case_report', 'disease_notification', 'notification', 'idsr_report',
})

# Appendix D question 7's cap, named rather than left as a literal at the assert that applies it.
# The spec states the number in one place only — the appendix row "Retention policy per data type
# needs ODPC sign-off (24-month cap assumed in code)" — and until this constant existed the code
# stated it in a different one, as a bare `730` with a message. Two statements of one number, one
# of which says *why* it is that number: the cap is an assumption the sign-off has not confirmed,
# which is a fact about the value and not a comment on it.
RETENTION_CAP_DAYS: int = 730

# §17.1, one row per instrument, with the Implementation cell split into its own items. The cell is
# a semicolon list and each item is a separate claim about this repo, so they are separate rows: a
# single boolean over "Consent registry; data minimisation by design; retention schedule; user data
# controls" would read covered while three of the four were missing.
#
# `control` is a `module:attr` reference for a code obligation and None for a process one. The three
# that are neither — MoH registration, ODPC registration, and the legal basis for outbreak sharing —
# are `registration` and `agreement` kinds rather than code, because what backs them is a record
# somewhere outside this repo and the assessment says so instead of inventing a module for them.
REGULATORY_INSTRUMENTS: tuple[RegulatoryInstrument, ...] = (
	RegulatoryInstrument(
		instrument='Kenya Data Protection Act 2019', kind=InstrumentKind.statute,
		requirement='Health data is sensitive personal data; requires explicit consent, purpose limitation, data minimisation, storage limitation',
		obligations=[
			InstrumentObligation(obligation='Consent registry', kind=ObligationKind.code,
				control='afya.privacy.service:PrivacyService.has_category_consent'),
			InstrumentObligation(obligation='data minimisation by design', kind=ObligationKind.code,
				control='afya.sensors.service:HANDLING'),
			InstrumentObligation(obligation='retention schedule', kind=ObligationKind.code,
				control='afya.retention.views:RETENTION_TABLE'),
			InstrumentObligation(obligation='user data controls', kind=ObligationKind.code,
				control='afya.retention.service:RetentionService.inventory'),
		]),
	RegulatoryInstrument(
		instrument='ODPC Guidance Note on Health Data', kind=InstrumentKind.regulatory_guidance,
		requirement='Lawful, fair, transparent processing; accuracy; accountability',
		obligations=[
			InstrumentObligation(obligation='Plain-language notices', kind=ObligationKind.code,
				control='afya.privacy.service:CONSENT_CATALOGUE'),
			InstrumentObligation(obligation='accuracy SLAs', kind=ObligationKind.code,
				control='afya.info.service:InfoService.stale'),
			InstrumentObligation(obligation='DPO appointed', kind=ObligationKind.process),
		]),
	RegulatoryInstrument(
		instrument='Digital Health Act No. 15 of 2023', kind=InstrumentKind.statute,
		requirement='Governs e-health service delivery including m-health and telehealth',
		obligations=[
			InstrumentObligation(obligation='Compliance review', kind=ObligationKind.process),
			InstrumentObligation(obligation='MoH registration', kind=ObligationKind.registration),
		]),
	RegulatoryInstrument(
		instrument='Computer Misuse and Cybercrimes Act 2018', kind=InstrumentKind.statute,
		requirement='Security of systems and data',
		obligations=[
			InstrumentObligation(obligation='Security controls', kind=ObligationKind.code,
				control='afya.security.service:CONTROLS'),
			InstrumentObligation(obligation='incident response', kind=ObligationKind.code,
				control='afya.operations.service:OperationsService.status'),
		]),
	RegulatoryInstrument(
		instrument='Public Health Act (Cap 242)', kind=InstrumentKind.statute,
		requirement='Disease surveillance obligations',
		obligations=[
			InstrumentObligation(obligation='Legal basis for outbreak data sharing where required',
				kind=ObligationKind.code,
				control='afya.privacy.service:PrivacyService.case_report_basis'),
		]),
	RegulatoryInstrument(
		instrument='WHO International Health Regulations', kind=InstrumentKind.international,
		requirement='Surveillance and reporting',
		obligations=[
			InstrumentObligation(obligation='Alignment with IDSR', kind=ObligationKind.code,
				control='afya.chw.views:JOB_AIDS'),
		]),
)

# §17.2's seven principles, same treatment: the Implementation cell split into the claims it makes.
# The three principles whose artefacts are named across several modules carry more than one item for
# exactly the reason the DPA row does.
PRIVACY_PRINCIPLES: tuple[tuple[str, str, tuple[InstrumentObligation, ...]], ...] = (
	('Lawfulness',
	 'Consent-based for all citizen data; legal obligation basis for mandatory disease notification only',
	 (
		InstrumentObligation(obligation='Consent-based for all citizen data', kind=ObligationKind.code,
			control='afya.privacy.views:LegalBasis'),
		InstrumentObligation(obligation='legal obligation basis for mandatory disease notification only',
			kind=ObligationKind.process),
	 )),
	('Purpose limitation',
	 'Data collected for Ebola response is not used for other purposes without fresh consent',
	 (
		InstrumentObligation(obligation='Data collected for Ebola response is not used for other purposes without fresh consent',
			kind=ObligationKind.code, control='afya.privacy.service:PrivacyService.has_consent'),
	 )),
	('Data minimisation',
	 'Only data necessary for the specific purpose is collected. Raw sensor data is never retained.',
	 (
		InstrumentObligation(obligation='Only data necessary for the specific purpose is collected',
			kind=ObligationKind.code, control='afya.retention.service:USER_DELETABLE'),
		InstrumentObligation(obligation='Raw sensor data is never retained', kind=ObligationKind.code,
			control='afya.sensors.service:HANDLING'),
	 )),
	('Accuracy',
	 'Content reviewed weekly; user data editable; correction workflows',
	 (
		InstrumentObligation(obligation='Content reviewed weekly', kind=ObligationKind.code,
			control='afya.info.service:REVIEW_CADENCE_DAYS'),
		InstrumentObligation(obligation='user data editable', kind=ObligationKind.code,
			control='afya.retention.service:RetentionService.correct'),
		InstrumentObligation(obligation='correction workflows', kind=ObligationKind.code,
			control='afya.retention.service:RetentionService.corrections'),
	 )),
	('Storage limitation',
	 'Defined retention periods per data type; automatic deletion',
	 (
		InstrumentObligation(obligation='Defined retention periods per data type', kind=ObligationKind.code,
			control='afya.retention.views:RETENTION_TABLE'),
		InstrumentObligation(obligation='automatic deletion', kind=ObligationKind.code,
			control='afya.retention.service:RetentionService.purge_expired'),
	 )),
	('Integrity and confidentiality', 'AES-256 at rest, TLS 1.3 in transit, RBAC, audit logging',
	 (
		InstrumentObligation(obligation='AES-256 at rest', kind=ObligationKind.code,
			control='afya.retention.views:ENCRYPTION_STANDARD'),
		InstrumentObligation(obligation='TLS 1.3 in transit', kind=ObligationKind.code,
			control='afya.retention.views:ENCRYPTION_STANDARD'),
		InstrumentObligation(obligation='RBAC', kind=ObligationKind.code,
			control='afya.privacy.views:_SCOPE'),
		InstrumentObligation(obligation='audit logging', kind=ObligationKind.code,
			control='afya.privacy.service:PrivacyService.check_access_logged'),
	 )),
	('Accountability', 'DPO appointed; DPIAs conducted; transparency reports published',
	 (
		InstrumentObligation(obligation='DPO appointed', kind=ObligationKind.process),
		InstrumentObligation(obligation='DPIAs conducted', kind=ObligationKind.code,
			control='afya.privacy.service:PrivacyService.assess_dpia'),
		InstrumentObligation(obligation='transparency reports published', kind=ObligationKind.code,
			control='afya.retention.service:RetentionService.transparency_report'),
	 )),
)


# §17.3's eight bullets, in the section's order, each with the field that describes it and the
# finding the assessment raises when it is present. The topic list is data because the assessment is
# only as complete as it: `assess_dpia` walks this, so a bullet added to the section and not here is
# the one failure mode that would otherwise be silent — a report that names eight topics while
# reading seven.
DPIA_TOPICS: tuple[tuple[str, str, str], ...] = (
	('LiDAR and acoustic monitoring (novel, potentially intrusive)', 'raw_sensor_data_retained',
		'raw sensor data retention violates data minimisation (spec 17.2)'),
	('Location tracking and geofencing', 'location_tracking',
		'location tracking requires a documented lawful basis and a geofence audit trail'),
	('Proximity logging and exposure notification', 'proximity_logging',
		'proximity logging requires opt-in transparency per DESIRE lesson'),
	('Contact tracing assistance', 'contact_tracing',
		'contact tracing assistance is a novel intrusion and needs its own DPIA review'),
	('AI-based risk scoring', 'automated_decisions',
		'automated health risk decisions require human override'),
	('Data sharing with health authorities', 'data_sharing_with_authorities',
		'sharing with health authorities requires a data-sharing agreement and aggregation floor'),
	("Processing of children's data", 'children_data',
		'children data requires guardian consent path'),
	('Cross-border data transfer', 'cross_border_transfer',
		'cross-border transfer requires ODPC approval + SCCs'),
)

BLOCKING_TOPICS: frozenset[str] = frozenset({
	'raw sensor data retention violates data minimisation (spec 17.2)',
})
"""The findings that stop the gate rather than merely inform it.

One, and it is §17.2's data-minimisation rule: §13.1 says raw sensor data never leaves the handset,
so a deployment that retains it is not a risk to weigh but a rule already broken. The other seven
are reviewable risks — they need a DPIA and a decision, which is what a DPIA is for.
"""


def _handling(sensitivity: Any) -> Any:
	"""The §13.1 handling row for a sensitivity class. Imported at call time because
	`afya.sensors.service` reaches back into the registry, and a module-level import would put the
	sensor table on the privacy module's import path."""
	from afya.sensors.service import HANDLING
	for row in HANDLING:
		if row.sensitivity is sensitivity:
			return row
	raise AssertionError(f'no handling row for {sensitivity}')


class PrivacyService(LogMixin):
	def __init__(self, store=None, identity: 'IdentityService | None' = None) -> None:
		"""`identity` is §5.4's single identity model, and it is what makes the ledger a *registry*
		rather than a table keyed by a name only the app knows. A channel holds an MSISDN and the
		ledger holds a `subject_ref`; without the index between them, "consent granted on one channel
		applies across channels" cannot be checked anywhere. Optional only so a unit test can build
		the ledger alone, and the phone-keyed reads answer False rather than raising when it is
		absent — an unknown phone has granted nothing, which is the same answer as a missing index
		for every question a caller can ask.
		"""
		self._consents: dict[str, ConsentRecord] = {}
		self._audit: list[tuple[bool, AccessRequest]] = []
		self._dpia_reviews: list[DPIARecord] = []
		self._store = store
		self._identity = identity
		assert self._consents == {} and self._audit == []

	async def record_consent(self, record: ConsentRecord) -> ConsentRecord:
		assert record.subject_ref, 'subject_ref required'
		assert record.purpose, 'purpose required'
		if not record.legal_basis is LegalBasis.legal_obligation:
			assert record.retention_days <= RETENTION_CAP_DAYS, (
				f'health data retention must be bounded ({RETENTION_CAP_DAYS} days — Appendix D '
				f'question 7\'s {RETENTION_CAP_DAYS // 30}-month cap, assumed pending ODPC sign-off)'
			)
		else:
			# §17.2 lawfulness: the legal-obligation basis is for "mandatory disease notification
			# only". Until this assert existed the basis was a label a caller chose, so the one door
			# §17.2 holds shut was open to any purpose — a person's symptom history could be filed
			# against a statute instead of against their consent, and the ledger would show a
			# lawful record. The list is of purposes, not of callers: the rule is about what the
			# data is for, which is what the section says.
			assert record.purpose in MANDATORY_NOTIFICATION_PURPOSES, (
				f'{record.purpose} is not a mandatory disease notification; '
				'§17.2 allows the legal-obligation basis for those only'
			)
		self._consents[record.consent_id] = record
		if self._store is not None:
			await self._store.save_consent(record)
		self._log_info('consent recorded', consent_id=record.consent_id)
		return record

	@staticmethod
	def case_report_basis(purpose: str) -> LegalBasis:
		"""The basis a purpose is lawfully processed under: the Public Health Act for a mandatory
		notification, consent for everything else.

		§17.1's Cap 242 row calls itself the "legal basis for outbreak data sharing where required",
		and §17.2 says where: mandatory disease notification, and nowhere else. Answering the question
		here rather than at each call site is what makes the two sections one rule.
		"""
		return LegalBasis.legal_obligation if purpose in MANDATORY_NOTIFICATION_PURPOSES else LegalBasis.consent

	def has_consent(self, subject_ref: str, purpose: str) -> bool:
		out = any(
			c.subject_ref == subject_ref and c.purpose == purpose and not c.withdrawn
			for c in self._consents.values()
		)
		return out

	# --- §SEC-001 consent categories ------------------------------------------------------------

	@staticmethod
	def consent_catalogue() -> list[ConsentScope]:
		"""§SEC-001's eight categories, each with the consequence its withdrawal carries."""
		return list(CONSENT_CATALOGUE)

	def sensor_consents(self) -> list[dict[str, object]]:
		"""§SEC-001 asks for "Sensor monitoring (each sensor separately)".

		That is one category in the catalogue and one decision per sensor here, enumerated from the
		§13.1 matrix so the two cannot drift: a sensor added to §13.1 without a consent toggle would
		be a measurement nobody consented to. A sensor whose class requires no consent under §17.2
		(the Low rows) still appears, because §SEC-001's granularity is per sensor rather than per
		class — but it is marked so a client does not demand a grant it does not need.
		"""
		from afya.sensors.service import SENSORS
		return [
			{
				'sensor': s.slug, 'name': s.name, 'used_for': s.used_for,
				'sensitivity': s.sensitivity.value,
				'needs_consent': _handling(s.sensitivity).capture_requires_consent,
				'raw_retained': _handling(s.sensitivity).raw_may_be_retained,
			}
			for s in SENSORS
		]

	def consent_toggles(self, granted: dict[str, bool] | None = None,
	                    sensors: dict[str, bool] | None = None) -> list[ConsentToggle]:
		"""The catalogue resolved against what a subject has actually granted.

		§SEC-001 wants granular toggles, one-tap revocation and a log the user can see. `granted` is
		keyed by category value; a category absent from it is off, because consent is opt-in and a
		default of on is not consent.
		"""
		granted = granted or {}
		sensors = sensors or {}
		from afya.sensors.service import SENSORS
		out: list[ConsentToggle] = []
		for scope in CONSENT_CATALOGUE:
			row = ConsentToggle(
				category=scope.category, label=scope.label, explains=scope.explains,
				on_withdrawal=scope.on_withdrawal, separate_from_core=scope.separate_from_core,
				granted=bool(granted.get(scope.category.value, False)),
			)
			if scope.per_sensor:
				row.sensors = {s.slug: bool(sensors.get(s.slug, False)) for s in SENSORS}
			out.append(row)
		return out

	def has_category_consent(self, subject_ref: str, category: ConsentCategory) -> bool:
		"""Whether a subject holds a live grant for one category. Revocation is one tap, so a
		withdrawn record is not consent — the same rule `has_consent` applies."""
		return any(
			c.subject_ref == subject_ref and c.purpose == category.value and not c.withdrawn
			for c in self._consents.values()
		)

	# --- §5.4's single consent registry -----------------------------------------------------------

	def subject_for_msisdn(self, msisdn: str) -> str | None:
		"""The subject a phone resolves to, through §5.4's identity model.

		The ledger is keyed by `subject_ref` and a channel arrives holding an MSISDN, so without this
		step the two never meet and "consent granted on one channel applies across channels" is false
		in the only place it is checkable. Reads rather than mints: a consent lookup must not create an
		identity for a number that has never messaged, because the record it would then be asked about
		cannot exist.
		"""
		if self._identity is None:
			return None
		return self._identity.subject_for(msisdn)

	def has_category_consent_for_phone(self, msisdn: str, category: ConsentCategory) -> bool:
		"""§5.4's cross-channel consent, asked the way a channel asks it.

		A USSD session holds a phone and nothing else, and the thing it needs to know — may I store
		this person's symptoms — was decided in the app. Resolving the phone to the subject and reading
		the one ledger is what makes the answer the same on both channels. False when the phone
		resolves to no subject: an unknown phone has granted nothing, which is the correct reading of a
		registry that is opt-in rather than of a lookup that failed.
		"""
		subject = self.subject_for_msisdn(msisdn)
		if subject is None:
			return False
		return self.has_category_consent(subject, category)

	def reassign_subject(self, old: str, new: str) -> int:
		"""Move every grant from one subject to another, and report how many moved.

		Called when a phone is linked to an app profile: the grants were written against the anonymous
		handle the phone was messaging under, and the app reads the profile's subject, so a person who
		consented over USSD and then installed the app would find the toggle off — §5.4's "consent
		granted on one channel applies across channels" failing in the one place it is checkable.

		The records are *moved* rather than read through a second lookup, because two records for one
		grant is how a withdrawal stops being one tap: the app would withdraw its copy and the channel's
		would survive. A withdrawn record moves too — the withdrawal is a fact about the person, and
		leaving it behind would resurrect a grant nobody renewed.
		"""
		moved = 0
		for consent_id, rec in list(self._consents.items()):
			if rec.subject_ref == old:
				self._consents[consent_id] = rec.model_copy(update={'subject_ref': new})
				moved += 1
		if moved:
			self._log_info('consent reassigned to a linked profile', count=moved)
		return moved

	async def record_consent_for_phone(self, msisdn: str, category: ConsentCategory,
	                                   retention_days: int = 365) -> ConsentRecord:
		"""A grant made on a channel, written to the one registry the app reads.

		The subject is resolved through the identity model, so a person who grants on USSD and then
		opens the app sees the toggle already on — and a person who withdraws in the app has withdrawn
		it for the USSD session too, because there is one record and not one per channel.
		"""
		if self._identity is None:
			raise RuntimeError('the privacy service has no identity model wired; §5.4 requires the shared one')
		subject = self._identity.resolve(msisdn)
		return await self.record_consent(ConsentRecord(
			subject_ref=subject, purpose=category.value, data_types=[category.value],
			retention_days=retention_days, legal_basis=LegalBasis.consent,
		))

	def sensor_consented(self, subject_ref: str, sensor: str) -> bool:
		"""Whether a subject consented to one sensor. §SEC-001's per-sensor rule means a blanket
		`sensor_monitoring` grant is not enough on its own — the grant must name the sensor."""
		return any(
			c.subject_ref == subject_ref and not c.withdrawn
			and c.purpose == f'{ConsentCategory.sensor_monitoring.value}:{sensor}'
			for c in self._consents.values()
		)

	async def withdraw(self, consent_id: str) -> ConsentRecord:
		rec = self._consents[consent_id]
		rec.withdrawn = True
		if self._store is not None:
			await self._store.save_consent(rec)
		self._log_warn('consent withdrawn', consent_id=consent_id)
		return rec

	def check_access(self, req: AccessRequest) -> bool:
		allowed = any(req.dataset.startswith(scope) or req.dataset == scope for scope in _SCOPE.get(req.role, set()))
		self._audit.append((allowed, req))
		return allowed

	async def check_access_logged(self, req: AccessRequest) -> bool:
		"""`check_access` plus the durable entry §17.4 requires. Every guarded route goes through
		here, so the log covers real access rather than only the calls a test happens to make.

		The in-memory list is kept because it is cheap and readable in-process; it is not the
		record. Before this the record was *only* that list, so an access log survived exactly as
		long as the process did.
		"""
		allowed = self.check_access(req)
		if self._store is not None:
			import time
			await self._store.append_audit(req.role.value, req.dataset, allowed, int(time.time() * 1000))
		return allowed

	def audit_log(self) -> list[tuple[bool, AccessRequest]]:
		return list(self._audit)

	def assess_dpia(self, inp: DPIAInput) -> DPIAReport:
		"""The eight §17.3 topics against the processing described, walked rather than spelled out.

		Spelled out, this was five `if` statements and the section names eight topics: location
		tracking, contact tracing and sharing with health authorities had no field to be described
		by, so the assessment could not report them and its silence read as clearance.
		"""
		risks = [finding for _topic, field, finding in DPIA_TOPICS if getattr(inp, field)]
		blocked = any(r in BLOCKING_TOPICS for r in risks)
		return DPIAReport(risks=risks, requires_dpia=bool(risks), blocked=blocked)

	@staticmethod
	def dpia_fingerprint(inp: DPIAInput) -> str:
		"""Which of §17.3's topics this processing raises, as one stable string.

		The gate asks "has this been reviewed", and the answer has to be about *this* processing
		rather than about some DPIA that happened once. The fingerprint is the set of topics the
		processing raises, sorted and joined, so a review recorded for a proximity-logging rollout
		does not answer for one that has since added cross-border transfer.
		"""
		raised = sorted(field for _topic, field, _finding in DPIA_TOPICS if getattr(inp, field))
		return ','.join(raised)

	def review_dpia(self, inp: DPIAInput, reviewed_at_iso: str, reviewed_by: str) -> DPIARecord:
		"""Record that the DPIA for this processing was conducted. Refuses a blocked assessment.

		The point of recording rather than asserting is that a review is a thing that happened at a
		time by someone; a boolean the caller supplies about itself is not. A blocked assessment is
		not reviewable into existence either — §17.2's data-minimisation violation has to be fixed
		in the processing, which is what `blocked` means.
		"""
		assert reviewed_at_iso, 'a review must carry when it happened'
		assert reviewed_by, 'a review must carry who conducted it'
		report = self.assess_dpia(inp)
		assert not report.blocked, \
			'a DPIA that finds a data-minimisation violation cannot be recorded as reviewed'
		record = DPIARecord(
			reviewed_at_iso=reviewed_at_iso, reviewed_by=reviewed_by,
			processing_id=inp.processing_id, fingerprint=self.dpia_fingerprint(inp),
			topics=[topic for topic, _f, _r in DPIA_TOPICS if getattr(inp, _f)],
			risks=report.risks, blocked=report.blocked,
		)
		self._dpia_reviews.append(record)
		return record

	def dpia_review_for(self, inp: DPIAInput | None) -> DPIARecord | None:
		"""The most recent review that still answers for this processing, or None.

		None is the honest answer for the two ways a review fails to cover: none was ever recorded,
		or the processing has changed since the last one — §17.3 says "reviewed and updated before
		each Tier 4 activation", and an update that added a topic is exactly the case the word
		"updated" is there for.
		"""
		if inp is None:
			return None
		wanted = self.dpia_fingerprint(inp)
		covering = [r for r in self._dpia_reviews if r.fingerprint == wanted]
		return max(covering, key=lambda r: r.reviewed_at_iso) if covering else None

	def dpia_reviews(self) -> list[DPIARecord]:
		return list(self._dpia_reviews)

	def anonymize(self, data: dict[str, Any]) -> dict[str, Any]:
		assert isinstance(data, dict), 'data must be dict'
		out = dict(data)
		if 'phone' in out:
			assert isinstance(out['phone'], str), 'phone must be str'
			out['phone'] = out['phone'][:6] + '*' * max(0, len(out['phone']) - 6)
		if 'national_id' in out:
			out['national_id'] = '****'
		if 'location' in out:
			lat, lon = out['location'].get('lat'), out['location'].get('lon')
			out['location'] = {'county': self._county_approx(lat, lon) if lat is not None else 'unknown'}
		if 'timestamp' in out:
			ts = out['timestamp']
			out['timestamp'] = ts[:10] if isinstance(ts, str) else str(ts)[:10]
		return out

	@staticmethod
	def _county_approx(lat: float, lon: float) -> str:
		assert -5.0 < lat < 6.0 and 33.0 < lon < 43.0, 'coords outside Kenya bounds'
		if lat < -0.5:
			return 'Coast'
		if lat > 1.0:
			return 'Northern'
		return 'Central'

	def breach_notification(self, event: BreachEvent) -> BreachNotification:
		"""§24.8's 72-hour ODPC notification, measured from when the breach was detected.

		The deadline floors at zero — the DPA gives a fixed window, not a negative one — but the
		floor loses the fact that matters: a breach notified three days late and one notified with
		three days to spare both reported `0`, which is a report that cannot tell a met statutory
		duty from a missed one. `overdue` carries it.
		"""
		deadline = max(0, 3 - event.detected_at_days_ago)
		high_risk = {'health_status', 'location', 'identity'}
		notify = event.affected_count > 100 or high_risk.intersection(event.affected_data) != set()
		if event.detected_at_days_ago > 3:
			self._log_error('ODPC notification deadline missed', days_ago=event.detected_at_days_ago)
		return BreachNotification(
			odpc_deadline_days=deadline,
			notify_users=notify,
			overdue=event.detected_at_days_ago > 3,
			summary=f"breach affecting {', '.join(event.affected_data)} (n={event.affected_count})",
		)

	async def purge_expired(self) -> int:
		return len([c for c in list(self._consents.values()) if c.withdrawn and self._consents.pop(c.consent_id)])

	# --- §17.1 instruments and §17.2 principles ----------------------------------------------

	def _assess(self, instrument: str, obligation: InstrumentObligation,
	            registrations: frozenset[str], agreements: frozenset[str]) -> InstrumentAssessment:
		"""One §17.1 obligation beside the answer to whether it is done.

		Three kinds fail differently, and collapsing them would lose the distinction that matters.
		A `code` obligation fails when its reference does not land — a claim about software that names
		software that is not there. A `registration` or `agreement` fails when no record backs it,
		and what backs those is outside this repo, so the caller passes in what it has rather than
		this method assuming. A `process` obligation fails when no §24 duty schedules it: a process
		item nobody owns is indistinguishable, from the register alone, from one somebody does, and
		that is the failure mode the obligation register exists to make visible.
		"""
		from afya.operations.service import OBLIGATIONS
		if obligation.kind is ObligationKind.code:
			lands = resolves(obligation.control)
			note = f'{obligation.control} resolves' if lands else f'{obligation.control} does not resolve'
			return InstrumentAssessment(instrument=instrument, obligation=obligation.obligation,
				kind=obligation.kind, control=obligation.control, resolves=lands, backed=lands, note=note)
		if obligation.kind is ObligationKind.registration:
			backed = obligation.obligation.lower() in registrations
			return InstrumentAssessment(instrument=instrument, obligation=obligation.obligation,
				kind=obligation.kind, control=None, resolves=False, backed=backed,
				note='a registration record backs this' if backed else 'no registration record backs this')
		if obligation.kind is ObligationKind.agreement:
			backed = obligation.obligation.lower() in agreements
			return InstrumentAssessment(instrument=instrument, obligation=obligation.obligation,
				kind=obligation.kind, control=None, resolves=False, backed=backed,
				note='a signed agreement backs this' if backed else 'no signed agreement backs this')
		owner = next((o for o in OBLIGATIONS if o.duty.lower() == obligation.obligation.lower()), None)
		return InstrumentAssessment(instrument=instrument, obligation=obligation.obligation,
			kind=obligation.kind, control=None, resolves=False, backed=owner is not None,
			note=f'{owner.owner} owns it (§{owner.section.lstrip("§")})' if owner else 'no §24 duty schedules this')

	def regulatory_report(self, registrations: frozenset[str] = frozenset(),
	                      agreements: frozenset[str] = frozenset()) -> RegulatoryReport:
		"""§17.1 and §17.2 against what actually exists.

		The two sections are the same question asked twice — what does the law require, and what
		implements it — and both answered in prose until now. The register is the answer as data.

		`unbacked` is the finding, and it is reported rather than repaired: whether to build the
		missing piece or to record that it is a duty outside this repo is a product decision, and a
		register that quietly resolved its own gaps would be the failure it exists to catch.
		"""
		assessments = [
			self._assess(row.instrument, ob, registrations, agreements)
			for row in REGULATORY_INSTRUMENTS for ob in row.obligations
		]
		principles: list[PrincipleImplementation] = []
		for name, implementation, artifacts in PRIVACY_PRINCIPLES:
			unbacked = [a.obligation for a in artifacts
				if not self._assess(name, a, registrations, agreements).backed]
			principles.append(PrincipleImplementation(
				principle=name, implementation=implementation, artifacts=list(artifacts),
				unbacked_artifacts=unbacked, backed=not unbacked,
			))
		unbacked = [
			f'{a.instrument}: {a.obligation}' for a in assessments if not a.backed
		] + [
			f'§17.2 {p.principle}: {u}' for p in principles for u in p.unbacked_artifacts
		]
		return RegulatoryReport(
			instruments=list(REGULATORY_INSTRUMENTS), assessments=assessments, principles=principles,
			unbacked=unbacked, instrument_count=len(REGULATORY_INSTRUMENTS),
			obligation_count=len(assessments),
		)
