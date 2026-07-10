# External source paths (`paths.videos`/`attachments`/`codebase`)

## Summary
A VideoDocRAG project's video/attachment/codebase material can live in a folder external to the project (referenced, not copied) instead of always being physically inside `projects/<slug>/videos/` etc. This mirrors how professional video editing tools (Premiere/Resolve) reference external media rather than duplicating it, and was driven by a real usage scenario: a user's workshop recordings already living in an existing folder elsewhere on disk.

## What was implemented
- `config.paths.videos` / `attachments` / `codebase` accept either a clean relative path (default, resolved under the project folder) or a fully absolute path (an external source). `config.paths.workdir` / `indexes` / `output` / `database` remain always-relative — this is the same distinction already established for data isolation in the project-registry step (generated/derived data must stay physically inside the project; source material may live anywhere).
- `core/utils/paths.py` (new): the single, shared definition of how VideoDocRAG classifies a path string — `is_external_source_path`, `has_any_anchor`, `has_ambiguous_anchor`, `has_parent_traversal`. All four are implemented purely with `PureWindowsPath` (never the platform-dependent `Path`), because **VideoDocRAG and its `config.yaml` format are Windows-only for now** (see README §1, `RUN.md`) — this module states that scope explicitly and is the one place to extend it later if that ever changes, instead of several independent implementations drifting apart.
  - Used by **both** the `PathsSection` Pydantic validators (`core/config.py`) **and** path resolution (`core/storage/filesystem.py::resolve_source_path`, `core/services/scan_service.py::SourceScanService._resolve_report`). Before this module existed, validation used `PureWindowsPath` but resolution used the platform-dependent `Path` — harmless on the current Windows-only deployment (`Path` *is* `PureWindowsPath` there), but a config validated as "external" could have silently resolved as "relative" (or vice versa) had the same code ever run on a non-Windows host. Sharing one implementation makes that impossible by construction, not just by convention.
- Two Pydantic validators on `PathsSection`:
  - `workdir`/`indexes`/`output`/`database` reject **any anchored form** (`has_any_anchor`), including Windows forms `pathlib` does not classify as absolute but which can still escape the project folder when joined with it: drive-relative (`C:foo`), root-relative (`\foo`, `/foo`), on top of the obviously-absolute `C:\foo`. They also reject **`..` parent-traversal segments** (`../outside`, `sub/../../outside`, via `has_parent_traversal`): an anchor-free relative value can still escape `project_dir` once joined with it by walking upward, which the anchor check alone doesn't catch.
  - `videos`/`attachments`/`codebase` accept a clean relative path or a fully absolute path, but reject the same ambiguous semi-absolute forms (`has_ambiguous_anchor`: `C:foo`, `\foo`, `/foo`) — these are neither safely relative-to-project nor an explicit external reference; their resolution would depend on mutable per-process/per-drive state. They also reject `..` in a **relative** value for the same escaping reason (a `..` inside an already-absolute value is fine — it's never joined with `project_dir`, so it resolves unambiguously on its own, checked via `is_external_source_path(v)`).
- `ProjectConfig.default()` is now "safe" like `ProjectConfig.load()`: it wraps `pydantic.ValidationError` into `InvalidConfigError`. Without this, `videodoc init --videos "C:foo"` would have propagated a raw Pydantic traceback to the CLI instead of a clean, readable error.
- `videodoc init` gains `--videos`/`--attachments`/`--codebase` options to set an external path already at creation time. On a fresh project they're written into `config.yaml`; on a rerun of an already-initialized project they are **ignored** (the same rule already in effect for `--language`: `init` never overwrites an existing `config.yaml`) but with an explicit warning listing which flags were ignored — never a silent drop. Exit code stays 0, consistent with the existing "already initialized" rerun behavior.
- `ProjectService.init()` validates the new `config.yaml` (via `ProjectConfig.default(...)`) **before** creating any folder or `sources.yaml` for a fresh project. An invalid `--videos`/`--attachments`/`--codebase` therefore leaves nothing on disk — matching the fail-fast, no-partial-state rule already applied to the registry conflict check that runs earlier in the same method.
- `core/storage/filesystem.py::resolve_source_path(project_dir, configured)` is the single resolution point: absolute → used directly; relative → resolved under `project_dir`. It never checks existence — that's `SourceScanService`'s job (see `docs/features/scan.md`), since a missing external source (e.g. a disconnected drive) must never crash a command.

## Main files
- `src/videodoc/core/utils/paths.py` — the shared path-classification helpers.
- `src/videodoc/core/config.py` — the two `PathsSection` validators (now delegating to `core/utils/paths.py`), `ProjectConfig.default()`.
- `src/videodoc/core/storage/filesystem.py` — `resolve_source_path`.
- `src/videodoc/core/services/project_service.py` — `ProjectService.init(videos=, attachments=, codebase=)` (config validated before any filesystem write), `ProjectInitResult.ignored_source_overrides`.
- `src/videodoc/core/services/scan_service.py` — `SourceScanService._resolve_report` (uses the same shared helper for `is_external`).
- `src/videodoc/cli/commands/init.py` — the three new options.

## Trade-off, stated explicitly
A project with an external source path is no longer a single self-contained folder you can zip and move in one step — moving the project folder does not bring the external video/attachment/codebase material with it. This is a conscious choice, not a silent gap: the isolation guarantee established for generated data (`project.db`, the Qdrant index) is untouched — only source material can be external, and only when the user explicitly asks for it.

## CLI

```bash
videodoc init corso-software-x --videos "D:\Corsi\Workshop"
# Project 'corso-software-x' initialized at ...
# Registered as 'corso-software-x' in the local project registry.

videodoc init corso-software-x --videos "D:\Altro"
# Project 'corso-software-x' already initialized at ... (config.yaml kept unchanged)
# Warning: --videos ignored: config.yaml already exists and 'init' never overwrites it.
```

## Tests
- Unit: `tests/core/test_paths.py` (the shared helpers directly), `tests/core/test_config.py` (`test_internal_paths_reject_any_anchored_form`, `test_internal_paths_reject_parent_traversal`, `test_source_paths_reject_ambiguous_windows_forms`, `test_source_paths_reject_relative_parent_traversal`, `test_source_paths_accept_parent_traversal_inside_true_absolute`, `test_source_paths_accept_true_absolute`, `test_source_paths_accept_clean_relative`, `test_load_missing_file_raises_invalid_config_error`), `tests/core/test_filesystem.py` (`resolve_source_path` variants), `tests/core/test_project_service.py` (`--videos` on fresh vs. rerun, invalid value raising `InvalidConfigError`, `test_init_invalid_videos_option_creates_nothing_on_disk`).
- CLI: `tests/cli/test_cli_project_commands.py` (`test_init_with_videos_option_end_to_end`, `test_init_invalid_videos_option_fails_cleanly`, `test_init_rerun_with_videos_option_prints_warning`).
- Manual: PowerShell walkthrough with a real external folder, a `..`-traversal rejection with no partial state, and a disconnected-drive scenario (`Z:\...`), the one case not reliably reproducible by an automated cross-platform test.
