"""CHW services (spec §5 CHAN-005, §11.4 COM-101).

A CHW account exists only if a county team provisioned it and the national registry verified
it — the trust layer is worthless if anyone can self-enrol as a health worker.
"""
from afya.chw.views import JOB_AIDS, TRAINING_MODULES, ActivityLogEntry, ActivitySummary, ChwCase, ChwProfile
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

	def training(self) -> list[dict[str, object]]:
		return [dict(m) for m in TRAINING_MODULES]

	@staticmethod
	def job_aid(topic: str) -> str:
		assert topic in JOB_AIDS, f'no job aid for {topic}'
		return JOB_AIDS[topic]

	@staticmethod
	def ppe_reminder() -> str:
		return JOB_AIDS['ppe_donning']

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
