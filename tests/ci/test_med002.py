"""§MED-002 — the drug interaction and safety checker, against the WHO Model Formulary 2008.

The section asks four things and this file tests each: select two or more medicines, check for
known interactions, flag contraindications for pregnancy, children and common conditions, and give
guidance to consult a pharmacist. The reference is Appendix 1 (interactions) plus Appendix 2
(pregnancy) and each monograph's own `Contraindications:` line (age and condition).

The properties that are *not* transcription are the ones worth testing, because they are the ones a
rewrite would silently lose: the pair lookup is order-independent, a hazard disagreement between
the appendix's two listings resolves toward the warning, and a name the reference cannot place is
reported rather than read as "no interaction".
"""
import httpx
import pytest

from afya.medicine import contraindications, interactions
from afya.medicine.service import MedicineService
from afya.medicine.views import InteractionReport
from afya.service import create_app


class _PPB:
	async def verify(self, req: object) -> object:
		raise NotImplementedError


def _svc() -> MedicineService:
	return MedicineService(_PPB())  # type: ignore[arg-type]


def test_pair_lookup_is_order_independent() -> None:
	"""`['warfarin', 'aspirin']` and `['aspirin', 'warfarin']` are the same question.

	The appendix lists the pair twice, once under each drug, so a table keyed on the ordered pair
	would answer one of the two orderings and silently miss the other.
	"""
	svc = _svc()
	forward = svc.check_interactions(['warfarin', 'aspirin'])
	backward = svc.check_interactions(['aspirin', 'warfarin'])
	assert len(forward.pairs) == 1 and len(backward.pairs) == 1
	assert (forward.pairs[0].a, forward.pairs[0].b) == (backward.pairs[0].a, backward.pairs[0].b)


def test_brand_names_resolve_to_the_sources_generic() -> None:
	"""A person types what is printed on the box; the appendix names the molecule."""
	svc = _svc()
	branded = svc.check_interactions(['coumadin', 'asa'])
	assert len(branded.pairs) == 1
	assert branded.pairs[0].a == 'Acetylsalicylic acid'
	assert branded.unmatched == []


def test_unmatched_name_is_reported_not_read_as_safe() -> None:
	"""`unmatched` is the field that keeps "unknown medicine" from becoming "no interaction".

	This is the dangerous direction: a caller that drops an unrecognised name reports a clean check
	for a medicine it never looked at.
	"""
	report = _svc().check_interactions(['metformin', 'unobtainium'])
	assert report.unmatched == ['unobtainium']
	assert report.pairs == []
	# And the name is echoed back as the caller wrote it, so they can see which one failed.
	assert 'unobtainium' in report.unmatched[0]


def test_hazard_disagreement_resolves_toward_the_warning() -> None:
	"""Where the appendix disagrees with itself, the table keeps the more severe marking.

	The appendix lists each pair twice and 7 pairs carry a different mark under the two listings.
	Erring toward the warning is the only safe resolution, and the count is recorded in the module
	rather than left for a reader to rediscover.
	"""
	assert interactions.PAIRS_WITH_DISAGREEING_HAZARD == 7
	assert interactions.PAIRS_LISTED_TWICE > 1000
	# Clomipramine + Warfarin is `noted` under clomipramine's section and `hazardous` under
	# warfarin's, so it is one of the 7. The table must carry the severe one: the whole point of
	# resolving the disagreement is that the answer is the warning and not the clearance.
	row = interactions._BY_PAIR[frozenset(('clomipramine', 'warfarin'))]
	assert row[2] == interactions.HAZARDOUS
	assert _svc().check_interactions(['clomipramine', 'warfarin']).pairs[0].hazard == 'hazardous'
	# Every pair carries one of the appendix's two marks and nothing else.
	assert {row[2] for row in interactions.INTERACTIONS} == {interactions.HAZARDOUS, interactions.NOTED}
	# The two-valued axis is the source's own, and its definition travels with the answer.
	assert 'should be avoided, or only taken with caution' in interactions.HAZARD_DEFINITION


def test_pregnancy_flag_carries_the_sources_own_caveat() -> None:
	"""The appendix says absence from its list does not imply safety, so the answer must too.

	Without the caveat, "no flag" reads as reassurance for a drug the appendix simply does not
	mention — which is a claim the source explicitly refuses to make.
	"""
	report = _svc().check_interactions(['warfarin', 'aspirin'], pregnant=True)
	axes = {f.axis for f in report.flags}
	assert 'pregnancy' in axes
	warfarin = next(f for f in report.flags if f.drug == 'Warfarin')
	assert 'Congenital malformations' in warfarin.text
	assert report.pregnancy_caveat is not None
	assert contraindications.PREGNANCY_CAVEAT in report.pregnancy_caveat
	assert contraindications.PREGNANCY_BENEFIT_CAVEAT in report.pregnancy_caveat
	# A caller who did not say they are pregnant has not asked the question, so the sentence is not
	# volunteered about a patient whose state nobody stated.
	assert _svc().check_interactions(['warfarin', 'aspirin']).pregnancy_caveat is None


def test_age_axis_fires_below_the_floor_the_source_states() -> None:
	"""Doxycycline's monograph says "children under 8 years", so 8 years is not below it."""
	svc = _svc()
	below = svc.check_interactions(['doxycycline', 'metformin'], age_months=60)
	assert any(f.axis == 'children' for f in below.flags)
	at = svc.check_interactions(['doxycycline', 'metformin'], age_months=96)
	assert not any(f.axis == 'children' for f in at.flags)
	# An adult with no age sent is not a child: nothing is inferred from an absent input.
	assert not any(f.axis == 'children' for f in svc.check_interactions(['doxycycline', 'metformin']).flags)


def test_condition_axis_fires_only_for_a_condition_the_caller_names() -> None:
	"""A condition is selected by the caller; the service does not guess one from the drug list."""
	svc = _svc()
	named = svc.check_interactions(['doxycycline', 'metformin'], conditions=['porphyria'])
	assert any(f.axis == 'porphyria' for f in named.flags)
	# Doxycycline's line names porphyria; naming a different condition must not fire it.
	other = svc.check_interactions(['doxycycline', 'metformin'], conditions=['asthma'])
	assert not any(f.axis == 'porphyria' for f in other.flags)


def test_paracetamol_has_no_contraindication_line_and_is_not_invented_one() -> None:
	"""Paracetamol's monograph has only `Precautions:`, and the table must reflect that.

	This is the row a window-based extraction got wrong: reading a fixed window past the end of the
	monograph attributed the next drug's contraindications to paracetamol.
	"""
	svc = _svc()
	report = svc.check_interactions(['paracetamol', 'metformin'], age_months=24, conditions=['asthma'])
	assert not any(f.drug == 'Paracetamol' for f in report.flags)
	# It *is* in Appendix 2, and the appendix says it is not known to be harmful there.
	pregnant = svc.check_interactions(['paracetamol', 'metformin'], pregnant=True)
	assert any(f.drug == 'Paracetamol' and f.axis == 'pregnancy' for f in pregnant.flags)


def test_guidance_and_disclaimer_are_served_with_every_answer() -> None:
	"""The section's fourth bullet and its Disclaimer line, both carried verbatim."""
	report = _svc().check_interactions(['metformin', 'glibenclamide'])
	assert report.guidance == MedicineService.PHARMACIST_GUIDANCE
	assert 'pharmacist' in report.guidance
	assert report.disclaimer == 'Informational only. Not a substitute for professional advice.'
	assert report.hazards == interactions.HAZARD_DEFINITION


def test_no_spec_feature_code_in_anything_served() -> None:
	"""The catalogue is the only place a feature id belongs, and it is stripped there.

	A spec id in a served field is a code percolating into the interface, which the product forbids.
	"""
	report = _svc().check_interactions(['warfarin', 'aspirin'], pregnant=True, conditions=['asthma'])
	blob = InteractionReport.model_validate(report.model_dump()).model_dump_json()
	assert 'MED-002' not in blob and 'MED-' not in blob


async def test_route_serves_the_report_and_refuses_a_single_drug() -> None:
	"""The front door, not the service: one medicine is not a pair and the schema says so."""
	transport = httpx.ASGITransport(app=create_app())
	async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
		out = (await client.post('/medicine/interactions',
		                         json={'drugs': ['warfarin', 'aspirin'], 'pregnant': True})).json()
		assert out['pairs'][0]['hazard'] == 'hazardous'
		assert out['guidance'] and out['disclaimer'] and out['pregnancy_caveat']
		assert (await client.post('/medicine/interactions', json={'drugs': ['aspirin']})).status_code == 422


@pytest.mark.parametrize('axis,label', [
	('renal_impairment', 'Kidney problems'),
	('hepatic_impairment', 'Liver problems'),
	('porphyria', 'Porphyria'),
])
def test_condition_labels_are_human_readable(axis: str, label: str) -> None:
	"""A condition is selected by a person, so its label is prose and its slug is the wire value."""
	assert dict(contraindications.CONDITION_AXES)[axis] == label
	# And the slug is not a feature code wearing a different hat.
	assert '-' not in axis and not axis.isupper()


async def test_the_catalogue_offers_condition_labels_and_the_route_reads_them() -> None:
	"""The vocabulary a person types, sent back through the front door, must select the axis it names.

	The route reads `CONDITION_AXES`' *labels* as well as their slugs — a person names a condition
	by its name — and the matcher used to compare only slugs, so the value the control produced
	matched no axis and a stated condition was silently not considered: a refusal the person never
	sees, on the one field where silence is dangerous. `nitrofurantoin` is used because its
	monograph's own line names renal impairment, so the flag is the drug's and not the test's.

	The catalogue carries this as a text field with the vocabulary in its hint rather than as
	`options`: `conditions` is a `list`, and both clients draw a `list` as comma text, so an
	`options` list would be a closed set no control offered (see
	`tests/ci/test_catalogue_vocabulary.py`). The examples in the hint are therefore the only
	vocabulary a person sees, and each one has to be a label the route actually resolves.
	"""
	from afya.mobile.actions import catalogue

	offered = next(a for a in catalogue() if a.id == 'drug_interactions')
	field = next(f for f in offered.fields if f.name == 'conditions')
	assert field.type == 'list' and field.options is None, (
		'a list field carries no `options`: neither client draws a chooser for one')
	examples = [part.strip().removeprefix('e.g. ').strip()
	            for part in (field.placeholder or '').split(',') if part.strip()]
	assert examples, 'the hint must name the vocabulary the route reads'
	for label in examples:
		assert contraindications.condition_axis(label) is not None, (
			f'the hint offers {label!r}, which selects no axis')

	transport = httpx.ASGITransport(app=create_app())
	async with httpx.AsyncClient(transport=transport, base_url='http://testserver') as client:
		# The label exactly as the control renders it — this is the string a client puts on the wire.
		by_label = (await client.post('/medicine/interactions', json={
			'drugs': ['nitrofurantoin', 'paracetamol'], 'conditions': ['Kidney problems']})).json()
		by_slug = (await client.post('/medicine/interactions', json={
			'drugs': ['nitrofurantoin', 'paracetamol'], 'conditions': ['renal_impairment']})).json()
		assert any(f['axis'] == 'renal_impairment' for f in by_label['flags']), by_label['flags']
		# The two spellings are one condition: the flag set is identical, so the bridge is not a
		# second code path that happens to answer the same way.
		assert by_label['flags'] == by_slug['flags'], (by_label['flags'], by_slug['flags'])
		# And a condition the drug's line does not name fires nothing — so the match is real.
		other = (await client.post('/medicine/interactions', json={
			'drugs': ['nitrofurantoin', 'paracetamol'], 'conditions': ['Gout']})).json()
		assert not any(f['axis'] == 'renal_impairment' for f in other['flags']), other['flags']
		# Every label the matcher publishes resolves to an axis, so the vocabulary has no dead entry.
		for label in contraindications.CONDITION_LABELS.values():
			assert contraindications.condition_axis(label) is not None, label
