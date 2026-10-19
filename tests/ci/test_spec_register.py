"""The spec-completeness register's own claims: are its carriers reachable, and are its figures true?

`test_content_audit.py` asks whether the register *covers* the spec. It does not ask whether a row's
`carried` verdict is worth anything, and that is a separate question: `resolves` walks a `module:attr`
reference and says the attribute exists, which is true of a method no route and no caller ever
reaches. Four rows in this tree were `carried` by code with no caller at all — `record_donation`,
`cells_from_signals`, `stock_for` and `EvidenceService.encrypted` — and every gate in the repo was
green on all four, because "the code exists" and "the capability is reachable" are different claims
and only the first was being tested.

So this file makes the second claim computable. For every `carried` row naming a function or method,
it walks `src/` for a *use* of that name — a load, an import, a `getattr` string, or a string constant
— and asserts the set is non-empty. A row that genuinely has no caller must say so in its note, in the
words `NO_CALLER`, and then the assertion runs the other way: the note is a claim about the code and
a stale one is as wrong as a missing one. Both directions are needed because a gate that only checked
"reachable rows are referenced" would pass on a row whose note says "unreachable" while a route
started calling it.

**Three exemptions, each a false positive the naive scan produces:**

* a Pydantic hook (`model_post_init`, or anything carrying a `model_validator` decorator) is called
  by the library, not by name in this tree;
* a property is read as an attribute (`x.encrypted`), and `inspect` hands it back as a `property`
  object rather than a function, so it is outside the population this gate is about;
* a name reached only through `getattr(obj, 'name')` — `ChwService.serving` is — is found by the
  string branch of the scan rather than the load branch.

The docstring figures are checked the same way: every number the module docstring quotes is parsed
out of it and compared to the value computed from the tables. A reworded docstring that the parser
cannot match fails rather than skipping, because a gate that silently ignores what it cannot read is
the checker-that-enumerates-one-spelling defect wearing a test's clothes.
"""
import ast
import importlib
import inspect
import pathlib
import re
from typing import Any

from afya.channels.outbound import plain_language_report
from afya.content_audit.service import (
	_CLAIM_LABELS, _DUAL_LABELS, _LABELS, CLAIM_CONTENT, FEATURE_CONTENT,
	content_report,
)
from test_content_audit import _spec_feature_ids, _split_items

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / 'src'
REGISTER = SRC / 'afya' / 'content_audit' / 'service.py'

# A row whose carrier is not reachable from any route says so in its note, and this is the token it
# says it with. It is a marker rather than a word in prose so that the gate reads one spelling.
NO_CALLER = 'no route and no caller'

# Pydantic calls these by protocol. They are real code and they run on every construction, so a
# "no caller" verdict on one would be the instrument's mistake rather than the register's.
_HOOK_NAMES = frozenset({'model_post_init', 'model_validator', 'model_serializer', 'field_validator'})


def _claims_no_caller(note: str | None, leaf: str) -> bool:
	"""Whether *this carrier* is the one a note calls unreachable.

	A note can mention an uncalled helper while its own carrier is reachable — §FND-004's names
	`stock_for` as the superseded accessor beside `report_stock`, which is the row's carrier. The
	marker therefore has to sit in the same sentence as the carrier's own name, or the gate reads a
	statement about one callable as a statement about another.
	"""
	if note is None or NO_CALLER not in note:
		return False
	return any(NO_CALLER in sentence and leaf in sentence
		for sentence in re.split(r'(?<=[.!?])\s+', note))


def _resolved(ref: str) -> Any:
	module_name, _, attr_path = ref.partition(':')
	target: Any = importlib.import_module(module_name)
	for part in attr_path.split('.'):
		target = getattr(target, part)
	return target


def _is_hook(obj: Any, attr_path: str) -> bool:
	"""Whether a carrier is invoked by Pydantic rather than by a call site in this tree.

	Read off the decorator as well as the name: `SenseIngest._no_raw_field_name_reaches_an_ingest`
	is a `@model_validator(mode='before')` under a name of its own, and a name-only rule would call it
	uncalled.
	"""
	if attr_path.split('.')[-1] in _HOOK_NAMES:
		return True
	try:
		source = inspect.getsource(obj)
	except (OSError, TypeError):
		return False
	return '@model_validator' in source or '@field_validator' in source or '@model_serializer' in source


def _used_names() -> set[str]:
	"""Every name `src/` can be said to use, in any of the four spellings a use takes.

	* a load — `obj.attr`, `name(...)`, `name` in an expression;
	* an import — `from m import Name`, `from m import Name as Alias` (the alias's *original* name is
	  the one the register cites, and `WhisperSpeechEngine as WSE` is a use of `WhisperSpeechEngine`);
	* a `getattr` string — `getattr(chw, 'serving')`;
	* a string constant — the register's own `module:attr` references are excluded by file, but a
	  dynamic dispatch table written as strings is a use.
	"""
	used: set[str] = set()
	for path in SRC.rglob('*.py'):
		if path == REGISTER:
			continue
		for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
			if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
				used.add(node.id)
			elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
				used.add(node.attr)
			elif isinstance(node, ast.ImportFrom):
				used.update(alias.name for alias in node.names)
			elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
					and node.func.id == 'getattr' and len(node.args) > 1 \
					and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
				used.add(node.args[1].value)
			elif isinstance(node, ast.Constant) and isinstance(node.value, str):
				used.add(node.value)
	return used


def _carried_rows() -> list[tuple[str, str, str, str | None]]:
	"""`(feature, bullet, ref, note)` for every carried row that names a carrier."""
	return [(row[0], row[2], row[4], row[5])
		for row in (*FEATURE_CONTENT, *CLAIM_CONTENT)
		if row[3] == 'carried' and row[4]]


def test_every_reachable_carrier_is_used_somewhere_in_src() -> None:
	"""A `carried` verdict says code does the bullet, and this is the half that makes it mean something.

	The population is every carried row whose reference lands on a function or method. Properties,
	types and constants are outside it: a `computed_field` is read as an attribute and a class is
	constructed by its importer, so neither is a capability nobody can reach in the sense this gate
	measures.

	A row that has no caller must say `no route and no caller` in its note, and this test asserts the
	note and the code agree in *both* directions — a reachable row whose note claims it is not is the
	next stale note, and the register is a document people act on.
	"""
	used = _used_names()
	unreached: list[str] = []
	mislabelled: list[str] = []
	checked = 0
	for feature, bullet, ref, note in _carried_rows():
		assert ref is not None
		obj = _resolved(ref)
		if isinstance(obj, property) or not (inspect.isfunction(obj) or inspect.ismethod(obj)):
			continue
		attr_path = ref.partition(':')[2]
		if _is_hook(obj, attr_path):
			continue
		checked += 1
		leaf = attr_path.split('.')[-1]
		claimed_unreachable = _claims_no_caller(note, leaf)
		reachable = leaf in used
		if not reachable and not claimed_unreachable:
			unreached.append(f'§{feature} {bullet!r} -> {ref}')
		if reachable and claimed_unreachable:
			mislabelled.append(f'§{feature} {bullet!r} -> {ref}')
	assert checked >= 100, f'the scan resolved only {checked} callable carriers — the population is wrong'
	assert unreached == [], (
		'a carried row names a callable nothing in src/ uses, and its note does not say so:\n  '
		+ '\n  '.join(unreached))
	assert mislabelled == [], (
		'a note claims a carrier has no route and no caller, and src/ uses it:\n  '
		+ '\n  '.join(mislabelled))


def _docstring() -> str:
	return ast.get_docstring(ast.parse(REGISTER.read_text(encoding='utf-8'))) or ''


def _quoted(pattern: str, text: str) -> tuple[int, ...]:
	"""The figures a docstring sentence quotes, asserted present rather than silently skipped."""
	match = re.search(pattern, text)
	assert match is not None, f'the register docstring no longer states {pattern!r}'
	return tuple(int(g) for g in match.groups() if g is not None)


def test_the_register_docstring_counts_match_the_tables() -> None:
	"""The module docstring is the register's own summary, and every figure in it is checkable.

	It drifted by a whole revision — 42/53 labels, 78 sections, 567 rows over 99 pairs, 92 pairs and
	165 passages — because nothing compared prose to data. A docstring is not decorative when it is
	the thing a reader uses to decide whether to trust the table under it, so each figure is parsed
	out of the text and compared to the value computed from the code. A reworded sentence fails the
	parse rather than dropping the assertion.
	"""
	text = _docstring()
	assert _quoted(r'`_LABELS` \((\d+)\)', text) == (len(_LABELS),)
	assert _quoted(r'`_CLAIM_LABELS`\s*\((\d+)\)', text) == (len(_CLAIM_LABELS),)
	assert _quoted(r'`_DUAL_LABELS` \((\d+)\)', text) == (len(_DUAL_LABELS),)

	sections = _spec_feature_ids()
	rows, pairs = len(FEATURE_CONTENT), len({(r[0], r[1]) for r in FEATURE_CONTENT})
	assert _quoted(r'prints (\d+) feature sections', text) == (len(sections),)
	assert _quoted(r'(\d+) rows over (\d+) \(section, label\) pairs', text) == (rows, pairs)
	assert _quoted(r'(\d+) of the (\d+) sections print a claim label and (\d+) print', text) == (
		len({r[0] for r in CLAIM_CONTENT}), len(sections),
		len(sections) - len({r[0] for r in CLAIM_CONTENT}))
	assert _quoted(r'reads (\d+) pairs and (\d+) passages', text) == (
		len({(r[0], r[1]) for r in CLAIM_CONTENT}), len(CLAIM_CONTENT))
	assert _quoted(r'would shred (\d+) of the (\d+) claim passages', text) == (
		sum(1 for r in CLAIM_CONTENT if len(_split_items(r[2])) > 1), len(CLAIM_CONTENT))

	report = content_report()
	assert _quoted(r'useful claim is not "(\d+)" but "(\d+) of the (\d+)', text) == (
		report.audited_features, report.audited_features, len(sections))


def test_the_chan001_note_measures_what_the_walker_measures() -> None:
	"""The one register row that quotes a measurement of another module's output.

	`§CHAN-001`'s Format note said "181 outbound strings across 30 tables" while the walker measured
	191. A figure copied into prose beside the thing that computes it is a second source of truth
	unless something crosses the two, and this crosses them.
	"""
	note = next(row[5] for row in FEATURE_CONTENT if row[0] == 'CHAN-001' and row[2] == 'plain language')
	assert note is not None
	quoted = re.search(r'measures all (\d+) outbound strings across (\d+) tables', note)
	assert quoted is not None, 'the CHAN-001 note no longer quotes the walker’s figures'
	rows = plain_language_report()
	assert (int(quoted.group(1)), int(quoted.group(2))) == (
		sum(r.strings for r in rows), len(rows)), (
		f'the note says {quoted.group(1)} strings over {quoted.group(2)} tables; the walker measures '
		f'{sum(r.strings for r in rows)} over {len(rows)}')
