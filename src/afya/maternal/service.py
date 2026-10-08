"""Maternal service — ANC scheduling, danger-sign triage (immediate escalation), delivery planning."""
from datetime import date, timedelta

from afya.logmixin import LogMixin
from afya.maternal.views import ANC_CONTACTS_WEEKS, ANCRecord, DANGER_SIGNS, DangerAssessment, Pregnancy


class MaternalService(LogMixin):
	def __init__(self) -> None:
		self._pregnancies: dict[str, Pregnancy] = {}
		self._anc: list[ANCRecord] = []
		assert self._pregnancies == {} and self._anc == []

	async def register(self, p: Pregnancy) -> Pregnancy:
		assert p.subject_ref, 'subject required'
		assert p.lmp_week >= 4, 'pregnancy must be confirmed'
		self._pregnancies[p.subject_ref] = p
		return p

	def anc_due(self, subject_ref: str, today_iso: str, gest_week: int) -> list[int]:
		assert subject_ref in self._pregnancies, 'unknown pregnancy'
		done = {r.contact_no for r in self._anc if r.subject_ref == subject_ref}
		target = next((n for n, wk in enumerate(ANC_CONTACTS_WEEKS, 1) if wk >= gest_week), 8)
		return [n for n in range(1, target + 1) if n not in done]

	async def record_anc(self, rec: ANCRecord) -> ANCRecord:
		assert 1 <= rec.contact_no <= 8, 'ANC contact bounds'
		self._anc.append(rec)
		self._log_info('anc recorded', contact=rec.contact_no)
		return rec

	def assess_danger(self, signs: list[str]) -> DangerAssessment:
		assert all(s in DANGER_SIGNS for s in signs), 'unknown danger sign'
		escalate = bool(signs)
		blocked = ('bleeding', 'convulsions', 'water_breaks')
		msg = (
			'IMMEDIATE: go to the maternity unit now — ' + ' / '.join(signs)
			if any(s in blocked for s in signs)
			else ('Contact your ANC clinic today: ' + ' / '.join(signs) if signs else 'No danger signs recorded.')
		)
		out = DangerAssessment(signs=signs, escalate=escalate, message=msg)
		if escalate:
			self._log_warn('danger sign reported', signs=signs)
		return out

	def delivery_plan(self, p: Pregnancy) -> dict[str, str]:
		assert self._pregnancies[p.subject_ref] is p, 'registered pregnancy'
		return {
			'facility': p.delivery_plan_facility_id or 'UNPLANNED — choose a facility before EDD',
			'edd': p.edd_iso,
			'note': 'Deliver at a health facility; skilled birth attendant reduces haemorrhage and sepsis risk.',
		}