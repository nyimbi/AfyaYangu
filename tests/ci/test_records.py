import pytest
from typing import Any

from afya.records.service import RecordsService
from afya.records.views import GrowthRecord, ImmunisationRecord, MedReminder, WalletMember


async def test_minor_requires_guardian() -> None:
	svc = RecordsService()
	with pytest.raises(AssertionError):
		await svc.add_member(WalletMember(member_ref='KID1', dob_iso='2015-01-01'))
	await svc.add_member(WalletMember(member_ref='KID1', dob_iso='2015-01-01', guardian_ref='GUARD1'))
	assert svc._members['KID1'].is_minor  # noqa: SLF001 — contract check


async def test_epi_gap_detection() -> None:
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='CH1', dob_iso='2025-10-01', guardian_ref='GUARD1'))  # ~12 months
	gaps = svc.immunisation_gaps('CH1')
	assert 'BCG dose 1' in gaps or 'PCV10 dose 1' in gaps
	await svc.record_immunisation(ImmunisationRecord(member_ref='CH1', vaccine='BCG', dose_no=1, given_iso='2025-10-02'))
	assert 'BCG dose 1' not in svc.immunisation_gaps('CH1')


def test_growth_underweight_flag() -> None:
	svc = RecordsService()
	flag = svc.growth_flag(GrowthRecord(member_ref='CH1', age_months=12, weight_kg=4.5, height_cm=74.5))
	assert flag.flag == 'underweight'
	normal = svc.growth_flag(GrowthRecord(member_ref='CH1', age_months=12, weight_kg=9.5, height_cm=74.5))
	assert normal.flag == 'normal'


def test_growth_stunted_flag() -> None:
	svc = RecordsService()
	flag = svc.growth_flag(GrowthRecord(member_ref='CH1', age_months=24, weight_kg=11.0, height_cm=70.0))
	assert flag.flag == 'stunted'


async def test_reminders() -> None:
	svc = RecordsService()
	rem = MedReminder(member_ref='CH1', drug='amoxicillin', times_per_day=3, started_iso='2026-10-01', channel='sms')
	await svc.add_reminder(rem)
	assert svc.reminders_for('CH1') == [rem]
	assert svc.reminders_for('OTHER') == []

# --- §17.6 children's data: the age at which control transfers -----------------------------------

def test_age_is_computed_from_the_dates_not_from_a_constant() -> None:
	"""The first version of this arithmetic was `(2026 - year) * 12 + (10 - month)` — the clock
	written into the expression. It read correctly in October 2026 and nowhere else, and wrong in
	the one direction that matters: a child born in 2008 read as 18 forever, so §17.6's transfer
	never fired, and nobody ever aged, so a 17-year-old enrolled in 2026 was still a minor in 2030."""
	from datetime import date
	from afya.records.service import age_years
	assert age_years('2008-05-01', date(2026, 10, 12)) == 18, 'a birthday already passed this year'
	assert age_years('2008-11-01', date(2026, 10, 12)) == 17, 'a birthday still to come this year'
	assert age_years('2008-10-12', date(2026, 10, 12)) == 18, 'the birthday itself counts'
	assert age_years('2008-10-13', date(2026, 10, 12)) == 17, 'the day before does not'
	assert age_years('2026-01-01', date(2026, 10, 12)) == 0


async def test_control_transfers_at_eighteen() -> None:
	"""§17.6 line 4: "At age 18, control transfers to the individual." Guardianship is a relation
	with an end date, and a rule that read only `guardian_ref == subject_ref` gave a guardian
	perpetual access to a child's record — a 30-year-old's health history readable by whoever
	enrolled them as a minor, which is the failure the line exists to prevent."""
	from datetime import date
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='KID', dob_iso='2015-01-01', guardian_ref='GUARD1'),
		today=date(2026, 10, 12))
	assert svc.owns('GUARD1', 'KID') is True, 'a guardian reads their minor'
	assert svc.owns('STRANGER', 'KID') is False
	# The same wallet, read after the child's eighteenth birthday: the relation ended on its own,
	# without anything being re-enrolled — which is the part a stored `is_minor` flag gets wrong.
	after = date(2033, 1, 2)
	assert svc.owns('GUARD1', 'KID', after) is False, 'control transferred to the individual at 18'
	assert svc.owns('GUARD1', 'KID', date(2033, 1, 1)) is False, 'the eighteenth birthday is the transfer'
	assert svc.owns('GUARD1', 'KID', date(2032, 12, 31)) is True, 'the day before it is still a minor'
	assert svc.owns('KID', 'KID', after) is True, 'they still read their own records'


async def test_an_adult_cannot_be_enrolled_as_someone_elses_dependent() -> None:
	"""The assert that stops the transfer being undone by the next enrolment. A guardian_ref on an
	adult is a reference `owns` would have honoured before this rule existed, so the model refuses
	it rather than storing a relation nothing will ever apply."""
	from datetime import date
	svc = RecordsService()
	with pytest.raises(AssertionError, match='an adult controls their own records'):
		await svc.add_member(WalletMember(member_ref='ADULT', dob_iso='1990-01-01', guardian_ref='GUARD1'),
			today=date(2026, 10, 12))
	# Naming yourself is not a guardianship claim, so it is allowed.
	await svc.add_member(WalletMember(member_ref='ADULT', dob_iso='1990-01-01', guardian_ref='ADULT'),
		today=date(2026, 10, 12))
	assert svc.owns('ADULT', 'ADULT') is True
	assert svc.owns('GUARD1', 'ADULT') is False, "a self-named guardian_ref is not a claim by anyone else"


async def test_the_transfer_date_is_reported_not_only_the_boolean() -> None:
	"""A guardian told "no" without a date has no way to know whether the record moved or they
	mistyped a reference, so the route that serves them can answer both questions."""
	from datetime import date
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='KID', dob_iso='2015-03-04', guardian_ref='GUARD1'),
		today=date(2026, 10, 12))
	assert svc.transfers_at('KID', date(2026, 10, 12)) == '2033-03-04'
	await svc.add_member(WalletMember(member_ref='ADULT', dob_iso='1990-01-01'),
		today=date(2026, 10, 12))
	assert svc.transfers_at('ADULT', date(2026, 10, 12)) is None, 'already their own controller'


def test_the_canary_watches_the_minor_check_fire() -> None:
	"""The ownership rule's new conjunct is the thing to canary, because dropping it is a silent
	change: `owns` still returns True for the self case and False for a stranger either way, and
	only a guardian-and-adult pair distinguishes the two versions."""
	from datetime import date
	svc = RecordsService()
	svc._members['KID'] = WalletMember(member_ref='KID', dob_iso='2008-01-01', guardian_ref='GUARD1')  # noqa: SLF001
	assert svc.owns('GUARD1', 'KID', date(2026, 10, 12)) is False, 'the age check did not fire'
	# The same stored row, read one day earlier, reads True — so what decided it was the date and
	# not the guardian_ref, which is the conjunct a future edit would be tempted to drop.
	assert svc.owns('GUARD1', 'KID', date(2008, 1, 1)) is True
	# And a member with no guardian at all is still nobody else's to read.
	svc._members['ORPHAN'] = WalletMember(member_ref='ORPHAN', dob_iso='2020-01-01')  # noqa: SLF001
	assert svc.owns('GUARD1', 'ORPHAN', date(2026, 10, 12)) is False


# --- §9.2 REC-001's contents and the ten-profile cap ------------------------------------------

def _spec_wallet_contents() -> list[str]:
	"""§9.2 REC-001's "Contents:" bullets, read out of the spec so a revision fails here."""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('#### REC-001: Family Health Wallet (Basic)', 1)[1].split('**Features:**', 1)[0]
	return [line[2:].strip() for line in section.splitlines() if line.startswith('- ')]


def test_the_wallet_contents_are_the_sections_bullets() -> None:
	"""§9.2 lists eight things a wallet holds. Each is carried in the section's order, so a bullet
	added to the spec and not to the table fails here rather than being silently absent."""
	from afya.records.service import WALLET_ITEMS
	spec = _spec_wallet_contents()
	assert len(spec) == 8, f'the section names {len(spec)} contents'
	assert [item for item, _, _ in WALLET_ITEMS] == spec


def test_the_contents_report_names_what_is_unbacked() -> None:
	"""The finding, and the day it closed.

	Seven of the section's eight contents had a model and discharge summaries did not — reported
	rather than padded, because the wallet is what a person opens when they have lost the paper, so
	an item with nothing behind it is a document the app promises to keep and cannot. The eighth
	now has a carrier: the `discharge` kind of `WalletDocument`, which is where the paper a facility
	handed someone gets filed.

	The test asserts the *report* rather than the absence of a gap, and asserts the reference still
	resolves, so the day a `module:attr` rots this fails for the reason it exists — a rotted
	reference reads exactly like a carried item until something imports it.
	"""
	from afya.records.service import RecordsService
	report = RecordsService().wallet_contents()
	assert len(report.items) == 8
	assert report.unbacked_items == [], (
		f'every §9.2 content has a carrier; these do not: {report.unbacked_items}'
	)
	assert all(i.module is not None for i in report.items), 'an item with no carrier is unbacked'
	assert all(i.resolves for i in report.items), \
		'a module:attr reference that does not import is a rotted reference, not a missing document'
	# A module-less item must say why, so the gap is explained rather than merely listed.
	assert all(i.note for i in report.items if i.module is None)


async def test_the_ten_profile_cap_is_enforced_at_enrolment() -> None:
	"""§9.2 REC-001: "Multiple profiles (up to 10)". The cap is on the wallet, so it is enforced
	where a member joins one — a wallet that accepted an eleventh profile would be a section claim
	nothing kept."""
	from afya.records.service import MAX_WALLET_PROFILES, RecordsService
	from afya.records.views import WalletMember
	svc = RecordsService()
	assert MAX_WALLET_PROFILES == 10, '§9.2 names ten'
	for n in range(MAX_WALLET_PROFILES):
		await svc.add_member(WalletMember(member_ref=f'K{n}', dob_iso='2015-01-01', guardian_ref='G1'))
	# The eleventh is refused, and the message names the section and the cap.
	with pytest.raises(AssertionError, match='§9.2 caps a wallet at 10'):
		await svc.add_member(WalletMember(member_ref='K10', dob_iso='2015-01-01', guardian_ref='G1'))
	# And a *different* wallet is unaffected, so the cap is per guardian and not global.
	await svc.add_member(WalletMember(member_ref='OTHER', dob_iso='2015-01-01', guardian_ref='G2'))
	assert len([m for m in svc._members.values() if m.guardian_ref == 'G1']) == MAX_WALLET_PROFILES


async def test_the_contents_view_is_auditor_scoped() -> None:
	"""The report names module references for every §9.2 content, which is evidence about the build."""
	import httpx
	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app
	svc = build_services()
	auth: Any = svc['auth']
	tok = auth.provision_staff('rec-aud', RBACRole.auditor, registrar='MoH ops').access_token
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		assert (await c.get('/records/wallet/contents')).status_code in (401, 403)
		body = (await c.get('/records/wallet/contents',
			headers={'authorization': f'Bearer {tok}'})).json()
		assert body['unbacked_items'] == []
		assert body['max_profiles'] == 10 and body['max_profiles_enforced'] is True


# --- §17.6's last line: "Extra protections for adolescent reproductive health data" -------------

def test_the_adolescent_band_is_grounded_and_below_the_age_of_majority() -> None:
	"""WHO defines the phase the word names — "Adolescence is the phase of life between childhood and
	adulthood, from ages 10 to 19" — and the band is intersected with this tree's age of majority.
	Above 18 `owns` already returns False for a guardian, so the 18–19 half is unreachable and a
	bound carrying it would be a claim with no member behind it."""
	from afya.records.service import ADOLESCENT_YEARS, MAJORITY_YEARS
	assert ADOLESCENT_YEARS == (10, 17)
	assert ADOLESCENT_YEARS[1] < MAJORITY_YEARS, 'the band must end below the transfer of control'
	# The import-time assert is the gate; this is the same fact asserted where a reader will look.
	assert ADOLESCENT_YEARS[0] > 0, 'a lower bound is what keeps a six-year-old out of the band'


def test_the_classifier_reads_the_document_and_not_a_caller_supplied_flag() -> None:
	"""The whole mechanism. A `sensitive: bool` on the request would be a value the person filing
	the record attests about itself, and the case this protection exists for — a guardian filing
	their daughter's contraceptive under a benign title — is exactly the case the flag would be set
	to False on. So the classification is computed from the document's own fields.

	The negative cases are the ones that matter: a rule that swept in every minor's record would
	withhold from a parent what §17.6's third line gives them."""
	from afya.women.content import REPRODUCTIVE_TERMS, is_reproductive_health_data as is_rh
	assert is_rh(kind='prescription', title='Prescription: Levonorgestrel'), 'a drug name is the method'
	assert is_rh(kind='prescription', title='Prescription: Norethisterone')
	assert is_rh(kind='anc', title='Antenatal visit 1'), 'the kind is itself a term'
	assert is_rh(kind='referral', title='Family planning referral')
	assert is_rh(kind='appointment', title='Postnatal check')
	# Not reproductive health data — the guardian keeps every one of these.
	assert not is_rh(kind='immunisation', title='OPV dose 1')
	assert not is_rh(kind='lab', title='Malaria RDT')
	assert not is_rh(kind='prescription', title='Prescription: Amoxicillin')
	assert not is_rh(kind='discharge', title='Discharge summary')
	# `REFERRAL_SERVICES` also lists counselling and GBV support and neither is in the vocabulary:
	# §17.6 names *reproductive* health data, and sweeping a mental-health referral in would be this
	# protection widening itself past the sentence it implements.
	assert not is_rh(kind='referral', title='Counselling and emotional support')
	assert not is_rh(kind='referral', title='Gender-based violence support')
	# A short term must not match inside an unrelated word, which is why the short ones are matched
	# on a word boundary. "anc" is a real clinical abbreviation and also the start of "balance".
	assert not is_rh(kind='lab', title='Balance test')
	assert 'anc' in REPRODUCTIVE_TERMS, 'the boundary guard is for a term that is really there'


async def test_a_guardian_cannot_read_an_adolescents_reproductive_documents() -> None:
	"""§17.6's last line, at the service boundary. The section gives the guardian control of the
	record and then asks for extra protection for adolescent reproductive health data; if the third
	line were absolute the last line would be vacuous. WHO names the mechanism — adolescents are
	kept from care by "parental or partner control" and "lack of confidentiality" — so the
	protection with content is the one that withholds these documents from the guardian."""
	from datetime import date
	from afya.records.views import WalletDocument
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='TEEN', dob_iso='2011-03-02', guardian_ref='GUARD'),
		today=date(2026, 10, 12))
	for doc in (
		WalletDocument(member_ref='TEEN', kind='prescription', title='Contraceptive pill',
		               occurred_iso='2026-09-05'),
		WalletDocument(member_ref='TEEN', kind='anc', title='Antenatal visit 1',
		               occurred_iso='2026-09-01'),
		WalletDocument(member_ref='TEEN', kind='immunisation', title='OPV dose 1',
		               occurred_iso='2026-08-01'),
		WalletDocument(member_ref='TEEN', kind='prescription', title='Amoxicillin',
		               occurred_iso='2026-07-01'),
	):
		await svc.add_document(doc)
	today = date(2026, 10, 12)
	seen = {d.title for d in svc.documents('TEEN', reader='GUARD', today=today)}
	assert seen == {'OPV dose 1', 'Amoxicillin'}, seen
	# The adolescent reads all four of her own — the first condition in `readable` is that the
	# reader is the subject, checked before any band or classifier, so no rule locks a person out
	# of their own record.
	own = {d.title for d in svc.documents('TEEN', reader='TEEN', today=today)}
	assert len(own) == 4, own
	assert svc.readable('TEEN', next(d for d in svc.documents('TEEN') if d.kind == 'anc'), today)
	# And the unfiltered read still exists for the internal callers that need it — the count and
	# the certificate — so the protection is a filter on readers and not a deletion.
	assert len(svc.documents('TEEN')) == 4


async def test_an_adult_guardian_reads_everything_and_so_does_a_young_childs() -> None:
	"""The band has two bounds and both are load-bearing. Above 17 the guardian is not a guardian at
	all — `owns` has already refused — so the protection cannot be what stops them. Below 10 the
	record is a child's and §17.6's third line gives the parent the whole of it."""
	from datetime import date
	from afya.records.views import WalletDocument
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='KID', dob_iso='2020-01-01', guardian_ref='GUARD'),
		today=date(2026, 10, 12))
	await svc.add_document(WalletDocument(member_ref='KID', kind='prescription',
	                                      title='Contraceptive pill', occurred_iso='2026-09-05'))
	# A nine-year-old is outside the band, so the document is served: a rule with no lower bound
	# would withhold a child's record from their parent on the strength of a word in its title.
	kid = svc.documents('KID', reader='GUARD', today=date(2026, 10, 12))
	assert [d.title for d in kid] == ['Contraceptive pill']
	# A seventeen-year-old is inside it, and the same document is withheld.
	await svc.add_member(WalletMember(member_ref='TEEN', dob_iso='2009-03-02', guardian_ref='GUARD'),
		today=date(2026, 10, 12))
	await svc.add_document(WalletDocument(member_ref='TEEN', kind='prescription',
	                                      title='Contraceptive pill', occurred_iso='2026-09-05'))
	assert svc.documents('TEEN', reader='GUARD', today=date(2026, 10, 12)) == []
	# An eighteen-year-old: `owns` refuses the guardian outright, so the protection is not what
	# stops them and the band's upper bound is asserted against the ownership rule rather than
	# against this filter.
	assert svc.owns('GUARD', 'TEEN', date(2027, 3, 2)) is False


async def test_the_export_says_it_is_short_rather_than_being_silently_short() -> None:
	"""A guardian's export is missing the documents the protection withholds, and a short record
	that does not say it is short reads as a complete one. The count travels on the document; the
	list does not, because naming them would hand over the index of what was kept back."""
	from datetime import date
	from afya.records.views import WalletDocument
	svc = RecordsService()
	await svc.add_member(WalletMember(member_ref='TEEN', dob_iso='2011-03-02', guardian_ref='GUARD'),
		today=date(2026, 10, 12))
	for kind, title in (('prescription', 'Contraceptive pill'), ('immunisation', 'OPV dose 1')):
		await svc.add_document(WalletDocument(member_ref='TEEN', kind=kind, title=title,
		                                      occurred_iso='2026-09-05'))
	doc = svc.export('GUARD', 'TEEN', 'json', '2026-10-12T00:00:00+00:00')
	assert doc.document_count == 1 and doc.withheld_count == 1
	assert 'adolescent reproductive health data' in doc.withheld_note
	assert 'Contraceptive' not in doc.content, 'the withheld document is not in the export body'
	# The adolescent's own export is complete and says nothing about withholding.
	own = svc.export('TEEN', 'TEEN', 'json', '2026-10-12T00:00:00+00:00')
	assert own.document_count == 2 and own.withheld_count == 0 and own.withheld_note == ''
	# Past the eighteenth birthday there is no guardianship left for the protection to bite on, so
	# the export is empty and carries no note — the field is not a warning that fires on every
	# record. `today` is threaded through both `assert_owns` and the filter, so a birthday cannot
	# transfer control in one and not the other.
	with pytest.raises(AssertionError, match='belong to someone else'):
		svc.export('GUARD', 'TEEN', 'json', '2033-01-01T00:00:00+00:00', today=date(2033, 1, 1))


async def test_the_protection_holds_at_the_front_door_and_on_both_doors() -> None:
	"""The service filter is only half the claim; this is what the app serves. Two doors reach the
	same data — the document envelope and the typed lab row — and a control fitted to one is the
	control the other walks past, which is how the evidence consent and the §17.4 ledger both failed
	before they were moved to the boundary. The lab is filed with a value that names a pregnancy
	test and a `test` code that says nothing, which is the shape a real record has."""
	import httpx
	from afya.service import build_services, create_app
	svc = build_services()
	app = create_app(svc)
	async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
		tok = (await c.post('/auth/anonymous', json={})).json()['token']
		h = {'authorization': f'Bearer {tok}'}
		subj = (await c.get('/auth/whoami', headers=h)).json()['subject_ref']
		await c.post('/records/member', json={
			'member_ref': 'teen-1', 'guardian_ref': subj, 'dob_iso': '2011-03-02'}, headers=h)
		for body in (
			{'member_ref': 'teen-1', 'kind': 'prescription', 'title': 'Contraceptive pill',
			 'occurred_iso': '2026-09-05'},
			{'member_ref': 'teen-1', 'kind': 'immunisation', 'title': 'OPV dose 1',
			 'occurred_iso': '2026-08-01'},
		):
			assert (await c.post('/records/documents', json=body, headers=h)).status_code == 200
		assert (await c.post('/records/labs', json={
			'member_ref': 'teen-1', 'test': 'other', 'value': 'positive pregnancy test',
			'performed_iso': '2026-09-02', 'flag': 'abnormal'}, headers=h)).status_code == 200

		docs = (await c.get('/records/teen-1/documents', headers=h)).json()
		assert [d['title'] for d in docs] == ['OPV dose 1'], docs
		assert (await c.get('/records/teen-1/labs', headers=h)).json() == [], 'the second door is closed'
		tl = (await c.get('/records/timeline', headers=h)).json()
		assert [e['title'] for e in tl] == ['OPV dose 1'], tl
		search = (await c.get('/records/search', params={'q': 'Contraceptive'}, headers=h)).json()
		assert search == [], 'search is a third door and is filtered too'
		exp = (await c.get('/records/teen-1/export', params={'fmt': 'json'}, headers=h)).json()
		assert exp['document_count'] == 1 and exp['withheld_count'] == 2, exp['withheld_count']
		# The unfiltered set still exists behind the filter, so the protection is a rule about who
		# reads rather than a deletion — and the guardian's refusal is not the record being gone.
		# Asked for by omitting `reader`, which is the same argument the route passes: if this ever
		# returned 1, the filter would have become a deletion.
		records: RecordsService = svc['records']  # type: ignore[assignment]
		assert len(records.documents('teen-1')) == 3
