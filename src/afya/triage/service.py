"""Triage service — febrile algorithm with malaria trap (§6.3), EVD escalation, symptom diary."""
from afya.logmixin import LogMixin
from afya.registry.service import FeatureRegistry
from afya.strings import answerable, rec
from afya.triage.views import (
	DiaryEntry, DiaryExport, DiaryPrompt, DiaryTrend, Differential, EBOLA_SYMPTOMS, EMERGENCY_FLAGS,
	RiskLevel, TriageAction, TriageInput, TriageResult, TrendDirection, WATCH_FOR, WatchForItem,
)


def _one_tap(level: RiskLevel, red_flag: bool) -> list[TriageAction]:
	"""§8.1's second Output, "recommended action with one-tap execution (call 719, find facility,
	request CHW visit)".

	All three the section names are always offered, and the *order* is what the classification
	decides: an emergency leads with the call, a moderate case leads with the facility search, and a
	low case leads with the CHW visit. Offering only one of the three would make the client decide
	which screen to show from `risk_level`, which is the same defect as a prose recommendation — the
	action would exist as a sentence rather than as something executable.
	"""
	call = TriageAction(kind='call', label='Call 719', href='tel:719')
	facility = TriageAction(kind='find_facility', label='Find the nearest facility',
		href='/places/nearest')
	chw = TriageAction(kind='request_chw', label='Ask a community health worker to visit',
		href='/channels/chw/tasks')
	if level in (RiskLevel.emergency, RiskLevel.high_ebola_suspicion) or red_flag:
		return [call, facility, chw]
	if level is RiskLevel.high_other:
		return [facility, call, chw]
	return [chw, facility, call]


def _watch_for(level: RiskLevel) -> list[WatchForItem]:  # noqa: ARG001 — the signature is the point
	"""§8.1's third Output, "watch-for list for the next 24–48 hours".

	Every classification gets the list, including low: the section prints the output unconditionally,
	and the person who most needs to know what deterioration looks like is the one sent home. The
	list is ordered by urgency and the first four are the ones a person can act on tonight.

	The argument is taken and unused. §8.1 prints the same list for every rung, and a caller that
	had to know that would be one more place for the two to drift; `level` is in the signature so
	that a future section that *does* vary it changes one function rather than five call sites.
	"""
	assert isinstance(level, RiskLevel), 'level required'
	return [WatchForItem(sign=sign, action=action) for sign, action in WATCH_FOR]


class TriageService(LogMixin):
	def __init__(self, registry: FeatureRegistry) -> None:
		self._registry = registry
		self._diary: dict[str, DiaryEntry] = {}
		assert registry.available() and self._diary == {}, 'registry must be available'

	def assess(self, inp: TriageInput, lang: str = 'en') -> TriageResult:
		"""§8.1's ladder, walked in the order the section's own Outputs list it.

		Two branches produce a `high`, and they are separate members because they send a person to
		different places: `high_ebola_suspicion` is an isolation-and-notify answer and `high_other`
		is a seek-care-today answer. §8.1 prints them as two of its five classifications, and the
		enum carrying one `high` for both meant the payload could not say which.

		`emergency` is the red-flag rung and it is checked first, because a convulsing or bleeding
		person is not a fever question. §8.1 lists "unexplained bleeding, bleeding gums, blood in
		stool or vomit, bruising without cause, confusion, difficulty breathing, inability to drink,
		convulsions" as its own Inputs list, and they were absent from the input entirely.
		"""
		major = [s for s in inp.symptoms if s in EBOLA_SYMPTOMS]
		cluster = len([s for s in major if s != 'fever'])
		has_contact_history = inp.exposure_history
		bleeding = 'bleeding' in inp.symptoms
		emergency_flag = bool(EMERGENCY_FLAGS & set(inp.red_flags))
		if emergency_flag or bleeding:
			level = RiskLevel.emergency
		elif has_contact_history and (inp.temperature_c >= 38.0 or cluster >= 1):
			level = RiskLevel.high_ebola_suspicion
		elif inp.temperature_c >= 38.0 and cluster >= 3:
			level = RiskLevel.high_other
		elif inp.temperature_c >= 38.0:
			level = RiskLevel.malaria_suspect
		elif cluster >= 1:
			level = RiskLevel.medium
		else:
			level = RiskLevel.low
		# §ACC-002 names six voice-reporting languages; two have tables. The answer falls back to
		# English and says so, rather than raising: a person on a feature phone asking for Dholuo
		# cannot act on a stack trace, and §CHAN-2's own USSD menu offers Dholuo by name.
		served = answerable(lang)
		out = TriageResult(
			risk_level=level,
			recommendation=rec(lang, level.value),
			treated_as_malaria_first=level is RiskLevel.malaria_suspect,
			escalate_719=level in (RiskLevel.medium, RiskLevel.high_other,
				RiskLevel.high_ebola_suspicion, RiskLevel.emergency),
			served_in=served,
			language_fallback=served != lang,
			actions=_one_tap(level, emergency_flag),
			watch_for=_watch_for(level),
			red_flag_triggered=emergency_flag,
		)
		self._log_info('triage assessed', risk=out.risk_level.value, lang=lang, served_in=served)
		assert out.recommendation, 'recommendation required'
		assert out.actions and out.watch_for, '§8.1 prints four Outputs; two of them are lists'
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

	def diary_escalation(self, subject_ref: str) -> TriageResult | None:
		"""§TRI-002's "automatic escalation if new red flags are logged".

		The escalation is computed from the diary rather than stored on the entry, so it answers the
		question the section asks — is there a red flag *newly* logged — rather than "did any entry
		ever carry one". A flag already escalated on day 2 must not escalate again on day 4, or the
		person gets the same ambulance message every day until they stop reading it.

		Returns `None` when there is nothing to escalate. Returning a low-risk result instead would
		be worse than nothing: a client that renders the return value would show a triage answer
		where the section asks for silence.
		"""
		entries = self.diary(subject_ref)
		if not entries:
			return None
		escalated: set[str] = set()
		for entry in entries:
			flag = entry.worst_red_flag
			if flag is None or flag in escalated:
				continue
			escalated.add(flag)
			# The most recent entry's flag is the live one; an older flag that a later entry did
			# not repeat has already been acted on.
			if entry is entries[-1]:
				inp = TriageInput(
					symptoms=entry.symptoms, temperature_c=entry.temperature_c,
					red_flags=list(entry.red_flags),
				)
				result = self.assess(inp)
				self._log_info('diary escalated', subject_ref=subject_ref, flag=flag)
				return result
		return None

	def diary_trend(self, subject_ref: str) -> DiaryTrend:
		"""§TRI-002's "trend view: is this getting better or worse?".

		Read from the entries rather than asked of the person, because a self-report of "worse" and
		a diary that shows a rising temperature are two different facts and the section wants the
		second. The direction is decided by temperature first — it is the one continuous measure in
		the entry — and by symptom count second, which is why `changed` names what moved instead of
		leaving the reader to infer it from a word.
		"""
		entries = self.diary(subject_ref)
		if len(entries) < 2:
			return DiaryTrend(
				direction=TrendDirection.unknown, days_logged=len(entries), changed=[],
				note='One entry so far — a trend needs at least two days to read.' if entries
					else 'No entries yet.',
			)
		first, last = entries[0], entries[-1]
		changed: list[str] = []
		delta = last.temperature_c - first.temperature_c
		if abs(delta) >= 0.3:
			changed.append(f'temperature {"up" if delta > 0 else "down"} {abs(delta):.1f} °C')
		new_symptoms = sorted(set(last.symptoms) - set(first.symptoms))
		gone = sorted(set(first.symptoms) - set(last.symptoms))
		if new_symptoms:
			changed.append('new: ' + ', '.join(s.replace('_', ' ') for s in new_symptoms))
		if gone:
			changed.append('gone: ' + ', '.join(s.replace('_', ' ') for s in gone))
		if last.red_flags and not first.red_flags:
			changed.append('a red flag was logged')
			direction = TrendDirection.worsening
		elif delta >= 0.3 or len(new_symptoms) > len(gone):
			direction = TrendDirection.worsening
		elif delta <= -0.3 or len(gone) > len(new_symptoms):
			direction = TrendDirection.improving
		else:
			direction = TrendDirection.stable
		note = {
			TrendDirection.worsening: 'Getting worse over the days logged. Call 719 if it continues.',
			TrendDirection.improving: 'Improving over the days logged. Keep logging until day 21.',
			TrendDirection.stable: 'No clear change across the days logged.',
			TrendDirection.unknown: 'Not enough entries to read a trend.',
		}[direction]
		return DiaryTrend(direction=direction, days_logged=len(entries), changed=changed, note=note)

	def diary_export(self, subject_ref: str) -> DiaryExport:
		"""§TRI-002's "exportable summary for a clinician".

		Rendered as text the person can hand over, and it carries the day, the temperature, the
		symptoms and the red flags — the four things a clinician reading a fever history needs. It
		carries no location and no contact history: the export is given to a clinician, but it is
		also a document that leaves the phone, and §8.1's Privacy clause is about triage data
		leaving the device. The clinician can ask the two questions the text omits.
		"""
		entries = self.diary(subject_ref)
		trend = self.diary_trend(subject_ref)
		lines = [f'Symptom diary — {len(entries)} day(s) logged, days 1–21', f'Trend: {trend.direction.value} — {trend.note}', '']
		for e in entries:
			when = e.logged_at_iso or f'day {e.day}'
			flags = f'  red flags: {", ".join(f.replace("_", " ") for f in e.red_flags)}' if e.red_flags else ''
			lines.append(f'{when}: {e.temperature_c:.1f} °C — {", ".join(s.replace("_", " ") for s in e.symptoms) or "no symptoms"}{flags}')
		text = '\n'.join(lines)
		return DiaryExport(subject_ref=subject_ref, days_logged=len(entries), trend=trend,
			text=text, entries=entries)

	def diary_prompt(self, subject_ref: str, day: int, opted_in: bool) -> DiaryPrompt | None:
		"""§TRI-002's daily "how are you feeling?" prompt (opt-in).

		Returns `None` for a person who did not opt in, rather than a prompt with a flag. The
		section writes the opt-in into the Feature, so a declined prompt is not a prompt — and a
		client that renders whatever it is handed would show it to someone who said no.
		"""
		if not opted_in:
			return None
		assert 1 <= day <= 21, 'the prompt is inside the 21-day window'
		entries = self.diary(subject_ref)
		return DiaryPrompt(
			subject_ref=subject_ref, day=day,
			question='How are you feeling today? Any fever, or anything new?',
			last_logged_day=entries[-1].day if entries else None,
		)

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
	'malaria': 'Test and treat for malaria first; call 719 if there is no improvement in 48 hours.',
	'typhoid': 'Fever for more than 3 days suggests typhoid. Get a blood test (Widal or culture) at a facility.',
	'flu': 'Rest, fluids; seek care if breathing is difficult or fever >3 days.',
	'cholera': 'START ORS NOW and get to a facility. Rapid dehydration is the danger. Call 719.',
	'covid': 'Mask up; test if available; seek care for breathing difficulty.',
	'evd': 'Isolate immediately; call 719; go to nearest isolation treatment unit.',
}
