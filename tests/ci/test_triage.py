import pytest

from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.triage.service import TriageService
from afya.triage.views import RED_FLAGS, DiaryEntry, RiskLevel, TriageInput


@pytest.fixture
def svc() -> TriageService:
	return TriageService(FeatureRegistry())


async def test_healthy_low(svc: TriageService) -> None:
	out = svc.assess(TriageInput(symptoms=[], temperature_c=37.0))
	assert out.risk_level is RiskLevel.low and not out.escalate_719


async def test_malaria_trap(svc: TriageService) -> None:
	out = svc.assess(TriageInput(symptoms=['fever'], temperature_c=38.6, ebola_contact=False))
	assert out.risk_level is RiskLevel.malaria_suspect
	assert out.treated_as_malaria_first and 'malaria' in out.recommendation.lower()


async def test_contact_history_escalates_to_ebola_suspicion(svc: TriageService) -> None:
	"""§8.1 prints High twice — "(Ebola suspicion)" and "(other cause)" — and the two send a person
	to different places. A contact-history fever is the first: isolate and notify, not "seek care"."""
	out = svc.assess(TriageInput(symptoms=['fever', 'headache'], temperature_c=38.2, ebola_contact=True))
	assert out.risk_level is RiskLevel.high_ebola_suspicion and out.escalate_719


async def test_a_fever_without_contact_history_is_high_other_cause(svc: TriageService) -> None:
	"""The other half of §8.1's fifth classification: three or more symptoms and a fever with no
	exposure history is serious and is *not* an Ebola suspicion."""
	out = svc.assess(TriageInput(symptoms=['fever', 'headache', 'vomiting', 'rash'], temperature_c=38.5))
	assert out.risk_level is RiskLevel.high_other, 'no exposure history, so not the Ebola branch'


async def test_bleeding_is_the_emergency_rung(svc: TriageService) -> None:
	"""§8.1 lists unexplained bleeding first among its red flags and prints Emergency as its own
	classification. It returned `high` — the same value as an exposure risk."""
	out = svc.assess(TriageInput(symptoms=['bleeding'], temperature_c=36.8))
	assert out.risk_level is RiskLevel.emergency


async def test_a_red_flag_escalates_without_a_fever(svc: TriageService) -> None:
	"""§8.1's red flags are a separate Inputs list from the symptom multi-select, and the section
	does not require a fever for them. A convulsing person with a normal temperature is an
	emergency, and before this the input had no field to say so at all."""
	out = svc.assess(TriageInput(symptoms=[], temperature_c=36.9, red_flags=['convulsions']))
	assert out.risk_level is RiskLevel.emergency and out.red_flag_triggered
	# `confusion` is a red flag but not one of the four that means an ambulance
	out = svc.assess(TriageInput(symptoms=[], temperature_c=36.9, red_flags=['confusion']))
	assert out.risk_level is RiskLevel.low and not out.red_flag_triggered


def test_an_unknown_red_flag_is_refused() -> None:
	"""The red flags are §8.1's own eight. A free-text flag would be a value nothing escalates on
	and nothing can render, so the set is closed."""
	from pydantic import ValidationError
	with pytest.raises(ValidationError):
		TriageInput(symptoms=[], red_flags=['dizziness'])
	assert len(RED_FLAGS) == 8, 'the section prints eight'


def test_the_three_exposure_criteria_are_one_derived_fact() -> None:
	"""§8.1's epidemiological criteria are travel, contact and attendance at a known exposure site.
	The `or` of the three was written twice in the algorithm and `exposure_site` had no field, so a
	person who attended a funeral of a known case could only be triaged by claiming contact."""
	assert not TriageInput(symptoms=[]).exposure_history
	assert TriageInput(symptoms=[], ebola_contact=True).exposure_history
	assert TriageInput(symptoms=[], affected_area_travel=True).exposure_history
	assert TriageInput(symptoms=[], exposure_site=True).exposure_history, \
		'§8.1 names attendance at a known exposure site as its own criterion' 


async def test_the_four_outputs_the_section_prints_are_all_present(svc: TriageService) -> None:
	"""§8.1's Outputs are the classification, the one-tap action, the watch-for list and the
	forwardable card. Only the first existed; `recommendation` was prose and `escalate_719` a bool,
	so a client had a sentence and a flag and nothing executable."""
	out = svc.assess(TriageInput(symptoms=['fever'], temperature_c=38.6))
	assert [a.kind for a in out.actions] == ['request_chw', 'find_facility', 'call'], \
		'a malaria-suspect case leads with the CHW visit, not the ambulance'
	assert all(a.href for a in out.actions)
	assert out.watch_for, 'the watch-for list is printed for every rung'
	assert out.summary_card.startswith('Afya Yangu triage:')


async def test_an_emergency_leads_with_the_call(svc: TriageService) -> None:
	"""The classification decides the *order*, not the menu. §8.1 names three one-tap actions and
	all three are always offered — an emergency still needs the facility search and the CHW visit,
	and a client that showed only the call would drop the two the person may need next."""
	out = svc.assess(TriageInput(symptoms=['bleeding'], temperature_c=36.8))
	kinds = [a.kind for a in out.actions]
	assert kinds[0] == 'call'
	assert set(kinds) == {'call', 'find_facility', 'request_chw'}, 'all three, in the order the rung sets'
	assert kinds == ['call', 'find_facility', 'request_chw']


async def test_the_summary_card_carries_no_exposure_history(svc: TriageService) -> None:
	"""§3.3 principle 10 wants every output forwardable; §8.1's Privacy clause says triage data
	stays on-device unless the user consents. The card is the one output that leaves the phone, so
	what travels is the classification and what to do about it — not the contact history, which is
	what would identify the sender as a suspected case to whoever reads the forward."""
	# The card carries no exposure detail a client would have to strip out: not the travel flag, not
	# the exposure site, not the symptom list. What it does carry is the section's own recommendation
	# verbatim, and that sentence tells the person to say they may have had contact with Ebola when
	# they call — which is the advice, not a disclosure the card made on its own.
	out = svc.assess(TriageInput(symptoms=['fever', 'headache'], temperature_c=38.2, ebola_contact=True))
	card = out.summary_card.lower()
	# The card is exactly the classification, the recommendation and the next steps — asserted as an
	# equality on the parts rather than by grepping for words, because the recommendation legitimately
	# says "do not travel by public transport" and a substring check for "travel" would fail on the
	# advice while a real leak of the travel *flag* went unnoticed.
	assert 'funeral' not in card and 'exposure site' not in card
	assert 'headache' not in card, 'the symptom list is not on the card either'
	assert 'isolate' in card, 'the Ebola-suspicion advice is what the recipient needs'
	lines = out.summary_card.splitlines()
	assert lines[0] == f'Afya Yangu triage: {out.risk_level.value.replace("_", " ")}'
	assert lines[1] == out.recommendation, 'the recommendation is carried verbatim, not paraphrased'
	assert lines[2].startswith('Next: ') and lines[3].startswith('Watch for: ')
	assert len(lines) == 4, f'the card carries nothing else: {lines[4:]}' 


async def test_tri003_gated_when_dormant(svc: TriageService) -> None:
	with pytest.raises(PermissionError):
		svc.assess_evd(TriageInput(symptoms=['fever'], temperature_c=39.0, ebola_contact=True))


async def test_tri003_active_after_gate() -> None:
	registry = FeatureRegistry(Tier4Activation(authorized_by_pheoc=True, dpia_review_id='r1', flag_enabled=True))
	assert registry.tier4_active()
	out = TriageService(registry).assess_evd(TriageInput(symptoms=['fever'], temperature_c=39.0, ebola_contact=True))
	assert out.risk_level is RiskLevel.high_ebola_suspicion


async def test_diary_21_day_window(svc: TriageService) -> None:
	from pydantic import ValidationError
	with pytest.raises(ValidationError):
		DiaryEntry(entry_id='DIARY-ABC123XY99', subject_ref='U1', day=22, symptoms=['fever'], temperature_c=37.0)
