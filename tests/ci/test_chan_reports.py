"""§5.4's "single case-report backend" on the two channels that had no writer.

The dedup machinery was real and unreachable. `CaseReport.reporter_msisdn` reaches
`IdentityService.dedup_key`, which normalises `0712345678` and `+254712345678` onto one key — and
`CommunityService.submit_case` has one caller, `POST /community/cases`, guarded on `assigned`. A
USSD caller holds no token at all. So §5.4's "deduplicated by phone number" held for the app and the
CHW and for neither of the channels §4.1 gives to people without smartphones, and §CHAN-2's
Integration sentence described a flow that did not exist.

The second half is worse than the first. §AI-003's early-warning ledger is fed by six app surfaces
through `_record_signal` and by no channel at all: a fever reported over USSD reached no backend and
no signal, on exactly the population an outbreak in a low-connectivity county shows up in first.

Every test here asserts what a person's message *does*, not what the tree contains — a sink nothing
writes to passes any test that reads the sink.
"""
from afya.channels.service import ChannelService
from afya.channels.views import UssdRequest, WhatsAppIn
from afya.identity.service import IdentityService
from afya.registry.service import FeatureRegistry
from afya.triage.service import TriageService

MSISDN = '+254711222333'
# The same handset as the carrier spells it: bare, with the country code and no plus.
BARE = '254711222333'


def _svc(identity: IdentityService | None = None, signals: list[tuple[str, str, str]] | None = None) -> ChannelService:
	async def record_signal(county: str, signal: str, ref: str) -> None:
		if signals is not None:
			signals.append((county, signal, ref))
	return ChannelService(
		_NoSms(), None, TriageService(FeatureRegistry()), identity or IdentityService(), None, None,
		record_signal)


class _NoSms:
	"""A port that does not send. These tests are about what is recorded, not what is delivered."""

	async def send(self, msg: object) -> str:
		return 'at:queued'


def _walk(svc: ChannelService, text: str, lang: str = 'en') -> None:
	svc.ussd(UssdRequest(session_id='s1', msisdn=MSISDN, text=text), lang)


def test_a_ussd_walk_files_a_report_and_not_only_a_callback() -> None:
	"""The defect, at the point it was: the walk recorded the callback and the answers and no report.

	`record_callback` was wired and `_callbacks` grew; `_reports` did not exist. A fever reported from
	the one channel §4.1 gives to people without smartphones was answered and then dropped.
	"""
	svc = _svc()
	assert svc.channel_reports() == [], 'nothing is filed before a symptom is chosen'
	_walk(svc, '1*1*1*1')
	reports = svc.channel_reports()
	assert len(reports) == 1, reports
	assert reports[0].channel == 'ussd' and reports[0].msisdn == MSISDN
	assert reports[0].symptoms == ['fever'], reports[0].symptoms
	assert reports[0].symptom_label == 'Fever'
	assert reports[0].handled is False


def test_declining_the_callback_does_not_retract_the_report() -> None:
	"""Two different things a person did. `2` on the callback prompt is a declined call, not a
	withdrawn symptom — and a walk that filed the report only when the callback was requested would
	drop the report of everyone who did not want to be phoned."""
	svc = _svc()
	_walk(svc, '1*1*2*2')
	assert svc.callback_requests() == [], 'the callback was declined'
	assert len(svc.channel_reports()) == 1, 'and the fever was still reported'


def test_a_menu_item_the_engine_cannot_classify_is_still_a_report() -> None:
	"""§CHAN-2 offers "Cough" and "Other" and `USSD_SYMPTOM_MAP` maps both to nothing.

	That mapping is honest — the engine's vocabulary is §8.1's febrile set — and it is exactly why
	`symptom_label` exists. A report carrying the empty list alone would be indistinguishable from a
	person who reported nothing, and the deployment would have no way to see that a hundred people
	chose "Cough".
	"""
	svc = _svc()
	_walk(svc, '1*2*1*1')  # the second symptom is Cough
	reports = svc.channel_reports()
	assert len(reports) == 1, reports
	assert reports[0].symptoms == [], 'the engine has no word for cough'
	assert reports[0].symptom_label == 'Cough', 'and the menu item is what survives the miss'


def test_the_report_is_keyed_the_way_the_case_backend_keys_it() -> None:
	"""§5.4's whole claim, and the only reason it is true.

	`IdentityService.dedup_key` is the one spelling of a phone number, and both sinks build their key
	from it. A local normalisation in the channel layer would be a second key, and a second key finds
	nothing — which is how "deduplicated by phone number" becomes a sentence rather than a behaviour.
	"""
	identity = IdentityService()
	svc = _svc(identity)
	_walk(svc, '1*1*1*1')
	assert svc.channel_reports()[0].dedup_key == identity.dedup_key(MSISDN)
	# And the same phone written the other way is the same key, which is the cross-channel case: a
	# person who reports on USSD and again from the app is one reporter.
	assert identity.dedup_key('0711222333') == identity.dedup_key('+254711222333')


def test_the_whatsapp_router_files_a_report_too() -> None:
	"""§CHAN-2's Integration clause names WhatsApp explicitly ("the same backend as app and WhatsApp
	reports"), and the router is the second producer. One writer, so the two cannot file two shapes."""
	svc = _svc()
	svc.route_whatsapp(WhatsAppIn(from_msisdn=MSISDN, body='I have fever and bleeding'), lang='en')
	reports = svc.channel_reports()
	assert len(reports) == 1, reports
	assert reports[0].channel == 'whatsapp'
	assert reports[0].symptoms == ['fever', 'bleeding'], reports[0].symptoms


def test_a_question_is_not_filed_as_a_report() -> None:
	"""The guard that keeps the backend a report store rather than a message log.

	§CHAN-3's intent list has "symptom" as a trigger word, so "what is a symptom?" takes the symptom
	branch — and a body that named no symptom the engine heard is a question, not a report. Filing it
	would put a question into the count a surveillance officer reads.
	"""
	svc = _svc()
	svc.route_whatsapp(WhatsAppIn(from_msisdn=MSISDN, body='what is a symptom?'), lang='en')
	svc.route_whatsapp(WhatsAppIn(from_msisdn=MSISDN, body='I need a clinic'), lang='en')
	assert svc.channel_reports() == []


def test_the_swahili_report_is_filed_with_the_engine_key() -> None:
	"""The other half of §CHAN-1's prefix, carried into the backend.

	A `SW` body that named a fever is filed as `fever` — the engine's key, not the Swahili word —
	because the report has to be readable by the same detector that reads the app's.
	"""
	svc = _svc()
	svc.route_whatsapp(WhatsAppIn(from_msisdn=MSISDN, body='nina homa'), lang='sw')
	reports = svc.channel_reports()
	assert len(reports) == 1 and reports[0].symptoms == ['fever'], reports


async def test_a_report_with_no_locality_is_held_and_not_counted() -> None:
	"""§AI-003's signal is a rise *in a locality*, and this is the honest answer for both channels.

	Every USSD and SMS report today has no county — those channels carry none — so the ledger is told
	nothing and the report is still held. `reports_for_signal` is how the deployment reads the split
	rather than assuming it, and `emit_report_signal` returning False is the fact rather than a
	failure.
	"""
	signals: list[tuple[str, str, str]] = []
	svc = _svc(signals=signals)
	_walk(svc, '1*1*1*1')
	report = svc.channel_reports()[0]
	assert report.county is None, 'a USSD session carries no locality'
	assert await svc.emit_report_signal(report) is False
	assert signals == [], 'nothing is counted against a county baseline it does not belong to'
	assert svc.reports_for_signal() == [], 'and the split is readable'


async def test_a_report_that_names_a_county_reaches_the_signal_ledger() -> None:
	"""The leg that was missing. Six app surfaces recorded their events and no channel recorded any,
	so a fever reported from a feature phone could not raise the county signal it is evidence for."""
	signals: list[tuple[str, str, str]] = []
	svc = _svc(signals=signals)
	report = svc.record_report(MSISDN, 'whatsapp', ['fever'], county='Busia')
	assert await svc.emit_report_signal(report) is True
	assert signals == [('Busia', 'fever_triage', report.report_id)], signals
	assert svc.reports_for_signal() == [report]


async def test_a_report_is_counted_once_however_many_requests_follow_it() -> None:
	"""The failure mode a rise-detector must not have: a signal that rises with *traffic*.

	The routes emit by walking the sink, so a second USSD session — any second session, by anyone —
	would re-count every report already filed. One fever would become two signals because someone
	else opened the menu, and the z-score that is supposed to detect an outbreak would instead detect
	how busy the channel was. Emission is idempotent per report.
	"""
	signals: list[tuple[str, str, str]] = []
	svc = _svc(signals=signals)
	report = svc.record_report(MSISDN, 'whatsapp', ['fever'], county='Busia')
	assert await svc.emit_report_signal(report) is True
	# Every later request walks the same sink. None of them may count it again.
	for _ in range(3):
		assert await svc.emit_report_signal(report) is False
	assert len(signals) == 1, signals


async def test_a_non_febrile_report_is_not_a_fever_signal() -> None:
	"""§AI-003's bullet is "a sudden increase in fever triage in a locality" and the ledger's
	vocabulary is fixed. Counting a bleeding report as a fever would make the signal mean "any
	report", which is the drift the one-vocabulary rule exists to prevent."""
	signals: list[tuple[str, str, str]] = []
	svc = _svc(signals=signals)
	report = svc.record_report(MSISDN, 'whatsapp', ['bleeding'], county='Busia')
	assert await svc.emit_report_signal(report) is False
	assert signals == []


async def test_an_unwired_detector_does_not_stop_a_report() -> None:
	"""A deployment with no detector still triages and still files. The ledger is one leg, and a
	channel that refused to record a report because the detector was absent would be a channel whose
	availability depends on a component the person never asked for."""
	svc = ChannelService(_NoSms(), None, TriageService(FeatureRegistry()), IdentityService())
	report = svc.record_report(MSISDN, 'ussd', ['fever'], county='Busia')
	assert await svc.emit_report_signal(report) is False
	assert svc.channel_reports() == [report], 'the report is held regardless'


def test_a_report_with_no_identity_model_refuses_rather_than_filing_an_unkeyed_one() -> None:
	"""§5.4's claim is about the key. A report that cannot be keyed cannot be deduplicated, and a
	silent fallback to the raw number would be the duplicate the section promises is gone."""
	import pytest

	svc = ChannelService(_NoSms(), None, TriageService(FeatureRegistry()))
	with pytest.raises(RuntimeError, match='identity model'):
		svc.record_report(MSISDN, 'ussd', ['fever'])


def test_a_report_names_something() -> None:
	"""The model's own refusal, at the boundary. A report with neither an engine symptom nor a menu
	label is not a report, and this is what stops one being constructed by a future caller."""
	import pytest
	from pydantic import ValidationError

	from afya.channels.views import ChannelReport

	with pytest.raises(ValidationError, match='names neither'):
		ChannelReport(channel='ussd', msisdn=MSISDN, symptoms=[], symptom_label=None,
		              reported_at_ms=1, dedup_key='k', consent_to_store=False)


def test_the_report_records_whether_storage_was_consented_to() -> None:
	"""§5.4's consent crossing, recorded rather than enforced.

	A person who has not granted symptom storage still gets triaged — refusing to answer someone is
	not a privacy protection — and the field is what lets the deployment see that the record is held
	without a grant rather than having to infer it. With no registry wired the answer is False, which
	is the safe direction `may_store_symptoms` was written to refuse a default on.
	"""
	svc = _svc()
	_walk(svc, '1*1*1*1')
	assert svc.channel_reports()[0].consent_to_store is False, 'no registry is wired, so no grant is held'


def test_a_handled_report_leaves_the_record_and_the_default_read_is_the_record() -> None:
	"""A report is a record of what a person said, so the default read is the record — the opposite
	of the callback queue, where the default read is the work remaining. A caller that wants the work
	asks for it by name."""
	import pytest

	svc = _svc()
	_walk(svc, '1*1*1*1')
	report = svc.channel_reports()[0]
	svc.handle_report(report.report_id)
	assert svc.channel_reports() == [report], 'the record is kept'
	assert svc.channel_reports(unhandled_only=True) == []
	with pytest.raises(KeyError):
		svc.handle_report('CHR-NOSUCH')
