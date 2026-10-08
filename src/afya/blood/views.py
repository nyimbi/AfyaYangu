"""Blood donor matching — blood-group compatibility + 90-day eligibility + county radius (chronic shortages)."""
from datetime import date, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

COMPATIBILITY: dict[str, tuple[str, ...]] = {  # recipient -> compatible donor groups
	'O-': ('O-',), 'O+': ('O-', 'O+'), 'A-': ('O-', 'A-'), 'A+': ('O-', 'O+', 'A-', 'A+'),
	'B-': ('O-', 'B-'), 'B+': ('O-', 'O+', 'B-', 'B+'), 'AB-': ('O-', 'A-', 'B-', 'AB-'),
	'AB+': ('O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+'),
}


class Donor(BaseModel):
	model_config = MODEL_CONFIG
	donor_ref: str
	blood_group: str = Field(pattern=r'^(O-|O\+|A-|A\+|B-|B\+|AB-|AB\+)$')
	county: str
	last_donation_iso: str | None = None


class BloodRequest(BaseModel):
	model_config = MODEL_CONFIG
	request_id: str
	blood_group: str = Field(pattern=r'^(O-|O\+|A-|A\+|B-|B\+|AB-|AB\+)$')
	county: str
	urgency: str = Field(pattern=r'^(routine|urgent|critical)$')


class DonorMatch(BaseModel):
	model_config = MODEL_CONFIG
	donor_ref: str
	blood_group: str
	county: str
	eligible: bool
	compatible: bool


DONATION_INTERVAL_DAYS = 90


class BloodService:
	def __init__(self) -> None:
		self._donors: dict[str, Donor] = {}
		assert self._donors == {}

	async def register(self, d: Donor) -> Donor:
		assert d.donor_ref, 'donor ref'
		self._donors[d.donor_ref] = d
		return d

	def _eligible(self, d: Donor, today_iso: str) -> bool:
		if d.last_donation_iso is None:
			return True
		return date.fromisoformat(d.last_donation_iso) + timedelta(days=DONATION_INTERVAL_DAYS) <= date.fromisoformat(today_iso)

	def match(self, req: BloodRequest, today_iso: str, limit: int = 10) -> list[DonorMatch]:
		assert req.urgency in ('routine', 'urgent', 'critical'), 'urgency bounds'
		compatible_groups = COMPATIBILITY[req.blood_group]
		out = [
			DonorMatch(donor_ref=d.donor_ref, blood_group=d.blood_group, county=d.county, eligible=self._eligible(d, today_iso), compatible=d.blood_group in compatible_groups)
			for d in self._donors.values()
		]
		ranked = sorted(
			[m for m in out if m.compatible and m.eligible and m.county == req.county],
			key=lambda m: {'O-': 0, 'AB-': 1}.get(m.blood_group, 2),
		) or [m for m in out if m.compatible and m.eligible]
		assert all(m.compatible for m in ranked[:limit]), 'compatibility invariant'
		return ranked[:limit]

	async def record_donation(self, donor_ref: str, today_iso: str) -> Donor:
		d = self._donors[donor_ref]
		assert self._eligible(d, today_iso), 'donor not yet eligible'
		d.last_donation_iso = today_iso
		return d