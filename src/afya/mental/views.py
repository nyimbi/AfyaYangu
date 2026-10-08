"""Mental health: WHO-5 well-being self-assessment + counselling-line directory (content governance: unverified numbers flagged)."""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class WHO5(BaseModel):
	model_config = MODEL_CONFIG
	subject_ref: str
	scores: list[int] = Field(min_length=5, max_length=5)  # 0-5 each, past-2-weeks well-being

	@property
	def raw(self) -> int:
		return sum(self.scores) * 4  # 0-100 scale per WHO-5 convention


class WellbeingVerdict(BaseModel):
	model_config = MODEL_CONFIG
	raw: int = Field(ge=0, le=100)
	band: str = Field(pattern=r'^(good|low|very_low)$')
	advise: str


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