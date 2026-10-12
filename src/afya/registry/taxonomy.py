"""§7's tier model and feature-ID scheme — the two tables every other section's ids are drawn from.

§7 is three tables and a sentence, and it is the section the whole feature architecture is indexed
by: §7.1 names the four tiers and says what each one is *for*, §7.2 assigns each domain a prefix, and
§7.3 maps every feature id to a tier. Nothing carried any of them. `Tier` existed as an `IntEnum`
with four members and no names, `FeatureSpec.id` had a regex listing fifteen prefixes, and §7.3 was a
table nothing read — which is the shape this repo keeps finding: the ids are enforced, and the
scheme that gives them meaning is prose.

**§7.2 declares sixteen prefixes and the validator accepted fifteen.** The sixteenth is `GTM-xxx`,
Go-to-market, and it is the only prefix in the section with no feature behind it — §7.3's tier map
names no `GTM-` id, and no section of the spec defines one. So the gap is not a missing feature; it
is a declared namespace the code refused to accept, which means a `GTM-001` would have failed
validation with a message listing fifteen prefixes that did not include the one §7.2 gives it.
`PREFIXES` is now §7.2's table and `id_pattern()` is built from it, so the regex and the section
cannot drift.

**§7.1's "Ebola-Specific?" column is a check, not a label.** Three of the four tiers are No and
Tier 4 is Yes, and §11's opening sentence is the rule it encodes: "Dormant until triggered by
PHEOC." A feature the section marks Ebola-specific that the registry places outside Tier 4 is a
feature the activation gate cannot reach, and `ebola_specific_mismatches()` reports it. That is the
same crossing `registry/activation.py` already makes from the other direction — it asks which Tier-4
features no §11.1 trigger reaches; this asks which ids §7.3 places by tier in a way §7.1's column
contradicts.

**§7.1's "Usage Frequency" is the column nothing else states.** "First session", "Weekly–monthly",
"Daily", "Dormant → daily in outbreak" is what §22.3's engagement targets and §20.6's retention table
are both built on, and neither says it: §20.6 gives each mechanism a cadence in days and §22.3 gives
DAU/MAU a ratio, and the tier's own expected frequency — the thing a retention number is compared
against — was nowhere. It is carried as `usage_frequency` so a reader can see that a Tier-1 feature
used daily is not the same as a Tier-3 feature used daily.

**The strategic logic is the section's closing sentence** and is carried verbatim, because it is the
argument for the whole tier order: a person who installs for the facility finder in November has the
outbreak module in March without a second adoption effort. `install_earns_later_tier()` is that
sentence as a property the tier map must satisfy.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §7.2's prefix table, verbatim and in the section's order. `GTM` is the row the id regex was missing:
# §7.3's tier map names no `GTM-` feature and no section defines one, so accepting the prefix changes
# no existing id — it stops the code refusing a namespace the spec declares.
PREFIXES: tuple[tuple[str, str], ...] = (
	('CHAN', 'Channel features (Section 5)'),
	('INF', 'Information and content'),
	('TRI', 'Triage'),
	('FND', 'Find a facility / service'),
	('MED', 'Medicine and pharmacy'),
	('EMG', 'Emergency'),
	('REC', 'Records and health wallet'),
	('MON', 'Monitoring and reminders'),
	('SENS', 'Sensor-based capabilities'),
	('LOC', 'Location and proximity'),
	('COM', 'Community and CHW'),
	('ALT', 'Alerting'),
	('AI', 'AI and analytics'),
	('ACC', 'Accessibility'),
	('SEC', 'Security and privacy'),
	('GTM', 'Go-to-market'),
)

PREFIX_DOMAIN: dict[str, str] = dict(PREFIXES)


def id_pattern() -> str:
	"""The `FeatureSpec.id` regex, built from §7.2 rather than restated beside it.

	A second spelling is what let the regex fall one prefix behind the table: the pattern was written
	once by hand and the table is prose, so adding a row to the section could not change the code.
	"""
	return '^(' + '|'.join(prefix for prefix, _ in PREFIXES) + r')-\d{3}$'


def prefix_of(feature_id: str) -> str:
	"""The §7.2 domain a feature id belongs to, refusing an unknown prefix rather than guessing."""
	assert feature_id and '-' in feature_id, f'{feature_id!r} is not a §7.2 feature id'
	prefix = feature_id.split('-', 1)[0]
	assert prefix in PREFIX_DOMAIN, f'{prefix} is not one of §7.2’s prefixes'
	return prefix


def domain_of(feature_id: str) -> str:
	"""The domain name §7.2 gives a feature id's prefix — what the id means, not what it spells."""
	return PREFIX_DOMAIN[prefix_of(feature_id)]


class TierSpec(BaseModel):
	"""One §7.1 row: the tier, the name the section gives it, what it is for, how often it is used, and
	whether the section marks it Ebola-specific.

	`ebola_specific` is the column §11's dormancy rule rests on — three tiers are No and Tier 4 is Yes
	— and `usage_frequency` is the expectation §22.3's engagement targets and §20.6's retention table
	are both measured against without either stating it.
	"""

	model_config = MODEL_CONFIG
	tier: int = Field(ge=1, le=4)
	name: str = Field(min_length=1)
	purpose: str = Field(min_length=1)
	usage_frequency: str = Field(min_length=1)
	ebola_specific: bool

	@property
	def dormant(self) -> bool:
		"""§11's opening sentence — "Dormant until triggered by PHEOC" — read off §7.1's own column
		rather than asserted separately: the tier the section marks Ebola-specific is the tier that
		sleeps until an outbreak, and the three it does not are always on."""
		return self.ebola_specific


# §7.1's four rows, verbatim. `tier` is 1..4 and matches `registry.service.Tier`'s numbering; the
# cross-cutting tier §7.3 names is not a §7.1 row — §7.1's table has four tiers and cross-cutting is
# where §7.3 files features that belong to none of them.
TIERS: tuple[TierSpec, ...] = (
	TierSpec(tier=1, name='Earns the Download', purpose='Value in 60 seconds',
		usage_frequency='First session', ebola_specific=False),
	TierSpec(tier=2, name='Earns the Return Visit', purpose='Repeat utility',
		usage_frequency='Weekly–monthly', ebola_specific=False),
	TierSpec(tier=3, name='Earns the Home Screen', purpose='Daily habit',
		usage_frequency='Daily', ebola_specific=False),
	TierSpec(tier=4, name='Outbreak Superpower', purpose='Response capability',
		usage_frequency='Dormant → daily in outbreak', ebola_specific=True),
)

TIER: dict[int, TierSpec] = {row.tier: row for row in TIERS}

# §7.1's closing paragraph, verbatim. It is the argument for the tier order and the property
# `install_earns_later_tier()` checks, so it is carried as the section's own words rather than
# paraphrased into a docstring a reader has to trust.
STRATEGIC_LOGIC = (
	'A user who installs the app in November for the facility finder automatically has outbreak '
	'surveillance in their pocket in March. Tier 4 needs no separate adoption effort because Tiers '
	'1–3 already earned the install.'
)

assert tuple(r.tier for r in TIERS) == (1, 2, 3, 4), 'the §7.1 rows must be the four tiers in order'
assert [r.tier for r in TIERS if r.ebola_specific] == [4], \
	'§7.1 marks exactly one tier Ebola-specific, and it is Tier 4'


def tier_spec(tier: int) -> TierSpec:
	assert tier in TIER, f'{tier} is not one of §7.1’s four tiers'
	return TIER[tier]


def install_earns_later_tier() -> bool:
	"""§7.1's strategic logic as a property: the tiers a first session reaches are the ones that earn
	the install, and every later tier is dormant behind them rather than requiring its own adoption.

	It holds when Tier 1 is the only tier with a first-session frequency and the Ebola-specific tier
	is the last one. A tier map where Tier 4 were reachable at install would make the section's
	argument false — the outbreak module would need its own adoption effort after all.
	"""
	first_session = [r.tier for r in TIERS if r.usage_frequency == 'First session']
	return first_session == [1] and TIER[4].ebola_specific and not any(
		r.ebola_specific for r in TIERS if r.tier != 4
	)


# --- §7.3's tier-to-feature map ------------------------------------------------------------

def _expand(tiers: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
	"""§7.3 writes ranges as `FND-001…005` and singles as `TRI-003`. Expanding them here rather than
	in the test means the map is a set of ids a check can compare, and a reader can still see the
	section's own spelling in the literal below."""
	out: list[str] = []
	for prefix, span in tiers:
		if '…' in span:
			first, last = span.split('…')
			out += [f'{prefix}-{n:03d}' for n in range(int(first), int(last) + 1)]
		else:
			out.append(f'{prefix}-{span}')
	return tuple(out)


# §7.3's five rows, verbatim. This is a *summary* and two of its rows are coarser than the sections
# they summarise: §7.3 lists `SENS-001…008` under Tier 4, while §14 gives each sensor its own tier —
# §14.3 is "1 (basic) / 4 (outbreak-enhanced)", §14.5 "1 (basic) / 4 (monitoring)", §14.6
# "2 (basic) / 4 (outbreak)", §14.7 and §14.8 are "3". The registry follows §14, and `DIVERGENCES`
# records where the two disagree so the next reader does not have to find it again.
TIER_MAP: tuple[tuple[str, tuple[str, ...]], ...] = (
	('Tier 1', _expand((('TRI', '001'), ('TRI', '002'), ('FND', '001…005'), ('MED', '001…003'),
		('EMG', '001…003'), ('INF', '001…006'), ('LOC', '001')))),
	('Tier 2', _expand((('MON', '001…004'), ('REC', '001'), ('MED', '004'), ('FND', '006'),
		('INF', '007'), ('ALT', '003')))),
	('Tier 3', _expand((('REC', '002…006'), ('MON', '005…008'), ('ALT', '001…002'),
		('INF', '008…010'), ('COM', '005')))),
	('Tier 4', _expand((('TRI', '003'), ('MON', '009'), ('COM', '101…104'), ('LOC', '002…005'),
		('SENS', '001…008'), ('AI', '001…003'), ('ALT', '004')))),
	('Cross-cutting', _expand((('ACC', '001…005'), ('SEC', '001…006'), ('AI', '004…005')))),
)

# §7.3's summary against the per-feature sections it summarises, and against Appendix B's own tier
# column — which is a *third* statement of the same fact and disagrees with §14 on two ids. Each row
# is a `TierDivergence` whose every field the tests check against the spec, so a row that misstates
# the section it cites fails rather than being trusted. The first cut of this table was prose and
# two of its four notes were false: SENS-007's said "Followed §14.7" beside a registry tier of 2
# while §14.7 says 3, and §14.8's Tier 3 against a registry Tier 4 was recorded nowhere at all. A
# note a reader cannot check is a note that drifts — the §13.1 lossy-enum defect wearing a comment's
# clothes.
class TierDivergence(BaseModel):
	"""One sensor whose tier three tables state differently.

	`section` and `section_tier_cell` are §14's own heading number and `**Tier:**` cell verbatim, so
	the register quotes the section rather than paraphrasing it. `appendix_b_tier` is the third
	statement — Appendix B's tier column, which agrees with §14 on three of the five and disagrees
	on two — carried because a register that compared only two of the three tables would have read
	as complete. `registry_tier` is what the code carries, and the disagreements among the four are
	the finding, reported rather than reconciled: §7.3 is a summary, §14 is the detail, and neither
	is overruled here.
	"""

	model_config = MODEL_CONFIG
	feature_id: str
	section: str = Field(min_length=1)
	section_tier_cell: str = Field(min_length=1)
	appendix_b_tier: str = Field(min_length=1)
	registry_tier: int = Field(ge=1, le=4)


# §7.3 lists every sensor in Tier 4; §14 gives each its own tier and Appendix B states a third
# value. Rows are here only where at least two of the three disagree with what the registry carries.
DIVERGENCES: tuple[TierDivergence, ...] = (
	TierDivergence(feature_id='SENS-003', section='14.3',
		section_tier_cell='1 (basic) / 4 (outbreak-enhanced)', appendix_b_tier='1', registry_tier=1),
	TierDivergence(feature_id='SENS-005', section='14.5',
		section_tier_cell='1 (basic) / 4 (monitoring)', appendix_b_tier='2', registry_tier=2),
	TierDivergence(feature_id='SENS-006', section='14.6',
		section_tier_cell='2 (basic) / 4 (outbreak)', appendix_b_tier='2', registry_tier=2),
	TierDivergence(feature_id='SENS-007', section='14.7',
		section_tier_cell='3', appendix_b_tier='2', registry_tier=2),
	TierDivergence(feature_id='SENS-008', section='14.8',
		section_tier_cell='3', appendix_b_tier='4', registry_tier=4),
)

DIVERGENT_IDS: frozenset[str] = frozenset(d.feature_id for d in DIVERGENCES)

TIER_OF: dict[str, str] = {feature_id: tier for tier, ids in TIER_MAP for feature_id in ids}


def spec_tier(feature_id: str) -> str:
	"""The §7.3 tier a feature id is listed under, refusing an id the map does not name rather than
	returning None. §7.3 is a summary of the spec's own features, so an id it does not name is either
	a typo or a feature the summary has not caught up with — and both need saying."""
	assert feature_id in TIER_OF, f'§7.3 lists no {feature_id}'
	return TIER_OF[feature_id]


def mapped_feature_ids() -> frozenset[str]:
	return frozenset(TIER_OF)
