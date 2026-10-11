"""§5.1's rationale and the one thing in it a build can get wrong: where attention actually is.

§5.1 is two paragraphs and a sentence, and the sentence is an ordering — "Information must live where
people already are. In Kenya that is, in rough order of daily attention: WhatsApp, SMS, radio,
Facebook, TikTok, and human conversation." Nothing carried it. `channels/cost.py` carries §5.2's
seven rows with their Ch numbers and their Reach column, and those are two *different* orderings
already; §5.1 is a third, and it is the only one written as a reason rather than as a table.

**The three orderings disagree, and the disagreement is the point.** §5.2's Ch column numbers the
channels 0–6 for reference, and §5.2's Reach column ranks them radio-first ("Highest") down to the
app ("Moderate"). §5.1 ranks WhatsApp first and radio third. Reach is not attention: community radio
reaches the most people, and it is not where a person's attention is at any given hour. §3.3
principle 1 — "Channels before apps… The app is the power tier, not the entry point" — is the
conclusion §5.1 argues for, and the argument is this ordering. A build that took Reach for attention
would lead with radio on every alert, which is the one channel §5.2 itself calls "Daily situation
updates" rather than a channel for reaching a specific person now.

**§5.1 names six places and §5.2 has seven channels, and the sets are not the same set.** Facebook
and TikTok are two entries in §5.1 and one row in §5.2 (`social`); USSD and the native app are rows
in §5.2 that §5.1 does not name at all. So the crossing is many-to-one at the top and one-to-none at
the bottom, and both directions are recorded rather than smoothed: `COLLAPSED` holds the two names
that fold into one channel, `UNRANKED` the two channels the rationale is silent about. Sorting a
channel list by an ordering that silently omits half of it would put USSD and the app at an arbitrary
end and call it the section's answer.

**Where a channel list is ordered, and why §5.1 does not order it.** `AlertingService.notify_exposure`
builds `delivery_channels=['native', 'sms', 'whatsapp']`, which leads with the app — the channel §3.3
principle 1 calls the power tier and not the entry point. It is *not* a defect: §ALT-004's Delivery
cell reads "Push notification, SMS fallback, WhatsApp fallback", and the list is that cell transcribed
in order. The two sections answer different questions — §ALT-004 orders the channels *one exposure
notification* may travel by, starting with the one the app itself raises; §5.1 orders where
*information* should be placed so a person meets it without being reached. Reading §5.1's order onto
the delivery list would reorder a cell that is already correct, so this module does not do it, and
`order_channels` is offered as a function rather than applied to that list.

What was missing is the ordering itself, and the fact that it is a third one. Two orderings in §5.2
and one in §5.1, all three different, none of them stated as relating to the others — a build that
picked up "Reach" and used it to choose where to put an alert would lead with community radio, which
§5.2 itself describes as "Daily situation updates" rather than a channel for reaching a person now.
`attention_report()` serves the order with the two ways it does not cover §5.2, so the crossing is
visible rather than inferred.
"""
from afya.registry.service import CHANNELS

# §5.1's sentence, verbatim, with the word that qualifies it kept: the section says "in rough order",
# and a module that presented this as a strict ranking would be claiming a precision §5.1 declines to
# make. Every use below therefore sorts by position and treats ties and absences as ordinary rather
# than as defects.
ATTENTION_SENTENCE = (
	'Information must live where people already are. In Kenya that is, in rough order of daily '
	'attention: WhatsApp, SMS, radio, Facebook, TikTok, and human conversation.'
)

# §5.1's six entries, in the order the section writes them, each with the §5.2 channel it names.
# Facebook and TikTok are separate entries here and one row in §5.2, which is why this is a list of
# (entry, channel) pairs rather than a list of channels: the duplication is the section's, and
# flattening it here would hide that §5.1 counts places and §5.2 counts channels.
ATTENTION_ORDER: tuple[tuple[str, str], ...] = (
	('WhatsApp', 'whatsapp'),
	('SMS', 'sms'),
	('radio', 'radio'),
	('Facebook', 'social'),
	('TikTok', 'social'),
	('human conversation', 'chw'),
)

# The entries that fold into one channel, and the channels §5.1 does not name. Both are reported so
# a reader meeting a channel list sorted by this order can see what the ordering could not rank.
COLLAPSED: dict[str, tuple[str, ...]] = {'social': ('Facebook', 'TikTok')}
UNRANKED: tuple[str, ...] = tuple(c for c in CHANNELS if c not in {s for _, s in ATTENTION_ORDER})

assert tuple(e for e, _ in ATTENTION_ORDER) == (
	'WhatsApp', 'SMS', 'radio', 'Facebook', 'TikTok', 'human conversation',
), "§5.1's entries, in the section's order"
assert set(s for _, s in ATTENTION_ORDER) | set(UNRANKED) == set(CHANNELS), \
	'every §5.2 channel is either ranked by §5.1 or recorded as unranked'
assert not (set(s for _, s in ATTENTION_ORDER) & set(UNRANKED)), 'a channel cannot be both'

# The rank is the position of the channel's *first* mention, so `social` takes Facebook's place rather
# than TikTok's — the earlier of its two entries is the one that decides where the channel sits.
_RANK: dict[str, int] = {}
for _i, _pair in enumerate(ATTENTION_ORDER):
	_RANK.setdefault(_pair[1], _i)


def attention_rank(channel: str) -> int | None:
	"""§5.1's position for a channel, or `None` for one the rationale does not name.

	`None` rather than a large number, because "§5.1 does not rank USSD" and "§5.1 ranks USSD last"
	are different facts and a caller sorting a delivery list needs to tell them apart — the first is
	the section being silent, the second would be this module inventing an answer.
	"""
	assert channel in CHANNELS, f'{channel} is not a §5.2 channel'
	return _RANK.get(channel)


def order_channels(channels: list[str]) -> list[str]:
	"""A channel list in §5.1's attention order, with the unranked ones kept and put last.

	Stable, so two channels §5.1 ranks equally (only `social` can, and it is one channel) or two it
	does not rank keep the caller's relative order. The unranked channels go last rather than being
	dropped: a delivery list that lost USSD because the rationale is silent about it would be a
	channel removed by an ordering, which is not what §5.1 is for.
	"""
	for c in channels:
		assert c in CHANNELS, f'{c} is not a §5.2 channel'
	ranked = [c for c in channels if attention_rank(c) is not None]
	unranked = [c for c in channels if attention_rank(c) is None]
	return sorted(ranked, key=lambda c: _RANK[c]) + unranked


def attention_report() -> dict[str, object]:
	"""§5.1 as served data: the sentence, the order, and the two ways it does not cover §5.2.

	The crossings travel with the order because an ordering served without the entries it folds and
	the channels it omits is a second document rather than a check — the same reason §7.1's taxonomy
	route carries its divergences.
	"""
	return {
		'sentence': ATTENTION_SENTENCE,
		'order': [{'entry': e, 'channel': c} for e, c in ATTENTION_ORDER],
		'collapsed': {c: list(names) for c, names in COLLAPSED.items()},
		'unranked': list(UNRANKED),
	}
