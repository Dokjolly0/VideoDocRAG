# Markdown section generation (`videodoc generate`)

## Summary
`videodoc generate <project>` implements README §26, "Fase 13 — Generazione delle sezioni Markdown". It reads the editable outline at `docs/outline.md`, retrieves relevant chunks for each section from the local vector index, connects code blocks from `project.db`, and writes one Markdown file per outline section.

The current implementation is extractive and local. It does not call an LLM yet. Instead, each generated section is built from retrieved source excerpts and explicit references, preserving the anti-hallucination rule: when a section has no retrieved sources, it becomes a review placeholder rather than invented content.

## Outputs
For each outline section:

- `docs/<NN>-<section-slug>.md`
- `docs/sources/<NN>-<section-slug>.sources.json`

The JSON source manifest records the chunks and code blocks used by that section, including record id, video id/name, chunk id, timestamps, score, topic, source type, embedding type, text hash, code block id/language/confidence and verification state.

## Manual Edit Safety
Generated Markdown sections are expected to be reviewed and edited. Existing section files are preserved by default and reported as skipped. Use `--force` to regenerate them from the current outline and index.

## CLI

```bash
videodoc generate corso-software-x --top-k 6
# Project: corso-software-x
# +-------------+
# | Generated | 8 |
# | Skipped   | 0 |
# +-------------+
```

## Main Files
- `src/videodoc/core/services/documentation_service.py` — outline parsing, retrieval-backed section generation and source manifest writing.
- `src/videodoc/core/models/document_section.py` — JSON manifest model for generated section sources.
- `src/videodoc/cli/commands/generate.py` — CLI command, `--force` and `--top-k`.

## Tests
- Model: `tests/core/test_document_section.py`.
- Service: `tests/core/test_documentation_service.py`, covering generation, source manifest creation, manual preservation, forced regeneration, missing outline and missing vector index.
- CLI: `tests/cli/test_cli_generate_command.py`.
