"""§INF-006's directory: the eight Contents, and the four Features rendered as URIs.

The section asks for "a single screen with all relevant contacts" and then prints eight of them and
four things a person can do with each. What existed was two rows of a table served as text, so the
audit recorded the section as carrying one of eight and none of the four. These tests are about the
two claims the section makes: that the screen is *complete or says what it lacks*, and that each row
is *actionable*.
"""
import httpx
import pytest

from afya.info.service import HOTLINES, InfoService, _dialable
from afya.info.views import SPEC_CONTENTS, ContactDirectory, ContactKind, HotlineActions, HotlineInfo
from afya.places.views import Place, PlaceKind, PlacesService


def test_the_section_names_eight_contents_and_the_enum_covers_them() -> None:
	"""§INF-006's Contents sentence, in the section's order. `SPEC_CONTENTS` is the eight; the enum
	carries two more because a deployment has a complaints desk the section does not name and NACADA's
	number is a substance-abuse line. The distinction is what makes `complete` answerable."""
	assert len(SPEC_CONTENTS) == 8, 'the section prints eight Contents'
	assert ContactKind.complaints_desk not in SPEC_CONTENTS, 'the desk is a row, not a Content'
	assert ContactKind.substance_abuse_helpline not in SPEC_CONTENTS, 'NACADA is not one of the eight'


def test_the_directory_lists_the_numbers_the_tree_already_held() -> None:
	"""The finding this closes: `mental.COUNSELLING_LINES` held the counselling numbers and the
	directory route never read the table, so "mental health helpline" was missing from a screen whose
	own section names it while the number sat three modules away."""
	directory = InfoService().hotline_directory()
	by_kind = {row.kind: row for row in directory.contacts}
	assert ContactKind.mental_health_helpline in by_kind
	assert ContactKind.substance_abuse_helpline in by_kind
	assert ContactKind.ambulance in by_kind
	assert by_kind[ContactKind.mental_health_helpline].number == '0722 178 177'
	# And the folded rows are not claimed as checked: `mental` marks every one `verified: 'False'`.
	assert all(not row.verified for row in directory.contacts), 'no folded row arrives looking verified'


def test_the_absent_list_is_coverage_of_the_sections_eight() -> None:
	"""A gap list is only useful if it is derived from the *section's* Contents rather than the enum.

	The distinction is invisible on today's data, which is why this constructs the case where the two
	differ: a directory holding every one of the eight *plus* a complaints desk the section does not
	name. Counted over the enum that directory reports itself incomplete for carrying an extra; counted
	over `SPEC_CONTENTS` it is complete, which is the true answer. A test that only compared the
	derivation against the served rows would pass either way.
	"""
	directory = InfoService().hotline_directory()
	assert set(directory.absent) == {k for k in SPEC_CONTENTS if k not in {r.kind for r in directory.contacts}}
	assert directory.complete == (not directory.absent)
	# The four the tree has no number for are named rather than omitted.
	assert {ContactKind.gbv_helpline, ContactKind.child_helpline} <= set(directory.absent)

	full = ContactDirectory(contacts=[
		HotlineInfo(name=f'contact {k.value}', number='719', hours='24/7', kind=k,
			actions=HotlineActions(tel_uri='tel:719', sms_uri='sms:719', vcard='BEGIN:VCARD',
				share_url='https://wa.me/?text=719'))
		for k in (*SPEC_CONTENTS, ContactKind.complaints_desk)
	])
	assert full.absent == [], 'a directory with all eight and one extra lacks nothing'
	assert full.complete is True, 'the extra row is not a gap'


def test_a_contact_row_is_dialable_sms_able_savable_and_shareable() -> None:
	"""§INF-006's four Features. Rendered server-side the way `Directions` renders its two map URLs,
	because "one-tap call" as a client obligation is a feature two clients implement differently."""
	row = next(r for r in InfoService().hotline_directory().contacts if r.kind is ContactKind.emergency_hotline)
	assert row.actions is not None
	assert row.actions.tel_uri == 'tel:719'
	assert row.actions.sms_uri == 'sms:719'
	assert 'TEL;TYPE=VOICE:719' in row.actions.vcard and row.actions.vcard.startswith('BEGIN:VCARD')
	assert row.actions.share_url.startswith('https://wa.me/?text=')
	assert '719' in row.actions.share_url


def test_a_row_naming_two_numbers_is_cut_to_one() -> None:
	"""`1199 (ambulance) / 719 (MoH)` is how the tree writes the emergency row. Stripping non-digits
	from it concatenates both into `1199719`, which dials nothing — a life-safety entry that looks
	actionable and is not, which is worse than one with no number at all."""
	assert _dialable('1199 (ambulance) / 719 (MoH)') == '1199'
	assert _dialable('+254-20-4226849') == '+254204226849'
	with pytest.raises(AssertionError):
		_dialable('call the office')


def test_the_nearest_facility_is_an_answer_about_a_position() -> None:
	"""The fourth Content is not a row — it is whichever facility is closest, so it exists only when
	the caller says where they are. Without a position the kind is *absent*, not silently blank."""
	svc = InfoService()
	assert ContactKind.nearest_facility in svc.hotline_directory().absent, 'no position, no nearest facility'
	places = PlacesService()

	async def _seed() -> None:
		await places.upsert(Place(osm_id='N1', kind=PlaceKind.clinic, name='Kayole Clinic',
			lat=-1.28, lon=36.90, phone='+254 20 555 0100'))
		await places.upsert(Place(osm_id='N2', kind=PlaceKind.hospital, name='Far Hospital',
			lat=-1.20, lon=36.95))

	import asyncio
	asyncio.run(_seed())
	directory = svc.hotline_directory(lat=-1.281, lon=36.901, places=places)
	assert ContactKind.nearest_facility not in directory.absent
	row = next(r for r in directory.contacts if r.kind is ContactKind.nearest_facility)
	assert row.name == 'Kayole Clinic', 'the closest, not the first imported'
	assert row.actions is not None and row.actions.tel_uri == 'tel:+254205550100'
	assert row.updated_line is not None and row.updated_line.endswith('km away')

	# A facility OSM gave no number for is still the nearest facility: the row answers "where do I
	# go", and dropping it for want of a number hides the destination because the number is missing.
	no_phone = PlacesService()

	async def _seed_far() -> None:
		await no_phone.upsert(Place(osm_id='N2', kind=PlaceKind.hospital, name='Far Hospital',
			lat=-1.20, lon=36.95))

	asyncio.run(_seed_far())
	listed = svc.hotline_directory(lat=-1.281, lon=36.901, places=no_phone)
	row = next(r for r in listed.contacts if r.kind is ContactKind.nearest_facility)
	assert row.name == 'Far Hospital' and row.actions is None, 'no number, no call button, still listed'


def test_the_directory_with_no_places_imported_reports_absent_rather_than_failing() -> None:
	"""`PlacesService.nearest` asserts a non-empty pool. A deployment whose OSM import has not run
	has no nearest facility — that is a gap to report, not a 500 on the screen a person opens when
	they need help."""
	directory = InfoService().hotline_directory(lat=-1.29, lon=36.91, places=PlacesService())
	assert ContactKind.nearest_facility in directory.absent
	assert len(directory.contacts) == len(HOTLINES) + 3, 'the fixed rows are still served'


def test_the_route_serves_the_directory_with_the_actions() -> None:
	"""The route is where the finding was: `hotlines()` served a list of two numbers and the section's
	Features were nowhere. It answers the directory now, and each row carries its URIs."""
	from afya.service import build_services, create_app
	app = create_app(build_services())

	async def _get() -> httpx.Response:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			return await c.get('/info/hotlines')

	import asyncio
	body = asyncio.run(_get()).json()
	assert set(body) == {'contacts', 'absent', 'complete'}, body
	assert body['complete'] is False
	assert {c['kind'] for c in body['contacts']} >= {'emergency_hotline', 'mental_health_helpline'}
	assert all(c['actions']['tel_uri'].startswith('tel:') for c in body['contacts'])
