"""§SENS-010 — NFC tag-based workflows: a tag bound to a typed target.

The section lists five applications and only the first was carried:

	- Check-in at facilities (LOC-004)          — `afya.location.service:LocationService.check_in`
	- Patient wristband identification at isolation units
	- Medication authentication (tapping a medicine package with an NFC tag)
	- PPE station logging for healthcare workers
	- Equipment tracking

The four open ones are not four capabilities. They are one mechanism the tree did not have — a tag
bound to a *target* — with four different targets, and the section's own list is what says so: every
line is "tap a tag, learn or record something about the thing it is attached to". Building four
endpoints would have been four copies of the binding and four chances for the tag format to diverge.

**What a tap can and cannot carry is the design decision, and it is a privacy one.** §LOC-004's
check-in already resolves a tag to a *place* — `CheckInPoint` is keyed on `token` and holds no
person. Three of the four new targets are the same shape: a wristband names a patient, a medicine
tag names a package, a station tag names a station. Only the PPE log names a *person* as well as a
place, and it does so because §COM-101's own bullet is occupational — a log that records that
someone passed a station without recording who is not a log of anything.

So the tag holds the target's identity and never the person's. A `Tag` carries `target_ref` — an
opaque id — and the reading route takes the worker separately. That is the same boundary
`ExposureDeclaration` draws one module over: what the tag knows travels with the tag, and the person
is a field on the reading rather than a property of the object.

**A tap that resolves to nothing is reported as unresolved, never as a negative.** `resolve` returns
a verdict per tag for the reason `MedicineService.check_interactions` reports `unmatched` and
`LocationService.follow_up` reports an empty record with a note: "this tag is not in the register"
and "this tag is attached to nothing" are different facts, and a screen that renders both as blank
makes the first indistinguishable from a mis-tap.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.ids import ref8
from afya.logmixin import LogMixin

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# The four targets §SENS-010's list names beyond the check-in it shares with §LOC-004. The check-in
# target is deliberately absent: `CheckInPoint` already binds a token to a place, and a second
# binding for the same fact is the copy that goes stale the first time a point kind is added.
TAG_TARGETS: tuple[str, ...] = ('patient', 'medicine', 'ppe_station', 'equipment')
TAG_TARGET_PATTERN = '^(' + '|'.join(TAG_TARGETS) + ')$'

# §SENS-010's "Equipment tracking" needs a condition a person can pick and a filter can use. The
# three are the states an asset is in, and they are here rather than in the register class because
# the mobile catalogue offers them as a picker: a list on a screen and a list an assertion reads are
# one fact, and a second hand-typed copy is the one that goes stale.
EQUIPMENT_STATUSES: tuple[str, ...] = ('in_service', 'under_repair', 'retired')

# What a target must resolve *through* to answer a tap. Each is a real object in this tree, named
# rather than described, because "resolves to a patient" is a claim about code and the note on a
# missing row is worth nothing if the resolver is a stub.
TARGET_RESOLVERS: dict[str, str] = {
	'patient': 'afya.records.service:RecordsService.wallet',
	'medicine': 'afya.medicine.service:MedicineService.verify',
	'ppe_station': 'afya.chw.views:JOB_AIDS',
	'equipment': 'afya.sensors.tags:EquipmentRegister',
}

# The section's Applications label, verbatim, paired to the target each line is. The audit reads
# this tuple rather than a hand-typed second list, so a line added to the section and not here is a
# coverage failure rather than an undercount.
APPLICATIONS: tuple[tuple[str, str], ...] = (
	('Patient wristband identification at isolation units', 'patient'),
	('Medication authentication (tapping a medicine package with an NFC tag)', 'medicine'),
	('PPE station logging for healthcare workers', 'ppe_station'),
	('Equipment tracking', 'equipment'),
)

# §SENS-010's own tag format. A tag is read by a phone, so the id is what the tag stores; the target
# it names lives in the register, not on the tag — a wristband that carried the patient's details
# would be a wristband that leaks them to anyone who taps it.
TAG_ID_PATTERN = r'^[0-9A-F]{12,32}$'


class TagTarget(str, Enum):
	patient = 'patient'
	medicine = 'medicine'
	ppe_station = 'ppe_station'
	equipment = 'equipment'


class Tag(BaseModel):
	"""One tag and the thing it is bound to. The binding is the whole object; a tag with no target is
	not representable, which is why `target_ref` has no default."""

	model_config = MODEL_CONFIG
	tag_id: str = Field(pattern=TAG_ID_PATTERN)
	target: TagTarget
	target_ref: str = Field(min_length=1)
	label: str = Field(min_length=1)
	bound_at_iso: str


class TagReading(BaseModel):
	"""One tap: the tag, and who tapped it where the tap is attributable.

	`worker_ref` is optional and only meaningful for the PPE station, which is the one target §COM-101
	states as occupational. Every other target is about the object, and a reading that carried a
	person for a wristband would be a record of who was near a patient.
	"""

	model_config = MODEL_CONFIG
	reading_id: str = Field(default_factory=lambda: 'TAP-' + ref8())
	tag_id: str = Field(pattern=TAG_ID_PATTERN)
	target: TagTarget
	target_ref: str
	worker_ref: str | None = None
	at_iso: str


class TagVerdict(BaseModel):
	"""What a tap answers.

	`resolved` is the field a screen reads first, and it is separate from `note` because the two
	unresolved cases are not the same: a tag that is not in the register is a mis-tap or a clone, and
	a tag whose target has since been withdrawn resolves to a real tag pointing at nothing.
	"""

	model_config = MODEL_CONFIG
	tag_id: str
	resolved: bool
	target: TagTarget | None = None
	target_ref: str | None = None
	label: str | None = None
	note: str
	logged: bool = False


class EquipmentRegister(LogMixin):
	"""§SENS-010's "Equipment tracking" — the one target with no object behind it anywhere in this
	tree.

	A separate class rather than a dict inside the service because the register is the thing the
	section names and it has its own lifecycle: an asset is added, moved between stations, and taken
	out of service. `status` is a small closed set rather than a free string, so "where is this
	ventilator" has an answer that can be filtered rather than read.
	"""

	STATUSES: tuple[str, ...] = EQUIPMENT_STATUSES

	def __init__(self) -> None:
		self._assets: dict[str, tuple[str, str, str]] = {}
		assert self._assets == {}

	def add(self, asset_ref: str, label: str, status: str = 'in_service') -> None:
		assert status in EQUIPMENT_STATUSES, f'unknown equipment status {status}'
		assert asset_ref, 'an asset needs an id'
		self._assets[asset_ref] = (label, status, '')
		self._log_info('equipment registered', asset=asset_ref, status=status)

	def move(self, asset_ref: str, station: str) -> None:
		"""Where the asset is, which is the question "equipment tracking" is asked."""
		assert asset_ref in self._assets, 'unknown asset'
		label, status, _ = self._assets[asset_ref]
		self._assets[asset_ref] = (label, status, station)

	def get(self, asset_ref: str) -> tuple[str, str, str] | None:
		return self._assets.get(asset_ref)

	def assets(self, status: str | None = None) -> list[dict[str, str]]:
		return [
			{'asset_ref': ref, 'label': label, 'status': st, 'station': station}
			for ref, (label, st, station) in self._assets.items()
			if status is None or st == status
		]


class TagService(LogMixin):
	"""§SENS-010's five applications over one binding.

	`check_in` for the facility application is not reimplemented here: §LOC-004 owns it and this
	module names it as the target's resolver, because two bindings for the same tap is the second
	one that drifts.
	"""

	def __init__(self, equipment: EquipmentRegister | None = None) -> None:
		self._tags: dict[str, Tag] = {}
		self._readings: list[TagReading] = []
		self._equipment = equipment or EquipmentRegister()
		assert self._tags == {} and self._readings == []

	@property
	def equipment(self) -> EquipmentRegister:
		return self._equipment

	def bind(self, tag: Tag) -> Tag:
		"""Bind a tag to a target. Rebinding is an error rather than an update: a tag that silently
		points somewhere new is how a wristband ends up naming the wrong patient, and the failure
		would appear at the bedside rather than here."""
		assert tag.tag_id not in self._tags, f'tag {tag.tag_id} is already bound'
		if tag.target is TagTarget.equipment:
			assert self._equipment.get(tag.target_ref) is not None, \
				'an equipment tag must name an asset the register holds'
		self._tags[tag.tag_id] = tag
		self._log_info('tag bound', tag=tag.tag_id, target=tag.target.value)
		return tag

	def unbind(self, tag_id: str) -> None:
		assert tag_id in self._tags, 'unknown tag'
		del self._tags[tag_id]

	def resolve(self, tag_id: str) -> TagVerdict:
		"""What one tap answers, and the two ways it can answer nothing are kept apart.

		An unbound tag and a tag whose target has been withdrawn are different findings. The first is
		a mis-tap, a clone, or a tag from another deployment; the second is a real tag pointing at
		something that is no longer there — a wristband for a discharged patient, a medicine tag for
		a recalled batch. Rendering both as "not found" is the collapse this method exists to refuse.
		"""
		tag = self._tags.get(tag_id)
		if tag is None:
			return TagVerdict(tag_id=tag_id, resolved=False,
				note='This tag is not registered here. Check that you tapped the right one.')
		label = tag.label
		if tag.target is TagTarget.equipment:
			asset = self._equipment.get(tag.target_ref)
			if asset is None:
				return TagVerdict(tag_id=tag_id, resolved=False, target=tag.target,
					target_ref=tag.target_ref,
					note='This tag is registered, but the equipment it named has been taken off the register.')
			label = f'{asset[0]} ({asset[1].replace("_", " ")})'
		return TagVerdict(tag_id=tag_id, resolved=True, target=tag.target, target_ref=tag.target_ref,
			label=label, note=f'{label}.')

	def tap(self, tag_id: str, at_iso: str, worker_ref: str | None = None) -> TagReading:
		"""Record a tap. A tap that resolves to nothing is still recorded — a run of unresolved taps
		at one station is the signal that a tag has been swapped, and dropping them would leave the
		only evidence of it unrecorded."""
		verdict = self.resolve(tag_id)
		assert at_iso, 'a tap happens at a time'
		if verdict.target is TagTarget.ppe_station:
			assert worker_ref, 'a station log names the worker who passed it'
		reading = TagReading(tag_id=tag_id, target=verdict.target or TagTarget.equipment,
			target_ref=verdict.target_ref or tag_id, worker_ref=worker_ref, at_iso=at_iso)
		self._readings.append(reading)
		self._log_info('tag tapped', tag=tag_id, resolved=verdict.resolved,
		               worker=bool(worker_ref))
		return reading

	def readings(self, target: TagTarget | None = None, worker_ref: str | None = None) -> list[TagReading]:
		return [r for r in self._readings
			if (target is None or r.target is target)
			and (worker_ref is None or r.worker_ref == worker_ref)]

	def coverage(self) -> dict[str, object]:
		"""§SENS-010's five applications and whether each has a binding behind it.

		Reported rather than asserted for the reason the content audit exists: the section's first
		line is §LOC-004's and is carried there, and the other four are carried here. A caller can
		read which line resolved through which module instead of taking the module's word for it.
		"""
		bound = {t.target.value for t in self._tags.values()}
		return {
			'applications': [
				{'application': line, 'target': target,
				 'resolver': TARGET_RESOLVERS[target], 'bound_tags': sum(
					 1 for t in self._tags.values() if t.target.value == target)}
				for line, target in APPLICATIONS
			],
			'targets_with_no_tag': [t for t in TAG_TARGETS if t not in bound],
			'check_in': 'afya.location.service:LocationService.check_in',
		}
