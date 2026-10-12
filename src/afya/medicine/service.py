"""Medicine service — PPB verification port + client, interactions, dosing, stock crowdsourcing."""
from typing import Protocol

from afya.logmixin import LogMixin
from afya.medicine.views import (
	BatchRecall, DoseRequest, DoseResult, ProductDisplay, RegistrationStatus, StockReport,
	VerifyRequest, VerifyResult,
)


class PPBRegistryPort(Protocol):
	async def verify(self, req: VerifyRequest) -> VerifyResult: ...


class PPBStubClient:
	"""Offline fallback registry used when PPB endpoint unreachable.

	It answers `unverified`, not `not_found`. The section's Offline clause promises a cached registry
	rather than a guess, and a stub that reported "this batch is not registered" while holding no
	registry at all would be accusing a medicine on the strength of an empty table — the one failure
	mode in this feature that can kill someone. `genuine` is False either way, so the fail-closed
	behaviour the README claims is unchanged; what changed is that the client can now tell the
	person *why*, and the answer is "we could not check", not "it is fake".
	"""

	async def verify(self, req: VerifyRequest) -> VerifyResult:
		return VerifyResult(status=RegistrationStatus.unverified, source='offline_stub',
			notes='PPB unreachable — verify manually at pharmacy')


# §MED-001's "Display" line reads from the two PPB feeds §18.7 already names: the registry (daily,
# "registered products, status") and recalls (on issue). Neither is a new wire, and `verify` is the
# only caller that needs both at once — which is why the join lives here rather than in the client,
# whose `verify` answers the single-batch question the endpoint is shaped for.
_REGISTRY_NAME_KEYS: tuple[str, ...] = ('product_name', 'name', 'brand_name')
_REGISTRY_MAKER_KEYS: tuple[str, ...] = ('manufacturer', 'marketing_authorisation_holder', 'holder')
_REGISTRY_EXPIRY_KEYS: tuple[str, ...] = ('expiry_iso', 'expiry', 'expires_on')
_REGISTRY_STATUS_KEYS: tuple[str, ...] = ('status', 'registration_status')


def _first(row: dict[str, object], keys: tuple[str, ...]) -> str | None:
	"""The first of `keys` the row carries, as a string.

	PPB's registry field names are not pinned by the spec, and a client that reads one spelling
	would render a blank the day the regulator renames a column. Reading a small set of known
	spellings and saying `None` when none is present keeps the blank honest.
	"""
	for key in keys:
		value = row.get(key)
		if isinstance(value, str) and value.strip():
			return value.strip()
	return None


def registration_outcome(row: dict[str, object] | None, *, recalled: bool) -> RegistrationStatus:
	"""§MED-001's four outcomes, decided from a registry row and the recall feed.

	A recall outranks every other status: a product can be registered, unexpired and still
	withdrawn, and the withdrawal is the fact that matters. An absent row is `not_found`, and a row
	whose status the regulator marks as lapsed is `expired`.
	"""
	if recalled:
		return RegistrationStatus.recalled
	if row is None:
		return RegistrationStatus.not_found
	stated = (_first(row, _REGISTRY_STATUS_KEYS) or '').lower()
	if stated in ('expired', 'lapsed', 'withdrawn', 'suspended'):
		return RegistrationStatus.expired
	return RegistrationStatus.registered


def display_from(row: dict[str, object] | None, status: RegistrationStatus,
	recalls: list[dict[str, object]]) -> ProductDisplay:
	"""The five display fields, assembled from the registry row and the recall rows."""
	if row is None:
		# Nothing to display about a product the registry does not hold, and the recalls list stays
		# empty: a recall row keyed on a batch nobody registered is not this person's medicine.
		return ProductDisplay()
	return ProductDisplay(
		product_name=_first(row, _REGISTRY_NAME_KEYS),
		manufacturer=_first(row, _REGISTRY_MAKER_KEYS),
		registration_status=status,
		expiry_iso=_first(row, _REGISTRY_EXPIRY_KEYS),
		batch_recalls=[_recall(r) for r in recalls],
	)


def _recall(row: dict[str, object]) -> BatchRecall:
	return BatchRecall(
		batch_number=str(row.get('batch') or row.get('batch_number') or ''),
		reason=str(row.get('reason') or 'recalled by the regulator'),
		recalled_at_iso=(str(row['recalled_at_iso']) if row.get('recalled_at_iso') else None),
	)


def _registry_row(data: dict[str, object]) -> dict[str, object] | None:
	"""The product row inside a `/verify` answer, or `None` if the answer carries no product.

	Three shapes are accepted because all three are things a registry plausibly returns and none is
	wrong: a nested `product`/`registry` object, or the fields at the top level. An answer that is
	nothing but `{"genuine": true}` yields `None`, and `None` here is what makes the caller say
	`unverified` rather than invent a product name — the difference between "the regulator confirms
	this batch" and "the regulator confirms this batch is *this medicine*".
	"""
	for key in ('product', 'registry', 'registration'):
		nested = data.get(key)
		if isinstance(nested, dict):
			return dict(nested)
	if any(k in data for k in _REGISTRY_NAME_KEYS + _REGISTRY_MAKER_KEYS + _REGISTRY_STATUS_KEYS):
		return dict(data)
	return None


def _matching_recalls(data: dict[str, object], batch_number: str) -> list[dict[str, object]]:
	"""Recall rows the answer carries for this batch, under either spelling of the key.

	A recall is filtered to the batch the person scanned. A registry that returns every recall it
	holds would otherwise put another batch's withdrawal on this person's screen, which is the kind
	of false alarm that teaches people to ignore the real one.
	"""
	rows = data.get('recalls') or data.get('batch_recalls') or []
	if not isinstance(rows, list):
		return []
	out: list[dict[str, object]] = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		row = dict(row)
		named = str(row.get('batch') or row.get('batch_number') or '')
		if named and named != batch_number:
			continue
		out.append(row)
	return out


def status_from_verify_answer(data: dict[str, object], batch_number: str) -> tuple[RegistrationStatus, dict[str, object] | None, list[dict[str, object]]]:
	"""One PPB `/verify` answer -> the status, the product row and this batch's recalls.

	The rule that matters: a `genuine: false` with no product row behind it is `not_found`, because
	the registry answered and this batch is not in it. An answer carrying *nothing* — no verdict and
	no product — is `unverified`, because a registry that returned an unrecognisable body has not
	told us the medicine is bad, only that we do not know. Folding that into `not_found` is the one
	mistake in this feature that can cost a life in the other direction: a person throws away
	medicine that was fine.
	"""
	recalls = _matching_recalls(data, batch_number)
	row = _registry_row(data)
	if row is None and 'genuine' not in data:
		return RegistrationStatus.unverified, None, []
	if row is None:
		return (RegistrationStatus.not_found if not data.get('genuine')
			else RegistrationStatus.registered), None, recalls
	return registration_outcome(row, recalled=bool(recalls)), row, recalls


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