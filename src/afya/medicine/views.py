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
	"""Two medicines the Formulary's Appendix 1 lists together, in the appendix's own vocabulary.

	`hazard` is `hazardous` or `noted`, not a severity scale. The appendix defines the axis itself
	and it is two-valued — see `afya.medicine.interactions.HAZARD_DEFINITION` — so a model that
	graded it `minor|moderate|major` would be inventing a scale the source does not have, and a
	client that rendered `noted` as "safe" would be misreading the source in the direction that
	matters.
	"""

	model_config = MODEL_CONFIG
	a: str
	b: str
	hazard: str = Field(pattern=r'^(hazardous|noted)$')
	note: str


class ContraindicationFlag(BaseModel):
	"""One drug, one patient axis, and the source's own sentence for it.

	`axis` is the input that selected the flag — `pregnancy`, `children`, or the slug of a condition
	the caller named. `text` is the Formulary's wording, carried rather than summarised: a
	paraphrase of a contraindication is a contraindication somebody rewrote.
	"""

	model_config = MODEL_CONFIG
	drug: str
	axis: str
	text: str


class InteractionReport(BaseModel):
	"""§MED-002's answer: what the source says about these medicines, and what it does not say.

	`unmatched` is the load-bearing field. "This medicine is not in the reference" and "these
	medicines are safe together" are opposite claims and only the second is one a person acts on,
	so a name the table could not place is reported back rather than dropped — the same distinction
	`DoseResult.unknown` draws.

	`pregnancy_caveat` travels with every answer that asked about pregnancy, because the appendix
	says in its own words that absence from its list does not imply safety; a report that omitted it
	would turn an absent row into a reassurance the source refuses to give.
	"""

	model_config = MODEL_CONFIG
	pairs: list[InteractionPair] = Field(default_factory=list)
	flags: list[ContraindicationFlag] = Field(default_factory=list)
	unmatched: list[str] = Field(default_factory=list)
	guidance: str
	disclaimer: str
	hazards: str
	pregnancy_caveat: str | None = None


class DoseRequest(BaseModel):
	"""§MED-003's question: how much of this medicine for this child.

	`mg_per_kg` is gone. It was the one constant a person opens a dosing calculator to look up, and
	asking them for it made the route a multiplication rather than an answer — a caller who knew the
	figure did not need the app. The calculator now reads the range from the WHO Pocket Book.

	`age_months` is required by §MED-003's "Enter weight and age" and is used where the source doses
	by age: zinc is 10 mg a day under six months and 20 mg from six months, and nothing else in the
	source turns on age at all. It is optional in the *model* because the four drugs that ignore it
	should not be refused for its absence — but a zinc lookup without it is refused by the service,
	which is the honest place for that rule rather than a schema that would refuse all five.
	"""

	model_config = MODEL_CONFIG
	drug: str = Field(min_length=2, max_length=120)
	weight_kg: float = Field(gt=0, le=300)
	age_months: int | None = Field(default=None, ge=0, le=216)
	# §AI-003 counts medicine searches for a drug by locality; the locality is the caller's, since a
	# dose lookup carries no geography of its own.
	county: str | None = None


class DoseLine(BaseModel):
	"""One form of the medicine, with the amount to give — as a range, in that form's own units.

	A tablet is counted and a syrup is measured, so `amount_low`/`amount_high` are in `unit`: a
	number of tablets, or millilitres. `amount_mg_low`/`amount_mg_high` carry the same range in
	milligrams for a caller that wants it. Both are here because a person holding a 5 ml spoon
	should not have to divide a milligram figure by the strength printed on a bottle — that
	division is the calculator's whole job.
	"""

	model_config = MODEL_CONFIG
	form: str
	strength: str
	unit: str
	amount_low: float
	amount_high: float
	amount_mg_low: float | None = None
	amount_mg_high: float | None = None


class DoseResult(BaseModel):
	"""§MED-003's "Get dose range", as a range rather than a single number.

	`total_mg` was one figure computed from a caller-supplied constant, and the section asks for a
	*range*. `mg_low`/`mg_high` are the source's own spread — paracetamol is 10–15 mg/kg, not 12.5 —
	and `lines` renders that spread in the forms the pharmacy actually stocks.

	`max_mg_per_dose` is `None` where the source states no ceiling, and a client must render the
	absence rather than a zero: "no maximum stated" and "maximum zero" are opposite claims, and the
	second would stop a child's medicine.
	"""

	model_config = MODEL_CONFIG
	drug: str
	matched: str
	mg_per_kg_low: float
	mg_per_kg_high: float
	doses_per_day_low: int
	doses_per_day_high: int
	mg_low: float | None = None
	mg_high: float | None = None
	max_mg_per_dose: float | None = None
	max_mg_per_day: float | None = None
	over_max: bool = False
	lines: list[DoseLine] = Field(default_factory=list)
	# Volume guidance for ORS, which is dosed by the stool rather than on a schedule.
	after_each_stool_ml_low: float | None = None
	after_each_stool_ml_high: float | None = None
	maintenance_ml_per_kg_per_hour: float | None = None
	days_low: int | None = None
	days_high: int | None = None
	note: str = ''
	warns: list[str] = Field(default_factory=list)
	# Present only when the name matched nothing in the formulary, so a caller can tell "no dose for
	# this" from "no such medicine" without reading a warning string.
	unknown: bool = False


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