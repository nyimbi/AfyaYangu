"""§5.2's cost-to-user column and §3.3 principle 3 — what each channel costs, and whether that is true.

§5.2 is a seven-row table whose fourth column is "Cost to User", and §3.3 principle 3 states the rule
it exists for: "**Zero-rated or it doesn't count** — Data cost is the single largest barrier. Every
channel must be zero-rated or free-at-point-of-use." Nothing carried either. `CHANNELS` in the registry
is a bare tuple of slugs, so a channel had a name and no cost.

What the repo did carry was a *claim* that could not be wrong. `SmsOut.zero_rated` defaulted to `True`,
so every message the system sent was stamped free whether or not any agreement existed, and the only
check on it was `AfricaTalkingSmsPort.send` asserting the flag it had just been handed — a tautology
that reads like a §5.3 control. Meanwhile §18.8's `zero_rating_rules()` pulls the carrier's billing
rules and its own docstring says why: "The app needs this to know whether an alert will actually cost
the recipient money — a zero-rating rule that changed but was not pulled means the app tells people
alerts are free when they are not." The rules were fetched, served at a route, and applied to nothing.
A control that exists is not a control that is applied.

Three things follow from taking the column at its word:

* **The cost is the spec's own cell, and the class is derived from it.** "Free", "Data (zero-rated)",
  "Data", "n/a" and "Data + storage" are five different claims and they collapse into three: nothing is
  charged (radio, USSD, a human conversation), the user pays for data (social, the app), or the user
  pays *unless a carrier rule says otherwise* (SMS at the shortcode, WhatsApp's data). The label is
  kept verbatim beside the class so the row can be checked against §5.2 rather than trusted.

* **SMS is "Free" and still needs a rule.** §5.3 CHAN-1's critical requirement is "Zero-rated at the
  telco level. If a user is charged, adoption collapses." An SMS carries no data charge to zero-rate —
  what makes it free is the shortcode agreement — so SMS is free by nature *and* conditional on an
  agreement, which is the one row where those two are not the same thing. Radio and USSD are free
  because there is nothing to bill; WhatsApp is free only while the data rule holds.

* **A free claim with no rule behind it is a gap, and it is reported.** The deployment may not have
  pulled the rules, or the carrier may have dropped one. Either way the honest state is "this channel
  charges the user", and the one thing that must not happen is the system continuing to tell people
  alerts are free. `zero_rating_gaps` names the rows whose claim is unbacked rather than letting the
  default stand in for the agreement.

The rule of §3.3 principle 3 is read here as what it says — a channel that charges does not count —
and the consequence is *reported* rather than enforced as a refusal. Refusing to deliver an outbreak
alert because the telco agreement is unconfigured would trade a shilling for a case, and neither §5.3
nor §3.3 asks for that; both ask for the free-ness to be real, which means the claim must be able to
come out false.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from afya.registry.service import CHANNELS

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# The channel slugs the registry declares, in §5.2's own numbering. Read from the registry rather
# than restated, because a second copy of the list is the duplication that drifts: a channel added
# to `FeatureSpec.channels` and not here would be a channel the cost table silently omits.
CHANNEL_ORDER: tuple[str, ...] = CHANNELS


class CostToUser(str, Enum):
	"""What reaches the user's airtime, in three classes rather than the table's five spellings.

	`free` and `not_applicable` both mean no charge, but they are different facts — a radio is free
	because listening costs nothing, a CHW visit is free because there is no channel to bill — and
	§5.2 writes them as different cells ("Free" and "n/a"), so they stay separate here and the
	verdict treats them alike.
	"""
	free = 'free'
	data = 'data'
	not_applicable = 'not_applicable'


class ChannelCost(BaseModel):
	"""One §5.2 row.

	`cost_label` is the section's cell verbatim, including the parenthetical, because the
	parenthetical is the whole distinction between WhatsApp ("Data (zero-rated)") and social media
	("Data") — and a paraphrase would drop exactly the part that carries the rule.
	"""
	model_config = MODEL_CONFIG
	channel: str
	number: int = Field(ge=0, le=6)
	# §5.2's own name for the channel, so a sentence about it reads as the section writes it.
	# Transcribed rather than title-cased from the slug: "Sms" and "Chw" are not words, and a name
	# derived from an internal slug is how an internal name reaches a person (§3.3 principle 9).
	name: str = Field(min_length=1)
	# The parenthetical §5.2 puts after a channel's name — "SMS (zero-rated)" — held apart from the
	# name rather than inside it. It is a qualifier and not part of the name, and the distinction
	# matters here: the sentence for an unverified SMS says the carrier's rules "have not been pulled,
	# so nothing has confirmed it", which a name reading "SMS (zero-rated)" would contradict in its
	# own first three words. `label` reconstructs the section's cell exactly, and `test_channel_cost`
	# asserts the reconstruction against the spec.
	qualifier: str | None = None

	def label(self) -> str:
		"""§5.2's Channel cell, as written."""
		return f'{self.name} ({self.qualifier})' if self.qualifier else self.name
	reach: str = Field(min_length=1)
	cost_to_user: CostToUser
	cost_label: str = Field(min_length=1)
	primary_role: str = Field(min_length=1)
	owned_by: str = Field(min_length=1)
	# True when the channel is free only while a carrier rule says so. SMS carries it by §5.3's
	# critical requirement, WhatsApp by the "(zero-rated)" in its own cell. False for radio, USSD
	# and the human channel, which have nothing to zero-rate — marking those True would claim an
	# agreement that does not exist and would make the gap report fire on channels that cannot gap.
	zero_rating_required: bool
	# The destination a rule must cover for this channel to be free, or None when no rule applies.
	# SMS is the shortcode §5.3 CHAN-1 names ("Fallback to a shortcode for inbound") and §18.4 wires
	# ("719 hotline"); WhatsApp is billed by *destination prefix* on the Meta Business API, and no
	# prefix is stated anywhere in the spec, so the hint is None and no shortcode rule can be
	# mistaken for data coverage. That absence is the point: guessing a prefix would manufacture the
	# coverage, and the honest report for a rule nobody can match is "not verified".
	rule_prefix_hint: str | None = None


# §5.2's table, transcribed row for row. `tests/ci/test_channel_cost.py` asserts every cell against
# `docs/spec.md`, so a revision that re-costs a channel fails here until the table moves with it.
CHANNEL_COSTS: tuple[ChannelCost, ...] = (
	ChannelCost(
		channel='radio', name='Community radio', number=0, reach='Highest', cost_to_user=CostToUser.free, cost_label='Free',
		primary_role='Daily situation updates, guidance, myth-busting in local language',
		owned_by='Partner stations', zero_rating_required=False,
	),
	ChannelCost(
		channel='sms', name='SMS', qualifier='zero-rated', number=1, reach='Very high', cost_to_user=CostToUser.free, cost_label='Free',
		primary_role='Alerts, hotline number, one-line triage, recall prompts',
		owned_by='Telco gateway', zero_rating_required=True, rule_prefix_hint='719',
	),
	ChannelCost(
		channel='ussd', name='USSD', number=2, reach='High', cost_to_user=CostToUser.free, cost_label='Free',
		primary_role='Symptom reporting, callback requests, facility lookup',
		owned_by='Telco', zero_rating_required=False,
	),
	ChannelCost(
		channel='whatsapp', name='WhatsApp bot', number=3, reach='High and growing', cost_to_user=CostToUser.data,
		cost_label='Data (zero-rated)', primary_role='Triage, Q&A, myth-busting, guidance, record sharing',
		owned_by='Meta Business API', zero_rating_required=True,
	),
	ChannelCost(
		channel='social', name='Social media', number=4, reach='High', cost_to_user=CostToUser.data, cost_label='Data',
		primary_role='Short video, myth-busting, reach, credibility',
		owned_by='Organic + paid', zero_rating_required=False,
	),
	ChannelCost(
		channel='chw', name='Human intermediaries', number=5, reach='High trust', cost_to_user=CostToUser.not_applicable, cost_label='n/a',
		primary_role='Explanation, referral, reassurance, enrolment',
		owned_by='CHWs, chemists, faith leaders', zero_rating_required=False,
	),
	ChannelCost(
		channel='native', name='Native app', number=6, reach='Moderate', cost_to_user=CostToUser.data, cost_label='Data + storage',
		primary_role='Persistent state, monitoring, sensors, proximity, records',
		owned_by='Owned', zero_rating_required=False,
	),
)

CHANNEL_COST: dict[str, ChannelCost] = {row.channel: row for row in CHANNEL_COSTS}
assert tuple(row.channel for row in CHANNEL_COSTS) == CHANNEL_ORDER, 'the rows must follow §5.2 order'
assert tuple(row.number for row in CHANNEL_COSTS) == tuple(range(7)), 'the Ch column is 0..6'


class ZeroRatingRule(BaseModel):
	"""One §18.8 billing rule, as the carrier sends it.

	§18.8's row is "Zero-rating configuration | Telco → App | Billing rules | On change", and the
	payload the integration test pins is `{'prefix': '719', 'rate': 0}`. `rate` is what the carrier
	bills per unit, so `0` is the only value that is a zero-rating rule; a rule that arrived with a
	non-zero rate is a rule that *charges*, and treating its presence as coverage would invert the
	thing it is evidence for.
	"""
	model_config = MODEL_CONFIG
	prefix: str = Field(min_length=1)
	rate: float = Field(ge=0)
	label: str | None = None

	def is_zero(self) -> bool:
		return self.rate == 0


def parse_rules(payload: list[dict[str, object]]) -> list[ZeroRatingRule]:
	"""§18.8's payload into rules, refusing a malformed row rather than dropping it.

	Dropping an unparseable rule would silently convert "the carrier sent something we did not
	understand" into "the carrier sent nothing", which is the state that makes a channel look
	uncovered when it may be covered. A refusal is reported; a dropped row is not.
	"""
	assert isinstance(payload, list), 'the zero-rating payload must be a list'
	return [ZeroRatingRule(**row) for row in payload]  # type: ignore[arg-type]


def covers(rule: ZeroRatingRule, destination: str) -> bool:
	"""Whether a rule governs a destination. A prefix match, which is how a shortcode rule covers a
	shortcode and a number-range rule covers a range — §18.8 calls the payload "billing rules", and
	a rule that named one number while covering another would not be one."""
	return destination == rule.prefix or destination.startswith(rule.prefix)


def covering_rule(channel: str, rules: list[ZeroRatingRule]) -> ZeroRatingRule | None:
	"""The rate-0 rule that makes a zero-rating channel free, or None.

	Matched against the channel's **own** destination — `rule_prefix_hint` — rather than against
	whatever the caller passes. That is the fix for a real defect in an earlier draft of this module:
	with the destination supplied per call, `cost_verdict('whatsapp', rules)` against a single
	`{'prefix': '719', 'rate': 0}` rule reported WhatsApp as covered, because with no destination to
	match, any rate-0 rule counted. A shortcode rule cannot zero-rate WhatsApp's data, and reporting
	it as covering it is the same class of false free claim the default `zero_rated=True` was.

	Only a rate-0 rule counts. A rule that arrived with a non-zero rate is evidence the carrier
	*bills* that destination, which is the opposite of coverage.
	"""
	row = CHANNEL_COST[channel]
	if not row.zero_rating_required or row.rule_prefix_hint is None:
		return None
	return next((r for r in rules if r.is_zero() and covers(r, row.rule_prefix_hint)), None)


class ChannelCostVerdict(BaseModel):
	"""What one channel costs a person right now, and what makes it so.

	`charged` is the field §3.3 principle 3 is about: a channel where it is True is a channel that
	does not count, in the section's own words, and the sentence says so without a spec code.

	`verified` is the distinction that keeps the finding honest. **"The rules were never pulled" and
	"the rules were pulled and do not cover this" are different facts**, and collapsing them would
	report a deployment with no carrier agreement configured — every dev environment, and the state
	before §20.5's Phase 0 step — as a channel that charges people. The first is unverified: the
	claim stands on §5.2's intent and nobody has checked it. The second is a gap: someone checked,
	and the answer was no. Only the second is a finding, which is why `charged` requires `verified`.
	"""
	model_config = MODEL_CONFIG
	channel: str
	name: str = Field(min_length=1)
	cost_label: str
	cost_to_user: CostToUser
	zero_rating_required: bool
	# Whether the carrier's rules were available *and* named a destination this channel could be
	# matched at. False for two different reasons — no pull, or no `rule_prefix_hint` to match — and
	# the sentence tells them apart; a reader who needs to know which must read `rules_pulled` off
	# the report rather than this flag.
	verified: bool
	free_at_point_of_use: bool
	charged: bool
	rule: ZeroRatingRule | None = None
	sentence: str = Field(min_length=1)


def _sentence(row: ChannelCost, free: bool, verified: bool, rule: ZeroRatingRule | None, *,
              pulled: bool = True) -> str:
	"""One sentence about what a channel costs, written so the channel's name can be singular or
	plural. §5.2's own names include "Human intermediaries", so a verb agreeing with the name would
	need a number for every row; the phrasings below take the name as a subject-free topic instead.

	`pulled` separates the two ways a claim can be unconfirmed, because they are opposite facts and
	the sentence is served to a person. "The carrier has not answered" and "the carrier answered and
	named nothing this channel could match" both leave `verified` False, and a sentence asserting the
	first when the second is true tells a reader something that did not happen. It is the same
	collapsing the model's own docstring warns about, one level down: the boolean is right either
	way, and the prose was not.
	"""
	name = row.name
	if not row.zero_rating_required:
		if free:
			return f'No charge reaches the person on {name}.'
		return f'{name} uses the person’s own data, so reaching them this way is not free.'
	if not verified:
		if not pulled:
			return (
				f'{name} is meant to be free, and the carrier’s billing rules have not been pulled, so '
				f'nothing has confirmed it.'
			)
		# Pulled, and this channel names no destination a rule could cover — WhatsApp, whose data is
		# billed by a prefix §5.2 never states. The rules answered; there was nothing to ask them.
		return (
			f'{name} is meant to be free, and no destination the carrier’s rules could name is stated '
			f'for it, so the rules that were pulled cannot confirm it.'
		)
	if rule is not None:
		return f'{name} is free — the carrier’s billing rules cover it.'
	return (
		f'{name} is not covered by a zero-rating rule right now, so a message sent this way costs '
		f'the person money.'
	)


def cost_verdict(channel: str, rules: list[ZeroRatingRule] | None) -> ChannelCostVerdict:
	"""Resolve one channel against the carrier's rules.

	A channel that needs no rule is free when its §5.2 class says no charge reaches the user, and
	charged when the user pays for data — no pull is required, because there is no agreement to
	check. A channel that needs a rule is free only while a rate-0 rule covers the destination that
	channel is billed at, which is the whole reason §18.8's rules are pulled and the case where the
	old default `zero_rated=True` was most likely to be a lie. `rules=None` means they have not been
	pulled: unverified, not charged.
	"""
	assert channel in CHANNEL_COST, f'unknown channel {channel}'
	row = CHANNEL_COST[channel]
	if not row.zero_rating_required:
		free = row.cost_to_user in (CostToUser.free, CostToUser.not_applicable)
		return ChannelCostVerdict(
			channel=channel, name=row.name, cost_label=row.cost_label, cost_to_user=row.cost_to_user,
			zero_rating_required=False, verified=True, free_at_point_of_use=free, charged=not free,
			rule=None, sentence=_sentence(row, free, True, None),
		)
	# A channel with no destination a rule could name cannot be checked at all, so it stays
	# unverified however many rules were pulled. Reporting it as covered would be inventing the
	# match; reporting it as a gap would blame the carrier for a hint the spec never gives.
	#
	# The two ways `verified` comes out False are kept apart for the sentence's sake: `rules is None`
	# is "nobody asked the carrier", while a channel with no `rule_prefix_hint` is "the carrier
	# answered and there was nothing to match against". Same boolean, opposite facts, and only the
	# first may be described as rules that were never pulled.
	pulled = rules is not None
	verified = pulled and row.rule_prefix_hint is not None
	rule = covering_rule(channel, rules or [])
	free = rule is not None or not verified
	return ChannelCostVerdict(
		channel=channel, name=row.name, cost_label=row.cost_label, cost_to_user=row.cost_to_user,
		zero_rating_required=True, verified=verified, free_at_point_of_use=free,
		charged=verified and not free, rule=rule,
		sentence=_sentence(row, free, verified, rule, pulled=pulled),
	)


def cost_report(rules: list[ZeroRatingRule] | None) -> list[ChannelCostVerdict]:
	"""All seven channels, in §5.2's order. What a deployment is serving, and what it costs."""
	return [cost_verdict(row.channel, rules) for row in CHANNEL_COSTS]


def zero_rating_gaps(rules: list[ZeroRatingRule] | None) -> list[ChannelCostVerdict]:
	"""The channels whose free claim was checked and came back false — §3.3 principle 3, as a list.

	Only the rows that *claim* to be zero-rated can gap, and only once the rules have actually been
	pulled and a destination was known to match against. Reporting the paying channels here would
	bury the finding in a list of things that were never supposed to be free, and reporting the
	unverified ones would report every deployment that has not yet signed its carrier agreement.
	"""
	return [v for v in cost_report(rules) if v.zero_rating_required and v.charged]
