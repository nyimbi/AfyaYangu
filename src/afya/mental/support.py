"""§REC-005's other four bullets: coping strategies, outbreak-specific support, and referral.

§REC-005 asks for six things and `afya.mental` carried one of them (the crisis-line directory).
`instruments.py` takes the first — PHQ-9 and GAD-7 as instruments with item text rather than a
positional score list. This module takes the remaining four:

* **Mood tracking.** A series, not a screening. WHO-5 and PHQ-9 are point measurements of a
  fortnight; a mood log is a person's own daily reading, and the two are stored separately because
  a trend over a person's own scores and a validated instrument's total are not the same number.
* **Coping strategies and psychoeducation.** Derived from WHO's *Psychological first aid: guide for
  field workers* (`sources/who-pfa/`), which is archived here in English **and Kiswahili** — the
  source's own translation, so the Kiswahili guidance is the publisher's words and not mine.
* **Outbreak-specific: isolation distress, grief support, healthcare worker burnout.** The three
  conditions §REC-005 names, each with guidance drawn from the same source, and each a *named*
  condition rather than a band on a total, because "your PHQ-9 is 14" does not tell someone in
  isolation that what they are feeling has a name and a route.
* **Referral to services.** `assess` used to return referral *advice* as prose ("consider 719 for
  referral") and nothing that routes anyone anywhere. A referral here names the service, records
  who it is for, and reports what it could not reach.

**The line PFA draws, and why it shapes the content.** The guide states plainly that PFA "is not
professional counselling", "is not 'psychological debriefing'", and "is not about pressuring people
to tell you their feelings". So the coping guidance here does not tell anyone to recount the
traumatic event, and no text in this module promises that talking about it will help. That is not a
stylistic preference — a self-check that pushes a distressed person into an unguided debrief is
doing the thing the source explicitly says not to do, and it is the commonest thing a
wellness feature gets wrong.

**Stigma.** §REC-005's "why this matters" names stigma as one of the four consequences. Nothing here
is labelled with a diagnosis, no response says "you have depression", and the Kiswahili content
uses the source's own register rather than a translated clinical term.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# The three outbreak-specific conditions §REC-005 names, as slugs rather than prose so a client can
# route on them. They are not diagnoses and are not labelled as such anywhere a person reads.
OUTBREAK_CONDITIONS: tuple[str, ...] = ('isolation_distress', 'grief', 'worker_burnout')

# --- Psychoeducation, from WHO PFA -----------------------------------------------------------------
#
# Each entry is one coping strategy in the source's own terms. `slug` is what a client routes on;
# `title` and `body` are what a person reads. The Kiswahili is the archived translation's wording,
# kept to the source's register: the guide addresses a *helper* ("wasikize watu na uwasaidie
# kutulia" — listen to people and help them feel calm), so where the app addresses the person
# directly the text is adapted from that instruction rather than quoted, and it says so.
#
# The action principles themselves are the source's structure — look, listen, link, rendered in the
# Kiswahili edition as Tazama, Sikiliza, Unganisha — and they are the spine of the coping list
# rather than a decoration on it.

COPING_STRATEGIES: tuple[dict[str, str | dict[str, str]], ...] = (
	{
		'slug': 'steady-yourself',
		'en': {'title': 'Steady yourself first',
		       'body': 'Before you decide anything, take a few moments to be calm, be safe and think '
		               'before you act. Breathe slowly. You do not have to solve everything today.'},
		'sw': {'title': 'Tulia kwanza',
		       'body': 'Kabla ya kuamua kitu chochote, chukua muda kutulia, kuhakikisha usalama na '
		               'kufikiri kabla ya kutenda. Vuta pumzi taratibu. Huna budi kutatua kila kitu leo.'},
	},
	{
		'slug': 'basic-needs-first',
		'en': {'title': 'Cover the basics',
		       'body': 'Food, water, shelter, sleep and safety come first, and distress is worse '
		               'without them. Sorting out a meal and a place to sleep is mental health care, '
		               'not a distraction from it.'},
		'sw': {'title': 'Shughulikia mahitaji ya kimsingi',
		       'body': 'Chakula, maji, malazi, usingizi na usalama huja kwanza, na mfadhaiko huwa '
		               'mbaya zaidi bila hivyo. Kupanga chakula na mahali pa kulala ni huduma ya afya '
		               'ya akili, si kukengeuka kutoka kwayo.'},
	},
	{
		'slug': 'keep-contact',
		'en': {'title': 'Stay in contact with people',
		       'body': 'Being with people you trust helps. Keep contact with family and friends by '
		               'phone or in person where it is safe, even briefly. You do not have to talk '
		               'about what happened to be together.'},
		'sw': {'title': 'Endelea kuwasiliana na watu',
		       'body': 'Kuwa na watu unaowaamini kunasaidia. Endelea kuwasiliana na familia na marafiki '
		               'kwa simu au ana kwa ana pale ambapo ni salama, hata kwa muda mfupi. Huna budi '
		               'kuzungumzia yaliyotokea ili muwe pamoja.'},
	},
	{
		'slug': 'no-pressure-to-talk',
		'en': {'title': 'You do not have to tell the story',
		       'body': 'Talking through a distressing event in detail, on someone else\'s schedule, '
		               'does not help and can make things worse. Share what you want, when you want. '
		               'Being listened to is not the same as being made to explain.'},
		'sw': {'title': 'Huna budi kueleza kisa',
		       'body': 'Kueleza kwa kina tukio la kufadhaisha, kwa muda wa mtu mwingine, hakusaidii na '
		               'kunaweza kuzidisha hali. Shiriki unachotaka, wakati unataka. Kusikilizwa si sawa '
		               'na kulazimishwa kueleza.'},
	},
	{
		'slug': 'routines',
		'en': {'title': 'Keep small routines',
		       'body': 'Sleep, movement and regular meals steady a person more than they look like '
		               'they should. Keep the routines you can and let the rest go for now.'},
		'sw': {'title': 'Dumisha mazoea madogo',
		       'body': 'Usingizi, mwendo na milo ya kawaida humtuliza mtu zaidi kuliko inavyodhaniwa. '
		               'Dumisha mazoea unayoweza na uache mengine kwa sasa.'},
	},
	{
		'slug': 'know-when-to-refer',
		'en': {'title': 'Know when to hand over',
		       'body': 'If someone is not able to care for themselves or others, is a danger to '
		               'themselves or someone else, or you are unsure, link them to a health worker '
		               'or one of the lines below. Passing it on is the right move, not a failure.'},
		'sw': {'title': 'Jua wakati wa kumkabidhi mwingine',
		       'body': 'Kama mtu hawezi kujitunza au kutunza wengine, ni hatari kwake au kwa mtu '
		               'mwingine, au huna uhakika, muunganishe na mhudumu wa afya au moja ya namba '
		               'hapa chini. Kumkabidhi mwingine ni hatua sahihi, si kushindwa.'},
	},
)

# The three outbreak-specific conditions, each with what the source supports and what to do. The
# `signs` list is what a person can recognise in themselves; it is not a diagnostic criterion and
# none of the three is presented as one.
OUTBREAK_SUPPORT: tuple[dict[str, object], ...] = (
	{
		'slug': 'isolation_distress',
		'en': {
			'title': 'Distress while isolating or in quarantine',
			'body': 'Being kept apart from people is hard in itself, and it is worse when you are '
			        'frightened. Keep contact by phone, keep a routine, and tell a health worker if '
			        'you are not sleeping or eating. Isolation is a measure, not a punishment, and '
			        'asking for help does not break it.',
			'signs': ['not sleeping or sleeping far too much', 'no appetite',
			          'fear that will not settle', 'feeling you cannot cope alone'],
		},
		'sw': {
			'title': 'Mfadhaiko wakati wa kujitenga au karantini',
			'body': 'Kutengwa na watu ni kugumu yenyewe, na huwa kugumu zaidi ukiwa na hofu. Endelea '
			        'kuwasiliana kwa simu, dumisha mazoea, na mwambie mhudumu wa afya kama hulali au '
			        'huli. Kujitenga ni hatua ya kinga, si adhabu, na kuomba msaada hakuvunji hiyo '
			        'hatua.',
			'signs': ['kutolala au kulala kupita kiasi', 'kukosa hamu ya kula',
			          'hofu isiyotulia', 'kujiona hauwezi kuvumilia peke yako'],
		},
	},
	{
		'slug': 'grief',
		'en': {
			'title': 'Grief and bereavement',
			'body': 'Crying, sadness and grief after a death are expected reactions and not an '
			        'illness. Outbreak deaths are often sudden, sometimes without a funeral, and '
			        'sometimes without being able to be with the person — that makes grief harder, '
			        'not weaker. Grief has no schedule. If it is still stopping you from living '
			        'months on, that is worth a health worker.',
			'signs': ['crying, sadness, low mood', 'numbness', 'anger at what happened',
			          'feeling you never got to say goodbye'],
		},
		'sw': {
			'title': 'Huzuni na msiba',
			'body': 'Kulilia, huzuni na majonzi baada ya kifo ni mwitikio wa kawaida, si ugonjwa. '
			        'Vifo vya mlipuko mara nyingi hutokea ghafla, wakati mwingine bila mazishi, na '
			        'wakati mwingine bila nafasi ya kuwa na mtu huyo — hiyo hufanya huzuni kuwa '
			        'ngumu zaidi, si dhaifu. Huzuni haina ratiba. Kama bado inakuzuia kuishi baada '
			        'ya miezi, hiyo inafaa kuonwa na mhudumu wa afya.',
			'signs': ['kulilia, huzuni, hali ya chini ya moyo', 'kukosa hisia',
			          'hasira kwa yaliyotokea', 'kujiona hukupata nafasi ya kuaga'],
		},
	},
	{
		'slug': 'worker_burnout',
		'en': {
			'title': 'Health and response workers',
			'body': 'Working an outbreak is a long shift with no end in sight, and the people who '
			        'keep going longest are often the last to say they are struggling. Tiredness, '
			        'irritability, dread before a shift and feeling nothing at all are common and '
			        'they are not a lack of commitment. Rotate duties, sleep when you can, and use '
			        'the same lines you send others to.',
			'signs': ['exhaustion that sleep does not fix', 'irritability with colleagues or patients',
			          'dreading the shift', 'feeling detached or numb'],
		},
		'sw': {
			'title': 'Wahudumu wa afya na wa mwitikio',
			'body': 'Kufanya kazi wakati wa mlipuko ni zamu ndefu isiyo na mwisho unaoonekana, na '
			        'wale wanaoendelea kwa muda mrefu mara nyingi ni wa mwisho kusema wanahangaika. '
			        'Uchovu, kukasirika haraka, kuogopa kabla ya zamu na kukosa hisia kabisa ni '
			        'kawaida na si ukosefu wa kujitolea. Badilishaneni majukumu, laleni mnapoweza, na '
			        'tumieni namba zile zile mnazowatuma wengine.',
			'signs': ['uchovu ambao usingizi hautulii', 'kukasirika na wenzako au wagonjwa',
			          'kuogopa zamu', 'kujiona mbali au kukosa hisia'],
		},
	},
)


class CopingStrategy(BaseModel):
	model_config = MODEL_CONFIG
	slug: str
	title: str
	body: str


class OutbreakGuidance(BaseModel):
	model_config = MODEL_CONFIG
	slug: str = Field(pattern=r'^(isolation_distress|grief|worker_burnout)$')
	title: str
	body: str
	signs: list[str]


# --- Mood tracking ------------------------------------------------------------------------------

class MoodEntry(BaseModel):
	"""One day's own reading. A person's score, not an instrument's.

	`score` is 0–10 and it is deliberately *not* the same scale as PHQ-9's 0–27 or WHO-5's 0–100.
	Keeping them apart is the point: a mood log is a person's own trend and a validated instrument's
	total is a measurement with cut-points behind it, and averaging the two produces a number with
	neither property. `note` is free text and is the person's own.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	score: int = Field(ge=0, le=10)
	logged_at_iso: str
	note: str = ''
	# §AI-003's fifth signal reads low check-ins. A mood entry is not a WHO-5 and does not emit on
	# its own; the county is carried so the entry can be attributed if a surface decides to.
	county: str | None = None


class MoodTrend(BaseModel):
	model_config = MODEL_CONFIG
	entries: int = Field(ge=0)
	mean: float
	direction: str = Field(pattern=r'^(rising|falling|flat|too_few)$')
	# Named so a client can say *why* there is no direction rather than drawing a flat line over a
	# gap: a trend needs readings, and "no direction" from two entries is not a steady mood.
	window_days: int = Field(ge=1)
	advise: str


# --- Referral -----------------------------------------------------------------------------------

class ReferralRequest(BaseModel):
	"""A request to be referred, not a referral. The service builds the record.

	Separate from `ServiceReferral` because a caller must not be able to supply the referral id, the
	service list, or the unreachable list: those are the app's statements about what it can reach,
	and a client that could set them could claim a referral to a service nobody checked.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	reason: str = Field(min_length=1)
	urgency: str = Field(default='routine', pattern=r'^(routine|soon|urgent)$')


class ServiceReferral(BaseModel):
	"""A referral that names a service and records what it could not reach.

	The predecessor was a prose sentence in `assess`: "consider 719 for referral". Nothing was
	created, nobody was routed, and no record existed of whether the advice was actionable. This
	carries the service, the reason, and — because a referral to a service that does not exist is
	worse than none — the services that could not be reached, by name.
	"""
	model_config = MODEL_CONFIG
	referral_id: str
	subject_ref: str
	reason: str
	urgency: str = Field(pattern=r'^(routine|soon|urgent)$')
	services: list[dict[str, str]]
	unreachable: list[str]
	advise: str
