"""§2's problem statement — seven citizen-layer gaps and five conditioned lessons, as data.

§2 is the argument for the product, and it was the last block in the spec with no carrier. §2.1 is
Kenya's existing posture, §2.2 is a table of seven things the health-system layer does not do, §2.3
is five lessons from comparable deployments. Two of the three are checkable against this repo, and
the second half of §2.3 is the half that matters.

**§2.2 is the product's own claim list.** Seven rows, each naming a gap and its consequence. Every
one is a capability this build either has or does not, and a product whose problem statement names
seven gaps while closing six has a claim it cannot support. `closed_by` is a `module:attr`
reference and `unclosed` is the finding — reported, not repaired, because whether a gap is this
repo's to close is a product decision.

**§2.3's lessons are conditions, and the condition is the checkable half.** Each paragraph reads
"X works, *when* Y" or "X is feasible, *but only if* Y". The claim is about somebody else's
deployment — a fact about the world that no tree can settle. The qualifier is a requirement on
*this* one, and a build that reads only the bolded half implements the lesson and drops the thing
that made it safe. That is why `condition` is carried separately and asserted to be a clause of the
lesson rather than a paraphrase of it.

**One lesson is not honoured, and it is the one §LOC-002 also rests on.** Lesson 3's condition is
"only if it is opt-in and transparent". `proximity_logging` is a §SEC-001 consent category with a
written scope and a written revocation consequence ("Close-contact alerts cannot reach you if you
are exposed"), and no proximity path reads it: `log_encounter` appends the token and asserts a bound
on the store. The gate exists and is correct — `PrivacyService.has_category_consent` — and nothing
on this path calls it, which is the shape §16.2's `backoff_delay_s` had. The declaration side *is*
gated, by `proxied`, but that is a different property: it prevents social-graph inference, not
collection without consent.
"""
from afya.problem.views import CitizenGap, GapReport, Lesson, LessonReport
from afya.refs import resolves

# §2.1's eight bullets, verbatim. They describe the health-system layer §2.2 contrasts against —
# isolation units, trained providers, mobile labs, a toll-free platform, a chatbot, dashboards,
# traveller screening, the laboratory network. Only two name a system this repo integrates with, and
# `SITUATION_JOINS` records which; the rest are facts about Kenya's posture and are carried so a
# citation resolves rather than because anything here checks them.
SITUATION_ITEMS: tuple[str, ...] = (
	'Isolation and treatment units across the country, with plans for further expansion',
	'Thousands of healthcare providers trained in Ebola prevention and case management',
	'Mobile laboratories at border points including Busia and Lwakhakha',
	'Activation of a toll-free reporting platform',
	'A WhatsApp chatbot for public information',
	'Daily health dashboards tracking ICU bed availability and priority indicators',
	'Screening of hundreds of thousands of travelers',
	'Hundreds of samples tested through the national laboratory network',
)

# The two §2.1 items that name something §18 integrates with. Keyed by the section's own wording so
# a revision that rewords the bullet fails here rather than silently detaching the join.
SITUATION_JOINS: dict[str, str] = {
	'A WhatsApp chatbot for public information': '§18.2 JALI — afya.integrations.service:JaliClient',
	'Daily health dashboards tracking ICU bed availability and priority indicators':
		'§18.3 PHEOC — afya.integrations.service:PheocClient',
}

# §2.2's seven rows, verbatim, in the section's order. The Gap cell is the section's wording and the
# Consequence cell is carried because it is what makes the row a requirement rather than a heading —
# "no self-triage tool" is a category; "people with fever don't know whether to stay home, go to a
# clinic, or call a hotline" is the failure the feature exists to prevent.
CITIZEN_GAPS: tuple[tuple[str, str, str | None, str | None], ...] = (
	('No self-triage tool',
		"People with fever don't know whether to stay home, go to a clinic, or call a hotline",
		'afya.triage.service:TriageService.assess', None),
	('No persistent monitoring tool',
		'Contacts under 21-day observation have no structured way to log symptoms',
		'afya.monitoring.service:MonitoringService', None),
	('No citizen reporting channel beyond a phone number',
		'Reporting requires a call, which many avoid',
		'afya.community.service:CommunityService.submit_case', None),
	('No localized risk awareness',
		"National case counts are abstract; people don't know their own neighbourhood status",
		'afya.info.service:InfoService.dashboard', None),
	('No consented contact-tracing assistance',
		'Manual recall is unreliable; phone data is unused',
		'afya.community.service:CommunityService.save_contacts',
		'the list is held on the phone until the reporter chooses to share it'),
	('No passive surveillance',
		'Symptom signals never reach the health system until someone presents at a facility',
		'afya.ai.service:AIService.assess_warning',
		'aggregated signals only; a raised signal routes to an epidemiologist, never a public alert'),
	('No misinformation counter',
		'Rumours spread faster than official correction',
		'afya.community.service:CommunityService.flag_misinfo', None),
)

# §2.3's five paragraphs. `lesson` is the section's bolded "Key lesson" sentence verbatim; `condition`
# is the qualifying clause inside it, or None where the lesson carries none.
#
# `honoured` is tri-state and the three values mean different things. True is a verdict this repo can
# reach. False is a verdict it can also reach, and lesson 3 is the one. None means the question is
# not about this tree at all — lesson 4 claims viability "on consumer handsets" while §13.1's own
# availability cell says LiDAR reaches "Select flagships" only, so the answer is a fact about the
# phone market and the honest report is `undecided` with the reason attached.
LESSONS: tuple[tuple[str, str, str | None, str | None, bool | None, str | None], ...] = (
	('AVADAR (Auto-Visual AFP Detection and Reporting)',
		'CHW-mediated mobile reporting works, when the tool is simple and the alerting is automatic.',
		'when the tool is simple and the alerting is automatic',
		'afya.community.service:CommunityService.submit_case', True,
		'the officer is alerted inside the submission, so escalation is not a second manual step'),
	('Offline-first modular mHealth platforms',
		'assume no connectivity, treat sync as a bonus.',
		'assume no connectivity, treat sync as a bonus',
		'afya.sync.service:SyncService.flush', True,
		'an offline flush defers every due operation rather than pretending it sent'),
	('COVID-19 exposure notification systems',
		'proximity notification is feasible and privacy-preservable, but only if it is opt-in and transparent.',
		'only if it is opt-in and transparent',
		'afya.privacy.service:PrivacyService.has_category_consent', False,
		'§SEC-001 carries `proximity_logging` with a scope and a revocation consequence; no proximity '
		'path reads it, so an encounter is logged without the opt-in the lesson requires'),
	('LiDAR respiration monitoring (LiBre and successors)',
		'contactless respiratory monitoring is now viable on consumer handsets.',
		None,
		'afya.sensors.service:SENSORS', None,
		'§13.1 gives LiDAR "Select flagships" / "iPhone Pro / iPad Pro" — whether that is a consumer '
		'handset is a fact about the phone market, not about this tree'),
	('On-device acoustic cough detection',
		'passive acoustic surveillance is possible without a privacy catastrophe, if processing stays on-device.',
		'if processing stays on-device',
		'afya.sensors.service:HANDLING', True,
		'no sensitivity class may retain raw data, so the audio never leaves the device'),
)

assert len(CITIZEN_GAPS) == 7, '§2.2 lists seven gaps'
assert len(LESSONS) == 5, '§2.3 draws five lessons'
assert all(c is None or c in lesson for _, lesson, c, _, _, _ in LESSONS), \
	'every §2.3 condition must be a clause of its own lesson, not a paraphrase of it'
assert set(SITUATION_JOINS) <= set(SITUATION_ITEMS), 'a §2.1 join must name a §2.1 bullet'


def gap_report() -> GapReport:
	"""§2.2's seven gaps against what closes each. `unclosed` is the finding."""
	gaps = [
		CitizenGap(gap=gap, consequence=consequence, closed_by=ref,
			resolves=resolves(ref) if ref else False, note=note)
		for gap, consequence, ref, note in CITIZEN_GAPS
	]
	unclosed = [g.gap for g in gaps if not g.resolves]
	return GapReport(gaps=gaps, unclosed=unclosed, closed_count=len(gaps) - len(unclosed))


def lesson_report() -> LessonReport:
	"""§2.3's five lessons with their conditions, and the three verdicts separated.

	`unhonoured` and `unresolved` are both findings and they are not the same one: the first is a
	condition this repo was supposed to meet and does not, the second is a reference that does not
	land. `undecided` is neither — it is a question the repo cannot answer, kept apart so a report
	that mixes them cannot be read as three ways of saying "incomplete".
	"""
	lessons = [
		Lesson(system=system, lesson=lesson, condition=condition, honoured_by=ref,
			resolves=resolves(ref) if ref else False, honoured=honoured, note=note)
		for system, lesson, condition, ref, honoured, note in LESSONS
	]
	return LessonReport(
		lessons=lessons,
		unhonoured=[l.lesson for l in lessons if l.honoured is False],
		unresolved=[l.lesson for l in lessons if l.honoured_by and not l.resolves],
		undecided=[l.lesson for l in lessons if l.honoured is None],
	)
