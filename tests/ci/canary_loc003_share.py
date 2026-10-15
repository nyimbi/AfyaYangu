"""Canaries for §LOC-003's share.

Each mutation is *disjoint* from what its predicate looks for — a canary that is a superstring of
the asserted text is a canary that did not run. Every one of these changes the implementation in a
way the observation must notice, and each is paired with the one node that should go red.

Run: `uv run python tests/ci/canary_loc003_share.py`. Any MISSED exits non-zero.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICE = REPO / 'src/afya/location/service.py'
ROUTES = REPO / 'src/afya/service.py'

# (name, path, old, new, node)
CANARIES: list[tuple[str, Path, str, str, str]] = [
	(
		'the consent gate stops refusing a history that was never consented to',
		SERVICE,
		"		assert history.consent_granted, (\n"
		"			'the location diary needs the person\\'s explicit consent before it can be read (§LOC-003)')\n",
		'',
		'tests/ci/test_loc003_share.py::test_a_history_without_the_tracking_consent_cannot_be_shared',
	),
	(
		'the tracking consent is read as the sharing permission, so a refused Ministry still gets the diary',
		SERVICE,
		"		assert self._share_consent is not None and self._share_consent(\n"
		"			subject_ref, SHARE_AUTHORITY_CATEGORY), (\n"
		"			'sharing with a health authority needs §SEC-001\\'s \"share with health authorities\" '\n"
		"			'permission, which is a different decision from keeping a location diary; refusing rather '\n"
		"			'than treating the tracking consent as the sharing one')\n",
		'',
		'tests/ci/test_loc003_share.py::test_a_diary_without_the_sharing_permission_cannot_be_shared',
	),
	(
		'a missing consent ledger fails open instead of closed',
		SERVICE,
		'		assert self._share_consent is not None and self._share_consent(',
		'		assert self._share_consent is None or self._share_consent(',
		'tests/ci/test_loc003_share.py::test_a_deployment_with_no_consent_ledger_refuses_to_share',
	),
	(
		'the missing-key gate stops checking for a key',
		SERVICE,
		'		assert self._sealer is not None and self._sealer.available, (',
		'		assert self._sealer is not None, (',
		'tests/ci/test_loc003_share.py::test_a_deployment_with_no_application_layer_key_refuses_to_share',
	),
	(
		'the seal is replaced by a passthrough, so the wire carries plaintext',
		SERVICE,
		'sealed=self._sealer(payload),',
		'sealed=payload.decode("utf-8"),',
		'tests/ci/test_loc003_share.py::test_the_report_travels_as_ciphertext_and_the_at_rest_key_does_not_open_it',
	),
	(
		'the geohash is not generalised before it leaves the device',
		SERVICE,
		'		cells = sorted({_geohash_cell(p.geohash) for p in history.points})',
		'		cells = sorted({p.geohash for p in history.points})',
		'tests/ci/test_loc003_share.py::test_what_travels_is_a_coarse_cell_and_never_the_coordinate',
	),
	(
		'delivered is read off the request rather than off the transport',
		SERVICE,
		"			except Exception as exc:  # noqa: BLE001 — any transport failure means the same thing here\n"
		"				self._log_warn('location report could not be delivered', subject=subject_ref,\n"
		"					error=str(exc)[:120])\n",
		"			except Exception as exc:  # noqa: BLE001 — any transport failure means the same thing here\n"
		"				self._log_warn('location report could not be delivered', subject=subject_ref,\n"
		"					error=str(exc)[:120])\n"
		"				delivered = True\n",
		'tests/ci/test_loc003_share.py::test_a_share_that_could_not_be_delivered_is_kept_and_says_so',
	),
	(
		'the envelope is not kept when the transport fails, so the sealed report is lost',
		SERVICE,
		"			self._shares[f'{subject_ref}:{recipient}'] = envelope\n",
		'',
		'tests/ci/test_loc003_share.py::test_a_share_that_could_not_be_delivered_is_kept_and_says_so',
	),
	(
		'the report claims a share again, which is the defect this unit closes',
		SERVICE,
		"			message='Report generated on your phone. Nothing has been sent.',",
		"			message='Report generated and shared as coarse locations only.',",
		'tests/ci/test_loc003_share.py::test_the_report_on_the_persons_screen_never_claims_a_share',
	),
	(
		'the ledger is written for a share that was never delivered',
		ROUTES,
		'		if receipt.delivered:\n			retention.record_share(',
		'		if True:\n			retention.record_share(',
		'tests/ci/test_loc003_share.py::test_the_route_shares_for_a_signed_in_person_and_reaches_the_dashboard',
	),
]


def main() -> int:
	missed: list[str] = []
	for name, path, old, new, node in CANARIES:
		source = path.read_text()
		count = source.count(old)
		if count != 1:
			print(f'MISSED (patch target occurs {count}x, not once): {name}')
			missed.append(name)
			continue
		backup = Path('/tmp') / f'{path.name}.canary.bak'
		shutil.copy2(path, backup)
		try:
			path.write_text(source.replace(old, new))
			# A same-second, same-size write can serve the *previous* canary's bytecode, so the
			# revert is only evidence once the cache is gone.
			subprocess.run(
				['find', str(REPO / 'src'), '-name', '__pycache__', '-type', 'd',
				 '-exec', 'rm', '-rf', '{}', '+'], check=False)
			run = subprocess.run(
				['uv', 'run', 'pytest', '-q', '-p', 'no:randomly', node],
				cwd=REPO, capture_output=True, text=True)
			fired = run.returncode != 0
			print(('fired  ' if fired else 'MISSED ') + name)
			if not fired:
				missed.append(name)
		finally:
			shutil.copy2(backup, path)
			backup.unlink()
			if path.read_text() != source:
				print(f'REVERT FAILED: {path}')
				return 2
	if missed:
		print(f'\n{len(missed)} canary/canaries did not fire: {missed}')
		return 1
	print(f'\nall {len(CANARIES)} canaries fired')
	return 0


if __name__ == '__main__':
	sys.exit(main())
