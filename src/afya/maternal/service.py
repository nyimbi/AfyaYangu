"""Maternal service — due-date arithmetic, ANC and postnatal scheduling, the birth plan, trimester
guidance, danger-sign education and escalation, and the PMTCT referral.

Date arithmetic is pure and takes the caller's `today_iso`, for the reason `MonitoringService` does
the same: a service that reads a clock cannot be tested against a fixed date, and every reminder
here is a question about a date.
"""
from datetime import date, timedelta

from afya.logmixin import LogMixin
from afya.maternal.views import (
	ANC_CONTACTS_WEEKS, DANGER_SIGN_EDUCATION, DANGER_SIGNS, GESTATION_DAYS, NEWBORN_DANGER_SIGNS,
	PMTCT_PROGRAMME, PMTCT_RELEVANT, POSTNATAL_CONTACTS, TRIMESTER_GUIDANCE, ANCRecord, ANCVisit,
	BirthPlan, CareAction, DangerAssessment, DangerEducation, NewbornDangerSign, PmtctReferral,
	PostnatalVisit, Pregnancy,
)

# §MON-002's "Visit reminders": the same 3-day/1-day leads §MON-001 uses for immunisation, because
# a person receiving two reminder cadences from one app reads neither.
REMINDER_LEAD_DAYS = (3, 1)

# The facility search the maternal escalation points at. §MON-002 asks for a maternity finder and
# §FND-001's `ServiceOffered` carries `maternal`, so the filter is the section's own service.
MATERNITY_FINDER_HREF = '/facilities/find?service=maternal'


def _iso_add_days(iso: str, days: int) -> str:
	"""Civil-date arithmetic on YYYY-MM-DD. No clock, no timezone: a due date is a day."""
	year, month, day = (int(p) for p in iso[:10].split('-'))
	return (date(year, month, day) + timedelta(days=days)).isoformat()


def _days_between(iso_a: str, iso_b: str) -> int:
	a = date(*(int(p) for p in iso_a[:10].split('-')))
	b = date(*(int(p) for p in iso_b[:10].split('-')))
	return (b - a).days


class MaternalService(LogMixin):
	def __init__(self) -> None:
		self._pregnancies: dict[str, Pregnancy] = {}
		self._anc: list[ANCRecord] = []
		self._plans: dict[str, BirthPlan] = {}
		self._births: dict[str, str] = {}
		assert self._pregnancies == {} and self._anc == [] and self._plans == {}

	# --- registration and the due-date calculator ------------------------------------------

	@staticmethod
	def estimated_due_date(lmp_iso: str) -> str:
		"""§MON-002's "Estimated due date calculator" — Naegele's rule, 280 days from the LMP.

		The section asks for a calculator and the model took `edd_iso` as an input, which put the
		arithmetic on the client: an app that computed it differently, or not at all, would register
		a pregnancy with a date nobody derived. The rule is stated here rather than inlined because
		"280 days" is the section's claim about which rule is used.
		"""
		assert len(lmp_iso) >= 10, 'the calculator needs a date, not a week count'
		return _iso_add_days(lmp_iso, GESTATION_DAYS)

	def gestation_week(self, subject_ref: str, today_iso: str) -> int:
		"""Weeks pregnant today, from the LMP when there is one and from the EDD when there is not.

		Both routes reach the same number: the LMP is 280 days before the EDD by construction, so a
		pregnancy registered with only a clinic-card date still answers every question below.
		"""
		assert subject_ref in self._pregnancies, 'unknown pregnancy'
		p = self._pregnancies[subject_ref]
		elapsed = _days_between(p.lmp_iso, today_iso) if p.lmp_iso else GESTATION_DAYS - _days_between(today_iso, p.edd_iso)
		return max(1, min(42, elapsed // 7))

	async def register(self, p: Pregnancy) -> Pregnancy:
		assert p.subject_ref, 'subject required'
		assert p.lmp_week >= 4, 'pregnancy must be confirmed'
		self._pregnancies[p.subject_ref] = p
		return p

	async def record_birth(self, subject_ref: str, birth_iso: str) -> str:
		"""§MON-002's postnatal half starts here: without a birth date there is no day 3 or week 6."""
		assert subject_ref in self._pregnancies, 'unknown pregnancy'
		self._births[subject_ref] = birth_iso
		self._log_info('birth recorded', sub=subject_ref, on=birth_iso)
		return birth_iso

	# --- ANC scheduling and reminders -------------------------------------------------------

	def visits(self, subject_ref: str, today_iso: str) -> list[ANCVisit]:
		"""§MON-002's "WHO/Kenya ANC visit schedule (8 contacts)" with the date each falls on.

		The dates come from the LMP where there is one and from the EDD where there is not, and the
		reminder leads are the 3-day/1-day pair. A contact already recorded is `done` and carries no
		lead, because reminding someone about a visit they attended is how a reminder stops being read.
		"""
		assert subject_ref in self._pregnancies, 'unknown pregnancy'
		p = self._pregnancies[subject_ref]
		start = p.lmp_iso or _iso_add_days(p.edd_iso, -GESTATION_DAYS)
		done = {r.contact_no for r in self._anc if r.subject_ref == subject_ref}
		out: list[ANCVisit] = []
		for n, wk in enumerate(ANC_CONTACTS_WEEKS, 1):
			due = _iso_add_days(start, wk * 7)
			attended = n in done
			until = _days_between(today_iso, due)
			leads = [d for d in REMINDER_LEAD_DAYS if 0 <= until <= d] if not attended else []
			out.append(ANCVisit(
				contact_no=n, gest_week=wk, due_iso=due, done=attended,
				remind_days_before=sorted(leads),
			))
		assert len(out) == len(ANC_CONTACTS_WEEKS), 'one row per contact the section prints'
		return out

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

	def postnatal_visits(self, subject_ref: str) -> list[PostnatalVisit]:
		"""§MON-002's "Postnatal visit reminders", from the recorded birth date.

		Before the birth there is nothing to remind about and the list is empty rather than
		provisional: four contacts with dates derived from a delivery that has not happened are four
		wrong dates, and a screen that rendered them would have a person planning around them.
		"""
		assert subject_ref in self._pregnancies, 'unknown pregnancy'
		birth = self._births.get(subject_ref)
		if birth is None:
			return []
		return [
			PostnatalVisit(day_after_birth=day, due_iso=_iso_add_days(birth, day - 1), what=what)
			for day, what in POSTNATAL_CONTACTS
		]

	# --- guidance ---------------------------------------------------------------------------

	def trimester_guidance(self, gest_week: int) -> dict[str, object]:
		"""§MON-002's "Trimester-specific guidance". The section asks for three, so there are three."""
		assert 1 <= gest_week <= 42, 'gestational week out of range'
		trimester = 1 if gest_week <= 13 else (2 if gest_week <= 27 else 3)
		advise, points = TRIMESTER_GUIDANCE[trimester]
		return {'trimester': trimester, 'gest_week': gest_week, 'advise': advise, 'points': list(points)}

	@staticmethod
	def newborn_danger_signs() -> list[NewbornDangerSign]:
		"""§MON-002's "Newborn danger signs". A different list from the mother's, and separate from it."""
		return [NewbornDangerSign(sign=sign, means=means) for sign, means in NEWBORN_DANGER_SIGNS]

	# --- danger signs: education and the one-tap escalation ---------------------------------

	def assess_danger(self, signs: list[str], subject_ref: str | None = None) -> DangerAssessment:
		"""§MON-002's danger signs, with the three that cannot wait separated from the rest.

		`subject_ref` is optional and carried only so the escalation can point at the right person's
		CHW task; the classification does not depend on it, which is why the route stays callable
		without a token the way §8.1's preliminary triage does.
		"""
		assert all(s in DANGER_SIGNS for s in signs), 'unknown danger sign'
		escalate = bool(signs)
		blocked = ('bleeding', 'convulsions', 'water_breaks')
		immediate = any(s in blocked for s in signs)
		msg = (
			'IMMEDIATE: go to the maternity unit now — ' + ' / '.join(signs)
			if immediate
			else ('Contact your ANC clinic today: ' + ' / '.join(signs) if signs else 'No danger signs recorded.')
		)
		out = DangerAssessment(
			signs=signs, escalate=escalate, message=msg,
			education=[self.education_for(s, subject_ref) for s in signs],
			action=self.escalation_action(immediate, subject_ref),
		)
		if escalate:
			self._log_warn('danger sign reported', signs=signs)
		return out

	def education_for(self, sign: str, subject_ref: str | None = None) -> DangerEducation:
		"""One sign, what it means, and the button. The section asks for education *and* escalation."""
		assert sign in DANGER_SIGN_EDUCATION, f'no education for {sign}'
		return DangerEducation(
			sign=sign, means=DANGER_SIGN_EDUCATION[sign],
			action=self.escalation_action(sign in ('bleeding', 'convulsions', 'water_breaks'), subject_ref),
		)

	@staticmethod
	def escalation_action(immediate: bool, subject_ref: str | None = None) -> CareAction:
		"""The one tap. An emergency leads with the call; anything else leads with the maternity finder.

		The order is the classification's, the same rule §8.1's action list follows: a person
		bleeding at 30 weeks needs the phone number first and the map second, and one with a
		headache needs the clinic today and the number if she cannot get there.
		"""
		call = CareAction(kind='call', label='Call 719 now', href='tel:719')
		find = CareAction(kind='find_maternity', label='Find a maternity facility', href=MATERNITY_FINDER_HREF)
		return call if immediate else find

	# --- birth plan -------------------------------------------------------------------------

	async def save_birth_plan(self, plan: BirthPlan) -> BirthPlan:
		assert plan.subject_ref in self._pregnancies, 'a birth plan belongs to a registered pregnancy'
		self._plans[plan.subject_ref] = plan
		return plan

	def birth_plan(self, subject_ref: str) -> BirthPlan:
		"""The plan as it stands, empty rather than absent for a pregnancy with none yet.

		An empty plan is the honest answer to "what have I arranged": a screen that showed nothing
		would read as a failed load, and `gaps()` names all five fields, which is the list of what
		the section asks for.
		"""
		assert subject_ref in self._pregnancies, 'unknown pregnancy'
		return self._plans.get(subject_ref, BirthPlan(subject_ref=subject_ref))

	# --- PMTCT ------------------------------------------------------------------------------

	@staticmethod
	def pmtct_referral(subject_ref: str, hiv_positive: bool) -> PmtctReferral:
		"""§MON-002's "Referral to PMTCT where relevant".

		Relevance is the mother's HIV result, asked at the point of care and not stored: the status
		never reaches this service, only the boolean the caller derived from it, which is the same
		rule §MON-003's separate PIN enforces for the chronic log. A referral that stored the result
		would be a second copy of a diagnosis in a module with no PIN on it.
		"""
		return PmtctReferral(
			subject_ref=subject_ref, relevant=hiv_positive,
			programme=PMTCT_PROGRAMME if hiv_positive else None,
			advise=PMTCT_RELEVANT if hiv_positive else 'No PMTCT referral needed on this result.',
		)
