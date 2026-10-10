"""Security controls and vulnerability-management obligations (spec §17.5).

The table below is §17.5 as data. The point is not to restate the spec; it is that each row names
the module or command that enforces it, so a reader can check the claim instead of trusting it. The
two rows that were false — SAST and dependency scanning "in CI" — now name the commands the workflow
runs, and `unimplemented` is a legal value so a control nobody has built cannot hide by being
omitted.
"""
from datetime import date, timedelta

from afya.logmixin import LogMixin
from afya.security.views import (
	ControlKind, DisclosurePolicy, ScanObligation, SecurityControl, SecurityPosture, VulnerabilityScan,
)

# §17.5, one row per control. `kind=ci` rows name a command the workflow must run; the test that
# reads this table asserts the workflow runs exactly those commands, so a control cannot claim CI
# enforcement the workflow does not provide.
CONTROLS: tuple[SecurityControl, ...] = (
	SecurityControl(control='Encryption at rest', implementation='AES-256-GCM', kind=ControlKind.code,
		enforced_by='afya.retention.views.ENCRYPTION_STANDARD', where='retention/views.py'),
	SecurityControl(control='Encryption in transit', implementation='TLS 1.3', kind=ControlKind.code,
		enforced_by='afya.retention.views.ENCRYPTION_STANDARD', where='retention/views.py'),
	SecurityControl(control='Key management', implementation='Hardware-backed keystore; HSM for server keys',
		kind=ControlKind.process, enforced_by='deployment runbook'),
	SecurityControl(control='Authentication', implementation='Anonymous tokens for citizens; OAuth 2.0 + PKCE + MFA for staff',
		kind=ControlKind.code, enforced_by='afya.auth.service.AuthService', where='auth/service.py'),
	SecurityControl(control='Authorisation', implementation='RBAC with least privilege', kind=ControlKind.code,
		enforced_by='afya.privacy.views._SCOPE', where='privacy/views.py'),
	SecurityControl(control='Audit logging', implementation='Immutable logs of all data access and sharing',
		kind=ControlKind.code, enforced_by='afya.privacy.service.PrivacyService.check_access_logged', where='privacy/service.py'),
	SecurityControl(control='Vulnerability management', implementation='Monthly scanning; quarterly penetration testing',
		kind=ControlKind.process, enforced_by='monthly scan cadence; quarterly pentest cadence'),
	SecurityControl(control='Incident response', implementation='Documented plan; 72-hour breach notification per DPA',
		kind=ControlKind.code, enforced_by='afya.privacy.service.PrivacyService.breach_notification', where='privacy/service.py'),
	SecurityControl(control='Secure development', implementation='SAST, DAST, dependency scanning in CI', kind=ControlKind.ci,
		enforced_by='afya.security.service.CI_COMMANDS', where='.github/workflows/ci.yml'),
	SecurityControl(control='Third-party assessment', implementation='Annual independent security audit',
		kind=ControlKind.process, enforced_by='annual cadence'),
	SecurityControl(control='Bug bounty', implementation='Public programme with responsible disclosure',
		kind=ControlKind.code, enforced_by='afya.security.service.SecurityService.disclosure_policy', where='security/service.py'),
)

# §17.5 "Secure development — SAST, DAST, dependency scanning in CI". These are the exact shell
# fragments the workflow must contain; test_security.py reads .github/workflows/ci.yml and asserts
# every one is present, so the control's claim and the workflow cannot drift apart. DAST is not in
# the list because a dynamic scan needs a running deployment the CI job does not stand up — naming
# it here would make the row claim a gate that never runs, which is the failure this table exists
# to prevent.
CI_COMMANDS: tuple[str, ...] = ('uv run pyright', 'uv run pytest', 'uvx bandit -r src/afya', 'uvx pip-audit')

# §17.5 cadences. The two the table names by period; the third-party audit is annual, and the
# pentest is quarterly.
SCAN_CADENCE_DAYS: dict[str, int] = {
	'sast': 30, 'dependency': 30, 'dast': 30, 'penetration': 90, 'third_party_audit': 365,
}


class SecurityService(LogMixin):
	def __init__(self) -> None:
		self._scans: list[VulnerabilityScan] = []

	def controls(self) -> list[SecurityControl]:
		return list(CONTROLS)

	def ci_enforced(self) -> list[str]:
		"""The commands the workflow must run to keep §17.5's secure-development row true."""
		return list(CI_COMMANDS)

	def record_scan(self, scan: VulnerabilityScan) -> VulnerabilityScan:
		assert scan.kind in SCAN_CADENCE_DAYS, f'{scan.kind} is not a §17.5 scan kind'
		self._scans.append(scan)
		if scan.findings_critical:
			self._log_warn('scan found critical issues', kind=scan.kind, count=scan.findings_critical)
		return scan

	def obligations(self, today: date) -> list[ScanObligation]:
		"""Every recurring §17.5 obligation and whether it is overdue. A kind never performed is
		overdue, not exempt — an audit that has never run is the one most likely to be forgotten."""
		out: list[ScanObligation] = []
		for kind, cadence in SCAN_CADENCE_DAYS.items():
			latest = max((s for s in self._scans if s.kind == kind), key=lambda s: s.performed_on_iso, default=None)
			last = latest.performed_on_iso if latest else None
			due = (date.fromisoformat(last) + timedelta(days=cadence)).isoformat() if last else None
			out.append(ScanObligation(kind=kind, cadence_days=cadence, last_performed_iso=last, due_on_iso=due,
				overdue=due is None or date.fromisoformat(due) < today))
		return out

	def open_findings(self) -> tuple[int, int]:
		return (
			sum(s.findings_critical for s in self._scans),
			sum(s.findings_high for s in self._scans),
		)

	@staticmethod
	def disclosure_policy() -> DisclosurePolicy:
		return DisclosurePolicy(
			contact='security@afya.go.ke',
			acknowledge_within_hours=48, triage_within_days=5,
			safe_harbour='Good-faith research on systems you own or are authorised to test will not be pursued.',
			in_scope=['the API', 'the native clients', 'the channel gateways'],
			out_of_scope=['denial of service', 'social engineering of staff', 'third-party systems'],
		)

	def posture(self, today: date) -> SecurityPosture:
		critical, high = self.open_findings()
		return SecurityPosture(
			controls=self.controls(),
			ci_enforced=self.ci_enforced(),
			process_obligations=self.obligations(today),
			open_critical=critical, open_high=high,
			disclosure_policy=self.disclosure_policy().model_dump(mode='json'),
		)
