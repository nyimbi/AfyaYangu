"""§11.1's activation model — five triggers, three scopes, and who each one reaches.

§11 opens with the design constraint the whole Tier-4 half rests on: "Dormant until triggered by
PHEOC. **Activates automatically for users in affected areas.** Requires no separate adoption effort
because Tiers 1–3 already earned the install." §11.1 then gives the model as a five-row table — each
row a trigger, a scope, and the features it turns on — and closes with a deactivation clause.

None of that existed. What existed was `Tier4Activation`, a single boolean over three keys, and
`FeatureRegistry.available()` reading it. One switch for five triggers and three scopes, which means
the model was not the section's in either direction:

* **The individual triggers could not fire.** §11.1 rows 3–5 activate `MON-009`, `LOC-001` and
  `LOC-002` for *one person* — "User identified as a contact", "User enters a high-risk zone", "User
  requests activation". Under one global gate, a person identified as a contact could not get their
  21-day diary until PHEOC declared a national event. §11's own constraint says the opposite:
  activation is automatic for the affected user, and it is the mechanism by which the product reaches
  people without a separate adoption effort. The person who most needs the diary is the one contact
  in a county with no declared event.

* **The county trigger could not fire either.** Row 2 is "Confirmed case in a county → County →
  LOC-001, ALT-004". A confirmed case in Busia is not a national declaration, and §11.1 is explicit
  that the scope is the county.

* **Two of the seven named features are not Tier 4 at all.** §11.1 rows 2 and 4 activate `LOC-001`,
  and §7.3's tier table puts `LOC-001` in Tier 1 — an always-on feature, per §7.3's own "cross-cutting
  and Tier 1 are always available". The divergence is recorded below rather than resolved by picking
  one: §7.3 is the tier model and §11.1 is the activation model, and a feature cannot be both always-on
  and dormant-behind-a-gate. The code follows §7.3, and `DIVERGENCES` says so where a reader will find
  it.

* **Twelve Tier-4 features have no trigger.** §11.1 names seven features and the registry has
  eighteen in Tier 4; six of the seven are Tier 4 (`LOC-001` is the seventh and is Tier 1, below).
  The remaining twelve (`TRI-003`, `SENS-001/002/004/008`, `LOC-004/005`, `COM-102/103/104`,
  `AI-002/003`) are dormant by §7.3's tier model and §11's opening sentence, and the table simply
  does not enumerate them. `unassigned()` names them, because a feature that is dormant with no
  trigger that turns it on is a capability nobody can reach — the §11.1 defect this module exists to
  surface, and the one an enumeration that only reads the table can never see.

The deactivation clause is modelled as what it says: "Automatic when PHEOC closes the event. Users
are notified. Data retention clocks begin." The clocks are computed from §17's retention table rather
than from a number written here, and the subjects notified are read off the firings — the people a
trigger reached, which is the set the notification is owed to.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.ids import uuid7str
from afya.retention.views import RETENTION_TABLE

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class TriggerScope(str, Enum):
	"""§11.1's Scope column. Three values, and the third is the one the global gate collapsed."""
	national_or_county = 'national_or_county'
	county = 'county'
	individual = 'individual'


class SubjectCondition(str, Enum):
	"""Which fact about a person makes an individual trigger fire. §11.1's three individual rows each
	name a different one — "identified as a contact", "enters a high-risk zone", "requests
	activation" — so a single `is_individual` flag would make three triggers one, which is the same
	collapse the global gate performed one level up."""
	is_contact = 'is_contact'
	in_risk_zone = 'in_risk_zone'
	requested = 'requested'


class ActivationTrigger(BaseModel):
	"""One §11.1 row.

	`scope_label` is the Scope cell verbatim ("National or county", "County", "Individual") and
	`features_label` is the Features cell verbatim, because row 2's cell is `LOC-001 (dynamic
	geofences)` and the parenthetical is the section saying *what* that activation turns on — the same
	reasoning §5.2's cost cells keep their parenthetical. `features` is the cell parsed to ids.
	"""
	model_config = MODEL_CONFIG
	number: int = Field(ge=1, le=5)
	trigger: str = Field(min_length=1)
	scope: TriggerScope
	scope_label: str = Field(min_length=1)
	features: tuple[str, ...]
	features_label: str = Field(min_length=1)
	# The fact that fires an individual trigger, or None for the two that are not about one person.
	condition: SubjectCondition | None = None


TRIGGERS: tuple[ActivationTrigger, ...] = (
	ActivationTrigger(
		number=1, trigger='PHEOC declares an outbreak event', scope=TriggerScope.national_or_county,
		scope_label='National or county', features=('ALT-004', 'LOC-002', 'LOC-003', 'COM-101', 'AI-001'),
		features_label='ALT-004, LOC-002, LOC-003, COM-101, AI-001',
	),
	ActivationTrigger(
		number=2, trigger='Confirmed case in a county', scope=TriggerScope.county,
		scope_label='County', features=('LOC-001', 'ALT-004'),
		features_label='LOC-001 (dynamic geofences), ALT-004',
	),
	ActivationTrigger(
		number=3, trigger='User identified as a contact', scope=TriggerScope.individual,
		scope_label='Individual', features=('MON-009',), features_label='MON-009',
		condition=SubjectCondition.is_contact,
	),
	ActivationTrigger(
		number=4, trigger='User enters a high-risk zone', scope=TriggerScope.individual,
		scope_label='Individual', features=('LOC-001', 'ALT-004'), features_label='LOC-001, ALT-004',
		condition=SubjectCondition.in_risk_zone,
	),
	ActivationTrigger(
		number=5, trigger='User requests activation', scope=TriggerScope.individual,
		scope_label='Individual', features=('MON-009', 'LOC-002'), features_label='MON-009, LOC-002',
		condition=SubjectCondition.requested,
	),
)

TRIGGER: dict[int, ActivationTrigger] = {t.number: t for t in TRIGGERS}
assert tuple(t.number for t in TRIGGERS) == (1, 2, 3, 4, 5), '§11.1 has five rows, in order'
assert all(t.condition is not None for t in TRIGGERS if t.scope is TriggerScope.individual), \
	'every individual trigger must name the fact that fires it'
assert all(t.condition is None for t in TRIGGERS if t.scope is not TriggerScope.individual), \
	'a non-individual trigger has no per-person condition'

# Every feature §11.1's table names, in first-mention order.
TRIGGERED_FEATURES: tuple[str, ...] = tuple(
	dict.fromkeys(f for t in TRIGGERS for f in t.features)
)

# The features §11.1 activates that §7.3 does not put in Tier 4. Recorded, not resolved: §7.3 is the
# tier model and §11.1 is the activation model, and a feature cannot be both always-on and dormant
# behind a gate. The code follows §7.3 — LOC-001 is always available — and this says where the two
# sections disagree so the next reader does not have to find it again.
DIVERGENCES: dict[str, str] = {
	'LOC-001': '§11.1 rows 2 and 4 activate it; §7.3 lists it under Tier 1. Followed §7.3: an '
	           'always-on feature cannot also be dormant behind the activation gate.',
}


class ActivationState(BaseModel):
	"""What is true right now, for one request.

	`pheoc_event_active` is the §11.1 row-1 trigger and is read from the three-key gate
	(`Tier4Activation`) rather than held separately — a declaration and the DPIA/flag/authorisation
	that permit it are one event, and a second copy of "is the outbreak on" is the drift this repo
	keeps finding. The rest is the recorded context: which counties have a confirmed case, and for the
	person making the request, which of the three individual facts hold.

	`county` and `subject_ref` are the request's own, and they are what make the individual and county
	scopes mean anything — a state with no county cannot satisfy a county trigger, and one with no
	subject cannot satisfy an individual one.
	"""
	model_config = MODEL_CONFIG
	pheoc_event_active: bool = False
	counties_with_cases: tuple[str, ...] = ()
	identified_contacts: tuple[str, ...] = ()
	subjects_in_risk_zone: tuple[str, ...] = ()
	subjects_requesting: tuple[str, ...] = ()
	county: str | None = None
	subject_ref: str | None = None

	def condition_met(self, condition: SubjectCondition) -> bool:
		"""Whether the person making the request has the fact an individual trigger names."""
		if self.subject_ref is None:
			return False
		held = {
			SubjectCondition.is_contact: self.identified_contacts,
			SubjectCondition.in_risk_zone: self.subjects_in_risk_zone,
			SubjectCondition.requested: self.subjects_requesting,
		}[condition]
		return self.subject_ref in held

	def scope_met(self, trigger: ActivationTrigger) -> bool:
		"""Whether a trigger's own scope condition holds — the first of the two things a Tier-4
		feature needs, the second being the PHEOC dependency below."""
		if trigger.scope is TriggerScope.national_or_county:
			return self.pheoc_event_active
		if trigger.scope is TriggerScope.county:
			return self.county is not None and self.county in self.counties_with_cases
		assert trigger.condition is not None, 'an individual trigger must name its condition'
		return self.condition_met(trigger.condition)


def triggers_for(feature_id: str) -> tuple[ActivationTrigger, ...]:
	"""Every §11.1 row that activates a feature. Two rows can, and do: `MON-009` is rows 3 and 5,
	`ALT-004` is rows 1, 2 and 4, `LOC-002` is rows 1 and 5. A feature with two triggers is reachable
	by either, which is why `feature_available` is an `any` and not a lookup."""
	return tuple(t for t in TRIGGERS if feature_id in t.features)


def is_triggered(feature_id: str) -> bool:
	return any(feature_id in t.features for t in TRIGGERS)


def unassigned(tier4_ids: frozenset[str]) -> tuple[str, ...]:
	"""The Tier-4 features §11.1's table does not name.

	They are dormant by §7.3's tier model and §11's opening sentence, and the table simply does not
	enumerate them — so they are not a defect in themselves. Naming them is the point: a feature that
	is dormant with no trigger that turns it on is a capability nobody can reach, and only a check
	that reads the *registry* against the table can see it. A check that read the table alone would
	report perfect coverage forever.

	Twelve of the registry's eighteen Tier-4 features land here, not eleven: `LOC-001` is §11.1's
	seventh named feature and §7.3 puts it in Tier 1, so it is triggered and not Tier 4 and cannot be
	among the unassigned. Counting the table's seven against the registry's eighteen gives eleven, and
	the difference is exactly the divergence recorded above — an arithmetic slip that would have made
	this docstring describe a set the function does not return.
	"""
	return tuple(sorted(f for f in tier4_ids if not is_triggered(f)))


class TriggerFiring(BaseModel):
	"""One recorded firing of a §11.1 trigger.

	The evidence and the actor are required because a trigger is a determination somebody made —
	"confirmed case in a county" is a laboratory or clinical finding, "identified as a contact" is a
	tracing decision — and a firing recorded without either is indistinguishable from one recorded by
	accident. `fired_at_iso` is the instant, not a boolean, because the deactivation clause's clocks
	are measured from when the event closed and an activation with no start has no clock.
	"""
	model_config = MODEL_CONFIG
	firing_id: str = Field(default_factory=uuid7str)
	trigger_number: int = Field(ge=1, le=5)
	scope: TriggerScope
	county: str | None = None
	subject_ref: str | None = None
	evidence: str = Field(min_length=1)
	fired_by: str = Field(min_length=1)
	fired_at_iso: str = Field(min_length=10)


class RetentionClock(BaseModel):
	"""One retention window that begins when the event closes (§11.1's deactivation clause).

	`retention_days` is read from §17's table rather than written here, and `deletion_trigger` with
	it: §11.1 says the clocks begin, not how long they run, and a second copy of "21 days" is the
	drift §5.2's APK budget and §22.5 already demonstrated between them.
	"""
	model_config = MODEL_CONFIG
	data_type: str
	retention_days: int = Field(ge=1)
	deletion_trigger: str
	started_at_iso: str
	expires_at_iso: str


class Deactivation(BaseModel):
	"""§11.1's closing clause as a report: what closed, who is told, and which clocks started."""
	model_config = MODEL_CONFIG
	at_iso: str = Field(min_length=10)
	closed_by: str = Field(min_length=1)
	clocks: tuple[RetentionClock, ...]
	subjects_notified: tuple[str, ...]
	counties_notified: tuple[str, ...]
	sentence: str = Field(min_length=1)


# The data types a Tier-4 event produces, and therefore the clocks §11.1's deactivation starts. Read
# as the intersection of §17's table with the Tier-4 surfaces: proximity and location history are
# LOC-002/003, the contact list is MON-009/COM-103. Types outside the retention table cannot acquire
# a clock — `policy_for` refuses an unknown type, which is the §17 rule this list inherits.
TIER4_DATA_TYPES: tuple[str, ...] = ('location_history', 'proximity_tokens', 'contact_lists')
assert all(t in RETENTION_TABLE for t in TIER4_DATA_TYPES), \
	'every Tier-4 data type must have a §17 retention window, or its clock cannot be computed'
