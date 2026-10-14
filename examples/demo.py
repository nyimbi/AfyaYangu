"""End-to-end demo: USSD session -> febrile triage -> SOS -> offline sync flush -> Tier-4 gate.
Run: uv run python examples/demo.py
"""
import asyncio

from afya.channels.outbound import plain_language_report
from afya.channels.service import AfricaTalkingSmsPort, ChannelService
from afya.channels.views import UssdRequest
from afya.chw.service import ChwService
from afya.emergency.service import EmergencyService, Inline719Port
from afya.emergency.views import SOSEvent
from afya.identity.service import IdentityService
from afya.live.service import LiveService
from afya.live.views import LivePlatform, LiveSession
from afya.privacy.views import DPIARecord, LegalBasis
from afya.registry.service import FeatureRegistry, Tier4Activation
from afya.surveillance.service import SurveillanceService
from afya.sync.service import SyncService
from afya.sync.views import SyncOp
from afya.triage.service import TriageService
from afya.triage.views import TriageInput


async def main() -> None:
	registry = FeatureRegistry()
	tr = TriageService(registry)
	ch = ChannelService(AfricaTalkingSmsPort('https://api.africastalking.com', 'demo'),
	                    triage=tr, identity=IdentityService())
	em = EmergencyService(Inline719Port())
	sync = SyncService()
	surv = SurveillanceService(registry)

	menu = ch.ussd(UssdRequest(session_id='ss1', msisdn='+254711222333', text=''))
	print('USSD menu:\n' + (menu.menu or ''))
	print(ch.ussd(UssdRequest(session_id='ss1', msisdn='+254711222333', text='3')).end_text)
	# §CHAN-2's closing screen reports the *consent* the first prompt collected, not a transmission:
	# a USSD session carries no coordinates.
	print('consent declined:', ch.ussd(UssdRequest(
		session_id='ss2', msisdn='+254711222333', text='1*1*2*2')).end_text)

	# §CHAN-1's follow-up: composed when the report is filed, sent by the route once per report.
	ch.ussd(UssdRequest(session_id='ss1', msisdn='+254711222333', text='1*1*1*2'))
	report = ch.channel_reports()[-1]
	follow_up = await ch.send_follow_up(report)
	print('follow-up:', follow_up.body if follow_up else None)
	print('follow-up again:', await ch.send_follow_up(report))  # None — once per report, not per session
	print('plain:', follow_up.plain.model_dump(mode='json') if follow_up else None)
	print('plain-language report:', [r.surface for r in plain_language_report()][:3], '...')

	print('fever-only:', tr.assess(TriageInput(symptoms=['fever'], temperature_c=38.6)).recommendation)
	print('fever+contact:', tr.assess(TriageInput(symptoms=['fever', 'headache'], temperature_c=38.4, ebola_contact=True)).recommendation)

	sos = await em.sos(SOSEvent(sos_id='SOS-DEMO000123', lat=-1.29, lon=36.82, severity='high'))
	print('SOS dispatch ->', sos.notified, sos.actions)

	await sync.enqueue(SyncOp(op_id='OP-DEMOAAA123', dataset='symptom_logs', client_ts=100, payload={'fever': '1'}))
	print('sync flush:', (await sync.flush(0)).model_dump(mode='json'))

	# §17.3's three-key gate. The `dpia_review` key is *derived* from a recorded review rather than
	# passed, so this example has to record one — `dpia_reviewed=True` is no longer a key a caller can
	# hold by saying so, which is the defect the parameter used to be.
	print('tier4 dormant:', await surv.activate_tier4(False, True))  # no review recorded, so the key stays shut
	review = DPIARecord(reviewed_at_iso='2026-10-14T09:00:00Z', reviewed_by='DPO', processing_id='evd_contact_tracing',
	                    fingerprint='demo', topics=['contact tracing'], risks=['re-identification'], blocked=False)
	print('tier4 active:', await surv.activate_tier4(True, True, bulletin='PHEOC activation', review=review))
	print('TRI-003 now available:', tr.assess_evd(TriageInput(symptoms=['fever'], temperature_c=39.3, ebola_contact=True)).risk_level.value)

	# §CHAN-000's call-in and §CHAN-004's clinician Q&A: one queue, fed from the channel sink.
	live = LiveService()
	await live.schedule(LiveSession(
		session_id='LS-DEMO', platform=LivePlatform.radio_callin, topic='Ebola questions',
		clinician='Dr Achieng', starts_at_iso='2026-10-14T18:00:00Z', ends_at_iso='2026-10-14T19:00:00Z',
		lang='sw', venue='KBC Radio'))
	await live.open('LS-DEMO')
	# The asker is a §SEC-004 rotating handle derived from the subject, never the subject itself.
	asked = await live.ask('LS-DEMO', LiveService.handle_for('+254711222333', 0),
	                       'Is a headache a sign?', at_ms=0)
	answered = await live.answer(asked.question_id, 'Drink water and rest.', 'Dr Achieng', 0)
	print('live answered:', answered.status.value, 'verdicts:', answered.verdicts)
	print('live transcript:', live.transcript('LS-DEMO').model_dump(mode='json')['questions_answered'])

	# §CHAN-004's submitted content: refused without a real consent, drafted with one — never
	# published. Approval hands the story to §6.5's workflow, so moderation is not publication.
	from afya.info.service import InfoService
	from afya.info.submissions import StoryKind, StoryService, StorySubmission
	from afya.privacy.service import PrivacyService
	from afya.privacy.views import ConsentRecord

	privacy = PrivacyService()
	info = InfoService()
	story_svc = StoryService(privacy, info)
	story = StorySubmission(story_id='ST-DEMO', kind=StoryKind.testimonial, subject_ref='+254711222333',
	                        author=LiveService.handle_for('+254711222333', 0), author_role='CHW',
	                        text='I told my neighbours what I learned and two of them went for testing.',
	                        lang='en', consent_id='C-DEMO')
	try:
		story_svc.submit(story, None)
	except PermissionError as exc:
		print('story without consent:', exc)
	consent = ConsentRecord(consent_id='C-DEMO', subject_ref='+254711222333', purpose='publish_story',
	                        data_types=['story'], retention_days=365,
	                        legal_basis=LegalBasis.consent, channel='ussd', lang='en')
	await privacy.record_consent(consent)
	story_svc.submit(story, privacy.consent_record('C-DEMO'))
	drafted = await story_svc.approve('ST-DEMO', 'MoH content ops', 0)
	print('story approved ->', drafted.stage.value, '| in library:', any(
		i.item_id == drafted.item_id for i in info.library('en')))

	# §CHAN-5's printed job aids. The aid text and the PDF writer were both here and nothing joined
	# them, so a job aid was a string a screen showed and nothing a worker could carry.
	sheet = ChwService.job_aid_sheet('safe_burial')
	raw = sheet.content.encode('latin-1')
	print('job aid printed ->', sheet.filename, '|', len(raw), 'bytes | pdf:', raw.startswith(b'%PDF-1.4'))


if __name__ == '__main__':
	asyncio.run(main())