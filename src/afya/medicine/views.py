"""Medicine domain models (MED-001..004, §18.7 PPB)."""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)


class RegistrationStatus(str, Enum):
	"""§MED-001's four named outcomes, as four values.

	`genuine: bool` collapsed them: a recalled medicine and a medicine that was never registered
	both read `False`, and the two call for opposite actions — one is "take it back to where you
	bought it", the other is "this product does not exist, do not take it at all". A boolean is a
	set with the members thrown away, which is the §13.1 lossy-enum defect one level up.
	"""

	registered = 'registered'
	not_found = 'not_found'
	expired = 'expired'
	recalled = 'recalled'
	# The fifth is not one of the section's four and is deliberately not folded into them. "The
	# registry could not be consulted" and "this batch is not in the registry" are different claims,
	# and only one of them is an accusation against a medicine somebody is holding. §MED-001's
	# Offline clause is explicit that the lookup falls back to a cached registry; when even that is
	# unavailable the answer is this, and a client renders it as "we could not check", never as
	# "fake".
	unverified = 'unverified'


class BatchRecall(BaseModel):
	model_config = MODEL_CONFIG
	batch_number: str
	reason: str
	recalled_at_iso: str | None = None


class ProductDisplay(BaseModel):
	"""§MED-001's "Display" line: the five things the person is shown after a scan.

	Every field is optional because a product that is not in the registry has none of them — and
	`None` here is the honest answer, not a placeholder. A caller that fills these in for a
	`not_found` product has invented a medicine.
	"""

	model_config = MODEL_CONFIG
	product_name: str | None = None
	manufacturer: str | None = None
	registration_status: RegistrationStatus | None = None
	expiry_iso: str | None = None
	batch_recalls: list[BatchRecall] = Field(default_factory=list)


class VerifyRequest(BaseModel):
	model_config = MODEL_CONFIG
	batch_number: str = Field(min_length=4, max_length=40)
	gtin: str = Field(pattern=r'^\d{6,14}$')


class SuspiciousReport(BaseModel):
	"""§MED-001's "Report a suspicious medicine" — what one tap sends to the regulator.

	This was a bare `dict[str, object]` on the route, which is the one body in this tree that
	skipped `extra='forbid'` — and the one place it matters most, because the dict is forwarded
	verbatim to the PPB intake. A client that misspelled `batch` sent the regulator a report with no
	batch on it and got a case reference back for it.

	`photo_sha256` rather than the image: §18.7's row is "Report with photo", and the photo travels
	through the evidence pipeline that hashes, dedupes and size-caps every other image in the app
	(§SENS-004). What goes to the regulator is the reference, and the report is attributable
	because the route is self-scoped.
	"""

	model_config = MODEL_CONFIG
	# At least one of the two, asserted below: a report that names neither the product nor the
	# batch names nothing the regulator can act on.
	gtin: str | None = Field(default=None, pattern=r'^\d{6,14}$')
	batch_number: str | None = Field(default=None, min_length=4, max_length=40)
	note: str = Field(default='', max_length=1000)
	photo_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')
	county: str | None = None

	@model_validator(mode='after')
	def _names_something(self) -> 'SuspiciousReport':
		assert self.gtin or self.batch_number, 'a suspicious-medicine report needs a gtin or a batch number'
		return self


class VerifyResult(BaseModel):
	model_config = MODEL_CONFIG
	status: RegistrationStatus
	source: str
	notes: str | None = None
	display: ProductDisplay = Field(default_factory=ProductDisplay)

	@computed_field
	@property
	def genuine(self) -> bool:
		"""Whether the medicine may be taken, derived from the status.

		Kept because it is the question the person actually asked, and because it is the one thing
		that is *safe* to collapse: only `registered` is a yes. A client that reads nothing else
		still gets the right answer, and one that reads `status` gets the reason — which is the
		order these two should have been in from the start. `unverified` is a no, because a lookup
		that did not happen is not a licence to take the medicine.
		"""
		return self.status is RegistrationStatus.registered

	@computed_field
	@property
	def recalled(self) -> bool:
		"""The one outcome that obliges an action on a medicine the person may already have taken."""
		return self.status is RegistrationStatus.recalled


class InteractionPair(BaseModel):
	model_config = MODEL_CONFIG
	a: str
	b: str
	severity: str = Field(pattern=r'^(minor|moderate|major)$')
	note: str


class DoseRequest(BaseModel):
	model_config = MODEL_CONFIG
	drug: str
	weight_kg: float = Field(gt=1, le=300)
	mg_per_kg: float = Field(gt=0, le=100)
	# §AI-003 counts medicine searches for a drug by locality; the locality is the caller's, since a
	# dose lookup carries no geography of its own.
	county: str | None = None


class DoseResult(BaseModel):
	model_config = MODEL_CONFIG
	drug: str
	total_mg: float
	warns: list[str]


class StockReport(BaseModel):
	model_config = MODEL_CONFIG
	report_id: str = Field(pattern=r'^STOCK-[A-Z0-9]{6,}$')
	facility_id: str
	drug: str
	in_stock: bool
	reported_by: str