# Documentation outline (`videodoc outline`)

## Summary
`videodoc outline <project>` implements README §25, "Fase 12 — Generazione dell'indice della documentazione". It creates a manually editable Markdown outline at `docs/outline.md` using the structured material already produced by previous phases.

The implementation is deterministic and local. It does not call an LLM yet: it reads ingested video titles, chunk topics/summaries, OCR/transcript snippets, code blocks, and optional `sources.yaml` attachment/codebase entries, then maps them into the standard documentation sections from the README.

## Manual Edit Safety
`docs/outline.md` is meant to be edited before the future `videodoc generate` phase. For that reason, the command never overwrites an existing outline by default. A rerun reports `Skipped: yes` and preserves the file exactly. Use `--force` to regenerate it from the current chunks.

## Generated Shape
The generated outline contains:

- project documentation title
- the eight standard sections from README §25
- a short objective for each section
- candidate source bullets with video name and timestamp range
- relevant code snippets when linked to a chunk or timestamp
- attachment and codebase summaries from `sources.yaml`, when available

## CLI

```bash
videodoc outline corso-software-x
# Project: corso-software-x
# +-----------------------------------------------+
# | Generated | yes                               |
# | Skipped   | no                                |
# | Sections  | 8                                 |
# | Outline   | .../corso-software-x/docs/outline.md |
# +-----------------------------------------------+
```

## Main Files
- `src/videodoc/core/services/outline_service.py` — outline generation, source assignment and manual-edit skip behavior.
- `src/videodoc/cli/commands/outline.py` — CLI command and `--force` option.
- `src/videodoc/core/errors.py` — `OutlineSourceUnavailableError` for projects without chunks.

## Tests
- Service: `tests/core/test_outline_service.py`, covering fresh generation, code/source inclusion, manual edit preservation, forced regeneration and missing upstream data.
- CLI: `tests/cli/test_cli_outline_command.py`.
