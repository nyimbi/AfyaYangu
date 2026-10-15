"""§9.2 REC-001 and §10.1 REC-002 — the wallet as documents, and the operations over them.

Both sections describe the same set of eight documents and then a list of things to do with them.
The defect this file guards against is the one that had six features marked missing: the documents
existed as five unrelated row types and nothing could search them, order them, export them or share
them, because there was no set to operate on.

Three of these tests are about mechanisms that are easy to write and easy to fake: the PDF must be a
PDF, the share must actually stop at its expiry, and the certificate's seal must actually verify.
Each has a canary that points the same check at a known-bad input, so a check that passes because it
is not checking anything fails here instead.
"""
import re
from datetime import date

import httpx
import pytest

from afya.records.pdf import render
from afya.records.service import RecordsService, _parse_iso
from afya.records.views import (
	ShareGrant, WALLET_DOC_KINDS, WalletDocument, WalletMember,
)


def _svc() -> RecordsService:
	return RecordsService()


async def _family() -> RecordsService:
	svc = _svc()
	await svc.add_member(WalletMember(member_ref='G1', dob_iso='1990-01-01'))
	await svc.add_member(WalletMember(member_ref='K1', dob_iso='2020-01-01', guardian_ref='G1'))
	return svc


def _doc(doc_id: str, member: str = 'G1', **kw: object) -> WalletDocument:
	base: dict[str, object] = {
		'doc_id': doc_id, 'member_ref': member, 'kind': 'lab', 'title': 'Malaria test',
		'occurred_iso': '2026-09-01',
	}
	base.update(kw)
	return WalletDocument(**base)  # type: ignore[arg-type]


# --- the envelope is §9.2's eight kinds, and the section's own list ---------------------------

def test_the_eight_kinds_are_the_sections_eight_contents() -> None:
	"""The envelope's kind set is §9.2's "Contents:" list, in the section's order.

	Read off the spec rather than transcribed, so a revision that adds a ninth document fails here
	rather than leaving the wallet silently unable to hold it — and the order is asserted because the
	tuple is documented as the section's order, which a set comparison would not check.
	"""
	from pathlib import Path
	text = (Path(__file__).resolve().parents[2] / 'docs' / 'spec.md').read_text(encoding='utf-8')
	section = text.split('#### REC-001: Family Health Wallet (Basic)', 1)[1].split('**Features:**', 1)[0]
	bullets = [ln[2:].strip() for ln in section.split('**Contents:**', 1)[1].splitlines()
	           if ln.startswith('- ')]
	assert len(bullets) == 8, f'the section names eight contents, found {bullets}'
	assert len(WALLET_DOC_KINDS) == 8, WALLET_DOC_KINDS
	# Each kind names one bullet's document. The pairing is by word rather than by index, because an
	# index comparison would pass while the two lists drifted apart in meaning.
	joined = ' '.join(bullets).lower()
	for kind in WALLET_DOC_KINDS:
		assert kind in joined, f'the kind {kind!r} names no §9.2 content'


async def test_a_document_is_filed_once_and_never_replaced() -> None:
	"""A wallet exists so a lost document is not lost; a silent overwrite is the opposite."""
	svc = await _family()
	await svc.add_document(_doc('d1'))
	with pytest.raises(AssertionError, match='already filed'):
		await svc.add_document(_doc('d1', title='A different result'))
	assert len(svc.documents('G1')) == 1


async def test_a_document_cannot_be_filed_for_a_stranger() -> None:
	"""The envelope names its member, and a member outside every wallet is not a member."""
	svc = await _family()
	with pytest.raises(AssertionError, match='not in any wallet'):
		await svc.add_document(_doc('d1', member='STRANGER'))


# --- the four operations over the set ----------------------------------------------------------

async def test_the_timeline_is_a_sort_over_the_documents_not_a_second_store() -> None:
	"""§10.1's "Timeline view of all health events", newest first, naming who each event is about.

	The canary below is the reason this is a sort: an event log written on each filing path would
	drift from the wallet the first time a path forgot, and the timeline would be missing a document
	the wallet holds while both looked correct.
	"""
	svc = await _family()
	await svc.add_document(_doc('older', occurred_iso='2026-01-01'))
	await svc.add_document(_doc('newer', occurred_iso='2026-09-01'))
	await svc.add_document(_doc('kid', member='K1', occurred_iso='2026-05-01', title='Child visit'))
	timeline = svc.timeline('G1')
	assert [e.doc_id for e in timeline] == ['newer', 'kid', 'older'], 'newest first, across the family'
	assert {e.who for e in timeline} == {'G1', 'K1'}, 'a family timeline names the person'
	# Every document in the wallet appears, which is the property a second store would break.
	assert {e.doc_id for e in timeline} == {d.doc_id for d in svc.documents('G1')} | {'kid'}


async def test_the_timeline_drops_a_member_who_has_turned_eighteen() -> None:
	"""§17.6: control transfers at 18, so the guardian's timeline stops including them.

	The timeline asks `owns` per member rather than once for the wallet, which is what makes the
	transfer date real here and not only on the record routes. The member is enrolled on their
	seventeenth birthday — an adult cannot be enrolled as someone's dependent, which is the other
	half of §17.6 — and then read forward past their eighteenth.
	"""
	svc = _svc()
	await svc.add_member(WalletMember(member_ref='G1', dob_iso='1990-01-01'), today=date(2025, 6, 1))
	await svc.add_member(WalletMember(member_ref='ADULT', dob_iso='2008-06-01', guardian_ref='G1'),
	                     today=date(2025, 6, 1))
	await svc.add_document(_doc('a1', member='ADULT'))
	assert 'a1' in {e.doc_id for e in svc.timeline('G1', date(2026, 5, 1))}, 'still 17 in May'
	assert 'a1' not in {e.doc_id for e in svc.timeline('G1', date(2026, 7, 1))}, '18 in July'


async def test_search_reads_the_words_a_person_remembers() -> None:
	"""§REC-001's "Search": the word on the card, not the field it was filed under.

	Searched across the whole wallet, because the question a person brings is "where is that card",
	not "where is that card for this child".
	"""
	svc = await _family()
	await svc.add_document(_doc('d1', title='Malaria test', detail='positive, given coartem'))
	await svc.add_document(_doc('d2', member='K1', kind='immunisation', title='BCG dose 1'))
	assert [d.doc_id for d in svc.search('G1', 'COARTEM')] == ['d1'], 'case-insensitive, in the detail'
	assert [d.doc_id for d in svc.search('G1', 'bcg')] == ['d2'], "a child's document is in the wallet"
	assert [d.doc_id for d in svc.search('G1', 'immunisation')] == ['d2'], 'the kind is searchable'
	assert svc.search('G1', 'nothing-matches-this') == []
	with pytest.raises(AssertionError, match='empty search'):
		svc.search('G1', '   ')


async def test_search_does_not_reach_outside_the_wallet() -> None:
	"""The gate on search is `owns`, the same rule every family route binds to."""
	svc = await _family()
	await svc.add_member(WalletMember(member_ref='OTHER', dob_iso='1990-01-01'))
	await svc.add_document(_doc('mine', member='G1', title='my result'))
	await svc.add_document(_doc('theirs', member='OTHER', title='their result'))
	assert [d.doc_id for d in svc.search('G1', 'result')] == ['mine']
	assert [d.doc_id for d in svc.search('OTHER', 'result')] == ['theirs']


# --- the PDF is a PDF ---------------------------------------------------------------------------

def _xref_offsets_that_miss(pdf: bytes) -> list[int]:
	"""Objects whose xref entry does not point at the object it names.

	The one comparison the PDF test and its canary both run, so the canary exercises the check that
	ships rather than a copy of it: a canary against a re-implementation passes while the real check
	rots. Entry 0 is the free-list head and carries no object, so object N's row is at index 2 + N.
	"""
	start = int(re.search(rb'startxref\s+(\d+)', pdf).group(1))  # type: ignore[union-attr]
	assert pdf[start:start + 4] == b'xref', 'startxref must point at the xref table'
	table = pdf[start:].split(b'\n')
	count = int(table[1].split()[1])
	assert table[2].endswith(b'f '), 'entry 0 is the free-list head, not an object'
	miss: list[int] = []
	for obj_id in range(1, count):
		offset = int(table[2 + obj_id].split()[0])
		if not pdf[offset:].startswith(f'{obj_id} 0 obj'.encode()):
			miss.append(obj_id)
	return miss


def test_the_export_is_a_real_pdf() -> None:
	"""§REC-001's "PDF export". The bytes must be a PDF, not a `.pdf` filename on JSON.

	Checked structurally rather than by eye: the header, the trailer, and — the part that is easy to
	get wrong — a cross-reference table whose offsets actually land on the objects they claim.
	"""
	pdf = render('Health record', ['A line', 'Another line'])
	assert pdf.startswith(b'%PDF-1.4'), 'the header is what makes it a PDF'
	assert pdf.rstrip().endswith(b'%%EOF'), 'the trailer is what makes a reader accept it'
	assert _xref_offsets_that_miss(pdf) == [], 'every xref offset must land on its object'


def test_the_pdf_escapes_a_parenthesis_in_a_title() -> None:
	"""A `(` closes a PDF string literal early, and the file then opens to garbage.

	A clinic note saying "(review)" is not a contrived input; it is the shape of the defect.

	The last assertion is the weak half of the pair and is kept weak on purpose: it says the
	character must not reach the stream *raw*, which the mangling also satisfies. The strong half —
	that the character must still be there, in the encoding the font declares — is
	`test_the_pdf_keeps_the_punctuation_helvetica_can_draw`, which is the test this one was mistaken
	for.
	"""
	pdf = render('Record', ['Seen at (review) clinic', r'back\slash', 'name: O’Brien'])
	assert b'\\(review\\)' in pdf, 'an unescaped parenthesis terminates the literal'
	assert rb'back\\slash' in pdf, 'a backslash must be escaped, and escaped first'
	assert b'\xe2' not in pdf, 'a character Helvetica cannot draw must not reach the stream raw'


def test_the_pdf_keeps_the_punctuation_helvetica_can_draw() -> None:
	"""A base-14 font with no `/Encoding` is read as StandardEncoding, under which every byte from
	0x80 up is undefined — so the em dash and the typographic apostrophe this tree writes drew as
	garbage while `escape` reported success, because `ord(c) < 256` is a Latin-1 test and the font
	draws cp1252.

	The export's own heading is the input that makes it bite: `RecordsService.export` renders
	`f'Health record — {who}'`, so **every** PDF the wallet produced read `Health record ? Achieng`,
	and a name carrying O’Brien lost its apostrophe. Both halves are asserted because either alone
	passes a broken writer: the bytes must be the cp1252 codes, and the font must declare the
	encoding that gives those codes glyphs.
	"""
	pdf = render('Health record — Achieng O’Brien', ['Exported'])
	assert b'/Encoding /WinAnsiEncoding' in pdf, (
		'without the encoding a reader treats 0x80-0xFF as undefined and the punctuation vanishes'
	)
	assert b'(Health record \x97 Achieng O\x92Brien) Tj' in pdf, (
		'the em dash is 0x97 and the typographic apostrophe 0x92 under WinAnsiEncoding'
	)
	assert b'?' not in pdf, 'a character the font can draw must not be replaced by a question mark'


def test_the_pdf_marks_a_character_the_font_cannot_draw() -> None:
	"""The other direction, and the one the weak assertion cannot see: a character cp1252 has no
	glyph for must leave a mark where it was.

	Dropping it produces a certificate that reads cleanly and is wrong — `escape`'s own docstring
	argues the point, that a name in a script this font cannot draw should be visibly unrenderable
	rather than silently absent from a certificate. The distinction is invisible to a test that only
	checks the raw UTF-8 byte did not reach the stream, because both a `?` and a deletion satisfy it.
	"""
	pdf = render('Record', ['name: 山田太郎', 'also: Ω'])
	assert b'(name: ????) Tj' in pdf, (
		'each character with no cp1252 glyph becomes one `?`, so the mark is one per character and '
		'not one per UTF-8 byte — four characters, four marks'
	)
	assert b'(also: ?) Tj' in pdf, 'a Greek capital omega is not in cp1252 either'
	assert b'\xe5\xb1\xb1' not in pdf, 'the UTF-8 bytes must not reach the stream raw'
	assert b'\xce\xa9' not in pdf, 'the UTF-8 bytes must not reach the stream raw'


def test_the_pdf_paginates_a_long_record() -> None:
	"""A wallet with more documents than fit on a page must produce more than one page."""
	one = render('Record', [f'line {i}' for i in range(10)])
	many = render('Record', [f'line {i}' for i in range(200)])
	assert many.count(b'/Type /Page\n') + many.count(b'/Type /Page ') > 1, 'a long record is one page'
	assert many.count(b'/Type /Pages') == 1, 'exactly one page tree'
	assert len(many) > len(one)


def test_the_canary_catches_an_xref_offset_that_does_not_land() -> None:
	"""Canary. The xref check must fail on a table whose offsets are wrong.

	The patch shifts object 1's offset by one byte, which is exactly the defect of assembling the
	file in two passes: the table is written from lengths that no longer describe the bytes on disk.
	The shipped check (`_xref_offsets_that_miss`) is re-run over the patched bytes, so this proves
	the check rather than a copy of it — a canary against a re-implementation passes while the real
	one rots, which is the failure this test exists to not be.
	"""
	pdf = render('Health record', ['A line'])
	start = int(re.search(rb'startxref\s+(\d+)', pdf).group(1))  # type: ignore[union-attr]
	table = pdf[start:].split(b'\n')
	count = int(table[1].split()[1])
	assert count >= 2, 'the fixture must have an object to move'
	assert _xref_offsets_that_miss(pdf) == [], 'the real table must land first'

	row = table[3]  # object 1's entry
	good = int(row.split()[0])
	patched = pdf[:start] + pdf[start:].replace(
		row, row.replace(f'{good:010d}'.encode(), f'{good + 1:010d}'.encode(), 1), 1)
	assert patched != pdf, 'the canary patch did not apply, so nothing was tested'
	assert _xref_offsets_that_miss(patched) == [1], (
		'the check is blind to an xref offset that does not land on its object'
	)


# --- sharing is one grant with a mandatory expiry -----------------------------------------------

def _grant(**kw: object) -> ShareGrant:
	base: dict[str, object] = {
		'grant_id': 'SH1', 'member_ref': 'G1', 'issued_iso': '2026-10-01T08:00:00',
		'expires_iso': '2026-10-08T08:00:00', 'issued_by': 'G1',
	}
	base.update(kw)
	return ShareGrant(**base)  # type: ignore[arg-type]


async def test_the_provider_view_stops_at_the_expiry() -> None:
	"""§10.1's "limited time" is the feature; the expiry field is not.

	A share whose reader is not actually stopped at the limit is an unlimited share with a date on
	it, and the date is the part that gets tested while the limit is the part that matters.
	"""
	svc = await _family()
	await svc.add_document(_doc('d1', title='Discharge summary', kind='discharge'))
	await svc.grant_share(_grant(recipient='KNH', kinds=['discharge']))
	view = svc.share_view('SH1', '2026-10-05T00:00:00')
	assert [d.doc_id for d in view.documents] == ['d1']
	assert view.recipient == 'KNH' and view.expires_iso == '2026-10-08T08:00:00'
	with pytest.raises(AssertionError, match='this share ended'):
		svc.share_view('SH1', '2026-10-09T00:00:00')
	# The boundary is inclusive: a share ending at 08:00 is readable at 08:00.
	assert svc.share_view('SH1', '2026-10-08T08:00:00').documents


async def test_the_share_scope_narrows_what_the_provider_sees() -> None:
	"""§10.1's provider share names what they may read; the REC-001 link shares everything."""
	svc = await _family()
	await svc.add_document(_doc('discharge', kind='discharge', title='Discharged'))
	await svc.add_document(_doc('lab', kind='lab', title='Malaria test'))
	await svc.grant_share(_grant(grant_id='NARROW', kinds=['discharge']))
	await svc.grant_share(_grant(grant_id='WIDE'))
	assert [d.doc_id for d in svc.share_view('NARROW', '2026-10-05T00:00:00').documents] == ['discharge']
	assert {d.doc_id for d in svc.share_view('WIDE', '2026-10-05T00:00:00').documents} == {'discharge', 'lab'}


async def test_a_share_that_ends_before_it_starts_is_refused() -> None:
	"""An expired-at-issue grant is a share that never was one."""
	svc = await _family()
	with pytest.raises(AssertionError, match='must end after it begins'):
		await svc.grant_share(_grant(expires_iso='2026-09-01T08:00:00'))
	with pytest.raises(AssertionError, match='must end after it begins'):
		await svc.grant_share(_grant(expires_iso='2026-10-01T08:00:00'))


async def test_a_revoked_share_is_refused_and_stays_in_the_record() -> None:
	"""§17.1's withdrawal: consent that cannot be taken back is not consent.

	The grant stays in the list after revocation, because "who has seen my record" is a question
	about the past and a list that dropped the dead grants would answer with the wrong tense.
	"""
	svc = await _family()
	await svc.add_document(_doc('d1'))
	await svc.grant_share(_grant())
	await svc.revoke_share('SH1')
	with pytest.raises(AssertionError, match='withdrawn'):
		svc.share_view('SH1', '2026-10-05T00:00:00')
	history = svc.grants_for('G1')
	assert len(history) == 1 and history[0].revoked is True


def test_a_bare_date_and_a_timestamp_compare_as_the_same_day() -> None:
	"""The comparison that makes the expiry real, checked at the boundary it is easy to get wrong.

	Comparing `2026-10-08` and `2026-10-08T08:00:00` as strings puts the expiry at midnight, which
	is *before* an issue time the same morning — so a share issued at 8am for one day would be
	refused at issue. `_parse_iso` normalises both to a timezone-aware datetime.
	"""
	assert _parse_iso('2026-10-08') < _parse_iso('2026-10-08T08:00:00')
	assert _parse_iso('2026-10-08T08:00:00Z') == _parse_iso('2026-10-08T08:00:00+00:00')
	with pytest.raises(AssertionError):
		_parse_iso('last Tuesday')


# --- the certificate is a view, and its seal verifies -------------------------------------------

async def test_the_certificate_is_rendered_from_the_dose_log() -> None:
	"""A certificate keeping its own copy could disagree with the record it certifies."""
	from afya.records.views import ImmunisationRecord
	svc = await _family()
	await svc.record_immunisation(ImmunisationRecord(member_ref='K1', vaccine='BCG', dose_no=1,
	                                                 given_iso='2020-02-01'))
	await svc.record_immunisation(ImmunisationRecord(member_ref='K1', vaccine='MMR', dose_no=1,
	                                                 given_iso='2021-01-01', batch='B7'))
	cert = svc.vaccination_certificate('G1', 'K1', 'travel', '2026-10-12T09:00:00', 'secret')
	assert [d['vaccine'] for d in cert.doses] == ['BCG', 'MMR'], 'in the order they were given'
	assert cert.doses[1]['batch'] == 'B7'
	assert cert.purpose == 'travel' and cert.holder_name == 'K1'
	# And the seal verifies against the same fields, so it is a mechanism and not a printed string.
	assert svc.certificate_seal_holds(cert, 'secret')
	assert not svc.certificate_seal_holds(cert, 'a-different-secret')


async def test_the_canary_catches_a_certificate_whose_fields_were_changed() -> None:
	"""Canary. Change a dose and the seal must stop verifying.

	A seal that verified regardless would be a hex digest printed at the bottom of a page, which is
	exactly what an unverified HMAC is. The check is re-run on the tampered certificate.
	"""
	from afya.records.views import ImmunisationRecord
	svc = await _family()
	await svc.record_immunisation(ImmunisationRecord(member_ref='K1', vaccine='BCG', dose_no=1,
	                                                 given_iso='2020-02-01'))
	cert = svc.vaccination_certificate('G1', 'K1', 'school', '2026-10-12T09:00:00', 'secret')
	assert svc.certificate_seal_holds(cert, 'secret'), 'the real certificate must verify first'
	patched = cert.model_copy(update={'doses': [{**cert.doses[0], 'given_iso': '2020-02-02'}]})
	assert not svc.certificate_seal_holds(patched, 'secret'), (
		'the seal is blind to a changed dose, so it attests to nothing'
	)


# --- growth: the WHO standard rather than a band -------------------------------------------------

def test_the_growth_zscore_reproduces_the_published_sd_columns() -> None:
	"""§REC-003's "percentile charts" rest on the z-score, so it is checked against WHO's own table.

	The published `-2 SD` column for a 12-month boy is 7.7 kg. The exact value from the LMS
	parameters is 7.7422, and the z of the *rounded* figure is -2.049 — which is the point: the
	printed columns are rounded to one decimal, a 0.042 kg difference that is 0.5% of the child's
	weight and enough to move a classification across its boundary. The implementation uses the
	parameters, so it agrees with the printed column to within that rounding and no more.
	"""
	from afya.records.growth import weight_z
	assert weight_z('boy', 12, 9.6479) == pytest.approx(0.0, abs=1e-9), 'the median is z=0'
	assert weight_z('boy', 12, 7.7) == pytest.approx(-2.0, abs=0.06), "WHO's printed -2 SD column"
	assert weight_z('boy', 12, 6.9) == pytest.approx(-3.0, abs=0.06), "WHO's printed -3 SD column"
	# Symmetry: the median is the median for girls too, at a different weight.
	assert weight_z('girl', 12, 8.9481) == pytest.approx(0.0, abs=1e-9)


def test_a_boy_and_a_girl_at_the_same_weight_are_not_the_same_child() -> None:
	"""The standards are tabulated by sex; a chart from the wrong column is wrong by more than the
	deficit it reports. At 12 months the girl's median is 1.2 kg below the boy's."""
	from afya.records.growth import weight_z
	boy = weight_z('boy', 12, 8.9)
	girl = weight_z('girl', 12, 8.9)
	assert girl > boy, 'the same weight is closer to the median for a girl at 12 months'
	assert abs(girl - boy) > 0.5, f'the two columns differ by less than expected: {girl - boy}'


def test_an_age_outside_the_standard_is_refused_rather_than_extrapolated() -> None:
	"""Past 60 months the WHO reference is the 5-19 year publication, which is not held here.

	Measuring a six-year-old against an infant standard would call them enormous, which is a wrong
	answer rather than a missing one.
	"""
	from afya.records.growth import height_z
	with pytest.raises(AssertionError, match='outside 0-60'):
		height_z('boy', 72, 120.0)


def test_the_chart_lines_are_the_same_function_read_backwards() -> None:
	"""The reference line a point is plotted against and the z reported for it cannot disagree.

	Both come from the LMS parameters — `zscore` forward and `_value_at` inverse — so a chart drawn
	from one and a verdict computed from the other would agree by construction. This asserts the
	round trip, which is what makes that true rather than intended.
	"""
	from afya.records.growth import _value_at, weight_z
	from afya.records.growth_standards import WEIGHT_FOR_AGE
	for month in (0, 6, 12, 24, 60):
		l, m, s = next(r[1:] for r in WEIGHT_FOR_AGE['boy'] if r[0] == month)
		for z in (-3.0, -2.0, 0.0, 2.0):
			value = _value_at(z, l, m, s)
			assert weight_z('boy', month, value) == pytest.approx(z, abs=1e-9), (
				f'month {month}, z {z}: the inverse does not round-trip'
			)


def test_the_reference_lines_span_the_whole_standard() -> None:
	"""A chart missing the months it covers is a chart with a gap where the child is."""
	from afya.records.growth import height_reference, weight_reference
	assert [r['month'] for r in weight_reference('boy')] == list(range(61))
	# Height joins the two WHO tables at 24 months: 0-24 recumbent plus 24-60 standing.
	months = [r['month'] for r in height_reference('girl')]
	assert months == list(range(61)), f'height reference has {len(months)} months, not 61'
	for row in weight_reference('girl'):
		assert row['minus_3'] < row['minus_2'] < row['median'] < row['plus_2'], row


async def test_growth_is_recorded_and_charted_over_time() -> None:
	"""A chart needs a series; one reading is a number with nothing to plot it against."""
	from afya.records.views import GrowthRecord
	svc = await _family()
	await svc.record_growth(GrowthRecord(member_ref='K1', age_months=12, weight_kg=9.6,
	                                     height_cm=74.8, sex='boy'))
	await svc.record_growth(GrowthRecord(member_ref='K1', age_months=15, weight_kg=10.4,
	                                     height_cm=78.0, sex='boy'))
	chart = svc.growth_chart('K1', 'boy')
	assert [p['month'] for p in chart.weight_points] == [12, 15]
	assert len(chart.weight_reference) == 61 and len(chart.height_reference) == 61


async def test_the_band_and_the_standard_disagree_where_the_band_was_wrong() -> None:
	"""The old band called a child `normal` whom WHO calls undernourished.

	At 12 months the band's low bound was `7.0 * 0.75 = 5.25`, so a boy weighing 7.7 kg — exactly
	WHO's -2 SD, the threshold at which §REC-003's alert should fire — was reported as normal. This
	is the defect the section's "undernutrition alerts" names, and the assertion is that the new
	verdict is the WHO one.
	"""
	from afya.records.views import GrowthRecord
	svc = await _family()
	assessment = svc.assess_growth(GrowthRecord(member_ref='K1', age_months=12, weight_kg=7.7,
	                                            height_cm=74.8, sex='boy'))
	assert assessment.weight_status == 'moderate', (
		f'7.7 kg at 12 months is WHO -2 SD; the assessment says {assessment.weight_status}'
	)
	assert svc.growth_flag(GrowthRecord(member_ref='K1', age_months=12, weight_kg=7.7,
	                                    height_cm=74.8, sex='boy')).flag == 'underweight'


# --- backup is consent-gated, and states its own cipher -----------------------------------------

async def test_the_backup_refuses_without_consent_and_reports_its_own_cipher() -> None:
	"""§REC-001's "Optional encrypted cloud backup": the consent is the gate, and the cipher is a fact.

	`retention.encryption_posture()` asserts `cloud_backup_e2e=True` and `user_held_key=True` as
	design properties. This deployment holds no key it does not also hold the data with, so the
	envelope says `none`/False rather than inheriting the claim — a service that cannot implement
	end-to-end encryption must not report that it has.
	"""
	svc = await _family()
	await svc.add_document(_doc('d1'))
	with pytest.raises(AssertionError, match='needs the cloud backup consent'):
		await svc.backup('G1', 'G1', '2026-10-12T09:00:00', consented=False)
	envelope = await svc.backup('G1', 'G1', '2026-10-12T09:00:00', consented=True)
	assert envelope.document_count == 1 and envelope.member_count == 1
	assert envelope.cipher == 'none' and envelope.user_held_key is False
	assert envelope.consent_category == 'cloud_backup'
	assert len(envelope.digest_sha256) == 64, 'the digest is a sha256'


async def test_a_passphrase_makes_the_backup_end_to_end() -> None:
	"""§SEC-003's "Cloud backup: end-to-end encrypted with user-held key", which was `missing`.

	The finding was that the envelope reported `none`/False and the posture asserted `True` — a
	claim and its denial in the same tree. With a passphrase the backup is genuinely end-to-end:
	the wallet is sealed under a key derived from it, the plaintext does not come back, and the
	key is never stored. Without one the envelope still reports `none`, so the two are
	distinguishable rather than both claiming the standard.
	"""
	from afya.crypto.service import CryptoService, new_key
	svc = await _family()
	await svc.add_document(_doc('d1'))
	crypto = CryptoService(new_key(), new_key())
	envelope = await svc.backup('G1', 'G1', '2026-10-13T09:00:00', consented=True,
		passphrase='a-long-enough-passphrase', crypto=crypto)
	assert envelope.cipher == 'aes-256-gcm' and envelope.user_held_key is True
	assert envelope.sealed is not None
	assert envelope.documents == [], 'the plaintext must not ship beside its own ciphertext'
	assert 'Malaria test' not in envelope.sealed, 'the title is not in the clear'
	assert envelope.open_hint and 'never sent to us' in envelope.open_hint

	from afya.crypto.service import Sealed
	sealed = Sealed.from_blob(envelope.sealed)
	assert crypto.open_for_user(sealed, 'a-long-enough-passphrase').decode().find('Malaria') > 0
	with pytest.raises(Exception):
		crypto.open_for_user(sealed, 'the-wrong-passphrase')


async def test_a_passphrase_with_no_crypto_service_is_refused_not_ignored() -> None:
	"""The dangerous fallback: a caller asks for encryption, the service has no key, and the
	wallet comes back in the clear under an end-to-end label."""
	svc = await _family()
	await svc.add_document(_doc('d1'))
	with pytest.raises(AssertionError, match='no crypto service'):
		await svc.backup('G1', 'G1', '2026-10-13T09:00:00', consented=True,
			passphrase='a-long-enough-passphrase', crypto=None)


# --- and the routes, as a client reaches them ---------------------------------------------------

async def _client() -> tuple[httpx.AsyncClient, object]:
	from afya.service import build_services, create_app
	services = build_services()
	app = create_app(services)
	return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t'), services


async def test_the_wallet_routes_as_a_client_reaches_them() -> None:
	"""The whole surface through HTTP, with a real token and a real family."""
	from afya.privacy.views import ConsentCategory, ConsentRecord, LegalBasis
	client, services = await _client()
	async with client:
		tok = (await client.post('/auth/anonymous', json={'subject_ref': 'G1'})).json()['token']
		h = {'authorization': f'Bearer {tok}'}
		me = 'G1'
		# A guardian and their child.
		assert (await client.post('/records/member', headers=h, json={
			'member_ref': me, 'dob_iso': '1990-01-01'})).status_code == 200
		child = 'K1'
		assert (await client.post('/records/member', headers=h, json={
			'member_ref': child, 'dob_iso': '2020-01-01', 'guardian_ref': me})).status_code == 200
		# File a document and read the wallet back.
		filed = await client.post('/records/documents', headers=h, json={
			'doc_id': 'doc-1', 'member_ref': me, 'kind': 'discharge',
			'title': 'Discharged after malaria', 'occurred_iso': '2026-09-14',
			'detail': 'Given coartem, review in 7 days', 'media_ref': 'evidence/abc.jpg',
			'captured_iso': '2026-09-14T10:00:00'})
		assert filed.status_code == 200, filed.text
		listed = (await client.get(f'/records/{me}/documents', headers=h)).json()
		assert [d['doc_id'] for d in listed] == ['doc-1']
		assert listed[0]['media_ref'] == 'evidence/abc.jpg', 'the photo reference survives'
		# Timeline and search.
		timeline = (await client.get('/records/timeline', headers=h)).json()
		assert any(e['doc_id'] == 'doc-1' for e in timeline)
		assert [d['doc_id'] for d in (await client.get('/records/search?q=coartem', headers=h)).json()] == ['doc-1']
		# Export: a real PDF, served as one.
		export = (await client.get(f'/records/{me}/export?fmt=pdf', headers=h)).json()
		assert export['media_type'] == 'application/pdf'
		assert export['content'].startswith('%PDF-1.4')
		assert (await client.get(f'/records/{me}/export?fmt=json', headers=h)).json()['media_type'] == 'application/json'
		# A share, then the provider view through the clinician scope.
		share = await client.post('/records/share', headers=h, json={
			'grant_id': 'sh-1', 'member_ref': me, 'recipient': 'KNH',
			'kinds': ['discharge'], 'issued_iso': '2026-10-01T08:00:00',
			'expires_iso': '2026-10-08T08:00:00'})
		assert share.status_code == 200, share.text
		# The clinician's token comes from the app flow, because `consented_patient` is a role the
		# app issues and not one an operator provisions.
		import secrets

		from afya.auth.views import s256
		verifier = secrets.token_urlsafe(64)[:64]
		authz = (await client.post('/auth/pkce/authorize', json={
			'client_id': 'app', 'redirect_uri': 'afya://cb',
			'code_challenge': s256(verifier), 'state': 'state-1234'})).json()
		clinician = (await client.post('/auth/pkce/token', params={'role': 'clinician'}, json={
			'authorization_code': authz['authorization_code'], 'client_id': 'app',
			'redirect_uri': 'afya://cb', 'code_verifier': verifier})).json()['access_token']
		ch = {'authorization': f'Bearer {clinician}'}
		view = await client.get('/records/share/sh-1/view?at_iso=2026-10-05T00:00:00', headers=ch)
		assert view.status_code == 200, view.text
		assert [d['doc_id'] for d in view.json()['documents']] == ['doc-1']
		# Past the expiry it is refused, and the clinician scope is what makes the route reachable.
		assert (await client.get('/records/share/sh-1/view?at_iso=2026-10-09T00:00:00',
		                         headers=ch)).status_code == 403
		# A citizen token cannot read another person's shared record.
		assert (await client.get('/records/share/sh-1/view?at_iso=2026-10-05T00:00:00',
		                         headers=h)).status_code == 403
		# Nor switch off a share they are not party to. A stranger's revoke must not withdraw it,
		# which is the difference between a withdrawal and a denial of care with §17.1 on it.
		other = (await client.post('/auth/anonymous', json={'subject_ref': 'STRANGER'})).json()['token']
		oh = {'authorization': f'Bearer {other}'}
		assert (await client.post('/records/share/sh-1/revoke', headers=oh)).status_code == 404
		assert (await client.get('/records/share/sh-1/view?at_iso=2026-10-05T00:00:00',
		                         headers=ch)).status_code == 200, 'the share survived a stranger'
		# The issuer can, and then the clinician is refused.
		assert (await client.post('/records/share/sh-1/revoke', headers=h)).status_code == 200
		assert (await client.get('/records/share/sh-1/view?at_iso=2026-10-05T00:00:00',
		                         headers=ch)).status_code == 403
		# The consent gate on backup, through the privacy service rather than a request field.
		assert (await client.post(f'/records/{me}/backup', headers=h,
		                          json={})).status_code == 403
		await services['privacy'].record_consent(ConsentRecord(  # type: ignore[attr-defined]
			consent_id='c1', subject_ref=me, purpose=ConsentCategory.cloud_backup.value,
			data_types=[ConsentCategory.cloud_backup.value], retention_days=365,
			legal_basis=LegalBasis.consent))
		backup = await client.post(f'/records/{me}/backup', headers=h, json={})
		assert backup.status_code == 200, backup.text
		assert backup.json()['cipher'] == 'none'


async def test_the_growth_chart_route_serves_the_reference_lines() -> None:
	client, _ = await _client()
	async with client:
		tok = (await client.post('/auth/anonymous', json={'subject_ref': 'G1'})).json()['token']
		h = {'authorization': f'Bearer {tok}'}
		me = 'G1'
		await client.post('/records/member', headers=h, json={'member_ref': me, 'dob_iso': '1990-01-01'})
		body = (await client.get(f'/records/{me}/growth-chart?sex=girl', headers=h)).json()
		assert len(body['weight_reference']) == 61
		assert len(body['height_reference']) == 61, 'the two WHO tables must not both answer for 24'
		assert body['sex'] == 'girl'


async def test_the_vaccination_certificate_route_seals_the_doses() -> None:
	client, _ = await _client()
	async with client:
		tok = (await client.post('/auth/anonymous', json={'subject_ref': 'G1'})).json()['token']
		h = {'authorization': f'Bearer {tok}'}
		me = 'G1'
		await client.post('/records/member', headers=h, json={'member_ref': me, 'dob_iso': '1990-01-01'})
		cert = (await client.get(
			f'/records/{me}/vaccination-certificate?purpose=school&at_iso=2026-10-12T09:00:00',
			headers=h)).json()
		assert cert['purpose'] == 'school'
		assert 'Ministry of Health signature' in cert['issuer'], (
			'the certificate must say what its seal is not'
		)
		assert len(cert['signature']) == 64
		# The seal verifies against the deployment secret the route used.
		from afya.config import ServiceConfig
		from afya.records.service import RecordsService
		from afya.records.views import VaccinationCertificate
		secret = ServiceConfig.from_env().webhook_secret or 'afya-dev-seal'
		assert RecordsService().certificate_seal_holds(
			VaccinationCertificate(**cert), secret), 'the served certificate must verify'


def test_every_route_that_serves_a_member_says_who_is_reading() -> None:
	"""§17.6's last line is enforced by an argument, and an argument is a thing a new route forgets.

	`documents()` and `labs()` take a *member* first, so nothing in the call itself says who is
	reading and the filter is opt-in — a route added tomorrow that calls `records.documents(ref)`
	serves an adolescent's contraceptive record to her guardian and every existing test still
	passes. This is the "control that exists is not a control that is applied" class the repo keeps
	meeting, and the fix is the same one `check_product_sync` and `undocumented_access` use: read
	the source, so the gate moves with the code rather than with a list someone maintains.

	The jurisdiction is exactly these two functions. `timeline`, `search`, `export` and `backup`
	take the *subject* first and apply the filter inside themselves, so their call sites are safe by
	construction — which is why they are not asserted here. A gate scoped wider than its
	jurisdiction fails for reasons its operator cannot act on, and the pressure that creates is to
	disable it.
	"""
	from pathlib import Path
	src = (Path(__file__).resolve().parents[2] / 'src' / 'afya' / 'service.py').read_text(encoding='utf-8')
	serving = [m for m in re.finditer(r'records\.(documents|labs)\(', src)]
	assert len(serving) == 2, f'expected the two member-first readers, found {len(serving)}'
	for m in serving:
		# The whole call, so a `reader=` in a later expression cannot be mistaken for this one's.
		call = src[m.start():src.index(')', m.start()) + 1]
		assert 'reader=' in call, f'{call} serves a member without saying who is reading'
	# And the reader must be the authenticated subject, not a value off the request body — the
	# protection is against the caller, so a reader the caller supplies is the caller's own claim.
	for m in serving:
		call = src[m.start():src.index(')', m.start()) + 1]
		assert 'reader=_subject' in call, call
