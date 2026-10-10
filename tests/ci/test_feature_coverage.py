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
from afya.mobile.actions import FEATURE_OF
from afya.registry.service import FeatureRegistry

# Features that are available but deliberately have no catalogue action, each with the reason.
# These are capabilities the device performs or the deployment holds, not screens a person opens;
# naming them here is what makes the gap a decision rather than an oversight.
ON_DEVICE: dict[str, str] = {
	# The three cross-cutting architecture properties. There is no call to make: the app either is
	# offline-first, processes on-device and can be used pseudonymously, or it is not.
	'ACC-003': 'offline-first is a property of every screen, not an action',
	'SEC-002': 'on-device processing means the raw data never reaches a route',
	'SEC-004': 'pseudonymous use is the absence of an account, not an action',
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
	'SENS-010': 'NFC tags are read by the device; the check-in they open has its own action',
	'EMG-002': 'fall auto-alert is the device arming the SOS it already has an action for',
	# Broadcast channels. The radio and social programmes are run by the communications team and
	# the audience receives them on a radio or a social feed, never through this app.
	'CHAN-000': 'radio is a broadcast programme, not a client action',
	'CHAN-004': 'social media publishing is run outside the app',
	# Feature ids whose capability is served under a sibling id the catalogue already covers.
	# Each is a spec duplicate rather than a missing route; the alias table in the registry records
	# the divergence, and these are the pairs where two ids name one thing.
	'MON-005': 'same water-quality service as INF-011, which the catalogue reaches',
	'MON-006': 'same air-quality service as INF-012, which the catalogue reaches',
	'MON-002': 'same antenatal tracker as REC-008, which the catalogue reaches',
	'REC-002': 'the full wallet is the wallet at REC-001 plus cloud sync, served by the same routes',
	# The health library is one corpus serving several spec features; each item carries its own
	# slug and harmony tag, and `health_library` reaches all of it.
	'INF-004': 'myth-busting items are in the health library corpus',
	'INF-008': 'health-tip items are in the health library corpus',
	'INF-009': 'first-aid items are in the health library corpus',
	'INF-010': 'burial-guidance items are in the health library corpus',
	'INF-015': 'herbal-safety items are in the health library corpus',
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
