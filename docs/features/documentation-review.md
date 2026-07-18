# Documentation review (`videodoc review`)

## Summary
`videodoc review <project>` implements README §27, "Fase 14 — Revisione, validazione e controllo qualità". It inspects generated Markdown sections and their `docs/sources/*.sources.json` manifests, then writes:

- `docs/review_report.md`
- `docs/review_report.json`

The review is deterministic and local. It does not rewrite section Markdown; it reports issues for human or future automated correction.

## Checks
The current reviewer verifies:

- generated section files exist
- source manifest exists and parses
- required Markdown headings are present and non-empty
- fenced code blocks are balanced
- exactly one H1 exists
- video references and timestamps from source manifests appear in the section
- citations point to known source ranks
- narrative claims in explanation/procedure/error sections are cited
- cited claims have a basic lexical overlap with the indexed source text when the vector index is available
- duplicate fenced code blocks are detected
- code blocks from the manifest are represented in Markdown
- code blocks are classified as `verified`, `high_confidence`, `ocr_extracted` or `needs_review`

`reconstructed` is reserved in the report schema for a future assistive generation mode; the current strict local generator does not create reconstructed code.

## CLI

```bash
videodoc review corso-software-x
# Project: corso-software-x
# +----------------------------------------------+
# | Sections | 8                                |
# | Issues   | 0                                |
# | Errors   | 0                                |
# | Warnings | 0                                |
# | Report   | .../corso-software-x/docs/review_report.md |
# +----------------------------------------------+
```

Quality findings are written to the report; they do not change section files.

## Main Files
- `src/videodoc/core/services/review_service.py` — Markdown/source/code quality checks and report rendering.
- `src/videodoc/core/models/document_review.py` — JSON review report model.
- `src/videodoc/cli/commands/review.py` — CLI command.

## Tests
- Model: `tests/core/test_document_review.py`.
- Service: `tests/core/test_review_service.py`, covering clean sections, missing source manifests, uncited claims, low-confidence code and missing generated sections.
- CLI: `tests/cli/test_cli_review_command.py`.
