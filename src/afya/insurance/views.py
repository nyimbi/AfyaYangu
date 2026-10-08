"""SHA / Social Health Authority (NHIF successor) — cover check + facility price transparency (§18.6)."""
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class SHAStatus(BaseModel):
	model_config = MODEL_CONFIG
	member_no_hash: str = Field(pattern=r'^[0-9a-f]{8,64}$')  # never store raw national ID
	product: str = Field(pattern=r'^(SHIF|TAIFA|EDU|SHCP)$')  # Comprehensive/Primary/Education/Chronic
	active: bool
	contributions_current: bool
	valid_thru_iso: str | None = None


class SHACheckRequest(BaseModel):
	model_config = MODEL_CONFIG
	member_no: str = Field(min_length=6, max_length=40)
	purpose: str = Field(default='facility_visit', pattern=r'^(facility_visit|registration|refund)$')


class PriceItem(BaseModel):
	model_config = MODEL_CONFIG
	facility_id: str
	procedure: str = Field(pattern=r'^(c_section|normal_delivery|outpatient|inpatient_day|dialysis|x_ray|theatre)$')
	kes: int = Field(ge=0, le=1_000_000)
	sha_covered: bool


class PriceQuote(BaseModel):
	model_config = MODEL_CONFIG
	procedure: str
	facility_id: str
	kes: int
	out_of_pocket_est: int


def sha_of_member_no(member_no: str) -> str:
	"""Privacy: only the hash of member numbers is ever persisted."""
	import hashlib
	return hashlib.sha256(member_no.encode()).hexdigest()


class InsurancePort(Protocol):
	async def status(self, req: SHACheckRequest) -> SHAStatus: ...


class InlineSHAPort:
	"""Offline fallback: treat as unknown-coverage, never fabricate active cover."""

	async def status(self, req: SHACheckRequest) -> SHAStatus:
		return SHAStatus(
			member_no_hash=sha_of_member_no(req.member_no),
			product='SHIF', active=False,
			contributions_current=False, valid_thru_iso=None,
		)


class InsuranceService:
	def __init__(self, sha: InsurancePort) -> None:
		self._sha = sha
		self._pricebook: list[PriceItem] = []

	async def check(self, req: SHACheckRequest) -> SHAStatus:
		out = await self._sha.status(req)
		assert out.member_no_hash == sha_of_member_no(req.member_no), 'hash binding'
		return out

	async def upsert_price(self, item: PriceItem) -> None:
		self._pricebook = [p for p in self._pricebook if not (p.facility_id == item.facility_id and p.procedure == item.procedure)]
		self._pricebook.append(item)
		assert len(self._pricebook) < 10_000, 'pricebook bounded'

	def quote(self, procedure: str, facility_id: str, sha_active: bool = False) -> PriceQuote | None:
		assert facility_id, 'facility required'
		match = next((p for p in self._pricebook if p.facility_id == facility_id and p.procedure == procedure), None)
		if match is None:
			return None
		return PriceQuote(procedure=procedure, facility_id=facility_id, kes=match.kes,
			out_of_pocket_est=0 if (sha_active and match.sha_covered) else match.kes)

	def cheapest(self, procedure: str) -> PriceItem | None:
		opts = [p for p in self._pricebook if p.procedure == procedure]
		return min(opts, key=lambda p: p.kes) if opts else None