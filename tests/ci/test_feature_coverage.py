"""Gate: every available feature is either reachable from the catalogue or deliberately not.

The failure this exists to prevent is the one that hid 24 features: a feature registered, marked
available, and offered by no action — so a client could never reach it and nothing failed. The
catalogue's own test asserted only that each *action* maps to a route; nothing asked the reverse
question, which is the one that finds a capability nobody can use.

The reverse question has two honest answers, and this gate requires the code to give one of them
rather than leaving it to a reader's head:

1. The feature has an action in the catalogue (`FEATURE_OF` names it), so a client can reach it.
2. The feature is named in `ON_DEVICE` below, with the reason it has no server route — an on-device
   capability, a transport rather than a screen, or a property of the app rather than a call. Each
   entry is a decision someone made and can be argued with, not an omission.

A feature that is neither fails here. The list is deliberately small: if it grows, the question is
whether the new entry is a real on-device capability or a route somebody did not write.
"""
import pytest

from afya.mobile.actions import FEATURE_OF
from afya.registry.service import FeatureRegistry

# Features that are available but deliberately have no catalogue action, each with the reason.
# These are capabilities the device performs or the deployment holds, not screens a person opens;
# naming them here is what makes the gap a decision rather than an oversight.
ON_DEVICE: dict[str, str] = {
	# §SEC-002's on-device processing has no call to make: the raw data never reaches a route. That
	# is still the section's shape for the LiDAR, audio, PPG and location bullets, and it is no
	# longer the whole of it: "Photos encrypted and only shared with explicit per-item consent" is
	# a *server-side* obligation, because the photo does leave the device — the encryption and the
	# consent both happen on the way in. It is enforced on `POST /evidence`, which is SENS-004's
	# action, so the section still has no action of its own; the reason now names what it does have.
	'SEC-002': 'the raw signals never reach a route; the photo bullet is enforced on the evidence route',
	# §SEC-004 was here as "pseudonymous use is the absence of an account, not an action". That was
	# true of the *anonymity* half and false of the pseudonymity half: the section's third feature is
	# an optional profile, which is a thing a person sets, and the public report feed was publishing
	# raw subject references with nothing to put in their place. It has two actions now. (ACC-003's
	# offline-first property has one call after all — `offline_state` serves the sync indicator
	# §16.1 principle 4 requires — so it is no longer listed here.)
	# On-device sensing and device integration: the raw signal is consumed locally and only a
	# derived metric is posted through `sensor_ingest`, so there is no route for the sensor itself.
	'SENS-003': 'fall detection runs on the accelerometer; only the derived verdict is ingested',
	'SENS-006': 'wearable pairing is a platform API, not a server call',
	'SENS-007': 'sleep and activity are derived on-device and ingested as a metric',
	# Pairing itself is a platform API with no route — but §14.9's *claim* about what pairing buys
	# is modelled: `SOURCES` marks a reading clinical grade only when a device measured it, and
	# BPReading/GlucoseReading/MonitoringDay carry that provenance. `sensors/external_device_gap`
	# reports whether any of them stopped doing so.
	'SENS-009': 'pairing is a platform API; the provenance it confers is `SOURCES`, checked by external_device_gap',
	# SENS-010 was here as "NFC tags are read by the device; the check-in they open has its own
	# action". The reading is still the device's, but what a tap *means* is now a server fact — a tag
	# bound to a typed target in `afya.sensors.tags`, with a register behind the equipment target —
	# and each of §SENS-010's four applications has its own action, so the entry came off.
	'EMG-002': 'fall auto-alert is the device arming the SOS it already has an action for',
	# §CHAN-000 and §CHAN-004 were here as "radio is a broadcast programme, not a client action"
	# and "social media publishing is run outside the app". The *broadcast* still is — a person
	# listens on a radio and reads a feed outside this app — but the sections' content programme is
	# now a server capability with routes behind it: a live session with a schedule, a queue and a
	# published transcript, and a submission path with a consent check and a moderation queue. The
	# audience half is a client fact and the programme half is not, and only the second is what this
	# list is for, so the two entries came off.
	# Feature ids whose capability is served under a sibling id the catalogue already covers.
	# Each is a spec duplicate rather than a missing route; the alias table in the registry records
	# the divergence, and these are the pairs where two ids name one thing.
	'MON-005': 'same water-quality service as INF-011, which the catalogue reaches',
	'MON-006': 'same air-quality service as INF-012, which the catalogue reaches',
	# MON-002 was here as "the same antenatal tracker as REC-008", which was true while the two ids
	# named one module: the schedule and a danger-sign classifier. §MON-002 prints ten features and
	# REC-008's name is the tracker, so the nine the section adds — the due-date calculator, the
	# visit and postnatal reminders, the birth plan, trimester guidance, the newborn signs, the
	# maternity finder, the PMTCT referral — have their own actions now and the entry came off.
	# REC-002 was here as "the full wallet is the wallet at REC-001 plus cloud sync, served by the
	# same routes", and it came off when the routes stopped being shared-only. §10.1 adds seven
	# features over REC-001 and each now has an action: the timeline, the growth chart, the
	# vaccination certificate, the export, the time-limited share, the provider-side view and the
	# backup. The wallet document set is still one store — that was the design insight, not an
	# excuse — but the operations over it are the section's own and a client can reach each.
	# The health library is one corpus serving several spec features; each item carries its own
	# slug and harmony tag, and `health_library` reaches all of it.
	# INF-004 was here as "myth-busting items are in the health library corpus", which was true
	# while the corpus held the corrections as prose and nothing could be done with them. §INF-004
	# prints four Features over that corpus — search, browse by category, ask about a rumour, share
	# the card — and each has its own action now, so the entry came off.
	# These three name a harmony tag the seed corpus actually carries, and
	# `test_the_corpus_reasons_name_a_tag_the_corpus_has` holds each to it — `tips` (20 items),
	# `first-aid` (33) and `burial` (10). The tag is the reason, so the reason is checkable.
	'INF-008': 'health-tip items are in the health library corpus (harmony tag `tips`)',
	'INF-009': 'first-aid items are in the health library corpus (harmony tag `first-aid`)',
	'INF-010': 'burial-guidance items are in the health library corpus (harmony tag `burial`)',
	# INF-015 was here as "herbal-safety items are in the health library corpus", and that reason
	# named something the corpus does not have: there is no herbal tag and no herbal item. The
	# capability is real and it is carried one module over — `afya.info.myths` holds §6.4's
	# `cure_claim` correction, whose fact reads "No herbal or religious remedy cures Ebola", drafted
	# in en and sw with a named authority. A registry-only id whose stated carrier does not exist is
	# the citation defect this repo keeps meeting, so the entry names the carrier it has.
	'INF-015': 'traditional and herbal safety is the `cure_claim` correction in afya.info.myths',
}


def _covered_feature_ids() -> set[str]:
	return set(FEATURE_OF.values())


def test_every_available_feature_is_reachable_or_named_as_on_device() -> None:
	"""The gate. A newly registered feature with no action and no reason fails here."""
	reg = FeatureRegistry()
	covered = _covered_feature_ids()
	unaccounted = sorted(
		f.id for f in reg.available()
		if f.id not in covered and f.id not in ON_DEVICE
	)
	assert unaccounted == [], (
		f'available features no client can reach and no one has accounted for: {unaccounted}. '
		'Add a catalogue action, or name the feature in ON_DEVICE with the reason it has none.'
	)


def test_the_on_device_list_does_not_drift() -> None:
	"""An entry naming a feature that is covered, dormant, or gone is stale and must be removed —
	otherwise the list accumulates reasons for gaps that no longer exist and stops meaning anything."""
	reg = FeatureRegistry()
	available = {f.id for f in reg.available()}
	covered = _covered_feature_ids()
	stale = sorted(fid for fid in ON_DEVICE if fid in covered or fid not in available)
	assert stale == [], f'ON_DEVICE names features that are covered, dormant or unknown: {stale}'
	for fid, reason in ON_DEVICE.items():
		assert len(reason) > 20, f'{fid} has no real reason, only {reason!r}'


def test_the_corpus_reasons_name_a_tag_the_corpus_has() -> None:
	"""A reason that cites a carrier is a citation, and a citation can point at nothing.

	Four entries said their feature's content "is in the health library corpus". Three of those are
	true and one was not: there is no herbal harmony tag and no herbal item, so INF-015's reason sent
	a reader to look for something that does not exist — which is how the §17.6 dangling
	`kenya-dpa-2019/` citation and the duplicated `gate.py` both went wrong. The capability was real
	and lived in `afya.info.myths`; only the pointer was wrong.

	The check is deliberately narrow: it reads the backticked tag out of a reason that says
	"harmony tag" and asserts the seed corpus carries it. A gate scoped wider than its jurisdiction
	fails for reasons its operator cannot act on, and the pressure that creates is to delete the
	gate. This one can only fail when a reason names a tag, and then only when the tag is absent.
	"""
	import re
	from afya.info.content_seed import rendition_rows, seed_rows
	tags = {r.harmony_tag for r in seed_rows() + rendition_rows()}
	named = {fid: m.group(1) for fid, reason in ON_DEVICE.items()
	         if (m := re.search(r'harmony tag `([a-z-]+)`', reason))}
	assert named, 'the corpus reasons stopped naming their tag, so this gate checks nothing'
	for fid, tag in named.items():
		assert tag in tags, f'{fid} cites harmony tag {tag!r}, which the corpus does not carry'
	# And the reason must name a tag with items under it, not merely a tag that exists — a tag
	# present and empty would satisfy the check above while pointing at the same nothing.
	for fid, tag in named.items():
		held = [r for r in seed_rows() + rendition_rows() if r.harmony_tag == tag]
		assert held, f'{fid} cites harmony tag {tag!r}, which has no items'


def test_the_corpus_reason_gate_catches_a_tag_the_corpus_lacks() -> None:
	"""Canary. Driven against a synthetic reason, so it proves the comparison rather than restating
	the current data — the mutation is a tag that is genuinely absent, not one spelled differently."""
	import re
	from afya.info.content_seed import rendition_rows, seed_rows
	tags = {r.harmony_tag for r in seed_rows() + rendition_rows()}
	synthetic = {'INF-999': 'x items are in the health library corpus (harmony tag `herbal-safety`)'}
	named = {fid: m.group(1) for fid, reason in synthetic.items()
	         if (m := re.search(r'harmony tag `([a-z-]+)`', reason))}
	assert named == {'INF-999': 'herbal-safety'}, 'the extraction must find the tag it is given'
	assert 'herbal-safety' not in tags, 'the canary tag must be one the corpus genuinely lacks'
	with pytest.raises(AssertionError, match='which the corpus does not carry'):
		for fid, tag in named.items():
			assert tag in tags, f'{fid} cites harmony tag {tag!r}, which the corpus does not carry'


def test_the_gate_catches_an_unaccounted_feature() -> None:
	"""Canary. The gate must fail on a feature that is available, uncovered and unnamed — the exact
	shape of the 24 that hid. Driven against a synthetic set rather than the registry, so it proves
	the comparison rather than restating the current data."""
	available = {'NEW-001', 'REC-001'}
	covered = {'REC-001'}
	on_device: dict[str, str] = {}
	unaccounted = sorted(f for f in available if f not in covered and f not in on_device)
	assert unaccounted == ['NEW-001'], 'the gate must flag a feature with no action and no reason'
	# And once accounted for, it passes.
	on_device['NEW-001'] = 'a reason long enough to be a real one'
	assert sorted(f for f in available if f not in covered and f not in on_device) == []


def test_the_catalogue_covers_the_bulk_of_available_features() -> None:
	"""Pin the split, so a change that drops actions and papers over it by growing ON_DEVICE fails.

	59 of the 79 available features are reached by an action; the other 20 are named in ON_DEVICE.
	The two together account for every available feature, which the gate above asserts; this pins
	the ratio so the balance cannot shift silently in either direction.
	"""
	reg = FeatureRegistry()
	available = {f.id for f in reg.available()}
	covered = _covered_feature_ids() & available
	assert len(covered) >= 59, f'the catalogue reaches only {len(covered)} of {len(available)} available features'
	assert len(ON_DEVICE) <= 25, 'the on-device list has grown past a handful of real on-device capabilities'
