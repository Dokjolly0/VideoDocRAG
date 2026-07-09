# Project initialization

## Summary
`videodoc init <name>` creates a new, isolated VideoDocRAG project on disk — the standard folder layout plus a validated `config.yaml` — without requiring any of the heavy pipeline dependencies (Ollama, FFmpeg, faster-whisper, OCR engines, Qdrant).

## What was implemented
- `ProjectService.init(name, path=None, language="it")`: creates the project folder structure, writes a default `config.yaml`, and registers the project in the local registry.
- Full Pydantic v2 schema for `config.yaml` (`ProjectConfig` and one model per section: `project`, `paths`, `llm`, `embedding`, `transcription`, `frames`, `ocr`, `chunking`, `retrieval`, `code`, `scan`, `documentation`, `chat`, `gui`), matching README §30. All models use `extra="forbid"` to catch typos/unknown keys.
- Idempotent folder creation (`ensure_project_structure`, `ensure_sources_yaml`): re-running `init` never overwrites an existing `config.yaml` or `sources.yaml`.
- `--path` option to create a project anywhere on the filesystem (README §4.7 / §8.1.2): when omitted, the project is created under a default home outside the program folder (`VIDEODOC_HOME` env var, falling back to `~/VideoDocRAG/projects/<slug>`).
- `project.db` is deliberately **not** created at this stage — no SQLite schema exists yet to justify it (README §37.8: heavy state is introduced only when a step actually needs it). It will be created during the ingestion step.
- The registry key used by `init` is always `slugify(name)`, never the raw display name — see `docs/features/slugify.md` for the full rationale.
- `init` refuses to re-initialize a path that already holds a *different* project (a `config.yaml` whose `project.slug` doesn't match the newly requested one), raising `RegistryConflictError` instead of silently aliasing it — see `docs/features/slugify.md`.

## Main files
- `src/videodoc/core/config.py` — Pydantic schema and YAML load/save.
- `src/videodoc/core/services/project_service.py` — `ProjectService.init`/`load`/`link`, default home resolution.
- `src/videodoc/core/storage/filesystem.py` — idempotent folder/file creation helpers.
- `src/videodoc/cli/commands/init.py` — `videodoc init` command.

## Design decisions
- The canonical `config.yaml` schema is the full one from README §30, not the simplified example in §14 (confirmed with the project owner) — the §14 example is illustrative only.
- `slugify()` stays a dependency-free utility raising a plain `ValueError`; `ProjectService` translates that into the domain exception `InvalidProjectNameError` at its single call site, so the CLI only ever needs to catch domain exceptions from `core.errors`.
- `sources.yaml` is created as an empty placeholder (`# Populated by 'videodoc scan'`), not a pre-defined schema — that schema belongs to the (not yet implemented) `scan` step.
- Canonical project identifier: the slug, always — see `docs/features/slugify.md` for the full rule and the two regressions it closes (registry key mismatch between `init`/`link`; unintended aliasing when re-initializing a path that already holds a different project).

## CLI

```bash
videodoc init corso-software-x
# Project 'corso-software-x' initialized at C:\Users\<user>\VideoDocRAG\projects\corso-software-x
# Registered as 'corso-software-x' in the local project registry.

videodoc init corso-software-x --path "D:\Corsi\corso-software-x"
```

Re-running `init` on the same project is safe and reports "already initialized" without touching the existing `config.yaml`.

## Tests
- Unit: `tests/core/test_config.py`, `tests/core/test_filesystem.py`, `tests/core/test_project_service.py`.
- CLI: `tests/cli/test_cli_project_commands.py` (init variants: default path, `--path`, idempotent rerun, path/name conflict).
- Manual: see `docs/CHANGELOG.md` entry and the project plan's PowerShell walkthrough (Track A/B) for end-to-end verification, including folder inspection and `config.yaml` content checks.
