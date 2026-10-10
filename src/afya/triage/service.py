"""Triage service — febrile algorithm with malaria trap (§6.3), EVD escalation, symptom diary."""
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry
from afya.strings import rec
from afya.triage.views import DiaryEntry, Differential, EBOLA_SYMPTOMS, RiskLevel, TriageInput, TriageResult


class TriageService(LogMixin):
	def __init__(self, registry: FeatureRegistry) -> None:
		self._registry = registry
		self._diary: dict[str, DiaryEntry] = {}
		assert registry.available() and self._diary == {}, 'registry must be available'

	def assess(self, inp: TriageInput, lang: str = 'en') -> TriageResult:
		major = [s for s in inp.symptoms if s in EBOLA_SYMPTOMS]
		cluster = len([s for s in major if s != 'fever'])
		has_contact_history = inp.ebola_contact or inp.affected_area_travel
		bleeding = 'bleeding' in inp.symptoms
		if bleeding:
			level = RiskLevel.high
		elif has_contact_history and (inp.temperature_c >= 38.0 or cluster >= 1):
			level = RiskLevel.high
		elif inp.temperature_c >= 38.0 and cluster >= 3:
			level = RiskLevel.high
		elif inp.temperature_c >= 38.0:
			level = RiskLevel.malaria_suspect
		elif cluster >= 1:
			level = RiskLevel.medium
		else:
			level = RiskLevel.low
		out = TriageResult(
			risk_level=level,
			recommendation=rec(lang, level.value),
			treated_as_malaria_first=level is RiskLevel.malaria_suspect,
			escalate_719=level in (RiskLevel.medium, RiskLevel.high),
		)
		self._log_info('triage assessed', risk=out.risk_level.value)
		assert out.recommendation, 'recommendation required'
		return out

	def assess_evd(self, inp: TriageInput) -> TriageResult:
		if not self._registry.tier4_active():
			# Refusal text a person may read: no spec code, no tier number.
			raise PermissionError('the Ebola check opens when the outbreak response is activated')
		result = self.assess(inp)
		return result

	async def diary_append(self, entry: DiaryEntry) -> DiaryEntry:
		assert entry.day <= 21, 'observation window is 21 days'
		entry.synced = True
		self._diary[entry.entry_id] = entry
		return entry

	def diary(self, subject_ref: str) -> list[DiaryEntry]:
		return sorted([e for e in self._diary.values() if e.subject_ref == subject_ref], key=lambda e: e.day)

	def diagnose(self, inp: TriageInput) -> 'Differential':
		"""Common-illness differential: profile overlap, base-rate-ordered (malaria trap), never certain."""
		from afya.triage.views import DISEASE_PROFILES, DiagnosisItem, Differential
		assert bool(inp.symptoms), 'symptoms required'
		have = set(inp.symptoms) | ({'fever'} if inp.temperature_c >= 38.0 else set())
		entries = [
			DiagnosisItem(disease=d, score=round(len(have & prof) / len(prof), 2), note='possible — needs testing to confirm')
			for d, prof in DISEASE_PROFILES.items()
		]
		malaria_first = not (inp.ebola_contact or inp.affected_area_travel)
		if malaria_first and ({'fever', 'chills'} & have):
			entries.sort(key=lambda e: -(e.score + (0.10 if e.disease == 'malaria' else 0.0)))
			mx = entries[:3]
			return Differential(entries=mx, lead='malaria', advise=RECMAP['malaria'], malaria_trap_applied=True)
		mx = sorted(entries, key=lambda e: -e.score)[:3]
		lead = mx[0].disease if mx and mx[0].score > 0 else 'no_match'
		advise = RECMAP.get(lead, 'Visit facility for assessment; call 719 if severe.')
		assert mx and all(e.note for e in mx), 'notes required'
		return Differential(entries=mx, lead=lead, advise=advise, malaria_trap_applied=malaria_first)


RECMAP = {
	'malaria': 'Test and treat for malaria first (spec 6.3); call 719 if no improvement in 48h.',
	'typhoid': 'Febrile >3 days suggests typhoid — get a blood test (Widal/culture) at a facility.',
	'flu': 'Rest, fluids; seek care if breathing is difficult or fever >3 days.',
	'cholera': 'START ORS NOW and get to a facility — rapid dehydration is the danger. Call 719.',
	'covid': 'Mask up; test if available; seek care for breathing difficulty.',
	'evd': 'Isolate immediately; call 719; go to nearest isolation treatment unit.',
}
