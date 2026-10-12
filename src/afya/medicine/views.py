"""Medicine domain models (MED-001..004, §18.7 PPB)."""
import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from afya.ids import uuid7str

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
	"""§MED-004's "Report availability yourself (one tap)".

	`at_iso` is what makes the section's own example renderable — "available at [pharmacy], 2 hours
	ago" is a sentence about a timestamp, and this model carried none, so no client could print it.
	It is optional because a report queued offline is stamped when it was *made*, not when it was
	sent, and the client is the only party that knows which.

	`reporter_geohash` is the Anti-gaming clause's first control: "Require location proximity to
	report." A geohash rather than a coordinate, matching §LOC-003's rule that raw location never
	crosses this boundary — the cell is decoded to a centre and the distance to the facility is
	checked, which is all a proximity test needs and leaves no coordinate in the record.
	"""

	model_config = MODEL_CONFIG
	report_id: str = Field(default_factory=lambda: 'STOCK-' + uuid7str().replace('-', '').upper()[:6])
	facility_id: str
	drug: str = Field(min_length=2, max_length=120)
	in_stock: bool
	# Optional because the route prefers the token's subject and only falls back to this: a form
	# that asked a person to type their own reporter reference would be asking them to name
	# themselves for a control that works by recognising them, and the catalogue offers no such
	# field. A report with neither a token nor a name is refused at the route, because
	# `reporter_weight` has nothing to weigh without one.
	reported_by: str | None = None
	at_iso: str | None = None
	reporter_geohash: str | None = Field(default=None, pattern=r'^[0-9a-z]{5,9}$')


class StockAvailability(BaseModel):
	"""One drug at one facility, as a person reads it: the newest report and how old it is.

	`reporter_weight` is the Anti-gaming clause's second control — "Weight reports by reporter
	reliability" — and it is derived server-side from the reporter's history rather than accepted
	from the client, because a client that sets its own weight is a client that has none.
	`age_hours` is the third: "Show report age clearly", as a number a screen can print rather than
	a timestamp it would have to diff against its own clock.
	"""

	model_config = MODEL_CONFIG
	drug: str
	facility_id: str
	facility_name: str | None = None
	in_stock: bool
	reported_at_iso: str | None = None
	age_hours: float | None = None
	# 1 is the floor, not 0: `reporter_weight` never returns a weight that means "no weight at all",
	# and a model that admitted one would let a caller hand back a reporter nobody counts.
	reporter_weight: int = Field(ge=1, le=10)
	reports: int = Field(ge=1)
	essential: bool = False


class StockAlert(BaseModel):
	"""§MED-004's "Alert when a previously out-of-stock medicine becomes available".

	Raised on the transition, not on the state: a report that a medicine is in stock is not news
	unless the last thing anyone said about it was that it had run out.
	"""

	model_config = MODEL_CONFIG
	alert_id: str
	drug: str
	facility_id: str
	became_available_at_iso: str
	out_of_stock_since_iso: str | None = None


# §MED-004's essential-medicines list, verbatim from the section: "insulin, ARVs, TB drugs,
# oxytocin, malaria ACTs, ORS, zinc, contraceptives". Each entry carries the plain-language label a
# client prints plus the spellings a crowd-sourced report might arrive under — a person typing
# "ARVs" and a person typing "dolutegravir" mean the same medicine and neither is wrong.
class EssentialMedicine(BaseModel):
	model_config = MODEL_CONFIG
	slug: str
	label: str
	aliases: list[str] = Field(default_factory=list)


ESSENTIAL_MEDICINES: tuple[EssentialMedicine, ...] = (
	EssentialMedicine(slug='insulin', label='Insulin',
		aliases=['insulin', 'mixtard', 'actrapid', 'lantus']),
	EssentialMedicine(slug='arvs', label='ARVs (HIV treatment)',
		aliases=['arv', 'arvs', 'antiretroviral', 'dolutegravir', 'tenofovir', 'lamivudine', 'nevirapine', 'tld']),
	EssentialMedicine(slug='tb-drugs', label='TB medicines',
		aliases=['tb', 'tb drugs', 'isoniazid', 'rifampicin', 'pyrazinamide', 'ethambutol']),
	EssentialMedicine(slug='oxytocin', label='Oxytocin',
		aliases=['oxytocin', 'pitocin']),
	EssentialMedicine(slug='malaria-acts', label='Malaria ACTs',
		aliases=['act', 'acts', 'coartem', 'artemether', 'lumefantrine', 'al', 'artemether-lumefantrine']),
	EssentialMedicine(slug='ors', label='ORS (oral rehydration salts)',
		aliases=['ors', 'oral rehydration salts', 'rehydration']),
	EssentialMedicine(slug='zinc', label='Zinc',
		aliases=['zinc', 'zinc sulphate', 'zinc sulfate']),
	EssentialMedicine(slug='contraceptives', label='Contraceptives',
		aliases=['contraceptive', 'contraceptives', 'family planning', 'implant', 'depo', 'combined pill']),
)


def essential_slug(drug: str) -> str | None:
	"""The essential-medicines slug a free-text drug name refers to, or `None`.

	Matched on whole words rather than substrings: "insulin" must not match "insulinoma", and "act"
	must not match "contact". A name that matches nothing is not an essential medicine, which is a
	different answer from "not stocked".
	"""
	words = set(re.findall(r'[a-z0-9-]+', drug.lower()))
	if not words:
		return None
	for item in ESSENTIAL_MEDICINES:
		for alias in item.aliases:
			alias_words = set(re.findall(r'[a-z0-9-]+', alias))
			if alias_words and alias_words <= words:
				return item.slug
	return None