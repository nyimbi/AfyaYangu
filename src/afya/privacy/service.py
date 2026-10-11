"""Privacy service — consent ledger, DPIA gate, RBAC, anonymization, breach notification (spec §17)."""
from typing import Any

from afya.identity.service import IdentityService
from afya.logmixin import LogMixin
from afya.privacy.views import (
	AccessRequest, BreachEvent, BreachNotification, ConsentCategory, ConsentRecord, ConsentScope,
	ConsentToggle, DPIAInput, DPIAReport, LegalBasis, RBACRole, _SCOPE,
)

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
		self._store = store
		self._identity = identity
		assert self._consents == {} and self._audit == []

	async def record_consent(self, record: ConsentRecord) -> ConsentRecord:
		assert record.subject_ref, 'subject_ref required'
		assert record.purpose, 'purpose required'
		if not record.legal_basis is LegalBasis.legal_obligation:
			assert record.retention_days <= 730, 'health data retention must be bounded (24 months cap)'
		self._consents[record.consent_id] = record
		if self._store is not None:
			await self._store.save_consent(record)
		self._log_info('consent recorded', consent_id=record.consent_id)
		return record

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
		risks: list[str] = []
		if inp.raw_sensor_data_retained:
			risks.append('raw sensor data retention violates data minimisation (spec 17.2)')
		if inp.automated_decisions:
			risks.append('automated health risk decisions require human override')
		if inp.cross_border_transfer:
			risks.append('cross-border transfer requires ODPC approval + SCCs')
		if inp.children_data:
			risks.append('children data requires guardian consent path')
		if inp.proximity_logging:
			risks.append('proximity logging requires opt-in transparency per DESIRE lesson')
		blocked = 'raw sensor data retention violates data minimisation (spec 17.2)' in risks
		return DPIAReport(risks=risks, requires_dpia=bool(risks), blocked=blocked)

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