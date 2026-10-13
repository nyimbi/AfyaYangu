"""Canaries for tests/ci/test_mon007.py.

§MON-007's two missing bullets were both closed by adding a *carrier* — a feed category for the
notice, a scheduled instant for the reminder. Both are shapes that render as working code when they
are wrong, because the wrong version still publishes something and still returns a time. Each canary
below is a plausible implementation of the same feature that does the wrong thing:

* **The supplement rule dropped from the published body** (#1) — the manual's condition that
  larviciding "should never be seen as a substitute for ITNs or IRS". The notice still publishes,
  the round is still announced, and a resident stops using a net. This is the canary whose failure
  mode is a malaria case.
* **The round filed under the wrong feed category** (#2) — it still reaches the feed and still has
  a category; it simply never matches the preference a person set, so the notice goes to nobody.
* **A county added to every item** (#3) — the feed filters by county, so an item for Siaya is
  invisible to a Kisumu subscriber and a Kisumu subscriber is shown a round in a place they are
  not. The test that catches it reads the other county's feed and expects nothing.
* **The reach filter inverted** (#4) — `>=` for `<=`, so a county is told about rounds that have
  not begun and told nothing about the one running now.
* **The net reminder anchored at an arbitrary hour** (#5) — the manual puts biting between dusk and
  dawn; a reminder at noon is a reminder to do the thing at the wrong time of day.
* **A reminder that fires in the past** (#6) — the `<= at` roll-forward removed, so a household
  asked after dusk is told to go to bed at the moment they are already up.
* **The container interval hand-typed** (#7) — a second definition of "the shortest re-treatment
  interval", which parts company with the table the moment a class is added.
* **The rain band's threshold shifted** (#8) — `wet` starting at 40 mm instead of 50, which is the
  difference between "keep using your net" and "drain the containers now".
* **The band-specific message collapsed to one string** (#9) — one string has to be the wet one and
  is then wrong for half the year.
* **The bad instant accepted** (#10) — a caller's typo becomes a reminder scheduled at the epoch.
* **The route dropping the county scope** (#11) — an anonymous caller issuing a public statement
  about a place, which is the defect the section's own audit reasoning names.

Every patch is asserted unique before it is applied and reverted from a `cp` backup, never with
`git checkout --` (the mutation and the real change live in the same uncommitted tree). A canary
that passes is a bug in the canary, so a MISSED line is a failure of this script. The `__pycache__`
purge after each write is load-bearing for the reason `canary_inf001.py` documents: two canaries
mutating two files with same-length edits in the same second make CPython reuse the previous
canary's bytecode, and the gate then reports a mutation it never made.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path('/Users/nyimbiodero/src/pjs/afya')
V = ROOT / 'src/afya/monitoring/views.py'
S = ROOT / 'src/afya/monitoring/service.py'
G = ROOT / 'src/afya/service.py'
A = ROOT / 'src/afya/alerting/views.py'

CANARIES = [
	# 1. The supplement rule is not appended, so the published notice announces a round and says
	#    nothing about nets. The manual's own condition, and the sentence a county notice drops.
	('the supplement rule is dropped from the body', S,
	 "		body = f'{notice.body} {SUPPLEMENT_RULE}'",
	 "		body = notice.body",
	 'test_every_published_body_carries_the_supplement_rule'),

	# 2. The round is published under a category that exists and has a preference behind it — just
	#    not the one that matches. Nothing errors; the notice simply reaches nobody.
	('the round is filed under the wrong feed category', S,
	 "					item_id=f'{notice.campaign_id}-{county}', category='vector_control', county=county,",
	 "					item_id=f'{notice.campaign_id}-{county}', category='service', county=county,",
	 'test_a_round_reaches_the_feed_under_the_vector_category'),

	# 3. Every item is addressed to the first county, so a two-county round publishes two items for
	#    the same place and none for the other.
	('every item is addressed to the first county', S,
	 "					item_id=f'{notice.campaign_id}-{county}', category='vector_control', county=county,\n					headline=notice.headline, body=body, source=notice.issued_by,",
	 "					item_id=f'{notice.campaign_id}-{county}', category='vector_control', county=notice.counties[0],\n					headline=notice.headline, body=body, source=notice.issued_by,",
	 'test_one_item_per_county_and_no_item_for_a_county_not_named'),

	# 4. The reach filter inverted: a round that has not begun is served and the running one is not.
	('the reach filter is inverted', S,
	 "		return sorted((n for n in self._larviciding if county in n.counties and n.first_round_iso <= on_iso),",
	 "		return sorted((n for n in self._larviciding if county in n.counties and n.first_round_iso >= on_iso),",
	 'test_a_round_is_not_hidden_by_a_day_it_has_not_reached'),

	# 5. The net reminder is anchored at noon. Biting is a dusk-to-dawn affair; a reminder to sleep
	#    under a net is worth nothing at midday.
	('the net reminder is anchored at an arbitrary hour', V,
	 "DUSK_HOUR = 18",
	 "DUSK_HOUR = 12",
	 'test_the_net_reminder_is_placed_at_dusk'),

	# 6. The roll-forward removed, so a reminder asked for after dusk is scheduled in the past —
	#    which on a device fires immediately, telling a person to go to bed while they are up.
	('a reminder asked for after dusk fires in the past', S,
	 "		if net_due <= at:\n			net_due += timedelta(days=1)",
	 "		if False:\n			net_due += timedelta(days=1)",
	 'test_a_reminder_asked_for_after_dusk_rolls_to_tomorrow'),

	# 7. The container interval hand-typed instead of derived, so it is a second definition of the
	#    same quantity and parts company with the table the moment a class is added.
	('the container interval is hand-typed', V,
	 "LARVICIDE_INTERVAL_FLOOR_DAYS: int = min(\n\tinterval for _label, interval in LARVICIDE_CLASSES.values() if interval is not None\n)",
	 "LARVICIDE_INTERVAL_FLOOR_DAYS: int = 14",
	 'test_the_container_reminder_uses_the_shortest_interval_any_class_carries'),

	# 8. The wet threshold moved, so a 40 mm week reads as wet. The band decides which advice is
	#    served, and a band boundary that drifts is a wrong instruction rather than a wrong number.
	('the rain band threshold is shifted', S,
	 "		if rainfall_mm_72h >= 50:\n			return 'wet'",
	 "		if rainfall_mm_72h >= 40:\n			return 'wet'",
	 'test_the_four_rain_bands_are_one_definition'),

	# 9. One message for every band. It has to be the wet one, and is then wrong for the dry half of
	#    the year — which is the whole reason the message varies.
	('the message is collapsed to one string', S,
	 "		if band in ('wet', 'flood'):\n			message = ('Rain has raised the mosquito risk here. Drain or cover every container holding '\n			           'water, and sleep under your net tonight.')\n		else:\n			message = ('Low mosquito activity right now — the time to clear standing water and check '\n			           'your net for holes, before the next rains.')",
	 "		message = ('Drain or cover every container holding water, and sleep under your net tonight.')",
	 'test_the_message_changes_with_the_rain_band'),

	# 10. The parse guard removed, so a caller's typo becomes an unhandled ValueError at the route —
	#     a 500 where the section's contract is a refusal a person can read.
	('the bad instant is not refused', S,
	 "		except ValueError:\n			raise AssertionError(f'{at_iso!r} is not an instant a reminder can be scheduled for') from None",
	 "		except ValueError:\n			at = datetime.now(timezone.utc)",
	 'test_an_instant_that_is_not_a_time_is_refused'),

	# 11. The county scope dropped from the publish route, so an anonymous caller can issue a public
	#     statement about a place. This is the shape the audit reasoning names for the alert beside
	#     it, and it is invisible to every test over the service.
	('the publish route drops the county scope', G,
	 "	async def monitoring_larviciding(notice: LarvicidingNotice, _subject: str = Depends(require_scope('county_aggregate'))) -> dict[str, object]:",
	 "	async def monitoring_larviciding(notice: LarvicidingNotice, _subject: str | None = None) -> dict[str, object]:",
	 'test_the_round_is_issued_over_the_wire_and_read_back_by_the_county'),
]

failures = []
for name, path, old, new, node in CANARIES:
	backup = pathlib.Path(f'/tmp/canary_mon007.{path.name}.bak')
	shutil.copy2(path, backup)
	s = path.read_text()
	count = s.count(old)
	assert count == 1, f'{name}: target not unique/found ({count})'
	path.write_text(s.replace(old, new))
	# See the module docstring: a same-second write of the same size reuses the previous canary's
	# bytecode, and the canary then tests code it never mutated. Purged for the file just written.
	for cache in path.parent.rglob('__pycache__'):
		shutil.rmtree(cache, ignore_errors=True)
	try:
		proc = subprocess.run(['uv', 'run', 'pytest', '-q', '-p', 'no:randomly',
			f'tests/ci/test_mon007.py::{node}'], cwd=ROOT, capture_output=True, text=True)
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
