#!/usr/bin/env python3
"""Test pdf-read-guard against the calls it must stop and the ones it must not.

A guardrail that has never blocked anything is a guess, so this drives the real
hook over stdin the way Claude Code does and reads the JSON decision back. The
canary is the whole point: `MUST_REWRITE` and `MUST_DENY` are the defect that
cost four repaired sessions in this repo, and `MUST_ALLOW` is every neighbouring
call the guard has no business touching.

Run: python3 .claude/hooks/test_pdf_read_guard.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).with_name("pdf-read-guard.py")
PROJECT = HOOK.parent.parent.parent  # .claude/hooks/<this> -> repo root

# A source PDF that has a committed text copy beside it.
PDF_WITH_TEXT = PROJECT / "sources/who-child-growth-standards/wfa_boys.pdf"
PDF_WITH_TEXT_TXT = PROJECT / "sources/who-child-growth-standards/wfa_boys.txt"
# A PDF with no text copy beside it.
PDF_NO_TEXT = PROJECT / "docs/spec.md.pdf"

MUST_REWRITE = [str(PDF_WITH_TEXT)]
MUST_DENY = [str(PDF_NO_TEXT)]
MUST_ALLOW = [
	# A page range is the supported path.
	{"file_path": str(PDF_NO_TEXT), "pages": "1-3"},
	{"file_path": str(PDF_WITH_TEXT), "pages": "1-2"},
	# Not a PDF.
	{"file_path": str(PDF_WITH_TEXT_TXT)},
	{"file_path": str(PROJECT / "docs/spec.md")},
	{"file_path": str(PROJECT / "README.md")},
	# A PDF-named directory-ish path that does not end in .pdf.
	{"file_path": str(PROJECT / "docs")},
]


def run(tool_name: str, tool_input: dict) -> tuple[int, dict | None, str]:
	payload = json.dumps(
		{
			"hook_event_name": "PreToolUse",
			"tool_name": tool_name,
			"tool_input": tool_input,
			"cwd": str(PROJECT),
		}
	)
	proc = subprocess.run(
		[sys.executable, str(HOOK)],
		input=payload,
		capture_output=True,
		text=True,
	)
	out = proc.stdout.strip()
	try:
		decision = json.loads(out) if out else None
	except json.JSONDecodeError:
		decision = None
	return proc.returncode, decision, proc.stderr.strip()


def decision_of(decision: dict | None) -> tuple[str | None, dict | None]:
	if not decision:
		return None, None
	hso = decision.get("hookSpecificOutput") or {}
	return hso.get("permissionDecision"), hso.get("updatedInput")


def main() -> int:
	failures: list[str] = []

	# --- MUST_REWRITE: the call is redirected to the text copy -----------------
	for path in MUST_REWRITE:
		rc, decision, err = run("Read", {"file_path": path})
		verdict, updated = decision_of(decision)
		if rc != 0:
			failures.append(f"rewrite {path}: exit {rc} ({err})")
		elif verdict != "allow" or not updated:
			failures.append(f"rewrite {path}: expected allow+updatedInput, got {verdict!r}")
		elif updated.get("file_path") != str(PDF_WITH_TEXT_TXT):
			failures.append(f"rewrite {path}: pointed at {updated.get('file_path')!r}")
		elif updated.get("pages"):
			failures.append(f"rewrite {path}: carried a `pages` onto a text file")

	# --- MUST_DENY: refused, with the fix named --------------------------------
	for path in MUST_DENY:
		rc, decision, err = run("Read", {"file_path": path})
		verdict, _ = decision_of(decision)
		if rc != 0:
			failures.append(f"deny {path}: exit {rc} ({err})")
		elif verdict != "deny":
			failures.append(f"deny {path}: expected deny, got {verdict!r}")

	# --- MUST_ALLOW: untouched -------------------------------------------------
	for tool_input in MUST_ALLOW:
		rc, decision, err = run("Read", tool_input)
		if rc != 0 or decision is not None:
			failures.append(
				f"allow {tool_input.get('file_path')}: expected silent allow, "
				f"got exit {rc} decision {decision!r} ({err})"
			)

	# --- Other tools are none of this guard's business -------------------------
	for tool in ("Bash", "Write", "Edit", "Grep", "Glob"):
		rc, decision, err = run(tool, {"file_path": str(PDF_NO_TEXT)})
		if rc != 0 or decision is not None:
			failures.append(f"tool {tool}: expected silent allow, got {decision!r}")

	# --- A malformed payload must not block -----------------------------------
	proc = subprocess.run(
		[sys.executable, str(HOOK)], input="not json", capture_output=True, text=True
	)
	if proc.returncode != 0:
		failures.append(f"malformed input: exit {proc.returncode}, must not block")

	# --- The canary: prove the fixture can fail --------------------------------
	# If PDF_WITH_TEXT_TXT did not exist, MUST_REWRITE would deny instead — so
	# assert the fixture is real, or a passing run means nothing.
	if not PDF_WITH_TEXT_TXT.is_file():
		failures.append(
			f"fixture missing: {PDF_WITH_TEXT_TXT} — MUST_REWRITE proves nothing"
		)

	total = len(MUST_REWRITE) + len(MUST_DENY) + len(MUST_ALLOW) + 6
	if failures:
		print(f"FAIL ({len(failures)} of {total} checks)")
		for f in failures:
			print(f"  - {f}")
		return 1
	print(f"PASS ({total} checks: {len(MUST_REWRITE)} rewrite, {len(MUST_DENY)} deny, "
	      f"{len(MUST_ALLOW)} allow, 6 other-tool/malformed)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
