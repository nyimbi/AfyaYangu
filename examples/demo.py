"""End-to-end demo: USSD session -> febrile triage -> SOS -> offline sync flush -> Tier-4 gate.
Run: uv run python examples/demo.py
"""
import asyncio

from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import UssdRequest
from afya.emergency.service import EmergencyService, Inline719Port
from afya.emergency.views import SOSEvent
from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.surveillance.service import SurveillanceService
from afya.sync.service import SyncService
from afya.sync.views import SyncOp
from afya.triage.service import TriageService
from afya.triage.views import TriageInput


async def main() -> None:
	registry = FeatureRegistry()
	tr = TriageService(registry)
	ch = ChannelService(AfricaTalkingSmsPort('https://api.africastalking.com', 'demo'))
	em = EmergencyService(Inline719Port())
	sync = SyncService()
	surv = SurveillanceService(registry)

	menu = ch.ussd(UssdRequest(session_id='ss1', msisdn='+254711222333', text=''))
	print('USSD menu:\n' + (menu.menu or ''))
	print(ch.ussd(UssdRequest(session_id='ss1', msisdn='+254711222333', text='3')).end_text)

	print('fever-only:', tr.assess(TriageInput(symptoms=['fever'], temperature_c=38.6)).recommendation)
	print('fever+contact:', tr.assess(TriageInput(symptoms=['fever', 'headache'], temperature_c=38.4, ebola_contact=True)).recommendation)

	sos = await em.sos(SOSEvent(sos_id='SOS-DEMO000123', lat=-1.29, lon=36.82, severity='high'))
	print('SOS dispatch ->', sos.notified, sos.actions)

	await sync.enqueue(SyncOp(op_id='OP-DEMOAAA123', dataset='symptom_logs', client_ts=100, payload={'fever': '1'}))
	print('sync flush:', (await sync.flush(0)).model_dump(mode='json'))

	print('tier4 dormant:', await surv.activate_tier4(False, True, True))
	print('tier4 active:', await surv.activate_tier4(True, True, True, bulletin='PHEOC activation'))
	print('TRI-003 now available:', tr.assess_evd(TriageInput(symptoms=['fever'], temperature_c=39.3, ebola_contact=True)).risk_level.value)


if __name__ == '__main__':
	asyncio.run(main())