"""§ACC-005's "Support for low-resolution screens" — the bullet with no field behind it.

Seven of the section's eight Targets were carried. The eighth had nothing: no flag on
`DeviceCompatibility`, no bucket on `UI_SCREENS`, nothing anywhere that recorded or handled a screen
constraint. §ACC-005 states no dimension for it, so the buckets are the platform's own published
figures rather than this deployment's invention — `sources/android-screen-compatibility/` archives the
page each number comes from, and the checksums are in `sources/INDEX.md`.

Three things these tests hold, and the third is the one that matters:

* a device's shorter side selects a bucket, and the shorter side is the same number in portrait and
  landscape — so a layout does not change columns because the phone was turned;
* every bucket's touch target is at or above §ACC-001's 48 dp floor. A small screen is exactly where
  a thumb misses, so the control is the last thing to shrink and not the first. This is the obvious
  wrong move and the assertion is here to stop it;
* the narrow layout is **not** the regular one with the numbers scaled down. It differs in a way the
  client can act on — columns, pictogram, reserved label lines — because a bucket that changed
  nothing but a width field would be `charging_adaptive` again: a flag with no referent.
"""
import httpx

from afya.access.service import SCREEN_LAYOUTS, AccessService
from afya.access.views import MIN_TOUCH_TARGET_DP, NARROW_WIDTH_DP, SCREEN_BUCKETS, TABLET_WIDTH_DP
from afya.mobile.actions import FEATURE_OF, catalogue
from afya.service import build_services, create_app


def test_the_buckets_are_the_platforms_published_figures() -> None:
	"""320dp and 600dp are Android's own numbers, not this deployment's.

	The page archived at `sources/android-screen-compatibility/supports-screens-element.html` states
	them in its own words: "a typical handset screen has a smallestWidth of 320dp, a 7-inch tablet
	has a smallestWidth of 600dp". Restated here so a later edit that quietly moves the boundary is a
	failing test rather than a layout that no longer matches the source it cites.
	"""
	assert dict(SCREEN_BUCKETS) == {'narrow': 320, 'regular': 600}
	assert NARROW_WIDTH_DP == 320 and TABLET_WIDTH_DP == 600


def test_the_shorter_side_selects_the_bucket() -> None:
	"""Boundary behaviour, because an off-by-one here is a phone rendering a tablet layout."""
	svc = AccessService()
	assert svc.screen_bucket(320) == 'narrow'
	assert svc.screen_bucket(319) == 'narrow', 'a 319dp device is narrower, not a third bucket'
	assert svc.screen_bucket(599) == 'narrow'
	assert svc.screen_bucket(600) == 'regular'
	assert svc.screen_bucket(1024) == 'regular', 'nothing above the tablet bucket is claimed'


def test_a_screen_bucket_never_shrinks_a_control_below_the_floor() -> None:
	"""§ACC-001's 48 dp, held across §ACC-005's buckets.

	This is the assertion the section needs and not the one it invites. Making a control smaller is
	how a small screen is usually accommodated, and it is the failure §ACC-001's whole bullet list is
	against: the person who cannot see the screen well is the person most likely to be on it.
	"""
	assert all(row.touch_target_dp >= MIN_TOUCH_TARGET_DP for row in SCREEN_LAYOUTS)
	narrow = next(r for r in SCREEN_LAYOUTS if r.bucket == 'narrow')
	assert narrow.touch_target_dp < 64, (
		'the narrow bucket must actually differ from the regular one, or this test is asserting a '
		'constant and would pass against a table that had no narrow row at all')


def test_the_narrow_layout_differs_in_more_than_its_width() -> None:
	"""A bucket that changed only a number would be a flag with no referent.

	Each of these is something a client does: how many columns to lay out, how large to draw the
	pictogram, how many lines to reserve for the label. `charging_adaptive` was hardcoded `True` with
	nothing reading a charging state; the equivalent here would be a `narrow: true` boolean.
	"""
	svc = AccessService()
	narrow = svc.layout_for(NARROW_WIDTH_DP)
	regular = svc.layout_for(TABLET_WIDTH_DP)
	assert narrow.columns < regular.columns, 'a narrow screen gets fewer columns'
	assert narrow.pictogram_dp < regular.pictogram_dp, 'a narrow screen gets a smaller pictogram'
	assert narrow.label_lines > regular.label_lines, 'a narrow screen wraps the label over more lines'
	assert narrow.bucket != regular.bucket


def test_the_layout_carries_the_width_the_caller_reported() -> None:
	"""360dp and 320dp are the same bucket and not the same device, so the answer says which it is."""
	svc = AccessService()
	assert svc.layout_for(360).smallest_width_dp == 360
	assert svc.layout_for(360).bucket == 'narrow'


def test_the_short_side_does_not_change_when_the_phone_is_turned() -> None:
	"""`smallestWidth` is the shorter of the two sides, which is why it is the key.

	A layout keyed on width would give a phone two columns in landscape and one in portrait — the
	person would see the app re-arrange itself on rotation for a reason that has nothing to do with
	the space available. Asserted by construction: the bucket function takes one number and the
	caller passes the shorter side, so there is no orientation input for it to depend on.
	"""
	import inspect
	params = list(inspect.signature(AccessService.screen_bucket).parameters)
	assert params == ['smallest_width_dp'], f'no orientation may enter the choice: {params}'


def test_the_compatibility_answer_carries_the_screen_layouts() -> None:
	"""The bullet's claim has to be reachable from the route that answers the device question."""
	svc = AccessService()
	for platform in ('android', 'ios'):
		out = svc.compatibility(platform)
		assert out.smallest_width_dp == NARROW_WIDTH_DP, 'a caller who does not say is on the small one'
		assert {row.bucket for row in out.screen_layouts} == {b for b, _ in SCREEN_BUCKETS}
	assert svc.compatibility('android', 600).smallest_width_dp == 600


async def test_the_route_serves_the_layout_for_the_width_it_was_given() -> None:
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		small = (await c.get('/access/compatibility/android?smallest_width_dp=320')).json()
		large = (await c.get('/access/compatibility/android?smallest_width_dp=720')).json()
		assert small['screen_layouts'][0]['bucket'] == 'narrow'
		assert large['screen_layouts'][0]['bucket'] == 'narrow', (
			'every bucket is served on every answer, so a designer can lay out for a phone they are '
			'not holding')
		assert [r['touch_target_dp'] for r in small['screen_layouts']] == [56, 64]
		rows = (await c.get('/access/screen-layouts')).json()
		assert {r['bucket'] for r in rows} == {'narrow', 'regular'}
		assert all(r['touch_target_dp'] >= MIN_TOUCH_TARGET_DP for r in rows)
		# A width that cannot be a screen is refused at the boundary rather than reaching the model.
		# It arrived as a 500 the first time: `smallest_width_dp=0` raised a pydantic
		# `ValidationError` inside `compatibility`, which is not the `AssertionError` the route
		# catches, so the front door answered with a stack trace for an input a client can send.
		assert (await c.get('/access/compatibility/android?smallest_width_dp=0')).status_code == 422
		assert (await c.get('/access/compatibility/android?smallest_width_dp=-5')).status_code == 422
		assert (await c.get('/access/compatibility/windows')).status_code == 404


async def test_the_layouts_are_reachable_from_the_catalogue() -> None:
	"""A capability with no action is a capability nobody can reach — the `report_stock` rule."""
	app = create_app(build_services())
	transport = httpx.ASGITransport(app=app)
	async with httpx.AsyncClient(transport=transport, base_url='http://t') as c:
		served = (await c.get('/mobile/actions')).json()
	ids = {a['id'] for a in served}
	assert 'screen_layouts' in ids, 'the layout table is served and nothing opens it'
	assert FEATURE_OF['screen_layouts'] == 'ACC-005'
	# And the compatibility form asks for the width, because a caller on a 720dp tablet otherwise
	# gets the narrow layout and no way to say so.
	compat = next(a for a in served if a['id'] == 'compatibility')
	assert 'smallest_width_dp' in {f['name'] for f in compat['fields']}


def test_the_narrow_question_stays_on_the_form_that_answers_it() -> None:
	"""No second place for the width to live. `DeviceCompatibility` carries it and `AccessProfile`
	does not: the screen is a property of the handset, and a profile field would let one account
	claim two screen sizes."""
	from afya.access.views import AccessProfile
	assert 'smallest_width_dp' not in AccessProfile.model_fields
	assert 'screen_layouts' not in AccessProfile.model_fields


def test_no_spec_feature_code_reaches_the_screen_layout_payload() -> None:
	"""The standing rule: feature ids are backend identifiers and §ACC-005 must not leak into a form."""
	import re
	svc = AccessService()
	payload = svc.compatibility('android').model_dump_json() + svc.screen_layouts()[0].model_dump_json()
	assert not re.search(r'\b(?:CHAN|INF|TRI|FND|MED|EMG|REC|MON|SENS|LOC|COM|ALT|AI|ACC|SEC)-\d{3}\b',
	                     payload), payload[:400]


def test_the_bucket_table_is_what_the_catalogue_renders_rather_than_a_second_copy() -> None:
	"""The route reads `SCREEN_LAYOUTS`; this asserts the catalogue action points at that route and
	not at a table of its own."""
	acts = {a.id: a for a in catalogue()}
	assert acts['screen_layouts'].path == '/access/screen-layouts'
	assert acts['screen_layouts'].method == 'GET'
