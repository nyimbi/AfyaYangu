"""Gate: a request body must accept the payload its own model serves.

`MODEL_CONFIG` sets `extra='forbid'` on every model here, which is what stops a client inventing a
field and having it silently dropped. A `@computed_field` is written into `model_dump()` and cannot
be supplied by a caller, so the two rules meet badly: `ContentItem` gained `share_card` and
`share_url` for §INF-004's "Shareable as a card", and from that commit the API's own output was a
422 against the API's own input, naming two fields the caller never wrote.

Nothing failed. The corpus tests read items and never posted one back; the defect surfaced two
files away, as two unrelated localisation tests failing on `assert 422 == 200` because they seed a
translated row by round-tripping a library item through `POST /info/content`. A gate that fires
three files from its cause is a gate nobody can read, so this asks the question directly.

Two assertions, because the defect has two halves. The structural one walks every request body the
published OpenAPI names, so a model that gains a computed field is caught at the model rather than
at whichever route happens to post it. The behavioural one constructs the real payload and reads it
back, because "mixes in the right base" is not the same claim as "a round trip closes".
"""
import inspect

import pytest
from pydantic import BaseModel

from afya.derived import DerivedFields
from afya.info.views import ContentItem
from afya.service import build_services, create_app


def _request_body_models() -> dict[str, type[BaseModel]]:
	"""Every model the published schema names as a request body, by class.

	Read off `app.openapi()` rather than off a list of routes, because the question is what the API
	*publishes* as accepting a body — a model that reaches a client through the schema is one a
	client will post back, whether or not a test here ever does.
	"""
	schema = create_app(build_services()).openapi()
	names: set[str] = set()
	for operations in schema['paths'].values():
		for operation in operations.values():
			body = operation.get('requestBody') if isinstance(operation, dict) else None
			for media in (body or {}).get('content', {}).values():
				ref = media.get('schema', {}).get('$ref', '')
				if ref:
					names.add(ref.rsplit('/', 1)[-1])
	assert names, 'the schema names no request bodies, so this gate would pass vacuously'
	found: dict[str, type[BaseModel]] = {}
	for module in ('afya.service', 'afya.grpc_api.service'):
		mod = __import__(module, fromlist=['*'])
		for name, obj in vars(mod).items():
			if name in names and inspect.isclass(obj) and issubclass(obj, BaseModel):
				found[name] = obj
	return found


def test_every_request_body_tolerates_its_own_derived_fields() -> None:
	"""A request body that computes a field must drop it on the way in.

	`DerivedFields` is the one supported way to do that, so the assertion is that every request-body
	model carrying a computed field mixes it in. A model that computes nothing is not required to —
	the mixin would be a no-op — which is why the condition is on `model_computed_fields` rather
	than on every body.
	"""
	bodies = _request_body_models()
	computing = {name: cls for name, cls in bodies.items() if getattr(cls, 'model_computed_fields', None)}
	assert computing, 'no request body computes a field, so this gate would pass vacuously'
	unprepared = sorted(
		f'{cls.__module__}.{name}' for name, cls in computing.items()
		if not issubclass(cls, DerivedFields)
	)
	assert unprepared == [], (
		f'request bodies that serve a computed field and refuse it on the way in: {unprepared}'
	)


def test_a_library_item_reads_back_into_the_route_that_serves_it() -> None:
	"""The behaviour the structural assertion stands for, on the item that broke.

	A myth row rather than a plain one, because the myth is what added the computed fields and is
	the row whose `share_card` a client is most likely to hand back: a client that fetches a rumour,
	edits the correction and posts it is doing the ordinary thing, and it must not be refused for
	echoing a field the server rendered.

	The unknown key is asserted to still be refused, because the fix must not cost `extra='forbid'`
	its teeth — dropping every unrecognised key would close the round trip by making the model accept
	anything, which is the failure the config exists to prevent.
	"""
	from afya.info.content_seed import myth_rows

	row = myth_rows()[0]
	assert row.claim is not None and row.source is not None, 'the corpus must carry a myth to test with'
	dumped = row.model_dump(mode='json')
	assert 'share_card' in dumped and 'share_url' in dumped, 'the payload must carry the computed fields'
	assert ContentItem(**dumped) == row, 'a served item must read back unchanged'

	with pytest.raises(Exception):
		ContentItem(**{**dumped, 'not_a_field': 1})


def test_the_mixin_drops_only_what_the_model_computes() -> None:
	"""The narrowness of the drop, asserted on a body whose computed set is not the one that broke.

	A mixin that dropped every field it did not recognise would close the round trip above while
	disarming `extra='forbid'` everywhere it was applied, and the round-trip test alone cannot tell
	the two apart — it only ever posts keys the model knows. This is that distinction, read off a
	body that computes something *other* than the card.

	`TriageInput` rather than a body with no computed fields at all: 98 of the schema's 105 bodies
	compute nothing, and `extra='forbid'` on those is already covered by the tests that construct
	them. The interesting case is the body that computes one field and must drop that one and no
	other, which is exactly what `exposure_history` is.
	"""
	from afya.triage.views import TriageInput

	assert set(TriageInput.model_computed_fields) == {'exposure_history'}
	assert TriageInput(symptoms=['fever'], temperature_c=38.0).symptoms == ['fever']
	# The computed name is accepted and *recomputed* rather than stored, which is the property that
	# makes this safe: a client echoing `exposure_history=True` over a payload with no exposure does
	# not get to set it, and the derived value wins. Any other unknown key is still refused.
	echoed = TriageInput(symptoms=['fever'], temperature_c=38.0, exposure_history=True)  # type: ignore[call-arg]
	assert echoed.exposure_history is False, 'a derived field is recomputed, never taken from the caller'
	assert TriageInput(symptoms=['fever'], temperature_c=38.0, ebola_contact=True).exposure_history is True
	with pytest.raises(Exception):
		TriageInput(symptoms=['fever'], typo=1)  # type: ignore[call-arg]


def test_the_computed_fields_a_body_carries_are_the_ones_it_serves() -> None:
	"""The premise of the whole file, checked rather than assumed.

	If `ContentItem` stopped computing `share_card` the two assertions above would still pass — an
	item with no computed fields round-trips trivially — and §INF-004's "Shareable as a card" would
	be gone with nothing failing. So the fields are named here, and this test is what makes the
	others non-vacuous.
	"""
	assert set(ContentItem.model_computed_fields) == {'share_card', 'share_url'}
