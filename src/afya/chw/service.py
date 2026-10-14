"""CHW services (spec §5 CHAN-005, §11.4 COM-101).

A CHW account exists only if a county team provisioned it and the national registry verified
it — the trust layer is worthless if anyone can self-enrol as a health worker.
"""
from afya.chw.views import (
	JOB_AID_TITLES, JOB_AIDS, TRAINING_MODULES, ActivityLogEntry, ActivitySummary, ChwCase, ChwProfile,
	JobAidSheet,
)
from afya.logmixin import LogMixin


class ChwService(LogMixin):
	def __init__(self) -> None:
		self._chws: dict[str, ChwProfile] = {}
		self._cases: dict[str, list[ChwCase]] = {}
		self._activity: list[ActivityLogEntry] = []
		assert self._chws == {} and self._activity == []

	async def provision(self, profile: ChwProfile) -> ChwProfile:
		assert profile.registry_verified, 'CHW must be verified against the national registry (§COM-101)'
		assert profile.provisioned_by in ('County', 'MoH'), 'accounts are provisioned by a county health team'
		self._chws[profile.chw_ref] = profile
		self._log_info('chw provisioned', chw=profile.chw_ref, county=profile.county)
		return profile

	def profile(self, chw_ref: str) -> ChwProfile:
		assert chw_ref in self._chws, 'unknown or unprovisioned CHW'
		return self._chws[chw_ref]

	def serving(self, county: str) -> ChwProfile | None:
		"""The worker §INF-006's directory lists for a county, or `None` if the county has none.

		`None` rather than an assertion, because "this county has no CHW provisioned" is an answer the
		directory needs — the sixth Content is then reported absent, which is a fact a screen can
		print. An assert here would turn a gap in the deployment into a 500 on a life-safety screen.

		The pick is the lowest `chw_ref` among the county's workers, which is stable across restarts
		and gives the same person every time; a random pick would show a caller a different worker on
		each refresh, and the number they saved would stop being the number they reach.
		"""
		workers = sorted((w for w in self._chws.values() if w.county == county), key=lambda w: w.chw_ref)
		return workers[0] if workers else None

	def training(self) -> list[dict[str, object]]:
		return [dict(m) for m in TRAINING_MODULES]

	@staticmethod
	def job_aid(topic: str) -> str:
		assert topic in JOB_AIDS, f'no job aid for {topic}'
		return JOB_AIDS[topic]

	@staticmethod
	def ppe_reminder() -> str:
		return JOB_AIDS['ppe_donning']

	@staticmethod
	def job_aid_sheet(topic: str) -> JobAidSheet:
		"""One job aid rendered as a printable PDF — §CHAN-5's "Printed job aids" half.

		The module held both halves and joined neither: `JOB_AIDS` is the text and `afya.records.pdf`
		is the writer, so a job aid was a string a screen could show and nothing a worker could carry.
		§CHAN-5's bullet is *printed*, and the flip-chart half of it is genuinely not producible here
		— a chart is drawn, and the tree's only vector primitives are the explainer's rectangles and
		circles, so `pictogram='house'` is a name with no geometry behind it. This is the half that is.

		The sheet wraps the aid text rather than trusting it to fit, because the aids are single long
		sentences and a PDF line that runs past the margin is clipped at the page edge.
		"""
		assert topic in JOB_AIDS, f'no job aid for {topic}'
		from afya.records.pdf import render, wrap

		title = JOB_AID_TITLES[topic]
		lines = wrap(JOB_AIDS[topic])
		return JobAidSheet(
			topic=topic, title=title, media_type='application/pdf',
			filename=f'job-aid-{topic}.pdf', content=render(title, lines).decode('latin-1'),
		)

	async def assign_case(self, chw_ref: str, case: ChwCase) -> ChwCase:
		self.profile(chw_ref)
		self._cases.setdefault(chw_ref, []).append(case)
		return case

	def cases(self, chw_ref: str) -> list[ChwCase]:
		return list(self._cases.get(chw_ref, []))

	def case_load(self, chw_ref: str) -> int:
		"""Open cases only — a closed case is not workload."""
		return len([c for c in self._cases.get(chw_ref, []) if c.status != 'closed'])

	async def log_activity(self, entry: ActivityLogEntry) -> ActivityLogEntry:
		self.profile(entry.chw_ref)
		self._activity.append(entry)
		return entry

	def activity_summary(self, chw_ref: str, period: str) -> ActivitySummary:
		rows = [e for e in self._activity if e.chw_ref == chw_ref]
		by_activity: dict[str, int] = {}
		for e in rows:
			by_activity[e.activity] = by_activity.get(e.activity, 0) + 1
		total = len(rows)
		note = (
			'Good coverage this period — keep logging so supervision reflects real work.'
			if total >= 10 else 'Light activity logged. Log each visit so your work is visible to the county team.'
		)
		return ActivitySummary(chw_ref=chw_ref, period=period, by_activity=by_activity, total=total, supervision_note=note)
