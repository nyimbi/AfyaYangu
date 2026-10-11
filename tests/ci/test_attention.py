"""§5.1's rationale and the ordering in it — the third ordering, and the one nothing carried.

§5.2 has two orderings (the Ch column 0–6 and the Reach column) and §5.1 has a third ("in rough order
of daily attention"). All three are different, and §5.1's is the only one written as a reason: it is
the argument §3.3 principle 1 draws its conclusion from. What is tested here is that the order is
data, that it is read off the section's sentence rather than typed, and that the two ways it fails to
cover §5.2's seven channels are recorded instead of smoothed over.
"""
import httpx

from afya.channels.attention import (
	ATTENTION_ORDER,
	ATTENTION_SENTENCE,
	COLLAPSED,
	UNRANKED,
	attention_rank,
	attention_report,
	order_channels,
)
from afya.registry.service import CHANNELS


def _spec_section(heading: str) -> str:
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	return text.split(heading, 1)[1].split('\n### ', 1)[0]


def test_the_order_is_the_sections_sentence_read_in_sequence() -> None:
	"""§5.1 names six places and gives them in an order. The test reads the sentence out of the spec
	and walks it, so the order in the code is the order in the section rather than a list someone
	retyped — and the sentence itself is carried verbatim, including "in rough order", because a
	module presenting it as a strict ranking would claim a precision §5.1 declines to make."""
	section = _spec_section('### 5.1 Rationale')
	sentence = next(
		ln.strip() for ln in section.splitlines()
		if ln.startswith('Information must live where people already are')
	)
	assert ATTENTION_SENTENCE == sentence

	# The order is the sentence's own sequence: each entry appears after the previous one.
	named = sentence.split(':', 1)[1]
	positions = [named.index(entry) for entry, _ in ATTENTION_ORDER]
	assert positions == sorted(positions), f'§5.1 lists them in this order: {named!r}'
	assert [entry for entry, _ in ATTENTION_ORDER] == [
		'WhatsApp', 'SMS', 'radio', 'Facebook', 'TikTok', 'human conversation',
	]


def test_every_section_5_1_entry_names_a_channel_the_registry_has() -> None:
	"""The crossing from places to channels. §5.1 counts *places* ("Facebook", "TikTok") and §5.2
	counts *channels* (`social`), and a mapping that invented a channel for one of the six would be
	this module widening the registry."""
	for entry, channel in ATTENTION_ORDER:
		assert channel in CHANNELS, f'{entry} -> {channel} is not a §5.2 channel'


def test_the_two_ways_the_order_does_not_cover_the_seven_channels_are_recorded() -> None:
	"""§5.1 names six places and §5.2 has seven channels, and the sets are not the same set.

	`social` is two §5.1 entries folded into one channel, and USSD and the native app are channels
	§5.1 does not name at all. Both are carried rather than smoothed: a channel list sorted by an
	ordering that silently omits half of itself would put the omitted channels at an arbitrary end and
	call it the section's answer."""
	assert COLLAPSED == {'social': ('Facebook', 'TikTok')}
	assert set(UNRANKED) == {'ussd', 'native'}
	assert attention_rank('ussd') is None and attention_rank('native') is None
	# `None` and "last" are different answers, which is why the rank is not a large sentinel.
	chw, radio = attention_rank('chw'), attention_rank('radio')
	assert chw is not None and radio is not None and chw > radio
	assert attention_rank('whatsapp') == 0, '§5.1 puts WhatsApp first'


def test_the_rank_of_a_folded_channel_is_its_earlier_entry() -> None:
	"""`social` has two §5.1 entries and one rank, and the earlier of the two decides it — Facebook is
	third in the sentence and TikTok fourth, so the channel sits at Facebook's place. The alternative
	(average, or the later entry) would be a number §5.1 does not give."""
	assert ATTENTION_ORDER[3] == ('Facebook', 'social') and ATTENTION_ORDER[4] == ('TikTok', 'social')
	assert attention_rank('social') == 3


def test_ordering_a_list_keeps_the_unranked_channels_and_is_stable() -> None:
	"""A delivery list sorted by §5.1 keeps the channels the rationale is silent about, at the end and
	in the caller's order. Dropping them would be a channel removed by an ordering, which is not what
	§5.1 is for — and the unranked ones are exactly the two a build is most likely to forget, USSD and
	the app."""
	assert order_channels(['native', 'sms', 'ussd', 'whatsapp']) == ['whatsapp', 'sms', 'native', 'ussd']
	assert order_channels(['ussd', 'native']) == ['ussd', 'native'], 'stable among the unranked'
	assert order_channels([]) == []
	# Every channel survives the sort, whichever order it arrives in.
	every = order_channels(list(CHANNELS))
	assert sorted(every) == sorted(CHANNELS) and len(every) == 7


def test_the_three_orderings_disagree_and_that_is_the_finding() -> None:
	"""§5.2's Ch column, §5.2's Reach column and §5.1's attention order are three different sequences,
	and this test states the disagreement rather than resolving it. Reach is not attention: radio
	reaches the most people ("Highest") and sits third in §5.1, because §5.2 itself gives it "Daily
	situation updates" — a channel for everyone, not a channel for reaching one person now."""
	from afya.channels.cost import CHANNEL_COST

	by_ch = sorted(CHANNELS, key=lambda c: CHANNEL_COST[c].number)
	by_attention = order_channels(list(CHANNELS))
	assert by_ch != by_attention
	assert CHANNEL_COST['radio'].reach == 'Highest' and attention_rank('radio') == 2
	assert by_ch[0] == 'radio' and by_attention[0] == 'whatsapp'


async def test_the_rationale_is_served_with_its_crossings() -> None:
	"""§5.1 over HTTP. The order travels with the entries it folds and the channels it omits, for the
	same reason §7.1's taxonomy route carries its divergences — an ordering served without them is a
	second document rather than a check."""
	from afya.service import build_services, create_app

	app = create_app(build_services())
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		body = (await c.get('/channels/attention')).json()

	assert body == attention_report()
	assert body['sentence'] == ATTENTION_SENTENCE
	assert [e['entry'] for e in body['order']][0] == 'WhatsApp'
	assert body['collapsed'] == {'social': ['Facebook', 'TikTok']}
	assert set(body['unranked']) == {'ussd', 'native'}
