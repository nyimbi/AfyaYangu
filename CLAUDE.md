# afya — repo notes

Repo-specific rules. Python, testing, style and commit conventions are in `../CLAUDE.md`.

## Never read a PDF without a `pages` argument

`Read(file.pdf)` with no page range returns a base64 `document` content block. The local LiteLLM
gateway cannot map that block and fails the whole turn:

```
400 litellm.BadRequestError: OpenAIException - Validation: Failed to convert
responses request: File function call output content is not yet supported
```

The block is then written into the session transcript, so **every later turn replays it and fails
identically** — including `claude -c` and `--resume`. The session is poisoned, not just the one
request, and it cannot be continued until the block is removed from the transcript.

- **Read the `.txt` copy** beside each source PDF. It is there for this reason.
- **If a PDF must be read**, pass `pages` (e.g. `pages: "1-3"`). The CLI renders pages to images,
  which the gateway accepts. Whole-file is the only shape that breaks.
- Images are fine, top-level or in a tool result. Only PDF `document` blocks fail.

A poisoned transcript is repaired by parsing each line, replacing the `document` block with a text
block, and re-serialising — untouched lines keep their exact bytes, and the rewrite is validated
(line count unchanged, every line re-parses) before it replaces the original. Back up first; the
file is outside git. Never `--resume` a poisoned session to test it — resuming writes to it.

## Sources are archived twice

`sources/` holds the published artefact **and** a `pdftotext -layout` extraction beside it, both
checksummed in `sources/INDEX.md`. `-layout` matters for the WHO tables — it keeps the
`Year: Month / Month / L / M / S` columns aligned.

	pdftotext -layout sources/<dir>/<file>.pdf sources/<dir>/<file>.txt
	shasum -a 256 sources/<dir>/*        # record the first 16 hex chars in INDEX.md

`INDEX.md` records, per source: publisher, retrieval date, URL, both checksums, and **what the
source does and does not support**. Where a source states no threshold, say so — a number invented
to fill a table is worse than a table with a gap. When code computes from a table, check the
extraction against the code row by row rather than eyeballing it.

## Commands

	uv run pytest -q tests/ci      # full suite, ~50s
	uv run pyright

CI (`.github/workflows/ci.yml`) runs pyright, pytest, `bandit` and `pip-audit`. `test_security.py`
asserts the workflow runs exactly those, so the control table in `afya/security/service.py` cannot
claim enforcement CI does not provide.
