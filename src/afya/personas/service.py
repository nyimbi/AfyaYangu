"""§4's personas and segments as data, crossed against the surfaces that already exist.

The section names seven people, seven secondary audiences and eight launch priorities. None of it
was in the code, so `readiness()` could report an APK budget met and §22.7 could report an equity
share without either having a population to be right about. What is built here is the table, plus
the crossings that turn it into findings rather than a second document:

* **The language each persona is reached in, against the strings that exist.** §ACC-002 puts Dholuo
  at tier 1 and §CHAN-2's own menu ends "Language: English / Kiswahili / Dholuo / ...", while
  `SUPPORTED_LANGS` is `{'en','sw'}` and `rec()` asserts on it. Persona F is a Dholuo speaker on a
  feature phone reached by SMS, USSD and radio, and the product throws `AssertionError` for her
  language on the triage path. That is a real defect this section exposes, not a modelling gap.

* **The entry point, against §5.2's seven channels.** §5.2's channels are all consumer-facing, and
  three personas do not arrive through one: Mama Zawadi comes in through a county health team
  rollout, Dr. Kimani through a professional rollout and hospital training, Amina through an ANC
  clinic recommendation. Reported rather than forced, because inventing an eighth channel would be
  this module deciding a product question.

* **The segment, against §4.1.** Two §4.3 rows name no persona at all. Reported.

The transcriptions are verbatim so the test can read §4 out of the spec and compare. A persona
summarised in a developer's words is one nobody can check against the section.
"""
from pathlib import Path

from afya.access.views import LANGUAGE_MATRIX
from afya.logmixin import LogMixin
from afya.personas.views import (
	DeviceClass, Persona, PersonaCoverage, Priority, SecondaryPersona, Segment,
)
from afya.privacy.views import RBACRole
from afya.registry.service import CHANNELS
from afya.strings import SUPPORTED_LANGS

REPO_ROOT = Path(__file__).resolve().parents[3]

# §5.2's channel slugs, in the table's own order, against the words §4.1's entry points use for
# them. The map is the crossing: a persona's entry point is prose, and this is what turns it into
# channel slugs so "which of the seven channels does this persona actually arrive through" has an
# answer. `chw` covers the human intermediaries of §5.2 row 5 — §CHAN-5 names SACCO chairmen, faith
# leaders and chemists alongside CHWs, and §4.1's "CHW visit" and "SACCO chairman" are both row 5.
ENTRY_CHANNEL_WORDS: dict[str, tuple[str, ...]] = {
	'radio': ('community radio', 'radio'),
	'sms': ('sms',),
	'ussd': ('ussd',),
	'whatsapp': ('whatsapp',),
	'social': ('tiktok', 'instagram', 'social media', 'social'),
	'chw': ('chw', 'sacco', 'health worker'),
	'native': ('app download', 'app for the'),
}

# §4.1, verbatim. `entry_channels` and `entry_unmapped` are derived in `_personas()` below rather
# than written here, so the split cannot drift from the sentence it splits.
_PRIMARY: tuple[dict[str, object], ...] = (
	{
		'key': 'a', 'name': 'Wanjiku', 'age': 34, 'location': 'Nairobi (Ruaka)',
		'summary': 'Market trader, Android Go phone, 1GB data bundle per week, Swahili-first, '
		           'moderate literacy. Two children aged 4 and 9.',
		'needs': [
			"Know if it's safe to send children to school.",
			'Find a clinic that takes SHA.',
			'Keep immunisation records.',
			'Get alerts about her area.',
		],
		'friction': [
			"Will not spend data on something she isn't sure she needs.",
			'Will not create an account.',
		],
		'entry_point': 'WhatsApp bot forwarded by a friend, then app download for the health wallet.',
		'languages': ['sw'], 'device': DeviceClass.android_go, 'role': None,
		'segments': ['high_risk_counties', 'caregivers_under_5'],
	},
	{
		'key': 'b', 'name': 'Otieno', 'age': 28, 'location': 'Kisumu',
		'summary': 'Boda boda rider, mid-range Android, WhatsApp heavy user, Luo and Swahili, '
		           'high literacy.',
		'needs': [
			'Emergency SOS.',
			'Community alerts.',
			'Somewhere to check if a medicine is genuine before his mother takes it.',
		],
		'friction': ['Wants speed.', 'Will abandon anything with a loading screen.'],
		'entry_point': 'SOS feature recommended by his SACCO chairman.',
		'languages': ['luo', 'sw'], 'device': DeviceClass.android, 'role': None,
		'segments': ['boda_boda_transport'],
	},
	{
		'key': 'c', 'name': 'Mama Zawadi', 'age': 45, 'location': 'Busia (border)',
		'summary': "Community Health Worker, 12 years' experience, Android phone with patchy data.",
		'needs': [
			'Structured case reporting that works offline.',
			'Automatic alerts to her supervisor.',
			'Guidance on what to do with a suspected case.',
			'PPE reminders.',
		],
		'friction': ['Already uses three reporting tools.',
		             'Will reject a fourth unless it saves time.'],
		'entry_point': 'County health team rollout, provisioned account.',
		'languages': [], 'device': DeviceClass.android, 'role': RBACRole.chw,
		'segments': ['community_health_workers', 'high_risk_counties'],
	},
	{
		'key': 'd', 'name': 'Dr. Kimani', 'age': 41, 'location': 'Nairobi',
		'summary': 'Clinician at a county referral hospital isolation unit.',
		'needs': [
			'Prognostic support.',
			'Structured case reporting.',
			'PPE guidance.',
			'Occupational monitoring for himself and his team.',
		],
		'friction': ['Clinical tools must be fast and accurate.',
		             'Will reject anything that adds time.'],
		'entry_point': 'Professional rollout, hospital training.',
		'languages': [], 'device': DeviceClass.professional, 'role': RBACRole.clinician,
		'segments': ['high_risk_counties'],
	},
	{
		'key': 'e', 'name': 'Hassan', 'age': 22, 'location': 'Garissa',
		'summary': 'University student, iPhone, high data usage, social-media native.',
		'needs': [
			'Credible information he can share.',
			'County risk dashboard.',
			'Air quality.',
		],
		'friction': ['Will not use anything that looks government-propaganda or outdated.'],
		'entry_point': 'TikTok/Instagram content, then app for the dashboard.',
		'languages': [], 'device': DeviceClass.iphone, 'role': None,
		'segments': ['students', 'high_risk_counties'],
	},
	{
		'key': 'f', 'name': 'Grace', 'age': 52, 'location': 'Siaya',
		'summary': 'Farmer, basic feature phone, no smartphone, low literacy, Dholuo speaker.',
		'needs': [
			"Know what's going around.",
			'Know what to do if someone in the household is sick.',
			'Reach a health worker.',
		],
		'friction': ['No smartphone at all.', 'Cannot read long text.'],
		'entry_point': 'SMS alerts, USSD menus, community radio, CHW visit.',
		'languages': ['luo'], 'device': DeviceClass.feature_phone, 'role': None,
		'segments': ['general_adult_population'],
	},
	{
		'key': 'g', 'name': 'Amina', 'age': 19, 'location': 'Mombasa',
		'summary': 'Pregnant, first child, smartphone, Swahili and English.',
		'needs': [
			'ANC visit reminders.',
			'Danger signs.',
			'Birth planning.',
			'Facility information.',
		],
		'friction': [],
		'entry_point': 'ANC clinic recommendation, then Tier 2 retention.',
		'languages': ['sw', 'en'], 'device': DeviceClass.smartphone, 'role': None,
		'segments': ['pregnant_women', 'high_risk_counties'],
	},
)

# §4.2, verbatim, in the section's order. `role` is the §17.4 row where one exists and None where
# the section names a group §17.4 has no row for — a pharmacy assistant, a faith leader and a
# school teacher read the product through no role the RBAC table defines.
_SECONDARY: tuple[tuple[str, RBACRole | None], ...] = (
	('County Health Management Team members', RBACRole.county_officer),
	('PHEOC analysts and epidemiologists', RBACRole.pheoc_analyst),
	('Ministry of Health policymakers', None),
	('Pharmacy and chemist staff', None),
	('Faith leaders and community mobilisers', None),
	('Implementing partner field staff', None),
	('School administrators and teachers', None),
)

# §4.3, verbatim: the priority, the segment and the section's own rationale. `key` is a slug so a
# persona can name the segment it belongs to without quoting the prose.
_SEGMENTS: tuple[tuple[str, Priority, str, str], ...] = (
	('high_risk_counties', Priority.p0, 'High-risk counties (border, urban)',
	 'Direct outbreak relevance'),
	('community_health_workers', Priority.p0, 'Community Health Workers',
	 'Force multiplier for adoption and reporting'),
	('caregivers_under_5', Priority.p1, 'Caregivers of children under 5',
	 'Highest health-seeking frequency'),
	('pregnant_women', Priority.p1, 'Pregnant women', 'Highest clinic-contact frequency'),
	('chronically_ill_adults', Priority.p1, 'Chronically ill adults',
	 'Highest daily medication need'),
	('students', Priority.p2, 'Students',
	 'Highest smartphone penetration and social spread'),
	('boda_boda_transport', Priority.p2, 'Boda boda and transport workers',
	 'High mobility, high contact, respected voices'),
	('general_adult_population', Priority.p3, 'General adult population',
	 'Reached primarily via non-app channels'),
)


def _split_entry(entry_point: str) -> tuple[list[str], list[str]]:
	"""The §5.2 channels an entry point names, and the clauses that name none.

	The unit is the comma-separated clause, not the word. An entry point is a sequence of routes —
	"WhatsApp bot forwarded by a friend, then app download for the health wallet" is two — and a
	clause either names a channel or is a route §5.2 has no row for. Splitting on words instead
	leaves connective debris ("forwarded friend then health wallet") that flags all seven personas
	and so flags none: a finding every row produces is not a finding.

	Longest phrase first, so "community radio" is claimed by `radio` before `radio` alone can match
	it, and a phrase already consumed is not matched again — "SMS alerts, USSD menus, community
	radio, CHW visit" is four channels, not five.
	"""
	phrases = sorted(
		((word, slug) for slug, words in ENTRY_CHANNEL_WORDS.items() for word in words),
		key=lambda pair: -len(pair[0]),
	)
	found: list[str] = []
	unmapped: list[str] = []
	for clause in entry_point.lower().split(','):
		text, matched = clause.strip(' .'), False
		for word, slug in phrases:
			if word in text:
				text = text.replace(word, ' ')
				matched = True
				if slug not in found:
					found.append(slug)
		if not matched:
			# "then" is the section's own connective, not part of the route.
			rest = text.strip().removeprefix('then ').strip()
			if rest:
				unmapped.append(rest)
	return [c for c in CHANNELS if c in found], unmapped


def _personas() -> tuple[Persona, ...]:
	rows = []
	for row in _PRIMARY:
		entry = str(row['entry_point'])
		channels, unmapped = _split_entry(entry)
		rows.append(Persona(
			**{k: v for k, v in row.items() if k != 'entry_point'},  # type: ignore[arg-type]
			entry_point=entry, entry_channels=channels, entry_unmapped=unmapped,
		))
	return tuple(rows)


PERSONAS: tuple[Persona, ...] = _personas()

SECONDARY_PERSONAS: tuple[SecondaryPersona, ...] = tuple(
	SecondaryPersona(name=name, role=role) for name, role in _SECONDARY
)

SEGMENTS: tuple[Segment, ...] = tuple(
	Segment(
		key=key, priority=priority, segment=segment, rationale=rationale,
		persona_keys=[p.key for p in PERSONAS if key in p.segments],
	)
	for key, priority, segment, rationale in _SEGMENTS
)

SEGMENTS_BY_KEY: dict[str, Segment] = {s.key: s for s in SEGMENTS}

# The languages §ACC-002 puts at launch, against the ones the string tables can speak. §4.1 is what
# gives this a population: a persona speaking a tier-1 language the product cannot answer in is not
# a coverage statistic, it is Grace being handed an `AssertionError`.
TIER1_LANGS: frozenset[str] = frozenset(
	str(meta['code']) for meta in LANGUAGE_MATRIX.values() if meta['tier'] == 1
)


class PersonaService(LogMixin):
	def __init__(self) -> None:
		assert len({p.key for p in PERSONAS}) == len(PERSONAS), 'persona keys must be unique'
		assert len({s.key for s in SEGMENTS}) == len(SEGMENTS), 'segment keys must be unique'
		for p in PERSONAS:
			unknown = [s for s in p.segments if s not in SEGMENTS_BY_KEY]
			assert not unknown, f'persona {p.key} names segments §4.3 does not have: {unknown}'

	@staticmethod
	def personas() -> list[Persona]:
		return list(PERSONAS)

	@staticmethod
	def persona(key: str) -> Persona:
		for p in PERSONAS:
			if p.key == key:
				return p
		raise KeyError(key)

	@staticmethod
	def secondary() -> list[SecondaryPersona]:
		return list(SECONDARY_PERSONAS)

	@staticmethod
	def segments(priority: Priority | None = None) -> list[Segment]:
		"""§4.3's rows, in priority order. Sorting by `Priority.order` rather than the string is what
		keeps `p10` — if the section ever grows one — from sorting before `p2`. The sort is stable
		and `SEGMENTS` is in the table's order, so two rows at the same priority keep the order the
		section put them in: High-risk counties before Community Health Workers, not alphabetically.
		"""
		rows = [s for s in SEGMENTS if priority is None or s.priority is priority]
		return sorted(rows, key=lambda s: s.priority.order)

	@staticmethod
	def priority_of(key: str) -> Priority:
		"""The highest priority any of a persona's segments carries. A persona in two segments is
		built at the earlier one — §4.3 orders the *launch*, and a person who is both a CHW and a
		resident of a high-risk county is reached when either row is."""
		p = PersonaService.persona(key)
		if not p.segments:
			raise AssertionError(f'persona {key} belongs to no §4.3 segment')
		return min((SEGMENTS_BY_KEY[s].priority for s in p.segments), key=lambda pr: pr.order)

	def unserved_languages(self) -> list[str]:
		"""Tier-1 languages §ACC-002 requires that no string table speaks, and who is left out.

		Reported rather than fixed here: adding a Dholuo triage recommendation is a content and
		clinical-review task, not a modelling one, and a table with a placeholder in it would report
		the gap as closed. `unserved_personas` names the people §4.1 says are waiting on it.
		"""
		return sorted(TIER1_LANGS - SUPPORTED_LANGS)

	def unserved_personas(self) -> list[str]:
		"""The personas who speak a language the product cannot answer in. Named by the section's
		own key and name, because "Dholuo is missing" is a language gap and "persona F (Grace) is
		waiting on it" is the finding."""
		missing = set(self.unserved_languages())
		return [f'{p.key} ({p.name})' for p in PERSONAS if missing & set(p.languages)]

	def unmapped_entry_points(self) -> list[str]:
		"""Entry points §5.2's seven channels do not cover, with what was left over.

		Persona G arrives through "ANC clinic recommendation" and Persona C through "County health
		team rollout" — both real routes the section names and §5.2 has no row for. Reported so the
		channel table and §4 can be reconciled by whoever owns that decision.
		"""
		return [f'{p.key} ({p.name}): {" ".join(p.entry_unmapped)}'
		        for p in PERSONAS if p.entry_unmapped]

	def segments_without_a_persona(self) -> list[str]:
		"""§4.3 rows no §4.1 persona belongs to. A P1 segment with no persona behind it is a launch
		priority resting on a population the section never describes."""
		return [s.key for s in self.segments() if not s.persona_keys]

	def secondary_without_a_role(self) -> list[str]:
		"""§4.2 audiences §17.4 gives no role. Five of the seven read the product through no scope
		the RBAC table defines, which is either a gap in the table or a gap in the audience list."""
		return [s.name for s in SECONDARY_PERSONAS if s.role is None]

	def coverage(self) -> PersonaCoverage:
		"""§4 crossed against the language matrix, the channel table and the RBAC table."""
		unserved = self.unserved_languages()
		unmapped = self.unmapped_entry_points()
		segments_gap = self.segments_without_a_persona()
		secondary_gap = self.secondary_without_a_role()
		notes: list[str] = []
		if unserved:
			notes.append(f'tier-1 languages no string table speaks: {", ".join(unserved)}')
		if unmapped:
			notes.append(f'entry points outside §5.2\'s seven channels: {len(unmapped)}')
		if segments_gap:
			notes.append(f'§4.3 segments with no §4.1 persona: {", ".join(segments_gap)}')
		if secondary_gap:
			notes.append(f'§4.2 audiences with no §17.4 role: {len(secondary_gap)}')
		self._log_info('persona coverage', personas=len(PERSONAS), unserved=len(unserved),
		               unmapped=len(unmapped))
		return PersonaCoverage(
			personas=len(PERSONAS), secondary=len(SECONDARY_PERSONAS), segments=len(SEGMENTS),
			unserved_languages=unserved, unserved_personas=self.unserved_personas(),
			unmapped_entry_points=unmapped, segments_without_a_persona=segments_gap,
			secondary_without_a_role=secondary_gap,
			note='; '.join(notes) if notes else 'every §4 persona is reachable in its own language',
		)
