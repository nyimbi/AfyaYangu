"""Triage service — febrile algorithm with malaria trap (§6.3), EVD escalation, symptom diary."""
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry
from afya.strings import rec
from afya.triage.views import DiaryEntry, EBOLA_SYMPTOMS, RiskLevel, TriageInput, TriageResult


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
			raise PermissionError('TRI-003 is Tier 4 dormant: requires PHEOC activation')
		result = self.assess(inp)
		return result

	async def diary_append(self, entry: DiaryEntry) -> DiaryEntry:
		assert entry.day <= 21, 'observation window is 21 days'
		entry.synced = True
		self._diary[entry.entry_id] = entry
		return entry

	def diary(self, subject_ref: str) -> list[DiaryEntry]:
		return sorted([e for e in self._diary.values() if e.subject_ref == subject_ref], key=lambda e: e.day)