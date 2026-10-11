"""The outbreak diseases the product is built for, as one vocabulary (spec §3.3 principle 12, §21.7).

§3.3 principle 12 states the rule the product's whole second half rests on: "Build for the outbreak
after this one — Tier 4 activates for Ebola, cholera, Rift Valley fever, mpox, measles, and the next
unknown." §21.7's Phase 6 deliverable repeats four of the six as "Multi-disease support". Nothing
carried the list. What existed instead was four spellings of a disease vocabulary on four surfaces,
none of them the section that names it:

* `surveillance.views.CountySignal` and `SignalReading` — `^(evd|cholera|malaria|dengue|mpox|rvf)$`
* `community.views.CaseReport` — the same, plus `measles|other`
* `mobile.actions.VECTOR_DISEASES` — the same eight as the case report
* `alerts.views.AlertKind` — six `outbreak_*` members with no `measles` and no `other`

**Measles is the defect that makes the class visible.** §3.3 principle 12 names it as one of the
diseases Tier 4 activates for, and `CountySignal` — the model the early-warning signal is computed
from — refused it. The county that reports measles is the county whose signal the system cannot
compute. Dengue, present on three of the four surfaces, appears nowhere in the spec at all.

Three things follow from one list:

* **The spec's diseases are the ones the system is accountable for.** `SPEC_DISEASES` is §3.3
  principle 12's own list, with `evd` as its slug because that is the code the wire has always used
  and §3.3's prose is the only place the English name appears. Every surface that accepts a disease
  accepts at least these, and a gate fails if one of them is missing anywhere — the class of defect
  measles was an instance of, not the instance.

* **`other` is not a disease and the spec says why it must exist.** Principle 12 ends "and the next
  unknown": a system that accepts only the five named diseases cannot report the sixth, which is
  exactly the outbreak it was built to be ready for. `other` is a required member of the vocabulary
  and is deliberately absent from `SPEC_DISEASES`, because it is the slot for a disease nobody has
  named yet rather than one the spec names.

* **`dengue` is kept and marked as the repo's addition.** It is on three surfaces, it is a real
  Kenyan outbreak disease (Mombasa and the coast have had recurring dengue), and removing it would
  break a working capability to tidy a list. It is recorded as `beyond_spec` rather than quietly
  folded in with the spec's six, because a vocabulary that cannot say which of its members the spec
  asked for is the state this module exists to end.
"""
from pydantic import BaseModel, ConfigDict, Field

MODEL_CONFIG = ConfigDict(extra='forbid', validate_by_name=True, validate_by_alias=True)

# §3.3 principle 12's list, in the section's own order. `slug` is the wire code — `evd` because that
# is what every surface has always used and the section spells the disease "Ebola" in prose, so the
# two spellings are joined here rather than left for a reader to reconcile.
SPEC_DISEASES: tuple[str, ...] = ('evd', 'cholera', 'rvf', 'mpox', 'measles')

# Diseases the repo carries that §3.3 principle 12 does not name. Kept, and kept separate.
BEYOND_SPEC: tuple[str, ...] = ('malaria', 'dengue')

# The slot principle 12 ends on: "and the next unknown". Not a disease — the absence of a name for
# one — so it is not in `SPEC_DISEASES` and is required everywhere a disease is reported.
OTHER = 'other'

DISEASES: tuple[str, ...] = SPEC_DISEASES + BEYOND_SPEC + (OTHER,)
DISEASE_PATTERN: str = '^(' + '|'.join(DISEASES) + ')$'


class Disease(BaseModel):
	"""One disease the product can be told about.

	`beyond_spec` is the field that keeps the list honest: True means the repo carries the disease and
	§3.3 principle 12 does not name it, so a reader can tell a capability the spec asked for from one
	this repo added. `english` is the name a person reads — the slugs are wire codes, and `rvf` is not
	a word anyone outside this codebase recognises.
	"""
	model_config = MODEL_CONFIG
	slug: str = Field(min_length=1)
	english: str = Field(min_length=1)
	beyond_spec: bool

	def label(self) -> str:
		"""How the disease is written for a person: §3.3's own spelling, with the repo's additions
		marked so an operator reading a report knows which list a row came from."""
		return f'{self.english} (beyond the spec’s list)' if self.beyond_spec else self.english


DISEASE_ROWS: tuple[Disease, ...] = (
	Disease(slug='evd', english='Ebola', beyond_spec=False),
	Disease(slug='cholera', english='Cholera', beyond_spec=False),
	Disease(slug='rvf', english='Rift Valley fever', beyond_spec=False),
	Disease(slug='mpox', english='Mpox', beyond_spec=False),
	Disease(slug='measles', english='Measles', beyond_spec=False),
	Disease(slug='malaria', english='Malaria', beyond_spec=True),
	Disease(slug='dengue', english='Dengue', beyond_spec=True),
	# §3.3 principle 12: "and the next unknown". The name says what it is — a placeholder, not a
	# disease — because a report row reading "Other" beside "Measles" must not look like a peer.
	Disease(slug=OTHER, english='Unnamed disease (the next unknown)', beyond_spec=False),
)

DISEASE: dict[str, Disease] = {row.slug: row for row in DISEASE_ROWS}

assert tuple(r.slug for r in DISEASE_ROWS) == DISEASES, 'the rows must follow the vocabulary order'
assert tuple(r.slug for r in DISEASE_ROWS if not r.beyond_spec and r.slug != OTHER) == SPEC_DISEASES, \
	'the spec rows must be §3.3 principle 12’s list, in its order'
assert DISEASE[OTHER].slug not in SPEC_DISEASES, 'the unknown slot is not one of the named diseases'


def english(slug: str) -> str:
	"""The readable name for a wire code, refusing an unknown one rather than echoing it back.

	Echoing is the failure this avoids: a report that prints an unrecognised slug looks exactly like
	one that prints a known disease, so the reader cannot tell a typo from a case.
	"""
	assert slug in DISEASE, f'unknown disease {slug}'
	return DISEASE[slug].english


def spec_disease_slugs() -> frozenset[str]:
	"""§3.3 principle 12's five, for a gate that checks every surface accepts them."""
	return frozenset(SPEC_DISEASES)
