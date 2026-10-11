"""§CHAN-5's intermediary programme — the seven kinds, the codes, and what makes a referral verified.

§CHAN-5 is the section §20.2 lever 4 rests on: "CHWs, chemists, faith leaders drive adoption, not
app stores", answered by "Structured intermediary programme (CHAN-5)". Its own rationale is the
mechanism — "These people, not app stores, drive adoption in Kenya. Trust transfers through
relationships." Nothing carried it. §4.1's Persona B arrives through "SOS feature recommended by his
SACCO chairman", §CHAN-5 names the SACCO chairmen as a target intermediary and says each gets a code,
and no code existed anywhere in the tree; the only thing named `referral` was a CHW activity label.

What the section states, and what each part becomes:

**Seven kinds, verbatim.** CHWs and Community Health Promoters, pharmacy and chemist staff, faith
leaders, boda boda SACCO chairmen, market association leaders, teachers and school health patrons,
chama leaders. The list is transcribed in the section's order, so a revision fails the test.

**Referral codes.** "each intermediary gets a code for attribution" — the code is the attribution
mechanism, so it is issued per intermediary and resolves back to exactly one. A code that resolved to
two people attributes a referral to nobody.

**Airtime or data bundles for verified referrals.** The word doing the work is *verified*. §18.8's
telco table has "Airtime incentives | App → Telco | Disbursement requests | Weekly", so the payment
is real; what the section does not say is who verifies and against what. Two things are checkable
from the code and neither is assumed: the referral must name a person who actually arrived (a code
alone is an intermediary's claim about themselves), and the incentive must not already have been paid
for that referral. The second is the one that matters — a weekly disbursement run that can pay the
same referral twice is a budget drain reachable by replaying a request, and it is the failure mode a
programme with real money in it actually has.

**What is not invented.** The section gives no incentive *amount*, so none is written here: the
amount arrives from the caller and §18.8's existing bound (500 KES) still applies at the telco
client. The section gives no code format, so the format is a property of this module rather than a
claim about the spec. And the section does not say an intermediary is a *user* of the product — §4.2
names seven audiences who read it and §CHAN-5 names seven who distribute it, and pharmacy staff,
faith leaders and teachers appear on both lists. They are not merged: an intermediary has a code, not
a session.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class IntermediaryKind(str, Enum):
	"""§CHAN-5's seven target intermediaries, in the section's order. The slug is this module's; the
	`name` is the section's own words, which is what the test compares."""

	chw = 'chw'
	pharmacy = 'pharmacy'
	faith_leader = 'faith_leader'
	boda_sacco = 'boda_sacco'
	market_leader = 'market_leader'
	teacher = 'teacher'
	chama_leader = 'chama_leader'

	@property
	def name(self) -> str:
		return _KIND_NAMES[self]


# §CHAN-5's "Target intermediaries" bullets, verbatim and in order. `boda_sacco` is the one §4.1's
# Persona B arrives through — his entry point is the SACCO chairman's recommendation — so the kind
# that carries a named persona is not the kind the section lists first.
_KIND_NAMES: dict[IntermediaryKind, str] = {
	IntermediaryKind.chw: 'Community Health Workers and Community Health Promoters',
	IntermediaryKind.pharmacy: 'Pharmacy and chemist staff',
	IntermediaryKind.faith_leader: 'Faith leaders (pastors, imams, catechists)',
	IntermediaryKind.boda_sacco: 'Boda boda SACCO chairmen',
	IntermediaryKind.market_leader: 'Market association leaders',
	IntermediaryKind.teacher: 'Teachers and school health patrons',
	IntermediaryKind.chama_leader: 'Chama (savings group) leaders',
}

# §CHAN-5's "Tools provided" bullets, verbatim. Transcribed because three of the five are things
# this repo can carry and two are not: a printed flip chart and a two-hour training are not code, and
# a list that dropped them would report the programme as fully implemented.
TOOLS_PROVIDED: tuple[str, ...] = (
	'Printed job aids and flip charts',
	'CHW-specific app module (see COM-101)',
	'Referral codes (each intermediary gets a code for attribution)',
	'Air time / data bundle incentives for verified referrals',
	'Short training (2 hours) and refresher content',
)

# The two tools with a code representation, named so `carried_tools()` can report the rest rather
# than the module silently claiming all five.
CODE_CARRIED_TOOLS: frozenset[str] = frozenset({
	'CHW-specific app module (see COM-101)',
	'Referral codes (each intermediary gets a code for attribution)',
})


class Intermediary(BaseModel):
	"""One enrolled intermediary. `code` is the §CHAN-5 attribution code and is unique by
	construction in the service — a code shared between two people attributes a referral to neither.

	`county` and `community` are carried because §CHAN-5's rationale is that trust transfers through
	relationships, and a relationship is local: an intermediary's referrals are read per community,
	which is the unit §4.3's P0 counties are made of.
	"""

	model_config = MODEL_CONFIG
	code: str = Field(pattern=r'^[A-Z]{3}-[A-Z2-9]{4}$')
	name: str = Field(min_length=1)
	kind: IntermediaryKind
	county: str = Field(min_length=1)
	community: str = Field(min_length=1)
	enrolled_iso: str = Field(min_length=1)
	trained: bool = False


class Referral(BaseModel):
	"""One referral attributed to a code.

	`arrived_subject_ref` is the person who actually turned up. It is required, and that is the
	section's word *verified* made checkable: a referral without a person behind it is the
	intermediary's claim about their own activity, and paying on it would pay for assertions. The
	ref is not a name and carries no other data — the programme needs to know someone arrived, not
	who they are.
	"""

	model_config = MODEL_CONFIG
	referral_id: str = Field(pattern=r'^REF-[A-Z0-9]{8,}$')
	code: str = Field(pattern=r'^[A-Z]{3}-[A-Z2-9]{4}$')
	arrived_subject_ref: str = Field(min_length=1)
	at_iso: str = Field(min_length=1)
	# Whether the person completed the profile the incentive is for. §20.2 lever 6 is "Airtime or
	# data bundles for health profile completion", so the completion is the qualifying event — not
	# the arrival alone, which would pay for a click.
	profile_completed: bool = False


class Incentive(BaseModel):
	"""One §CHAN-5 payment: the referral it is for, the code it is attributed to, and the amount.

	`kes` has no default and no value written in this module, because §CHAN-5 states no amount.
	`reason` is what the telco client puts on the disbursement request, and it names the code so the
	carrier's own record can be reconciled against this one.
	"""

	model_config = MODEL_CONFIG
	referral_id: str
	code: str
	msisdn: str = Field(pattern=r'^\+254\d{9}$')
	kes: int = Field(gt=0)
	paid_iso: str = Field(min_length=1)
	# Empty on the way in — the carrier's reference is what `pay_incentive` writes back once the
	# disbursement returns, so a caller that supplied one would be asserting a reference it does not
	# have. The field is on the model rather than beside it because the stored record and the request
	# are the same shape, and a separate request model would let the two drift.
	reference: str = ''


class ReferralAttribution(BaseModel):
	"""One intermediary's referral record: who they are, how many arrived, how many completed, and
	what has been paid. `paid_referrals` is the set the service checks against, so a second payment
	for the same referral is refusable rather than merely discouraged."""

	model_config = MODEL_CONFIG
	intermediary: Intermediary
	referrals: int = Field(ge=0)
	completed: int = Field(ge=0)
	paid_referrals: list[str]
	unpaid_completed: list[str]
	kes_paid: int = Field(ge=0)


class IntermediaryProgramme(BaseModel):
	"""§CHAN-5 as one answer: the seven kinds, the five tools, and which of the tools this repo
	carries.

	`uncarried_tools` is the finding. Three of the section's five tools are not code — a printed flip
	chart, an airtime incentive that depends on a carrier agreement, and a two-hour training — and a
	report that listed only what is implemented would describe a programme the section does not.
	"""

	model_config = MODEL_CONFIG
	kinds: list[str]
	tools: list[str]
	carried_tools: list[str]
	uncarried_tools: list[str]
	intermediaries: int = Field(ge=0)
	by_kind: dict[str, int]
	note: str
