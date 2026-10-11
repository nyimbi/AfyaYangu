"""§11.1's activation model as a service — who a trigger reaches, and what closing the event starts.

The registry's `tier4_active()` answers one question ("is the PHEOC event on") and §11.1 asks three
more: is there a confirmed case in *this* county, is *this* person a contact, have *they* asked. This
service holds the firings and resolves a feature for a given state, so an individual trigger can fire
for one person without a national declaration — which is what §11's own constraint describes
("Activates automatically for users in affected areas") and what the single global gate could not do.

Deactivation is here rather than in the retention module because §11.1 states it as part of the
activation model: the clocks that begin are the ones the activation created, and a service that starts
them without knowing which firings happened cannot know which subjects to notify.
"""
from datetime import date, timedelta

from afya.logmixin import LogMixin
from afya.registry.activation import (
	TIER4_DATA_TYPES, ActivationState, ActivationTrigger, Deactivation, RetentionClock,
	TriggerFiring, TriggerScope, triggers_for,
)
from afya.registry.service import FeatureRegistry, Tier
from afya.retention.views import RETENTION_TABLE


def _date(iso: str) -> date:
	assert len(iso) >= 10, 'an ISO date is required'
	return date.fromisoformat(iso[:10])


class ActivationService(LogMixin):
	def __init__(self, registry: FeatureRegistry) -> None:
		self._registry = registry
		self._firings: list[TriggerFiring] = []
		assert self._firings == []

	# --- firing ------------------------------------------------------------------------------

	async def fire(self, firing: TriggerFiring) -> TriggerFiring:
		"""Record a §11.1 trigger. The scope's own evidence is required, not inferred.

		The three scopes need different things to be true and the model refuses a firing that does not
		carry them: a county trigger without a county, an individual trigger without a subject. That
		is the check the global gate could not make, because it had nowhere to put the county or the
		person.
		"""
		if firing.scope is TriggerScope.county:
			assert firing.county, 'a county trigger must name the county'
			assert firing.subject_ref is None, 'a county trigger is about a county, not a person'
		if firing.scope is TriggerScope.individual:
			assert firing.subject_ref, 'an individual trigger must name the person'
		if firing.scope is TriggerScope.national_or_county:
			assert firing.subject_ref is None, 'a declared event is not about one person'
		self._firings.append(firing)
		self._log_info('activation trigger fired', number=firing.trigger_number, scope=firing.scope.value)
		return firing

	def firings(self) -> list[TriggerFiring]:
		return list(self._firings)

	# --- state -------------------------------------------------------------------------------

	def state(self, county: str | None = None, subject_ref: str | None = None) -> ActivationState:
		"""What §11.1 holds for one request, read off the recorded firings.

		`pheoc_event_active` is the registry's three-key gate rather than a fourth copy of it: §11.1
		row 1's trigger *is* the PHEOC declaration, and the keys are the conditions §11.1's own
		Appendix-D question 3 leaves open about who holds them.
		"""
		declared = [f for f in self._firings if f.scope is TriggerScope.national_or_county]
		county_cases = tuple(sorted({f.county for f in self._firings
		                             if f.scope is TriggerScope.county and f.county}))
		# An individual firing is recorded under the trigger that produced it, so the three facts
		# stay distinct — a person in a risk zone is not a person identified as a contact, and §11.1
		# gives them different features (row 4 vs row 3).
		by_number: dict[int, list[str]] = {}
		for f in self._firings:
			if f.scope is TriggerScope.individual and f.subject_ref:
				by_number.setdefault(f.trigger_number, []).append(f.subject_ref)
		return ActivationState(
			pheoc_event_active=self._registry.tier4_active() and bool(declared),
			counties_with_cases=county_cases,
			identified_contacts=tuple(sorted(set(by_number.get(3, [])))),
			subjects_in_risk_zone=tuple(sorted(set(by_number.get(4, [])))),
			subjects_requesting=tuple(sorted(set(by_number.get(5, [])))),
			county=county, subject_ref=subject_ref,
		)

	# --- resolution --------------------------------------------------------------------------

	def feature_available(self, feature_id: str, state: ActivationState) -> bool:
		"""Whether a feature may be used, given what §11.1 holds.

		Three answers, and the middle one is the model: a feature below Tier 4 is always available
		(§7.3); a Tier-4 feature is available when *any* of its §11.1 triggers has fired for this
		state; and a Tier-4 feature with no trigger at all is available only under a declared event,
		because §11's opening sentence makes Tier 4 dormant until PHEOC triggers it and the table
		simply does not enumerate the remaining eleven. Refusing those eleven outright would be
		stricter than the section, and `unassigned()` is where the gap is reported instead.
		"""
		spec = self._registry.get(feature_id)
		if spec.tier is not Tier.tier4:
			return True
		rows = triggers_for(feature_id)
		if not rows:
			return self._registry.tier4_active()
		return any(state.scope_met(t) for t in rows)

	def triggers_firing(self, feature_id: str, state: ActivationState) -> list[ActivationTrigger]:
		"""Which rows are firing for this feature and state. Named rather than a boolean, so a refusal
		can say what would have to happen — "no confirmed case in your county" rather than "denied"."""
		return [t for t in triggers_for(feature_id) if state.scope_met(t)]

	def reason(self, feature_id: str, state: ActivationState) -> str:
		"""Why a Tier-4 feature is or is not available, in the section's own terms and without a code.

		§11.1's rows are the only thing that turns a Tier-4 feature on, so the refusal names the one
		that would: a person told "not available" with no way to find out what would change it has a
		switch that refuses them, which is what §11.1 exists to prevent.
		"""
		if self.feature_available(feature_id, state):
			return 'This is available for you now.'
		rows = triggers_for(feature_id)
		if not rows:
			return 'This turns on when the outbreak response is activated.'
		parts = []
		for t in rows:
			if t.scope is TriggerScope.national_or_county:
				parts.append('the outbreak response is activated')
			elif t.scope is TriggerScope.county:
				parts.append('a case is confirmed in your county')
			else:
				parts.append({
					'is_contact': 'you are identified as a contact',
					'in_risk_zone': 'you enter a high-risk zone',
					'requested': 'you ask for it',
				}[t.condition.value if t.condition else 'requested'])
		return 'This turns on when ' + ', or '.join(parts) + '.'

	# --- deactivation (§11.1's closing clause) -----------------------------------------------

	def deactivate(self, at_iso: str, closed_by: str) -> Deactivation:
		"""Close the event: start the clocks and name who is told.

		"Automatic when PHEOC closes the event. Users are notified. Data retention clocks begin." The
		three sentences are the three fields. The subjects notified are read off the individual
		firings — the people a trigger actually reached — and the counties off the county firings,
		because notifying a county nobody activated in is a message about an event that did not
		concern them. Closing with nothing fired is allowed and reported as an empty set: it is the
		honest answer, and refusing it would block a close on a deployment whose firings were recorded
		before this service existed.
		"""
		closed_on = _date(at_iso)
		clocks = tuple(
			RetentionClock(
				data_type=data_type,
				retention_days=int(RETENTION_TABLE[data_type]['days']),  # type: ignore[arg-type]
				deletion_trigger=str(RETENTION_TABLE[data_type]['trigger']),
				started_at_iso=at_iso,
				expires_at_iso=(closed_on + timedelta(days=int(RETENTION_TABLE[data_type]['days']))).isoformat(),  # type: ignore[arg-type]
			)
			for data_type in TIER4_DATA_TYPES
		)
		subjects = tuple(sorted({f.subject_ref for f in self._firings
		                         if f.scope is TriggerScope.individual and f.subject_ref}))
		counties = tuple(sorted({f.county for f in self._firings
		                         if f.scope is TriggerScope.county and f.county}))
		sentence = (
			f'The event is closed. {len(subjects)} people are told, and '
			f'{len(clocks)} retention clocks have started.'
			if subjects else
			f'The event is closed. No one was reached by an individual trigger, and '
			f'{len(clocks)} retention clocks have started.'
		)
		self._firings.clear()
		self._log_warn('tier4 deactivated', at=at_iso, subjects=len(subjects), counties=len(counties))
		return Deactivation(
			at_iso=at_iso, closed_by=closed_by, clocks=clocks,
			subjects_notified=subjects, counties_notified=counties, sentence=sentence,
		)
