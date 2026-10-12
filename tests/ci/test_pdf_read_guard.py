"""The PDF read guard — the hook that stops a whole-file PDF read poisoning a session.

`Read(file.pdf)` with no `pages` argument returns a base64 `document` content block. This project's
model gateway cannot map that block and fails the whole turn with a 400, and the block is then
written into the session transcript, so every later turn replays it and fails identically — four
sessions in this repo had to be repaired by hand that way. `.claude/hooks/pdf-read-guard.py`
enforces the rule that `.claude/CLAUDE.md` states, because a rule the model can forget is not a
guard.

These tests drive the real hook over stdin the way Claude Code does and read the JSON decision back,
so what is tested is the deployed contract rather than a reimplementation of it. A guardrail that
has never blocked anything is a guess, so the deny and rewrite cases are the point, and the allow
cases are every neighbouring call the guard has no business touching.

The guard is local — it protects this machine's gateway, not a shipped artefact — but it is
committed, so its test runs in CI like everything else. A gate that has never run is not a gate.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / '.claude' / 'hooks' / 'pdf-read-guard.py'

# A source PDF that has a committed text copy beside it.
PDF_WITH_TEXT = REPO / 'sources' / 'who-child-growth-standards' / 'wfa_boys.pdf'
PDF_WITH_TEXT_TXT = REPO / 'sources' / 'who-child-growth-standards' / 'wfa_boys.txt'
# A PDF with no text copy beside it.
PDF_NO_TEXT = REPO / 'docs' / 'spec.md.pdf'


def _run(tool_name: str, tool_input: dict) -> tuple[int, dict | None, str]:
	payload = json.dumps({
		'hook_event_name': 'PreToolUse',
		'tool_name': tool_name,
		'tool_input': tool_input,
		'cwd': str(REPO),
	})
	proc = subprocess.run(
		[sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
	)
	out = proc.stdout.strip()
	try:
		decision = json.loads(out) if out else None
	except json.JSONDecodeError:
		decision = None
	return proc.returncode, decision, proc.stderr.strip()


def _decision(decision: dict | None) -> tuple[str | None, dict | None]:
	if not decision:
		return None, None
	hso = decision.get('hookSpecificOutput') or {}
	return hso.get('permissionDecision'), hso.get('updatedInput')


def test_the_fixtures_are_real() -> None:
	"""The canary. If the text copy did not exist the rewrite case would deny instead, and a green
	suite would mean the guard was never pointed at anything."""
	assert HOOK.is_file(), f'the hook is not where the settings point: {HOOK}'
	assert PDF_WITH_TEXT.is_file(), f'missing fixture: {PDF_WITH_TEXT}'
	assert PDF_WITH_TEXT_TXT.is_file(), f'missing fixture: {PDF_WITH_TEXT_TXT}'


def test_a_whole_file_pdf_read_is_rewritten_to_its_text_copy() -> None:
	"""The defect this guard exists for. The call is redirected, not refused, because the text copy
	is both cheaper and always correct here."""
	rc, decision, err = _run('Read', {'file_path': str(PDF_WITH_TEXT)})
	assert rc == 0, f'hook exited {rc}: {err}'
	verdict, updated = _decision(decision)
	assert verdict == 'allow', f'expected a rewrite, got {verdict!r}'
	assert updated is not None, 'a rewrite must carry updatedInput'
	assert updated['file_path'] == str(PDF_WITH_TEXT_TXT)
	assert not updated.get('pages'), 'a `pages` argument must not carry onto a text file'


def test_a_whole_file_pdf_read_with_no_text_copy_is_denied() -> None:
	rc, decision, err = _run('Read', {'file_path': str(PDF_NO_TEXT)})
	assert rc == 0, f'hook exited {rc}: {err}'
	verdict, _ = _decision(decision)
	assert verdict == 'deny', f'expected a deny, got {verdict!r}'
	reason = (decision or {}).get('hookSpecificOutput', {}).get('permissionDecisionReason', '')
	assert 'pages' in reason, 'the refusal must name the fix'


@pytest.mark.parametrize('tool_input', [
	{'file_path': str(PDF_NO_TEXT), 'pages': '1-3'},
	{'file_path': str(PDF_WITH_TEXT), 'pages': '1-2'},
	{'file_path': str(PDF_WITH_TEXT_TXT)},
	{'file_path': str(REPO / 'docs' / 'spec.md')},
	{'file_path': str(REPO / 'README.md')},
	{'file_path': str(REPO / 'docs')},
], ids=['pages-on-a-bare-pdf', 'pages-on-a-sourced-pdf', 'the-text-copy', 'markdown', 'readme', 'a-directory'])
def test_reads_the_guard_has_no_business_touching_are_left_alone(tool_input: dict) -> None:
	"""A page range is the supported path — the CLI renders pages to images, which the gateway
	accepts. Everything that is not a whole-file PDF read must pass through untouched."""
	rc, decision, err = _run('Read', tool_input)
	assert rc == 0, f'hook exited {rc}: {err}'
	assert decision is None, f'expected a silent allow, got {decision!r}'


@pytest.mark.parametrize('tool', ['Bash', 'Write', 'Edit', 'Grep', 'Glob', 'NotebookEdit'])
def test_other_tools_are_not_this_guard_s_jurisdiction(tool: str) -> None:
	rc, decision, err = _run(tool, {'file_path': str(PDF_NO_TEXT)})
	assert rc == 0, f'hook exited {rc}: {err}'
	assert decision is None, f'{tool} must not be gated by the PDF read guard'


def test_a_malformed_payload_does_not_block() -> None:
	"""A guard that crashes on bad input stops the tool it was meant to protect. Failing open is the
	right direction for a convenience guard; the rule still stands in CLAUDE.md."""
	proc = subprocess.run(
		[sys.executable, str(HOOK)], input='not json', capture_output=True, text=True
	)
	assert proc.returncode == 0, 'a malformed payload must not block the call'
