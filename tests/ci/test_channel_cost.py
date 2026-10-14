"""Gate: §5.2's "Cost to User" column and §3.3 principle 3, "Zero-rated or it doesn't count".

The column was unmodelled. `CHANNELS` in the registry is a bare tuple of slugs, so a channel had a
name and no cost; `SmsOut.zero_rated` defaulted to `True`, so the free claim could not come out false
and the only check on it was `AfricaTalkingSmsPort.send` asserting the value it had just been handed;
and §18.8's `zero_rating_rules()` was pulled and served at a route while being applied to nothing.

What is tested here is that the column is now data, that the free claim can fail, and — the part that
is easiest to get wrong — that "nobody pulled the rules" and "the rules were pulled and do not cover
this" are reported as different facts. Collapsing them would report every deployment with no carrier
agreement as a channel that charges people, which is a false finding of exactly the kind the default
`zero_rated=True` was a false claim of.
"""
from pathlib import Path

import pytest
from pydantic import ValidationError

from afya.channels.cost import (
	CHANNEL_COST, CHANNEL_COSTS, CHANNEL_ORDER, CostToUser, ZeroRatingRule, cost_report, cost_verdict,
	covering_rule, parse_rules, zero_rating_gaps,
)
from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import SmsOut
from afya.registry.service import CHANNELS
from afya.service import create_app

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / 'docs' / 'spec.md'


def _spec_rows() -> list[list[str]]:
	"""§5.2's table, read out of the spec rather than restated here.

	The section is located by its heading and the table taken as the first seven pipe rows under it.
	Reading the spec is the point: a revision that re-costs a channel must fail these tests until the
	code moves with it, and a table transcribed into the test would move with nothing.
	"""
	lines = SPEC.read_text(encoding='utf-8').splitlines()
	start = next(i for i, ln in enumerate(lines) if ln.startswith('### 5.2 '))
	rows: list[list[str]] = []
	for ln in lines[start:]:
		if ln.startswith('### ') and rows:
			break
		if not ln.startswith('|'):
			continue
		cells = [c.strip() for c in ln.strip('|').split('|')]
		if set(''.join(cells)) <= set('-: ') or cells[0] == 'Ch':
			continue
		rows.append(cells)
	assert len(rows) == 7, f'§5.2 should have seven channel rows, found {len(rows)}'
	return rows


def _port() -> AfricaTalkingSmsPort:
	return AfricaTalkingSmsPort('http://at.ke', 'key')


def _rules(*pairs: tuple[str, float]) -> list[ZeroRatingRule]:
	return [ZeroRatingRule(prefix=p, rate=r) for p, r in pairs]


# --- §5.2's table, cell for cell ----------------------------------------------------------------

def test_every_spec_cell_is_carried_verbatim() -> None:
	"""The seven rows, against the section's own words. `**bold**` is stripped from the cells because
	§5.2 bolds the Ch and Channel columns and not the rest; everything else is compared as written,
	including the parenthetical in WhatsApp's cost cell, which is the whole difference between it and
	social media's."""
	spec_rows = _spec_rows()
	assert len(CHANNEL_COSTS) == len(spec_rows)
	for row, cells in zip(CHANNEL_COSTS, spec_rows):
		number, name, reach, cost, role, owner = [c.replace('**', '') for c in cells]
		assert row.number == int(number), f'{row.channel}: Ch column'
		# `label()` is the cell, `name` is the cell without its parenthetical. §5.2 writes
		# "SMS (zero-rated)", and the qualifier is a claim about the cost rather than part of the
		# name — a sentence saying "SMS (zero-rated) is meant to be free … nothing has confirmed it"
		# would contradict itself in its own first words.
		assert row.label() == name, f'{row.channel}: name'
		assert row.name == name.split(' (')[0], f'{row.channel}: name without the qualifier'
		assert (f'({row.qualifier})' in name) if row.qualifier else ('(' not in name), f'{row.channel}: qualifier'
		assert row.reach == reach, f'{row.channel}: reach'
		assert row.cost_label == cost, f'{row.channel}: cost to user'
		assert row.primary_role == role, f'{row.channel}: primary role'
		assert row.owned_by == owner, f'{row.channel}: owned by'


def test_the_channel_list_is_the_registrys() -> None:
	"""The rows follow `registry.CHANNELS`, in its order. A channel added to `FeatureSpec.channels`
	and not to the cost table would be a channel the report silently omits — which is how a channel
	becomes one nobody checks the cost of."""
	assert CHANNEL_ORDER == CHANNELS
	assert tuple(r.channel for r in CHANNEL_COSTS) == CHANNELS
	assert tuple(r.number for r in CHANNEL_COSTS) == tuple(range(7))


def test_the_five_spellings_collapse_into_three_classes() -> None:
	"""§5.2 writes five different cells and they are three different claims. "Free" and "n/a" are
	both no-charge but different facts — a radio costs nothing to hear, a CHW visit has no channel to
	bill — so they stay separate; a derivation that merged them would lose the section's distinction
	between "we are not charging you" and "there is no charge to make"."""
	assert {r.cost_label for r in CHANNEL_COSTS} == {'Free', 'Data (zero-rated)', 'Data', 'n/a', 'Data + storage'}
	assert CHANNEL_COST['radio'].cost_to_user is CostToUser.free
	assert CHANNEL_COST['chw'].cost_to_user is CostToUser.not_applicable
	assert CHANNEL_COST['native'].cost_to_user is CostToUser.data
	# The parenthetical is the rule, so the two "Data" rows must not read alike.
	assert CHANNEL_COST['whatsapp'].cost_label != CHANNEL_COST['social'].cost_label


def test_only_the_channels_whose_cell_implies_a_rule_require_one() -> None:
	"""SMS by §5.3 CHAN-1's critical requirement, WhatsApp by the "(zero-rated)" in its own cell.
	Radio, USSD and the human channel have nothing to zero-rate, and marking them as requiring one
	would fire the gap report on channels that cannot gap."""
	assert {r.channel for r in CHANNEL_COSTS if r.zero_rating_required} == {'sms', 'whatsapp'}


def test_the_shortcode_is_the_one_the_spec_names() -> None:
	"""SMS's rule must be matched at §5.3 CHAN-1's own shortcode. A destination invented here would
	make the match an assertion about this file rather than about the carrier agreement."""
	spec = SPEC.read_text(encoding='utf-8')
	hint = CHANNEL_COST['sms'].rule_prefix_hint
	assert hint == '719' and hint in spec, 'the SMS destination hint must be the spec’s shortcode'


# --- free, charged, and the gap between unverified and uncovered ---------------------------------

def test_unpulled_rules_are_unverified_not_charged() -> None:
	"""The distinction the whole module exists to keep. `rules=None` means nobody asked the carrier —
	every dev deployment, and the state before §20.5's Phase 0 step. Reporting that as a channel that
	charges people is a finding derived from an absence, and it would fire on every environment that
	has not yet signed its agreement."""
	# Only the rows whose cost depends on a rule. Social media and the native app are charged with or
	# without a pull — §5.2's cell says the user pays for data, and no carrier rule changes that — so
	# a blanket assertion over all seven would be testing the wrong set.
	conditional = [v for v in cost_report(None) if v.zero_rating_required]
	assert [v.channel for v in conditional] == ['sms', 'whatsapp']
	for verdict in conditional:
		assert verdict.charged is False, f'{verdict.channel} charged with no rules pulled'
		assert verdict.verified is False
		assert 'have not been pulled' in verdict.sentence
	assert zero_rating_gaps(None) == []


def test_the_two_ways_a_claim_is_unconfirmed_are_told_apart_in_the_sentence() -> None:
	"""`verified` is False both when nobody asked the carrier and when the carrier answered and named
	nothing this channel could match — and the sentence is served to a person, so it may not assert
	the first when the second is true.

	WhatsApp is the case: §5.2 states no destination prefix for it, so `rule_prefix_hint` is None and
	no pulled rule can ever match. Before this distinction the sentence read "the carrier's billing
	rules have not been pulled" for an empty *pulled* list and for a list carrying rules — a public
	payload telling a reader that a pull that happened did not. The boolean stays False either way;
	the prose is what had to change.
	"""
	assert cost_verdict('whatsapp', []).verified is False
	assert 'have not been pulled' not in cost_verdict('whatsapp', []).sentence, (
		'an empty list is a pull that returned nothing, not a pull that never happened'
	)
	pulled = _rules(('719', 0))
	assert 'have not been pulled' not in cost_verdict('whatsapp', pulled).sentence
	assert 'cannot confirm it' in cost_verdict('whatsapp', pulled).sentence
	# And the un-pulled state still says what it always said.
	assert 'have not been pulled' in cost_verdict('whatsapp', None).sentence
	# SMS can be matched, so its two states were already distinct and must stay so: pulled-and-empty
	# is a gap that charges, not an unconfirmed claim.
	assert cost_verdict('sms', []).charged is True
	assert 'have not been pulled' not in cost_verdict('sms', []).sentence


def test_pulled_rules_that_cover_nothing_are_a_gap() -> None:
	"""The carrier answered and the answer was no. This is a finding, and it is the case §18.8's own
	docstring describes: "a zero-rating rule that changed but was not pulled means the app tells
	people alerts are free when they are not". An empty list is that state, and it is not `None`."""
	verdict = cost_verdict('sms', [])
	assert verdict.verified is True and verdict.free_at_point_of_use is False and verdict.charged is True
	assert 'costs the person money' in verdict.sentence
	assert [g.channel for g in zero_rating_gaps([])] == ['sms']


def test_a_rate_zero_rule_on_the_shortcode_makes_sms_free() -> None:
	verdict = cost_verdict('sms', _rules(('719', 0)))
	assert verdict.verified and verdict.free_at_point_of_use and not verdict.charged
	assert verdict.rule is not None and verdict.rule.prefix == '719'
	assert zero_rating_gaps(_rules(('719', 0))) == []


def test_a_rule_on_another_destination_does_not_cover_sms() -> None:
	"""The match is a *match*, not a count of rules. This is the case a gate on the positive path
	misses: with only `{'prefix': '719', 'rate': 0}` in the fixture, a `covering_rule` that returned
	the first rate-0 rule regardless of destination passed every assertion — which is precisely the
	defect the per-channel hint was introduced to fix, still live one line further down. A rule for a
	different shortcode is not a rule for ours."""
	assert cost_verdict('sms', _rules(('254', 0))).charged is True
	assert cost_verdict('sms', _rules(('7190', 0))).charged is True, 'a longer number is not the shortcode'
	assert cost_verdict('sms', _rules(('7', 0))).charged is False, 'a prefix does cover what it prefixes'
	# The order of the carrier's rules must not decide the answer.
	mixed = _rules(('254', 0), ('719', 0))
	assert cost_verdict('sms', mixed).charged is False
	assert cost_verdict('sms', _rules(('254', 0), ('719', 1.5))).charged is True


def test_a_non_zero_rate_is_not_coverage() -> None:
	"""`rate` is what the carrier bills, so a rule that arrived with a rate above zero is evidence the
	carrier *charges* that destination — the opposite of coverage. Reading its presence as free would
	invert the thing it is evidence for."""
	verdict = cost_verdict('sms', _rules(('719', 1.5)))
	assert verdict.charged and not verdict.free_at_point_of_use
	assert [g.channel for g in zero_rating_gaps(_rules(('719', 1.5)))] == ['sms']


def test_a_shortcode_rule_does_not_cover_whatsapp() -> None:
	"""The defect this module was written after. With the destination supplied per call, one
	`{'prefix': '719', 'rate': 0}` rule made WhatsApp report as covered — a shortcode rule cannot
	zero-rate Meta's data charges, and reporting it as doing so is the same class of false free claim
	the `zero_rated=True` default was. WhatsApp's hint is None because the spec states no prefix, so
	it stays unverified rather than falsely covered."""
	assert CHANNEL_COST['whatsapp'].rule_prefix_hint is None
	verdict = cost_verdict('whatsapp', _rules(('719', 0)))
	assert verdict.rule is None and not verdict.charged
	assert verdict.verified is False, 'no prefix to match means nothing was checked'
	assert covering_rule('whatsapp', _rules(('719', 0))) is None


def test_the_channels_the_user_pays_for_are_charged_always() -> None:
	"""Social media and the native app cost the user data by §5.2's own cell, and no carrier rule
	changes that. They are charged with or without rules pulled, and they are never *gaps* — a gap is
	an unbacked free claim, and these never claimed to be free."""
	for rules in (None, [], _rules(('719', 0))):
		for channel in ('social', 'native'):
			verdict = cost_verdict(channel, rules)
			assert verdict.charged and verdict.verified and not verdict.zero_rating_required
	assert zero_rating_gaps(_rules(('719', 0))) == []


def test_the_free_without_a_rule_channels_are_free_regardless() -> None:
	"""Radio, USSD and the human channel have no agreement to check, so their verdict does not move
	when the carrier's rules do."""
	for rules in (None, [], _rules(('719', 0))):
		for channel in ('radio', 'ussd', 'chw'):
			verdict = cost_verdict(channel, rules)
			assert verdict.free_at_point_of_use and not verdict.charged


def test_an_unknown_channel_is_refused() -> None:
	with pytest.raises(AssertionError):
		cost_verdict('telepathy', None)


# --- §18.8's payload -----------------------------------------------------------------------------

def test_the_payload_is_the_integration_tests_shape() -> None:
	rules = parse_rules([{'prefix': '719', 'rate': 0}])
	assert rules == [ZeroRatingRule(prefix='719', rate=0)]
	assert rules[0].is_zero()
	assert not ZeroRatingRule(prefix='719', rate=1.5).is_zero()


def test_a_malformed_rule_is_refused_not_dropped() -> None:
	"""Dropping an unparseable row converts "the carrier sent something we did not understand" into
	"the carrier sent nothing", which reads as uncovered when it may be covered. A refusal is
	reported; a dropped row is not."""
	with pytest.raises(ValidationError):
		parse_rules([{'prefix': '719'}])
	with pytest.raises(AssertionError):
		parse_rules({'prefix': '719', 'rate': 0})  # type: ignore[arg-type]


# --- the message that reaches a person ------------------------------------------------------------

def test_sms_out_has_no_free_default() -> None:
	"""The defect in one assertion. `zero_rated` defaulted to `True`, so a caller that knew nothing
	about the carrier agreement still sent a message stamped free. A caller that does not know must
	say so by omission, not inherit the claim."""
	assert 'zero_rated' in SmsOut.model_fields
	assert SmsOut.model_fields['zero_rated'].is_required()
	with pytest.raises(ValidationError):
		SmsOut(to_msisdn='+254711222333', body='hi', segments=1)  # type: ignore[call-arg]


async def test_send_sms_resolves_the_flag_from_the_rules() -> None:
	"""The flag on the message is the verdict, not a constant. With no carrier configured it is free
	and unverified; with the shortcode rule pulled it is free and backed; with the carrier having
	answered "nothing" it is *not* free — which is the state the old default made unreachable."""
	unconfigured = ChannelService(_port())
	assert (await unconfigured.send_sms('+254711222333', 'Call 719')).zero_rated is True

	covered = ChannelService(_port(), lambda: _covered(_rules(('719', 0))))
	assert (await covered.send_sms('+254711222333', 'Call 719')).zero_rated is True

	uncovered = ChannelService(_port(), lambda: _covered([]))
	assert (await uncovered.send_sms('+254711222333', 'Call 719')).zero_rated is False


async def _covered(rules: list[ZeroRatingRule]) -> list[ZeroRatingRule] | None:
	return rules


async def test_a_carrier_that_is_down_is_not_a_carrier_that_charges() -> None:
	"""An unreachable telco is "the rules were not pulled", which is unverified — not the empty list
	that means the carrier answered and covers nothing. Reporting the outage as a gap would put a
	finding in front of an operator who cannot act on it."""
	async def down() -> list[ZeroRatingRule] | None:
		raise RuntimeError('connection refused')

	svc = ChannelService(_port(), down)
	assert await svc.zero_rating_rules() is None
	assert (await svc.send_sms('+254711222333', 'Call 719')).zero_rated is True


async def test_an_unconfigured_deployment_reports_none_rather_than_an_empty_list() -> None:
	svc = ChannelService(_port())
	assert await svc.zero_rating_rules() is None
	assert [v.channel for v in await svc.cost_report()] == list(CHANNELS)


# --- what the app serves --------------------------------------------------------------------------

async def test_the_cost_route_serves_the_report_and_the_gaps() -> None:
	import httpx

	app = create_app()
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as client:
		resp = await client.get('/channels/cost')
	assert resp.status_code == 200
	body = resp.json()
	assert [row['channel'] for row in body['channels']] == list(CHANNELS)
	assert body['rules_pulled'] is False, 'an unconfigured deployment has not pulled the rules'
	assert body['zero_rating_gaps'] == [], 'unpulled rules are unverified, not a gap'
	# `rules_pulled` is read off the pull, not off a row. Reporting row 0's `verified` — radio, which
	# is verified by construction because it needs no rule — would say a deployment with no carrier
	# agreement had been checked.
	assert {row['verified'] for row in body['channels'] if row['zero_rating_required']} == {False}


def test_no_served_sentence_carries_a_spec_code() -> None:
	"""§3.3 principle 9's rule, applied to the one string this module writes for a person. The
	channel slugs are internal identifiers; a sentence saying "CHAN-001 is free" is the feature code
	percolating into the UX, and the friendly copy for the catalogue action is where the user-facing
	wording lives."""
	import re

	code = re.compile(r'\b(CHAN|INF|REC|MON|SENS|ACC)-\d{3}\b')
	for rules in (None, [], _rules(('719', 0)), _rules(('719', 1.5))):
		for verdict in cost_report(rules):
			assert not code.search(verdict.sentence), verdict.sentence
			assert verdict.name in verdict.sentence
			# The slug must appear, if at all, only inside §5.2's own name. A bare `not in` would be
			# the wrong check: "radio" is an ordinary English word and a legitimate part of "Community
			# radio", so the sentence would fail for the right content and the wrong reason — the
			# shape of a global assumption about a canonical value wearing a lint's clothes.
			assert verdict.channel not in verdict.sentence.replace(verdict.name, ''), verdict.sentence
