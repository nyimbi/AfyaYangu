"""Cycle tracking service — calendar-method prediction, irregularity flagging, adolescent privacy note."""
from datetime import date, timedelta
from statistics import median

from afya.logmixin import LogMixin
from afya.women import content
from afya.women.views import (
	ContraceptionPlan, ContraceptionRequest, CycleLog, CyclePrediction, MenopauseStatus,
	ReproductiveReferral,
)

_MIN_LOGS = 3


def _add_days(iso: str, days: int) -> str:
	"""`iso` shifted by whole days, on the real calendar.

	This module used to do it with `int(month) * 30 + int(day)` — a 30-day month for every month, so
	January 31 + 28 days came out as `2026-03-03` where the calendar says `2026-02-28`. Every
	`next_period_iso` the service produced was wrong by one to three days, on both branches, and the
	fast branch (`day_ <= 28`) was wrong too because it never carried the month. A date the app shows
	a person about their own body has to be the date `datetime` computes.
	"""
	y, m, d = (int(p) for p in iso.split('-')[:3])
	return (date(y, m, d) + timedelta(days=days)).isoformat()


def _days_between(a_iso: str, b_iso: str) -> int:
	"""Whole days from `a_iso` to `b_iso`, negative when `b` is earlier. Real calendar, no 30-day month."""
	y, m, d = (int(p) for p in a_iso.split('-')[:3])
	y2, m2, d2 = (int(p) for p in b_iso.split('-')[:3])
	return (date(y2, m2, d2) - date(y, m, d)).days


def _months_between(a_iso: str, b_iso: str) -> int:
	"""Whole calendar months from `a_iso` to `b_iso`. §REC-004's twelve-month rule counts months."""
	y, m, d = (int(p) for p in a_iso.split('-')[:3])
	y2, m2, d2 = (int(p) for p in b_iso.split('-')[:3])
	months = (y2 - y) * 12 + (m2 - m)
	return months - 1 if d2 < d else months


class WomenService(LogMixin):
	def __init__(self) -> None:
		self._logs: dict[str, list[CycleLog]] = {}
		self._plans: dict[str, ContraceptionPlan] = {}
		self._referrals: list[ReproductiveReferral] = []
		assert self._logs == {}

	async def log(self, entry: CycleLog) -> int:
		assert entry.subject_ref, 'subject required'
		if entry.pain_level >= 7:
			self._log_warn('high dysmenorrhoea reported')
		self._logs.setdefault(entry.subject_ref, []).append(entry)
		return len(self._logs[entry.subject_ref])

	def _ordered(self, subject_ref: str) -> list[CycleLog]:
		"""The subject's logs, oldest first — the order every calculation below depends on.

		`predict` used to read `logs[-1]` for its anchor, which is the *last logged* and not the
		*latest period*: a person who backfills a missed earlier period — the ordinary way a tracker
		is used — moved their own anchor backwards, and the prediction followed it. A backfilled
		December log against January–March entries produced a next-period date in January, for a
		person standing in March.
		"""
		return sorted(self._logs.get(subject_ref, []), key=lambda entry: entry.start_iso)

	def predict(self, subject_ref: str, ref_date: str) -> CyclePrediction:
		"""The next period and the fertile window, anchored to the latest logged period.

		`ref_date` is the day the person is asking from, and its job is the one thing the anchor
		cannot say: whether the predicted date has already passed. A prediction is anchored to the
		last period and is therefore always in that period's future — a person who has not logged for
		three months gets a confident date in the past, and a tracker that reported it without comment
		would be telling them they are due last month.
		"""
		logs = self._ordered(subject_ref)
		assert logs, 'insufficient data: needs >= 3 cycles'
		specs = [entry.start_iso for entry in logs]
		spans = [_days_between(a, b) for a, b in zip(specs[:-1], specs[1:])]
		spans = [s for s in spans if 20 <= s <= 45]
		if len(spans) < _MIN_LOGS - 1:
			return CyclePrediction(
				next_period_iso=None, fertile_window_days=None,
				cycle_regularity='insufficient_data',
				advise='Log at least 3 periods for predictions.')
		md = round(median(spans))
		regularity = 'regular' if (max(spans) - min(spans)) <= 4 else 'irregular'
		last = specs[-1]
		next_period = _add_days(last, md)
		overdue_days = _days_between(next_period, ref_date)
		# §REC-004's "fertility awareness", as dates and as a pair of cycle days. Ovulation is
		# estimated `LUTEAL_PHASE_DAYS` before the next period — the source's midpoint — and the
		# window opens `SPERM_SURVIVAL_DAYS` earlier, because that is how long sperm survive.
		ovulation = _add_days(next_period, -content.LUTEAL_PHASE_DAYS)
		window = (md - content.LUTEAL_PHASE_DAYS - content.SPERM_SURVIVAL_DAYS,
		          md - content.LUTEAL_PHASE_DAYS + content.EGG_VIABILITY_DAYS)
		if regularity == 'irregular':
			advise = 'Cycle irregular across logs — consider clinic review.'
		elif overdue_days > 0:
			advise = (
				f'Your last logged period was {last} and your usual cycle is {md} days, so the next '
				f'one was expected around {next_period} — {overdue_days} days ago. Log it when it '
				f'starts, or see a clinician if you might be pregnant.')
		else:
			advise = (f'Next period expected ~{next_period}; fertile window approx days '
			          f'{window[0]}–{window[1]} of cycle. Log daily for better predictions.')
		out = CyclePrediction(
			next_period_iso=next_period,
			fertile_window_days=window,
			cycle_regularity=regularity,
			advise=advise,
			fertile_from_iso=_add_days(ovulation, -content.SPERM_SURVIVAL_DAYS),
			fertile_to_iso=_add_days(ovulation, content.EGG_VIABILITY_DAYS),
			ovulation_iso=ovulation,
			fertility_note=f'{content.FERTILE_WINDOW_CAVEAT} {content.FERTILITY_AWARENESS_NOTE}',
		)
		assert out.advise, 'advise required'
		assert out.fertile_from_iso and out.fertile_to_iso, 'a window with no dates is not a window'
		return out

	# --- §REC-004's contraception reminders --------------------------------------------------------

	def set_contraception(self, req: ContraceptionRequest) -> ContraceptionPlan:
		"""Record a method and work out the next date it is due.

		The method is looked up in WHO's own table rather than taken from the caller, so a client
		cannot label withdrawal "highly effective" and a method the source does not list cannot be
		recorded as one it does. That is why the argument is a `ContraceptionRequest` and the return
		is a `ContraceptionPlan`: the label, the reliability band and the STI flag are this method's
		answer, not the caller's.
		"""
		row = content.METHODS_BY_SLUG.get(req.method)
		assert row is not None, f'unknown contraceptive method {req.method!r}'
		assert req.repeat_days is None or req.method in ('pill', 'injection', 'patch', 'vaginal_ring'), (
			'a long-acting method is not taken on a repeating schedule')
		plan = ContraceptionPlan(
			subject_ref=req.subject_ref, method=req.method, started_iso=req.started_iso,
			repeat_days=req.repeat_days, label=str(row['label']),
			reliability=str(row['reliability']), prevents_sti=bool(row['prevents_sti']),
		)
		plan.next_due_iso = (
			_add_days(plan.started_iso, plan.repeat_days) if plan.repeat_days else None)
		notes = [content.NO_INFERTILITY_NOTE]
		if plan.reliability == content.Reliability.LESS_RELIABLE:
			notes.append(content.FERTILITY_AWARENESS_NOTE)
		if not plan.prevents_sti:
			notes.append(
				'This method does not protect against sexually transmitted infections, including '
				'HIV. Condoms are the only method that does both.')
		plan.notes = notes
		self._plans[plan.plan_id] = plan
		self._log_info('contraception recorded', plan_id=plan.plan_id, method=plan.method)
		return plan

	def contraception_due(self, subject_ref: str, on_iso: str) -> list[ContraceptionPlan]:
		"""The subject's methods whose next date has arrived by `on_iso` — the reminder, as data."""
		due = [p for p in self._plans.values()
		       if p.subject_ref == subject_ref and p.next_due_iso and p.next_due_iso <= on_iso]
		return sorted(due, key=lambda p: p.next_due_iso or '')

	def contraception_methods(self) -> list[dict[str, object]]:
		"""WHO's method table, so a client renders the same groups we record against."""
		return [dict(row) for row in content.CONTRACEPTIVE_METHODS]

	# --- §REC-004's menopause support --------------------------------------------------------------

	def menopause(self, subject_ref: str, today_iso: str) -> MenopauseStatus:
		"""The person's state under the fact sheet's twelve-month rule, and nothing beyond it.

		`postmenopausal` is reached only by twelve consecutive months with no logged period, which is
		the source's own sentence. Before that the state is `perimenopausal` — and the fact sheet is
		explicit that pregnancy is still possible and contraception still recommended, so
		`contraception_still_recommended` is True through the whole transition. The tracker never
		uses age to reach the state: the source's 45–55 is what "most women" experience and not a
		test to apply to one.
		"""
		logs = self._ordered(subject_ref)
		if not logs:
			return MenopauseStatus(
				subject_ref=subject_ref, state='insufficient_data', months_since_last_period=None,
				months_required=content.PERIMENOPAUSE_MONTHS, last_period_iso=None,
				contraception_still_recommended=True, symptoms=[],
				advise='Log a period to start tracking your cycle.')
		last = logs[-1].start_iso
		months = _months_between(last, today_iso)
		state = 'postmenopausal' if months >= content.PERIMENOPAUSE_MONTHS else 'perimenopausal'
		advise = {
			'postmenopausal': (
				f'Twelve consecutive months have passed since your last logged period. That is how '
				f'WHO defines the end of perimenopause. {content.MENOPAUSE_ADVICE}'),
			'perimenopausal': (
				f'{months} months since your last logged period, of the '
				f'{content.PERIMENOPAUSE_MONTHS} that mark the end of perimenopause. Pregnancy is '
				f'still possible during perimenopause, so contraception is still recommended. '
				f'{content.MENOPAUSE_ADVICE}'),
		}[state]
		return MenopauseStatus(
			subject_ref=subject_ref, state=state, months_since_last_period=months,
			months_required=content.PERIMENOPAUSE_MONTHS, last_period_iso=last,
			contraception_still_recommended=state == 'perimenopausal',
			symptoms=[dict(s) for s in content.MENOPAUSE_SYMPTOMS], advise=advise)

	# --- §REC-004's referral to services -----------------------------------------------------------

	def refer(self, subject_ref: str, reason: str) -> ReproductiveReferral:
		"""Name the services this section's referral is for, and what could not be reached.

		The counselling rows come from `mental.COUNSELLING_LINES` — the table §INF-006's directory
		also reads — so a number cannot drift between the two screens that show it. Every row in that
		table carries `verified: 'False'` today, which means the numbers are listed by name in
		`unreachable` rather than presented as checked: a referral to a number nobody confirmed is
		worse than none, because the person stops looking.
		"""
		from afya.mental.views import COUNSELLING_LINES
		assert reason, 'a referral without a reason is a record nobody can act on'
		unverified = [f"{row['name']} ({row['number']}) — number not verified against the provider"
		              for row in COUNSELLING_LINES if row.get('verified') != 'True']
		services = [dict(row) for row in content.REFERRAL_SERVICES]
		for row in COUNSELLING_LINES:
			services.append({'slug': 'counselling_line', 'label': row['name'],
			                 'where': row['number'], 'note': row.get('hours', '')})
		referral = ReproductiveReferral(
			subject_ref=subject_ref, reason=reason, services=services, unreachable=unverified,
			advise='Contact one of these services. If a number does not answer, call 719.')
		self._referrals.append(referral)
		self._log_info('reproductive referral recorded', referral_id=referral.referral_id)
		return referral