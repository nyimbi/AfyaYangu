"""Gate: the Android client may not permit cleartext, and may not back up its credentials.

`android:usesCleartextTraffic="true"` permits plain HTTP to *any* host, which is incompatible with
§SEC-003's "TLS 1.3 in transit". It is the kind of setting added to reach a dev server and left in
because nothing fails: the demo works, the release ships, and every request is readable on the wire.
Cleartext is allowed only to loopback, where the documented demo path (`adb reverse`) needs it.

The bearer token and cached personal data live in the `afya` SharedPreferences file. A cloud backup
a user did not ask for would carry the device's credential and its cached responses off the device,
so that file is excluded from both backup and device transfer.

Both checks are canaried against known-bad text before being trusted.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MAIN = REPO / 'android' / 'app' / 'src' / 'main'
MANIFEST = MAIN / 'AndroidManifest.xml'
NETWORK_CONFIG = MAIN / 'res' / 'xml' / 'network_security_config.xml'

# Hosts the demo genuinely needs: the emulator's alias for the developer's loopback, and loopback.
LOOPBACK = {'localhost', '127.0.0.1', '10.0.2.2'}


def _manifest_offences(text: str) -> list[str]:
	out: list[str] = []
	if re.search(r'android:usesCleartextTraffic\s*=\s*"true"', text):
		out.append('manifest permits cleartext to any host')
	if not re.search(r'android:networkSecurityConfig\s*=', text):
		out.append('manifest declares no network security config')
	if not re.search(r'android:(?:fullBackupContent|dataExtractionRules)\s*=', text):
		out.append('manifest excludes nothing from backup')
	return out


def _config_offences(text: str) -> list[str]:
	out: list[str] = []
	if not re.search(r'<base-config[^>]*cleartextTrafficPermitted="false"', text):
		out.append('base-config does not deny cleartext by default')
	for host in re.findall(r'<domain[^>]*>([^<]+)</domain>', text):
		if host.strip() not in LOOPBACK:
			out.append(f'cleartext permitted to non-loopback host {host.strip()}')
	return out


def test_the_transport_gate_fires_on_planted_defects() -> None:
	"""Canary. A gate never watched failing is not evidence."""
	# Each offence is isolated: the other two attributes are present so only one can fire.
	complete = 'android:usesCleartextTraffic="true" android:networkSecurityConfig="@xml/n" android:dataExtractionRules="@xml/d"'
	assert _manifest_offences(complete) == ['manifest permits cleartext to any host']
	assert _manifest_offences('<application android:label="Afya">') == [
		'manifest declares no network security config', 'manifest excludes nothing from backup',
	]
	assert _config_offences('<base-config cleartextTrafficPermitted="true" />') == ['base-config does not deny cleartext by default']
	assert _config_offences('<base-config cleartextTrafficPermitted="false"/><domain>evil.example.com</domain>') == [
		'cleartext permitted to non-loopback host evil.example.com',
	]


def test_android_permits_cleartext_only_to_loopback() -> None:
	assert _manifest_offences(MANIFEST.read_text()) == [], 'the Android manifest weakened transport security'
	assert _config_offences(NETWORK_CONFIG.read_text()) == [], 'the network security config weakened transport security'


def test_android_excludes_credentials_from_backup() -> None:
	"""Every backup rule the manifest points at must exclude the file holding the token."""
	manifest = MANIFEST.read_text()
	refs = re.findall(r'android:(?:fullBackupContent|dataExtractionRules)\s*=\s*"@xml/(\w+)"', manifest)
	assert refs, 'no backup rules are declared, so the token and cache are backed up'
	for name in refs:
		body = (MAIN / 'res' / 'xml' / f'{name}.xml').read_text()
		assert 'path="afya.xml"' in body, f'{name}.xml does not exclude the credential store'
