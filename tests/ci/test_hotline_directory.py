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
	# The two Contents that are answers about the *caller* rather than national rows are named rather
	# than omitted: a county health office and a CHW are whoever the caller's county and community
	# have, so a directory built with no county cannot list them and says so. The GBV and child
	# helplines used to be on this line and are now carried — 1195 and 116 are national and
	# toll-free, and both are archived in `sources/helpline-directory/`.
	assert {ContactKind.county_health_office, ContactKind.chw} <= set(directory.absent)
	assert ContactKind.gbv_helpline not in directory.absent
	assert ContactKind.child_helpline not in directory.absent

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


# --- the two Contents that are answers about the caller, not national rows ------------------------

def test_the_county_health_office_is_a_number_per_county_and_absent_without_one() -> None:
	"""§INF-006's second Content. It is not a national line: it is whoever the caller's county has.

	A directory that served all 47 offices would be a list a person has to search, and one that
	printed "County Health Office: no number" would spend a screen slot saying nothing. So the row
	exists when the caller names a county the deployment has a number for, and the kind is reported
	absent otherwise — the same shape as `nearest_facility`.
	"""
	import asyncio

	svc = InfoService()
	assert ContactKind.county_health_office in svc.hotline_directory().absent, 'no county, no office'
	assert ContactKind.county_health_office in svc.hotline_directory(county='Busia').absent, \
		'a county with no number on file is still a gap'

	asyncio.run(svc.register_county_office('Busia', '+254 55 123 4567'))
	directory = svc.hotline_directory(county='Busia')
	assert ContactKind.county_health_office not in directory.absent
	row = next(r for r in directory.contacts if r.kind is ContactKind.county_health_office)
	assert row.county == 'Busia' and row.name.startswith('Busia')
	assert row.actions is not None and row.actions.tel_uri == 'tel:+254551234567'
	# And another county does not see Busia's office.
	assert ContactKind.county_health_office in svc.hotline_directory(county='Kisumu').absent


def test_a_county_office_with_no_number_is_refused_rather_than_stored() -> None:
	"""`_county_office_rows` treats a falsy number as "not on file", so an empty string would be a
	registration that silently disappears — the operator would believe they had filed a number and
	the screen would disagree with them."""
	import asyncio

	svc = InfoService()
	for bad in (('Busia', ''), ('', '719')):
		with pytest.raises(AssertionError):
			asyncio.run(svc.register_county_office(*bad))


def test_the_chw_row_comes_from_the_provisioned_profile_and_is_absent_without_one() -> None:
	"""§INF-006's sixth Content, and the finding: `ChwProfile` carried a name, a county and a
	community and *no way to reach the person*, so a directory row for a CHW was unanswerable even
	for a deployment that had provisioned every worker in the country."""
	import asyncio

	from afya.chw.service import ChwService
	from afya.chw.views import ChwProfile

	svc = InfoService()
	chw = ChwService()
	assert ContactKind.chw in svc.hotline_directory(county='Busia').absent, 'nobody provisioned'

	async def _provision() -> None:
		await chw.provision(ChwProfile(
			chw_ref='CHW-1', name='Achieng Odhiambo', county='Busia', community='Budalangi',
			registry_verified=True, provisioned_by='County', phone='+254 71 234 5678'))
		# A second worker in the same county with no number: the row picks the one that has one.
		await chw.provision(ChwProfile(
			chw_ref='CHW-2', name='No Phone', county='Busia', community='Budalangi',
			registry_verified=True, provisioned_by='County'))
		# A county whose *only* worker gave no number is a gap rather than a row with a blank
		# number: the directory lists a CHW so a person can reach them, and a name that cannot be
		# dialled is a name spending a screen slot on a life-safety page.
		await chw.provision(ChwProfile(
			chw_ref='CHW-3', name='No Number', county='Kisumu', community='Kibuye',
			registry_verified=True, provisioned_by='County'))

	asyncio.run(_provision())
	directory = svc.hotline_directory(county='Busia', chw=chw)
	row = next(r for r in directory.contacts if r.kind is ContactKind.chw)
	assert row.name.startswith('Achieng Odhiambo') and row.number == '+254 71 234 5678'
	assert row.actions is not None and row.actions.tel_uri == 'tel:+254712345678'
	# The pick is stable, so the number a person saved is the number they reach next time.
	serving = chw.serving('Busia')
	assert serving is not None and serving.chw_ref == 'CHW-1'
	assert chw.serving('Kisumu') is not None, 'a worker exists, they just have no number'
	assert ContactKind.chw in svc.hotline_directory(county='Kisumu', chw=chw).absent, \
		'a worker with no number is a gap, not a row with a blank number'
	assert chw.serving('Garissa') is None, 'a county with no worker is an answer, not an error'


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


def test_registering_a_county_office_is_guarded_and_a_citizen_cannot_file_one() -> None:
	"""The write that fills a row a person may dial in an emergency. `infrastructure` rather than a
	citizen scope: a county office's published number is the county authority's fact, and a route any
	caller could post to would let anyone put a number on a life-safety screen. The test asserts the
	refusal rather than the write, because the refusal is the half that can be got wrong silently."""
	import asyncio

	from afya.privacy.views import RBACRole
	from afya.service import build_services, create_app

	services = build_services()
	app = create_app(services)
	ops = services['auth'].provision_staff('ops-0', RBACRole.sysadmin, registrar='MoH ops')  # type: ignore[union-attr]

	async def _post() -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
		async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://t') as c:
			anon = await c.post('/info/county-office', params={'county': 'Busia', 'number': '719'})
			blank = await c.post('/info/county-office', params={'county': 'Busia', 'number': ''},
			                     headers={'authorization': f'Bearer {ops.access_token}'})
			ok = await c.post('/info/county-office',
			                  params={'county': 'Busia', 'number': '+254 55 123 4567'},
			                  headers={'authorization': f'Bearer {ops.access_token}'})
			served = await c.get('/info/hotlines', params={'county': 'Busia'})
			return anon, blank, ok, served

	anon, blank, ok, served = asyncio.run(_post())
	assert anon.status_code in (401, 403), anon.text
	assert blank.status_code == 422, blank.text
	assert ok.status_code == 200, ok.text
	row = next(c for c in served.json()['contacts'] if c['kind'] == 'county_health_office')
	assert row['name'] == 'Busia County Health Office', row
	assert row['actions']['tel_uri'] == 'tel:+254551234567', row
