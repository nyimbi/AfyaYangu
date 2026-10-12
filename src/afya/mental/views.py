"""Mental health: validated screens (PHQ-9, GAD-7), WHO-5 well-being, mood log and support.

This module holds the request/response shapes; the instruments themselves live in
`afya.mental.instruments` (item banks, scale, cut-points) and the coping, outbreak and referral
content in `afya.mental.support`. Splitting them is deliberate: the item text is a transcription of
a published instrument and the cut-points are the publisher's, so they are worth a file whose diff
is readable against the source, while the support content is prose this app owns.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class WHO5(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	scores: list[int] = Field(min_length=5, max_length=5)  # 0-5 each, past-2-weeks well-being
	# The locality, for §AI-003's "increase in 'I feel unwell' check-ins" — the one bullet whose
	# source is a person saying so rather than an event the app observes on its own.
	county: str | None = None

	@property
	def raw(self) -> int:
		return sum(self.scores) * 4  # 0-100 scale per WHO-5 convention


class WellbeingVerdict(BaseModel):
	model_config = MODEL_CONFIG
	raw: int = Field(ge=0, le=100)
	band: str = Field(pattern=r'^(good|low|very_low)$')
	advise: str


class Screening(BaseModel):
	"""One administration of PHQ-9 or GAD-7.

	`answers` is positional and its length is checked against the instrument's item bank, so a
	seven-answer PHQ-9 is refused rather than scored as a shorter questionnaire. `lang` is what the
	person was actually shown: `items` in the response is served in that language, and where the
	instrument has no form in it the service says so instead of labelling English items with it.
	"""
	model_config = MODEL_CONFIG
	subject_ref: str
	instrument: str = Field(pattern=r'^(phq9|gad7)$')
	answers: list[int] = Field(min_length=1, max_length=9)
	lang: str = Field(default='en', pattern=r'^(en|sw)$')
	administered_at_iso: str
	county: str | None = None


class ScreeningResult(BaseModel):
	model_config = MODEL_CONFIG
	instrument: str
	lang: str
	# What the person was shown, so a client renders the same items the score came from and a later
	# reader can see which language produced the number.
	items: list[str]
	options: list[str]
	timeframe: str
	answers: list[int]
	total: int = Field(ge=0, le=27)
	band: str
	severity_note: str
	# PHQ-9 only, and never folded into `band`: a total of 4 with item 9 positive is a person at risk
	# in the mildest band, and a band alone would wave them through.
	self_harm_item_positive: bool
	advise: str
	# True when the instrument has no form in the requested language and the English items were
	# served instead. Served rather than refused, because an English screen beats no screen — but
	# named, because a caller that does not know has a score from a person who could not read it.
	served_in_english_instead: bool = False
	# GAD-7 only: the manual's recommended threshold for further evaluation, which is not one of the
	# severity bands. `None` for PHQ-9, whose bands are its thresholds.
	further_evaluation: bool | None = None


COUNSELLING_LINES: tuple[dict[str, str], ...] = (
	{'name': 'Befrienders Kenya (emotional support)', 'number': '0722 178 177', 'hours': 'daily', 'verified': 'False'},
	{'name': 'NACADA helpline (substance abuse)', 'number': '1192', 'hours': '24/7', 'verified': 'False'},
	{'name': 'Emergency', 'number': '1199 (ambulance) / 719 (MoH)', 'hours': '', 'verified': 'False'},
)


class MentalHealthService:
	def assess(self, who5: WHO5) -> WellbeingVerdict:
		assert all(0 <= s <= 5 for s in who5.scores), 'item bounds'
		raw = who5.raw
		if raw < 29:
			verdict_band, advise = 'very_low', 'Likely depression range. Please contact a counselling line today; consider 719 for referral. You are not alone.'
		elif raw < 50:
			verdict_band, advise = 'low', 'Well-being is low: talk to someone you trust; use the counselling lines listed; book a facility visit.'
		else:
			verdict_band, advise = 'good', 'Well-being within normal range. Keep strong routines: sleep, movement, people.'
		return WellbeingVerdict(raw=raw, band=verdict_band, advise=advise)

	def lines(self) -> list[dict[str, str]]:
		return list(COUNSELLING_LINES)
