"""Canaries for tests/ci/test_mon001.py — each gate pointed at a planted defect and watched to fail.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
S = ROOT / 'src/afya/monitoring/service.py'
V = ROOT / 'src/afya/monitoring/views.py'
R = ROOT / 'src/afya/records/views.py'
RS = ROOT / 'src/afya/records/service.py'
A = ROOT / 'src/afya/alerting/views.py'

CANARIES = [
	# 1. The tracker keeps its own schedule again, keyed differently from the wallet's. This is the
	#    defect that made a dose in one store invisible to the other.
	('the schedule is copied and renamed again', V,
	 "EPI_DUE_WEEKS: dict[str, list[tuple[int, int]]] = EPI_SCHEDULE",
	 "EPI_DUE_WEEKS: dict[str, list[tuple[int, int]]] = {'RV1': [(1, 6)], 'MMR': [(1, 39)], 'IPV': [(2, 14)]}",
	 'test_the_schedule_is_one_dict_and_the_tracker_re_exports_it'),

	# 2. The dose goes back to the tracker's own set and never reaches the wallet.
	('the dose stops reaching the wallet', S,
	 "		if self._wallet is not None and rec.member_ref in self._wallet_members():\n			await self._wallet.record_immunisation(rec)",
	 "		pass",
	 'test_a_dose_recorded_on_the_tracker_reaches_the_wallet'),

	# 3. The photo hash stops being checked, so any string is a photograph of a card.
	('the card digest stops being a digest', R,
	 "	card_photo_sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')",
	 "	card_photo_sha256: str | None = None",
	 'test_the_card_photo_travels_as_a_digest_and_is_optional'),

	# 4. Dose zero is refused again — OPV0, the birth dose, becomes unrecordable.
	('dose zero is refused again', R,
	 "	dose_no: int = Field(ge=0, le=4)",
	 "	dose_no: int = Field(ge=1, le=4)",
	 'test_dose_zero_is_recordable_because_opv0_is_a_real_dose'),

	# 5. The gap list measures whole years again, so no dose is due before the first birthday.
	('the gap list measures whole years again', RS,
	 "		age_days = ((today or date.today()) - born).days",
	 "		age_days = age_years(self._members[member_ref].dob_iso, today or date.today()) * 360",
	 'test_the_gap_list_sees_the_infant_schedule_before_the_first_birthday'),

	# 6. The alert list is built from the overdue rows only, so the coming reminder never fires —
	#    the reminder becomes a report of failures.
	('the coming alert never fires', S,
	 "			elif row.remind_days_before:",
	 "			elif False:",
	 'test_the_coming_alert_fires_three_days_out_and_not_before'),

	# 7. A missed dose stops being reported as missed.
	('a missed dose raises no alert', S,
	 "			if row.status == 'overdue':",
	 "			if False:",
	 'test_a_missed_dose_raises_an_alert_and_a_coming_one_raises_a_different_alert'),

	# 8. A given dose is also reported as missed — the alert list stops reading the schedule.
	('a given dose is also reported missed', S,
	 "		for row in self.schedule(member_ref, today_iso):",
	 "		for row in self.schedule(member_ref, today_iso):\n			row.status = 'overdue'",
	 'test_a_given_dose_raises_no_alert'),

	# 9. The campaign is published under a category no parent can subscribe to.
	('the campaign lands under a category nobody set', A,
	 "	'immunisation': 'immunisation_reminders',",
	 "	'immunisation': 'health_tips',",
	 'test_a_campaign_is_published_into_the_feed_under_a_category_a_parent_can_choose'),

	# 10. A campaign reaches no county and is published anyway.
	('a campaign with no county is published', S,
	 "		assert notice.counties, 'a campaign with no county reaches nobody'",
	 "		pass",
	 'test_a_campaign_with_no_county_or_a_backwards_window_is_refused'),

	# 11. The age band stops being ordered, so (59, 9) is a band of nobody.
	('a backwards age band is accepted', V,
	 "		assert 0 <= low < high <= 216, f'{low}-{high} months is not an age band a campaign can have'",
	 "		assert 0 <= low <= 216, 'age band in range'",
	 'test_a_campaign_with_no_county_or_a_backwards_window_is_refused'),

	# 12. The campaign window is ignored, so every campaign ever issued is "running today".
	('a campaign runs outside its dates', S,
	 "		               if county in c.counties and c.starts_iso <= on_iso <= c.ends_iso)",
	 "		               if county in c.counties)",
	 'test_a_campaign_is_running_only_between_its_dates'),

	# 13. The feed stops verifying what it publishes, so an unchecked notice reaches every parent.
	('an unverified campaign reaches the feed', S,
	 "					verified=True, published_iso=notice.starts_iso))",
	 "					verified=False, published_iso=notice.starts_iso))",
	 'test_a_campaign_is_published_into_the_feed_under_a_category_a_parent_can_choose'),

	# 14. The share stops expiring, so a "time-limited" share of a child's record is unlimited.
	('the share stops expiring', RS,
	 "		assert at <= _parse_iso(grant.expires_iso), (\n			f'this share ended on {grant.expires_iso}'\n		)",
	 "		pass",
	 'test_the_immunisation_record_is_shareable_through_the_wallets_own_grant'),

	# 15. The IDOR guard is loosened: another person's child becomes readable.
	('another persons child is readable', ROOT / 'src/afya/service.py',
	 "	async def monitoring_schedule(member_ref: str, today_iso: str = '2026-10-10', _subject: str = Depends(require_self_or_guardian(lambda r: r.path_params['member_ref']))) -> list[dict[str, object]]:",
	 "	async def monitoring_schedule(member_ref: str, today_iso: str = '2026-10-10', _subject: str = Depends(require_self(names_subject=False))) -> list[dict[str, object]]:",
	 'test_another_persons_child_is_refused'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_mon.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_mon001.py::{node}'],
			cwd=ROOT, capture_output=True, text=True)
		caught = proc.returncode != 0
	finally:
		shutil.copy2(backup, path)
		assert path.read_text() == s, f'{name}: revert did not restore'
	print(f'{"CAUGHT " if caught else "MISSED "} {name}')
	if not caught:
		failures.append(name)
		print(proc.stdout[-1500:])
print()
print(f'{len(CANARIES) - len(failures)}/{len(CANARIES)} fired')
sys.exit(1 if failures else 0)
