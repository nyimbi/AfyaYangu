"""§4's target users as models — seven primary personas, the secondary ones, and §4.3's priorities.

§4 is the section that says who the product is for, and it was the only section in the spec with no
representation in the code at all. Every other section had at least a table; this one had prose a
reader could quote and nothing a check could stand on. The consequence is the shape the repo keeps
finding: §22.7 can report the share of users who are female, §22.8 can demand the equity metrics
disaggregated by gender, geography, age and device, and nothing anywhere says who those people were
supposed to be — so no number has a target population to be measured against.

Two rules govern what is modelled here.

**The spec's own words, not a summary of them.** `summary`, `needs`, `friction`, `entry_point` and
§4.3's `segment`/`rationale` are transcribed from §4 verbatim. A persona re-written in a
developer's words is a persona nobody can check against the section, and the transcription is what
lets the test fail when the section moves.

**Nothing is inferred that the section does not say.** A persona's `role` is None where §4 does not
name a job §17.4 has a row for — only Mama Zawadi (a CHW) and Dr. Kimani (a clinician) do. A
`languages` list is empty where the section names no language, rather than filled from the county a
persona lives in: Busia is a Luhya county and Garissa a Somali one, but §4 says neither, and a
language attributed by geography is a claim the section does not make.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.privacy.views import RBACRole

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class Priority(str, Enum):
	"""§4.3's four launch priorities. The enum's order is the section's, so a caller can sort by
	`order` rather than by the string, which would put `p10` before `p2`."""

	p0 = 'p0'
	p1 = 'p1'
	p2 = 'p2'
	p3 = 'p3'

	@property
	def order(self) -> int:
		return list(Priority).index(self)


class DeviceClass(str, Enum):
	"""What the persona holds, in the classes §4's own descriptions distinguish.

	The distinction that matters is `feature_phone`: §4.3's P3 rationale is "Reached primarily via
	non-app channels", and a persona with no smartphone is the one the native client can never
	reach — the constraint the whole channel architecture is built around (§3.3 principle 1).
	`android_go` is separate because §22.7 sets a target for it by name.
	"""

	android_go = 'android_go'
	android = 'android'
	smartphone = 'smartphone'
	iphone = 'iphone'
	feature_phone = 'feature_phone'
	professional = 'professional'

	@property
	def runs_an_app(self) -> bool:
		"""Whether this device can install the native client at all. §5.2 gives the app "Moderate"
		reach and puts four channels above it; a feature phone is the row where that stops being a
		preference and becomes the only option."""
		return self is not DeviceClass.feature_phone


class Persona(BaseModel):
	"""One §4.1 persona.

	`entry_channels` is the §5.2 channel slugs the entry point names and `entry_unmapped` whatever is
	left of that sentence once they are taken out. The split is deliberate: "SMS alerts, USSD menus,
	community radio, CHW visit" is four channels and maps cleanly, while "ANC clinic recommendation"
	is a route into the product §5.2 has no channel for — and a model that dropped the remainder
	would report every persona as fully reachable.
	"""

	model_config = MODEL_CONFIG
	key: str = Field(pattern=r'^[a-g]$')
	name: str = Field(min_length=1)
	age: int = Field(ge=0, le=120)
	location: str = Field(min_length=1)
	summary: str = Field(min_length=1)
	needs: list[str] = Field(min_length=1)
	# Empty for Persona G: §4.1 gives Amina Needs and an Entry point and no Friction line at all.
	# The alternative was to write one — every persona obviously has friction — but a friction this
	# module invented would be indistinguishable from the six §4.1 states, and the empty list is
	# the section's own answer.
	friction: list[str] = []
	entry_point: str = Field(min_length=1)
	# Derived: the §5.2 channels the entry point names, and the rest of the sentence.
	entry_channels: list[str]
	entry_unmapped: list[str]
	# Read off the section's own text; empty where §4 names no language.
	languages: list[str]
	device: DeviceClass
	role: RBACRole | None = None
	# §4.3 segment keys this persona belongs to.
	segments: list[str] = []


class SecondaryPersona(BaseModel):
	"""One §4.2 bullet. The section gives these no Needs, Friction or Entry point — they are named
	and nothing more — so `role` is the only thing added, and it is None for the five §17.4 has no
	row for.

	§4.2 and §CHAN-5 are two different lists and are not merged. §4.2 names people who *read* the
	product; §CHAN-5 names people who *distribute* it. Pharmacy staff, faith leaders and school
	administrators appear on both, and collapsing the two would make a distributor look like a user.
	"""

	model_config = MODEL_CONFIG
	name: str = Field(min_length=1)
	role: RBACRole | None = None


class Segment(BaseModel):
	"""One §4.3 row: a priority, the segment, and the rationale the section gives for the ordering.

	`persona_keys` is derived — which §4.1 personas the segment names. It is empty for two rows, and
	that emptiness is a finding the service reports rather than a gap the model fills: §4.3 puts
	chronically ill adults at P1 with no persona behind them, and the honest reading is that the
	priority rests on a population §4.1 never describes.
	"""

	model_config = MODEL_CONFIG
	key: str = Field(min_length=1)
	priority: Priority
	segment: str = Field(min_length=1)
	rationale: str = Field(min_length=1)
	persona_keys: list[str] = []


class PersonaCoverage(BaseModel):
	"""What crossing §4 against the rest of the codebase finds, as one answer.

	Four findings, all the same shape — the section names something the product does not carry:

	* `unserved_languages` are languages §ACC-002 puts at tier 1 that the string tables cannot speak.
	  Persona F is the sharp case: Grace is a Dholuo speaker on a feature phone, reached by "SMS
	  alerts, USSD menus, community radio" — and §CHAN-2's own menu ends "Language: English /
	  Kiswahili / Dholuo / ...". The product cannot answer her in her language on any of the four
	  channels the section routes her through.
	* `unmapped_entry_points` are entry points §5.2's seven channels do not cover.
	* `segments_without_a_persona` and `secondary_without_a_role` are §4 rows nothing corresponds to.
	"""

	model_config = MODEL_CONFIG
	personas: int
	secondary: int
	segments: int
	unserved_languages: list[str]
	unserved_personas: list[str]
	unmapped_entry_points: list[str]
	segments_without_a_persona: list[str]
	secondary_without_a_role: list[str]
	note: str
