#!/usr/bin/env python3
"""PreToolUse guard: stop a PDF being read without a page range.

`Read(file.pdf)` with no `pages` argument returns a base64 `document` content
block. The local LiteLLM gateway cannot map that block and fails the whole
turn with

    400 litellm.BadRequestError: OpenAIException - Validation: Failed to
    convert responses request: File function call output content is not yet
    supported

The block is then written into the session transcript, so every later turn
replays it and fails identically — `claude -c` and `--resume` both die, and the
session stays un-resumable until the block is removed from the transcript by
hand. Four sessions in this repo had to be repaired that way. A rule in
CLAUDE.md states this; a rule the model can forget is not a guard, so this
enforces it.

Why the CLI's own `pages` requirement is not enough: a page range makes the CLI
render pages to *images*, which the gateway accepts. Whole-file is the only
shape that breaks. Images are fine, top-level or inside a tool result.

Two responses, in order:

  1. A text copy of the file exists beside the PDF (the `pdftotext -layout`
     extraction committed next to every source) -> rewrite the call to read
     that instead. Cheaper in context than the PDF and always correct here.
  2. No text copy -> deny, and say to pass `pages`.

Protocol: exit 0 to allow. To act, print a JSON decision on stdout and exit 0 —
`permissionDecision: "deny"` blocks; `permissionDecision: "allow"` with
`updatedInput` rewrites the call and lets it run. Exit 2 + stderr is the other
deny convention, used only when the decision cannot be expressed as JSON.
"""

from __future__ import annotations

import json
import os
import sys

PDF_SUFFIX = ".pdf"


def _decide(payload: dict) -> dict | None:
	"""Return a hook decision, or None to let the call through untouched."""
	if payload.get("tool_name") != "Read":
		return None
	tool_input = payload.get("tool_input") or {}
	path = tool_input.get("file_path")
	if not isinstance(path, str) or not path.lower().endswith(PDF_SUFFIX):
		return None

	# A page range is the supported path — the CLI renders pages to images.
	pages = tool_input.get("pages")
	if isinstance(pages, str) and pages.strip():
		return None
	if isinstance(pages, list) and pages:
		return None

	# 1. Prefer the committed text copy beside the PDF.
	text_path = path[: -len(PDF_SUFFIX)] + ".txt"
	if os.path.isfile(text_path):
		updated = dict(tool_input)
		updated["file_path"] = text_path
		updated.pop("pages", None)
		return {
			"hookSpecificOutput": {
				"hookEventName": "PreToolUse",
				"permissionDecision": "allow",
				"permissionDecisionReason": (
					f"Read the text copy {text_path} instead of the PDF. A whole-file PDF "
					"read returns a document block the gateway rejects, and the block "
					"poisons the transcript for every later turn."
				),
				"updatedInput": updated,
			}
		}

	# 2. No text copy — refuse, and name the fix.
	return {
		"hookSpecificOutput": {
			"hookEventName": "PreToolUse",
			"permissionDecision": "deny",
			"permissionDecisionReason": (
				f"Refusing to read {path} without a page range. A whole-file PDF read "
				"returns a base64 document block that this project's model gateway "
				"rejects with a 400, and the block is then written into the transcript "
				"so every later turn fails the same way. Pass `pages` (e.g. "
				'pages: "1-3") to read it, or add a `pdftotext -layout` text copy '
				"beside it and read that."
			),
		}
	}


def main() -> int:
	try:
		payload = json.load(sys.stdin)
	except Exception as exc:  # never block on our own failure
		print(f"pdf-read-guard: unreadable hook input: {exc}", file=sys.stderr)
		return 0

	try:
		decision = _decide(payload)
	except Exception as exc:  # a guard that crashes must not stop the tool
		print(f"pdf-read-guard: {exc}", file=sys.stderr)
		return 0

	if decision is not None:
		json.dump(decision, sys.stdout)
	return 0


if __name__ == "__main__":
	sys.exit(main())
