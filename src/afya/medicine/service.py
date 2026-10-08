"""Medicine service — PPB verification port + client, interactions, dosing, stock crowdsourcing."""
from typing import Protocol

from afya.logmixin import LogMixin
from afya.medicine.views import (
	DoseRequest, DoseResult, StockReport, VerifyRequest, VerifyResult,
)


class PPBRegistryPort(Protocol):
	async def verify(self, req: VerifyRequest) -> VerifyResult: ...


class PPBStubClient:
	"""Offline fallback registry used when PPB endpoint unreachable."""

	async def verify(self, req: VerifyRequest) -> VerifyResult:
		return VerifyResult(genuine=False, source='offline_stub', notes='PPB unreachable — verify manually at pharmacy')


class MedicineService(LogMixin):
	_INTERACTIONS: tuple[str, ...] = (
		'warfarin|aspirin:major:additive bleeding risk',
		'metronidazole|alcohol:moderate:disulfiram-like reaction',
		'artemether|ketoconazole:moderate:QT prolongation',
		'rifampicin|oral_contraceptives:major:reduced efficacy',
	)

	def __init__(self, ppb: PPBRegistryPort) -> None:
		self._ppb = ppb
		assert self._ppb is not None
		self._stock: list[StockReport] = []

	async def verify(self, req: VerifyRequest) -> VerifyResult:
		assert req.batch_number and req.gtin, 'batch+gtin required'
		return await self._ppb.verify(req)

	def check_interactions(self, drugs: list[str]) -> list[str]:
		assert len(drugs) <= 50, 'unreasonable polypharmacy'
		found: list[str] = []
		for idx, left in enumerate(drugs):
			for right in drugs[idx + 1:]:
				for row in self._INTERACTIONS:
					pair, severity, note = row.split(':', 2)
					names = pair.split('|')
					if {left.lower(), right.lower()} == set(names):
						found.append(f'{severity.upper()} {left}+{right}: {note}')
		self._log_info('interaction check', hits=len(found))
		return found

	def dose(self, req: DoseRequest) -> DoseResult:
		total = round(req.weight_kg * req.mg_per_kg, 1)
		warns: list[str] = []
		if req.weight_kg < 5:
			warns.append('paediatric low-weight: confirm with clinician')
		if req.mg_per_kg > 60:
			warns.append('high mg/kg: verify source guideline')
		return DoseResult(drug=req.drug, total_mg=total, warns=warns)

	async def report_stock(self, report: StockReport) -> None:
		self._stock.append(report)
		assert len(self._stock) < 10_000, 'unbounded stock store'

	def stock_for(self, drug: str, facility_id: str) -> list[StockReport]:
		return [r for r in self._stock if r.drug == drug and r.facility_id == facility_id]