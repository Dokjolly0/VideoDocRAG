# Source scanning (`videodoc scan`)

## Summary
`videodoc scan <project>` enumerates a project's video/attachment/codebase sources (internal or external — see `docs/features/external-source-paths.md`), applies the exclusion rules already configurable via `config.scan`, and writes `sources.yaml`. It stays pure filesystem + Pydantic — no hashing, no indexing, no heavy dependencies (README §37.8); those belong to later ingestion/embedding steps.

## What was implemented
- `DEFAULT_EXCLUDES` (README §8.3, 35 entries, grouped by ecosystem: VCS, JS/TS/Node, Python, .NET/C#, JVM, Go/PHP, Dart/Flutter, iOS/Swift, IDE/editor state) plus `resolve_excludes()`/`split_excludes()` implementing the merge rule `default_excludes ? DEFAULT_EXCLUDES : {} , + add_excludes, - remove_excludes`, split into directory names (trailing `/`) and file patterns (fnmatch, covering both exact names like `.DS_Store` and globs like `*.min.js`). Directory names are matched exactly, not via fnmatch, so a variable-suffix build directory (CMake's `cmake-build-<type>/`, Python's `*.egg-info/`) is not covered — would need glob-capable directory matching, not implemented. `packages/` is deliberately excluded from this list despite being a legacy NuGet artifact folder, because it is also the standard source directory in JS/TS monorepos (Yarn/npm/pnpm workspaces, Lerna, Turborepo, Nx) — the one case in this list where "exclude by default" would risk hiding real code instead of just noise.
- A pruning directory walker (`_walk_files`): excluded directories are removed from `os.walk`'s `dirnames` *before* it descends into them, not filtered after walking everything — essential for `node_modules/` with tens of thousands of files. `follow_symlinks=False` also excludes individual symlinked files, not just symlinked directories (`os.walk(followlinks=...)` only controls directory descent; a symlinked file still shows up in `filenames` regardless).
- `_walk_files` passes an `onerror` callback to `os.walk`. Without one, `os.walk` silently skips any subdirectory it can't `scandir()` into (e.g. permission denied) with zero indication anything was missed — a scan could produce an incomplete `sources.yaml` that looks complete. Errors are collected (not raised: one inaccessible subdirectory shouldn't abort an otherwise-successful scan) and flow up through `scan_videos`/`scan_attachments`/`scan_codebase`'s optional `errors` parameter into `SourceManifest.scan_errors` (prefixed per source, e.g. `"codebase: [Errno 13] Permission denied: '...'"`) and are printed as CLI warnings — never silently lost.
- `scan_videos`/`scan_attachments`/`scan_codebase` (`core/storage/filesystem.py`): videos and codebase are extension-filtered (`scan.allowed_video_extensions`, new field; `scan.allowed_code_extensions`, case-insensitive both), attachments are not (it's already a folder the user chose for heterogeneous material — PDFs, slides, zips, notes). `scan_codebase` additionally respects `max_file_size_mb` (codebase only — videos are physiologically GB-sized) and skips a file whose `.stat()` fails (e.g. a broken symlink) instead of crashing the whole scan.
- `codebase_is_present()`: independent of exclusions, checks whether the folder has *any* entry — a fresh project's empty `codebase/` stub (always created by `ensure_project_structure`) must read as "not present", and a real codebase made entirely of `node_modules/` must still read as "present" even though its files list ends up empty. `root.is_dir()` succeeding only means the entry is a directory *by type*; it doesn't guarantee `os.scandir(root)` can actually list it (e.g. permission denied on an external/network location). Without catching that, it would propagate uncaught and crash the whole `videodoc scan` *before* `scan_codebase()`'s own `onerror`-based error collection ever ran — since `codebase_is_present()` gates whether `scan_codebase()` is even called. It now shares the same `errors` list as `scan_codebase()` (both write into one `SourceScanService`-owned list, prefixed `"codebase: ..."`), so a problem reading the root itself and a problem reading a subdirectory mid-walk both end up reported the same way.
- `core/models/source_manifest.py::SourceManifest` — the schema for `sources.yaml`: `scanned_at`, `videos`/`attachments` (absolute posix paths), `codebase: {present, files}`, `exclusions: {directories, file_patterns}` (both halves of the effective exclusion set, not just directories — a `sources.yaml` audit needs to answer "why wasn't this file included" even when the reason is a file pattern), `scan_errors` (walk problems, see above). Always fully regenerated on scan, never merged with a prior version — unlike `config.yaml`.
- `core/services/scan_service.py::SourceScanService(project_dir, config).run() -> ScanResult` — resolves all three source paths, reports whether each is `is_external`, `exists`, and `is_directory` (kept separate so the CLI can distinguish "path not found at all" from "path exists but is a file, not a directory" — two different debugging situations that a single `exists` boolean would conflate).
- `videodoc scan` CLI: reports counts, marks external sources with `(external: <path>)`, warns (never fails, exit code stays 0) when an external source is missing or not a directory, for **all three** sources (videos/attachments/codebase), not just videos.

## Main files
- `src/videodoc/core/storage/filesystem.py` — exclusions, walker, enumerators.
- `src/videodoc/core/models/source_manifest.py` — `SourceManifest`, `CodebaseManifest`, `ExclusionsManifest`.
- `src/videodoc/core/services/scan_service.py` — `SourceScanService`.
- `src/videodoc/cli/commands/scan.py` — the `videodoc scan` command.

## Design decisions
- Zero videos found does not fail `scan` — it's ingestion's job (a future step), not scan's, to refuse to proceed without videos.
- A missing or non-directory external source never crashes or fails `scan` (exit code 0): 0 files found plus an explicit warning. Distinguishing "not found" from "exists but is a file" required a dedicated `is_directory` field on `SourcePathReport` separate from `exists`.
- `codebase.files`/`videos`/`attachments` are stored as absolute posix paths uniformly, even for codebase entries. A future relative-to-codebase-root form (for citations like `codebase/src/app/main.py#L24-L58`) is a single `.relative_to()` away once that step actually needs it — no reason to anticipate a mixed representation now.

## CLI

```bash
videodoc scan corso-software-x
# Project: corso-software-x
# +----------------------------------+
# | Videos      | 8 found            |
# | Attachments | 3 found            |
# | Codebase    | present (42 files) |
# +----------------------------------+
# Excluded directories: .git, node_modules, __pycache__, dist, build, ...
# Excluded file patterns: .DS_Store
# Sources manifest updated: sources.yaml
```
(The summary is a Rich table — box-drawing characters on a terminal that supports them, the ASCII fallback shown above on legacy Windows consoles.)

## Tests
- Unit: `tests/core/test_filesystem.py` (exclusions, pruning, extension filters, `max_file_size_mb`, symlink handling, `test_scan_codebase_collects_walk_errors_without_crashing`, `test_codebase_is_present_handles_unreadable_directory_without_crashing`), `tests/core/test_source_manifest.py` (roundtrip, missing/invalid file), `tests/core/test_scan_service.py` (internal/external videos, missing/non-directory external path, zero videos, codebase presence with exclusions, manifest always regenerated, `test_scan_errors_are_collected_and_prefixed_by_source`, `test_scan_unreadable_codebase_root_does_not_crash`).
- CLI: `tests/cli/test_cli_scan_command.py` (internal/external/missing/non-directory sources for all three source types, `node_modules` exclusion end-to-end, `test_scan_reports_walk_errors_as_warnings_without_failing`, `test_scan_unreadable_codebase_root_warns_without_crashing`, unknown project).
- Manual: PowerShell walkthrough including the one scenario not reliably reproducible by an automated cross-platform test — a genuinely disconnected Windows drive letter (`Z:\...`).
