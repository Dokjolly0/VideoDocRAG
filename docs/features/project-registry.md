# Project registry and portable project paths

## Summary
Since a VideoDocRAG project can live anywhere on disk (README §4.7/§8.1.2) rather than inside the program's own folder, a small local registry maps project names to absolute paths, so CLI commands can keep referring to projects by short name.

## What was implemented
- `ProjectRegistry` (JSON file, one entry per project: `name -> {path, created_at}`), stored outside both the program and any project folder, via `platformdirs.user_data_dir("videodoc", appauthor=False)` — overridable with `VIDEODOC_DATA_DIR` for tests/sandboxing.
- Resolution cascade used by `ProjectService.load()` (README §8.1.2): (a) a valid path with `config.yaml` is used directly, even if unregistered; (b) otherwise the reference is looked up by name in the registry; (c) otherwise a clear error suggesting `videodoc list`.
- Registry robustness: the file is created lazily (never on a pure read), writes are atomic (`.tmp` + `replace`), and a corrupted/invalid registry file is quarantined (renamed to `registry.json.corrupted-<timestamp>`) with a warning instead of crashing any command.
- Conflict handling: registering the same name at a different path raises `RegistryConflictError` — checked *before* any folder is created on disk (fail-fast, no partial state).
- CLI commands: `videodoc list`, `videodoc link <path>`, `videodoc unlink <name>` (registry-only, never deletes files), `videodoc path <name>`.

## Main files
- `src/videodoc/core/services/registry_service.py` — `ProjectRegistry`.
- `src/videodoc/core/services/project_service.py` — resolution cascade (`ProjectService.load`), `link`.
- `src/videodoc/cli/commands/{list_projects,link,unlink,path}.py`.
- `src/videodoc/cli/output.py` — shared console helpers.

## Design decisions
- `videodoc path` only consults the registry (not the full resolution cascade), matching its README description ("prints the absolute path of a *registered* project").
- `videodoc path` prints via plain `typer.echo`, not `rich`'s `console.print`: rich defaults to wrapping text at 80 columns when stdout isn't a real terminal (e.g. under test runners or when piped), which would corrupt a long path used programmatically (`cd (videodoc path myproj)`).
- The shared `rich.Console` instances in `cli/output.py` use `soft_wrap=True` for the same reason — status/error messages are log lines and must never be hard-wrapped mid-sentence just because an embedded path is long.
- The `list` table's Path column uses `overflow="fold"` instead of the rich default (crop + ellipsis): on narrow/legacy consoles the ellipsis character didn't render correctly on this Windows setup, silently truncating the very information the command exists to show.

## Environment note (Windows, Microsoft Store Python)
On a machine where `python`/`pip` resolve to the Microsoft Store package (`PythonSoftwareFoundation.Python.3.13_...`), Windows silently virtualizes writes under `%LOCALAPPDATA%` into a private per-package cache folder, invisible to PowerShell/Explorer/other processes. `platformdirs`/our code is correct — this is host-environment behavior specific to Store-distributed Python, not present with the official python.org distribution or inside a future packaged executable. Development on this project now uses the official interpreter (`...\AppData\Local\Programs\Python\Python313\python.exe`) to avoid the ambiguity.

## CLI

```bash
videodoc list
videodoc link "D:\Corsi\corso-software-x"
videodoc unlink corso-software-x
videodoc path corso-software-x
```

## Tests
- Unit: `tests/core/test_registry_service.py` (idempotency, conflicts, corruption recovery, env var override), `tests/core/test_project_service.py` (resolution cascade).
- CLI: `tests/cli/test_cli_project_commands.py` (`list`/`link`/`unlink`/`path`, including the end-to-end flow test).
- Manual: PowerShell walkthrough covering idempotent `init`, path conflicts, `link`/`unlink` round-trip, invalid `config.yaml`, corrupted registry recovery, and both the sandboxed (`VIDEODOC_HOME`/`VIDEODOC_DATA_DIR`) and real default-path scenarios.
