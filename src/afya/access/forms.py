"""§ACC-001's "Simplified forms" — the flag that reached the screens and not the forms.

The section prints two Features one line apart: "Simplified forms" and "Optional 'simple mode' that
hides advanced features". `AccessProfile.simple_mode` and `AccessService.screens` built the second —
a flag that drops whole screens — and the first was carried by nothing. A person who turned simple
mode on got fewer screens, and every form on the screens that remained asked exactly what it asked
everybody else. That is the same shape as the rest of this repo's gaps: every visible part exists
and the join does not.

What a simplified form is, here: **the same action, asking fewer of its optional questions.** The
route is unchanged, the body model is unchanged, and a client that renders what the catalogue says
renders a shorter form with no per-feature code — which is the property the catalogue exists for.

The drop list is a curation, not a derivation, and it is written down as one. A field cannot be
classified as "advanced" from its metadata: `temperature_c` is optional-with-a-default on
`/triage/preliminary` and is the input §6.3's malaria trap reads, while `muac_mm` on
`/records/growth` is optional in the same way and is a refinement most people never measure. Nothing
in the field distinguishes them, so a rule that tried would drop the first and keep the second. The
list is therefore a judgement, and the gates below are what keep a judgement from becoming a defect:

* a dropped field may not be one the route requires — that is §11.1's "a control the server
  refuses" read backwards, a form that cannot fill its own route;
* a simplified form may not be left with nothing drawn — a screen with no controls is a screen with
  no way forward, which is worse than the long form it replaced;
* every name in the list must still exist on the action it names, so a rename fails here rather than
  silently simplifying nothing.

`tests/ci/test_acc001.py` checks all three against the live catalogue and the live routes, and
`tests/ci/canary_acc001.py` breaks each one to watch it fail.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	from fastapi import FastAPI

	from afya.mobile.actions import MobileAction

# action id -> the fields a simple form leaves off. Everything not named here is kept, so an action
# with no entry is unchanged and a new action is never simplified by accident. The entries below are
# the fields a person has to *read or type* to answer, or a refinement of a question the form
# already asks. The one-tap questions stay: §ACC-001's whole premise is that a person who cannot
# read the form can still answer a picture, and a yes/no or a short list of choices is that picture's
# cheapest form.
SIMPLE_FORM_DROPS: dict[str, tuple[str, ...]] = {
	# §8.1/§11.2's triage. `symptoms`, `temperature_c` and `red_flags` stay — they are what the
	# classifier reads and what escalates to emergency. What goes is the detail beneath questions the
	# form already asks: `exposures` refines `exposure_site`, `isolation` and `age_band` refine who
	# the person is rather than what is wrong with them.
	'febrile_triage': ('exposures', 'isolation', 'age_band'),
	'evd_triage': ('exposures', 'isolation', 'age_band'),
	'differential': ('exposures', 'isolation', 'age_band'),
	# The diary drops only the instant, and that is the interesting entry in the table. `temperature_c`
	# and `red_flags` look droppable — they are optional and a diary entry reads fine without them —
	# and they are not, because `/triage/{ref}/diary/trend` computes its direction from exactly those
	# two: `delta = last.temperature_c - first.temperature_c` and a red flag appearing flips the
	# trend to worsening. Dropping them from the *entry* form would leave every entry at the default
	# 36.5 and no flag, so the trend screen would report "no change" forever and be right about the
	# data it was given. A form is not free to drop a field another screen reads.
	'symptom_diary': ('logged_at_iso',),
	# §FND-003/§FND-005's locators: the search refinements go, the position stays.
	'testing_sites': ('limit', 'max_cost_kes', 'max_turnaround_hours'),
	'vaccination_points': ('limit', 'max_cost_kes', 'age_months', 'walk_in_only'),
	# §EMG-001's "optional medical profile attachment". The four the section calls optional are
	# exactly the four a person filling in a simple SOS form does not have to hand.
	'sos': ('blood_group', 'allergies', 'conditions', 'medications'),
	'sos_countdown': ('channel',),
	# §REC-003's growth measurement: the two circumferences are what a clinic measures, not a parent.
	'growth_flag': ('sex', 'head_circumference_cm', 'muac_mm'),
	'milestone_check': ('present', 'lost', 'checked_earlier'),
	'add_lab': ('unit', 'flag'),
	'file_document': ('facility_id', 'media_ref', 'captured_iso', 'detail'),
	'share_record': ('recipient', 'kinds'),
	'save_birth_plan': ('blood_donor', 'funds_kes'),
	'record_dose': ('card_photo_sha256',),
	'report_issue': ('lat', 'lon'),
	'submit_case': ('age_years', 'exposure_history', 'geotagged', 'reported_offline'),
	'check_in': ('share_with_authority',),
	'monitoring_day': ('household_member', 'slot', 'location_logged'),
	'risk_score': ('proximity_encounters',),
	'flag_misinformation': ('topic', 'evidence_ref', 'transcript', 'evidence_consent', 'flagger_ref'),
	# Operator forms that are long for the same reason. §ACC-001 is cross-cutting, so an operator on
	# a phone benefits identically; the DPIA flags on `dpia_check` and `activate_outbreak_mode` are
	# deliberately absent from this list, because on those two forms the flags are the content and
	# dropping them would record a privacy assessment nobody made.
	'set_county_risk': ('source',),
	'record_case_counts': ('disease',),
	'record_sub_county': ('disease', 'locations'),
	'publish_content': ('harmony_tag', 'slug'),
	'report_content_error': ('correction_en', 'correction_sw', 'replacement_slug'),
	'publish_feed_item': ('county',),
	'register_border': ('mobile_lab', 'lab_turnaround_hours', 'lab_tests'),
	'traveller_declare': ('symptoms', 'lang'),
	'signal_scan': ('week', 'week_isoyear', 'baseline_weeks'),
	'battery_profile': ('hour', 'stationary'),
	'log_chw_activity': ('notes',),
}


def required_fields(app: 'FastAPI') -> dict[tuple[str, str], frozenset[str]]:
	"""Every field a route cannot be called without, keyed by `(method, path)`.

	Read off the live routes rather than restated, because the whole risk in a drop list is that it
	drifts away from the models it is dropping from. Three ways a route cannot be called without a
	value, and all three are collected: a body field with no default, a scalar parameter with no
	default, and a path placeholder — which FastAPI does not put in the signature at all, so a reader
	that only walked parameters would report `/facilities/{facility_id}/ed-status` as needing nothing.
	`authorization` is excluded because the header is the transport's, not the form's.

	The walk is recursive: FastAPI mounts routers, so the paths are on the nested `APIRoute`s and a
	top-level pass finds six routes and calls itself an inventory.
	"""
	import inspect
	import typing

	from pydantic import BaseModel

	by_route: dict[tuple[str, str], frozenset[str]] = {}

	def walk(routes: object) -> None:
		for route in routes:  # type: ignore[attr-defined]
			if hasattr(route, 'routes'):
				walk(route.routes)
				continue
			endpoint = getattr(route, 'endpoint', None)
			methods = getattr(route, 'methods', None) or []
			if endpoint is None or not methods:
				continue
			try:
				hints = typing.get_type_hints(endpoint)
			except Exception:  # pragma: no cover - an unresolvable annotation is its own defect
				continue
			sig = inspect.signature(endpoint)
			names: set[str] = set()
			for name, param in sig.parameters.items():
				annotation = hints.get(name)
				if isinstance(annotation, type) and issubclass(annotation, BaseModel):
					names |= {k for k, v in annotation.model_fields.items() if v.is_required()}
					continue
				if name == 'authorization':
					continue
				# A `Body(...)`/`Form(...)` marker is not `inspect.Parameter.empty`, so the obvious
				# test misses every one of them: `claim: str = Body(...)` is required by the route and
				# its default is a `Body` object, not `empty`. 34 routes were invisible here — and the
				# catalogue's marking is computed from this function, so each missed parameter was a
				# field drawn as optional that the route refuses without. The marker carries its own
				# answer, which is the one FastAPI itself uses.
				marked_required = getattr(param.default, 'is_required', None)
				if marked_required is not None and marked_required():
					names.add(name)
				elif marked_required is None and param.default is inspect.Parameter.empty:
					names.add(name)
			path = getattr(route, 'path', '')
			# A path placeholder is not a parameter FastAPI leaves in the signature, and a route
			# cannot be called without it. Collected here so the drop list cannot remove the field
			# that fills one — which would leave the client building a URL with braces in it.
			names |= {seg[1:-1] for seg in path.split('/') if seg.startswith('{') and seg.endswith('}')}
			for method in methods:
				by_route[(method, path)] = frozenset(names)

	walk(app.routes)
	assert by_route, 'the route walk found nothing, so every drop check below would pass vacuously'
	return by_route


def simplified(actions: 'list[MobileAction]',
               required: dict[tuple[str, str], frozenset[str]]) -> 'list[MobileAction]':
	"""The same actions with their declared refinements left off.

	Pure, so the route can call it per request and a test can call it with a catalogue it built. The
	three assertions are the gates the module docstring names, and they run here rather than in the
	test because a deployment must not serve a form that cannot fill its own route even if the test
	suite is the only thing that would have noticed.
	"""
	out: list[MobileAction] = []
	for act in actions:
		dropped = set(SIMPLE_FORM_DROPS.get(act.id, ()))
		if not dropped:
			out.append(act)
			continue
		names = {f.name for f in act.fields}
		unknown = dropped - names
		assert not unknown, f'{act.id}: simple form drops fields it does not carry: {sorted(unknown)}'
		required_here = required.get((act.method, act.path), frozenset())
		broken = dropped & required_here
		assert not broken, (
			f'{act.id}: simple form drops a field the route requires: {sorted(broken)}')
		kept = [f for f in act.fields if f.name not in dropped]
		assert kept, f'{act.id}: a simplified form with nothing drawn is a screen with no way forward'
		out.append(act.model_copy(update={'fields': kept}))
	return out
