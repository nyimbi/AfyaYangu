"""A computed field is an output, and a model must not refuse the payload it just served.

Every model here sets `extra='forbid'`, which is what stops a client inventing a field and having
it silently dropped. A `@computed_field` is served by `model_dump()` and cannot be set, so the two
rules meet badly: `ContentItem` gained `share_card` and `share_url` for §INF-004's "Shareable as a
card", and from that commit a client could no longer read an item and post it back. The API's own
output became a 422 against the API's own input, naming two fields the caller never wrote.

That is not a defect in the card. §3.3 principle 10 requires the server to render the share text —
two clients composing it from the fields would eventually disagree about what it says — so the
fields stay in the payload. What has to give is the input side: a key the model *derives* is not a
key a caller can supply, and dropping it is the only reading under which a round trip closes.

`extra='forbid'` keeps its teeth. Only the names this class actually computes are dropped, so
`ContentItem(**item.model_dump(), typo=1)` still raises, and a model with no computed fields is
unaffected. The alternative — `exclude_computed_fields=True` at every dump site — puts the
obligation on each caller and fails silently in the direction of a missing card.
"""
from typing import Any

from pydantic import model_validator


class DerivedFields:
	"""Drop this model's own computed fields from an incoming mapping, before validation.

	Runs in `mode='before'` because the keys have to be gone by the time `extra='forbid'` counts
	them, and class-level so the set is read off the class being constructed rather than the base.
	A non-mapping payload is returned untouched: a model validated from an object or a model instance
	has no keys to drop, and rebuilding it here would lose whatever it was.
	"""

	@model_validator(mode='before')
	@classmethod
	def _drop_derived(cls, data: Any) -> Any:
		if not isinstance(data, dict):
			return data
		# Read through `getattr` rather than off the class: this mixin is not a `BaseModel`, so the
		# attribute exists only on the classes that mix it in, and naming it on the base is both a
		# type error and a lie about where it lives. `{}` covers the model that computes nothing.
		derived = set(getattr(cls, 'model_computed_fields', {}))
		return {k: v for k, v in data.items() if k not in derived} if derived else data
