"""§18's Frequency column, declared once and tied to both the section and a route.

Each of §18.1–§18.8 gives every integration point a Frequency — "Real-time on sync", "On change",
"Hourly", "On report" — and until now those cells lived nowhere but prose. §18.3's six were the
exception and the proof that the exception is not enough: `FEED_CADENCE` carried `hourly`/`daily`
as slugs and the only test over it asserted the *key set*, so a feed could move from hourly to
weekly against a section reading "Hourly" and nothing failed. The other seven subsections had no
carrier at all — the cadence appeared in a client docstring ("App → ADaM, daily, consented only")
where no test reads and no operator can query it.

Two crossings make this a register rather than a list:

* **spec ↔ register** — `test_every_spec_18_frequency_is_the_sections_own` parses the eight tables
  out of `docs/spec.md` and asserts this dict equals them in both directions, so a reworded cell
  fails here rather than passing against a constant edited to match.
* **register ↔ route** — `CARRIER` names, per row, the served route that implements the wire. A row
  whose frequency is declared but which no route carries is a claim with no implementation, which is
  the defect §18 was fixed from in the first place ("the clients existed and no path reached them").

The Frequency values are the section's own words, kept verbatim. They are *not* normalised into a
slug vocabulary: `realtime` and `on_change` would be a second spelling of what the section already
states, and the §18.3 case is exactly how a normalised copy drifts from the cell it copies. §18.3's
`FEED_CADENCE` keeps its slugs because the PHEOC wire is a machine contract, and the gate asserts
the two agree rather than deriving one from the other.
"""
from afya.integrations.feeds import FEED_CADENCE

# (subsection, integration point as the section's first column spells it) -> Frequency cell, verbatim.
SPEC_18_FREQUENCY: dict[tuple[str, str], str] = {
	# §18.1 ADaM Platform
	('18.1', 'Case reports from CHW module'): 'Real-time on sync',
	('18.1', 'Contact monitoring summaries'): 'Daily',
	('18.1', 'Case status updates'): 'On change',
	('18.1', 'Contact assignments'): 'On assignment',
	('18.1', 'Case definitions'): 'On change',
	# §18.2 JALI Chatbot
	('18.2', 'User launch'): 'On demand',
	('18.2', 'Misinformation corrections'): 'On publish',
	('18.2', 'Symptom assessment sharing'): 'On request',
	('18.2', 'Health worker review'): 'On review',
	# §18.3 PHEOC Dashboards
	('18.3', 'Aggregated symptom reports'): 'Hourly',
	('18.3', 'Case reports'): 'Real-time',
	('18.3', 'Geofence entry/exit events'): 'Hourly',
	('18.3', 'Misinformation flags'): 'Hourly',
	('18.3', 'Early warning signals'): 'Daily',
	('18.3', 'Resource deployment recommendations'): 'Daily',
	# §18.4 719 Hotline
	('18.4', 'One-tap call'): 'On demand',
	('18.4', 'Auto-call on fall detection'): 'On event',
	('18.4', 'Callback request'): 'On request',
	('18.4', 'SMS follow-up'): 'On case action',
	('18.4', 'Call outcome'): 'On close',
	# §18.5 Kenya Master Health Facility List
	('18.5', 'Facility data'): 'Weekly',
	('18.5', 'Facility status updates'): 'On report',
	('18.5', 'Facility verification'): 'Weekly',
	# §18.6 SHA / NHIF
	('18.6', 'Cover verification'): 'On request',
	('18.6', 'Facility acceptance list'): 'Weekly',
	('18.6', 'Benefit information'): 'On change',
	# §18.7 Pharmacy and Poisons Board
	('18.7', 'Medicine registry'): 'Daily',
	('18.7', 'Recalls'): 'On issue',
	('18.7', 'Suspicious medicine reports'): 'On report',
	# §18.8 Telco Gateways
	('18.8', 'SMS outbound'): 'On trigger',
	('18.8', 'SMS inbound'): 'Real-time',
	('18.8', 'USSD sessions'): 'Real-time',
	('18.8', 'Zero-rating configuration'): 'On change',
	('18.8', 'Airtime incentives'): 'Weekly',
}

# The route that implements each row. `('GET', '/path')` for a pull, `('POST', '/path')` for a push.
# Two §18.4 rows are carried by routes outside the `/integrations` block because the section's wire
# *is* that route: a one-tap call is the SOS path, and an auto-call on a fall is the fall verdict's
# own `auto_alert`. Naming them here rather than leaving the rows carrierless is what stops the
# register describing a wire nobody built.
CARRIER: dict[tuple[str, str], tuple[str, str]] = {
	('18.1', 'Case reports from CHW module'): ('POST', '/integrations/adam/cases'),
	('18.1', 'Contact monitoring summaries'): ('POST', '/integrations/adam/monitoring'),
	('18.1', 'Case status updates'): ('GET', '/integrations/adam/cases/{report_id}'),
	('18.1', 'Contact assignments'): ('GET', '/integrations/adam/contacts'),
	('18.1', 'Case definitions'): ('GET', '/integrations/adam/case-definitions'),
	('18.2', 'User launch'): ('POST', '/integrations/jali/link'),
	('18.2', 'Misinformation corrections'): ('GET', '/integrations/jali/corrections'),
	('18.2', 'Symptom assessment sharing'): ('POST', '/integrations/jali/assessments'),
	('18.2', 'Health worker review'): ('GET', '/integrations/jali/assessments/{assessment_id}/review'),
	('18.3', 'Aggregated symptom reports'): ('POST', '/integrations/pheoc/feeds/{feed}'),
	('18.3', 'Case reports'): ('POST', '/integrations/pheoc/feeds/{feed}'),
	('18.3', 'Geofence entry/exit events'): ('POST', '/integrations/pheoc/feeds/{feed}'),
	('18.3', 'Misinformation flags'): ('POST', '/integrations/pheoc/feeds/{feed}'),
	('18.3', 'Early warning signals'): ('POST', '/integrations/pheoc/feeds/{feed}'),
	('18.3', 'Resource deployment recommendations'): ('POST', '/integrations/pheoc/feeds/{feed}'),
	('18.4', 'One-tap call'): ('POST', '/emergency/sos'),
	('18.4', 'Auto-call on fall detection'): ('POST', '/emergency/fall'),
	('18.4', 'Callback request'): ('POST', '/integrations/telco/sms/inbound'),
	('18.4', 'SMS follow-up'): ('POST', '/integrations/hotline/follow-up'),
	('18.4', 'Call outcome'): ('POST', '/integrations/hotline/outcome'),
	('18.5', 'Facility data'): ('POST', '/facilities/import-mohf'),
	('18.5', 'Facility status updates'): ('POST', '/facilities/{facility_id}/correction'),
	('18.5', 'Facility verification'): ('GET', '/facilities/verification'),
	('18.6', 'Cover verification'): ('POST', '/insurance/sha/verify'),
	('18.6', 'Facility acceptance list'): ('GET', '/insurance/sha/facilities'),
	('18.6', 'Benefit information'): ('GET', '/insurance/sha/benefits'),
	('18.7', 'Medicine registry'): ('GET', '/medicine/registry'),
	('18.7', 'Recalls'): ('GET', '/medicine/recalls'),
	('18.7', 'Suspicious medicine reports'): ('POST', '/medicine/suspicious'),
	('18.8', 'SMS outbound'): ('POST', '/channels/sms'),
	('18.8', 'SMS inbound'): ('POST', '/integrations/telco/sms/inbound'),
	('18.8', 'USSD sessions'): ('POST', '/channels/ussd/callback'),
	('18.8', 'Zero-rating configuration'): ('GET', '/integrations/telco/zero-rating'),
	('18.8', 'Airtime incentives'): ('POST', '/integrations/telco/airtime'),
}

# Which §18.3 feed each PHEOC row is. The section's label is prose and the wire's key is a slug, so
# the two cannot be joined by a rule ("Aggregated symptom reports" is not `symptom_reports`); the
# mapping is declared and the gate asserts it against `FEED_CADENCE` in both directions, which is
# what keeps this from being a third hand-kept list that drifts.
PHEOC_FEED: dict[str, str] = {
	'Aggregated symptom reports': 'symptom_reports',
	'Case reports': 'case_reports',
	'Geofence entry/exit events': 'geofence_events',
	'Misinformation flags': 'misinformation_flags',
	'Early warning signals': 'early_warning',
	'Resource deployment recommendations': 'resource_deployment',
}


def frequencies_for(system: str) -> list[dict[str, str]]:
	"""One §18 subsection's rows, in section order, for the wiring report."""
	rows = [(point, freq) for (section, point), freq in SPEC_18_FREQUENCY.items() if section == system]
	assert rows, f'§{system} declares no integration point'
	return [
		{'point': point, 'frequency': freq,
		 'carrier': f'{CARRIER[(system, point)][0]} {CARRIER[(system, point)][1]}'}
		for point, freq in rows
	]


# Every row carries a cadence and a route, and the two maps describe the same rows. A row with a
# frequency and no carrier is a declared wire nobody built — the defect this register was added to
# make visible — and a carrier with no frequency is a route with no stated obligation.
assert set(SPEC_18_FREQUENCY) == set(CARRIER), 'every §18 row needs both a frequency and a carrier'
assert set(PHEOC_FEED) == {p for (s, p) in SPEC_18_FREQUENCY if s == '18.3'}, 'every §18.3 row is a feed'
assert set(PHEOC_FEED.values()) == set(FEED_CADENCE), 'the feed keys are the six §18.3 feeds'


def _slug(cell: str) -> str:
	"""A Frequency cell as a wire key: lower-cased, punctuation dropped.

	The rule rather than a `.lower()`, because §18.3's own cell is "Real-time" and the key the PHEOC
	client posts is `realtime` — the hyphen is gone. Comparing the two with `.lower()` alone fails
	on that one row and passes on the other five, which is how a normalisation becomes a hand-kept
	exception list. Dropping every non-alphanumeric makes the join total.
	"""
	import re
	return re.sub(r'[^a-z0-9]', '', cell.lower())


for _label, _feed in PHEOC_FEED.items():
	_cell = SPEC_18_FREQUENCY[('18.3', _label)]
	assert _slug(_cell) == FEED_CADENCE[_feed], (
		f'§18.3 `{_label}` states {_cell!r} and FEED_CADENCE says {FEED_CADENCE[_feed]!r} — the '
		f'machine contract has drifted from the section')
