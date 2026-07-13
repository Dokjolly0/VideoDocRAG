# Video ingestion (`videodoc ingest`)

## Summary
`videodoc ingest <project>` is README §15's "Fase 2 — Ingestion dei video": for every video file in `videos/` (internal or external — see `docs/features/external-source-paths.md`), it records a fast filesystem fingerprint (`size` + `mtime_ns` + `inode`), computes a SHA-256 content hash only for new/changed files or when `--verify` is requested, probes duration/format/resolution/codec via `ffprobe`, registers the video in the project's own `project.db` SQLite database (README §31 schema), and creates a per-video `workdir/<id>/{audio,frames,transcript,ocr,chunks}/` plus a `metadata.json`. It is idempotent: an unchanged video is skipped without being rehashed or reprobed; a changed one is reprocessed only after the content hash changes. `ingest` is the first command allowed to require an external tool (`ffprobe`, part of FFmpeg) — `init`/`scan`/`list`/`link`/`unlink`/`path` remain dependency-free (README §37.8).

## What was implemented
- `core/utils/hashing.py::file_fingerprint()` — cheap `stat()`-based guard (`size` + `mtime_ns` + `inode`) used to skip ordinary unchanged reruns without streaming the whole video. `hash_file()` remains the streamed SHA-256 verifier, read in fixed-size blocks rather than loading the whole file at once (videos are routinely hundreds of MB to multiple GB).
- `core/utils/ffprobe.py::probe_video()` — invokes `ffprobe -show_format -show_streams` as a subprocess (not a Python binding library — no new pip dependency) and parses JSON into a `VideoProbeResult` (duration, format, width, height, codec). `VideoProbeError`, its failure type, is deliberately **not** a `VideoDocError`: it's a per-file failure the service always catches and folds into a per-video error list, the same role `slugify()`'s plain `ValueError` plays for a single unslugifiable name — never propagated to the CLI layer. Availability of the `ffprobe` binary itself is a separate, structural concern, checked once up front by `VideoIngestionService` via `shutil.which("ffprobe")` and reported as the domain exception `ExternalToolNotFoundError`.
- `core/storage/database.py` — a thin `sqlite3` wrapper (no ORM): `ensure_schema()` (`CREATE TABLE IF NOT EXISTS videos` per the exact README §31 schema — no `format`/`resolution`/`codec` columns; those, plus the `*_path` pointers, belong in each video's `metadata.json`, the same raw-vs-structured-data split already established by README §4.6), `get_video()`, `upsert_video()`, `update_video_file_fingerprint()`. The upsert uses SQLite's `ON CONFLICT(id) DO UPDATE SET ...` and deliberately **excludes `title` and `created_at`** from the update clause — a reingest triggered by a changed hash must never clobber a title set elsewhere in the pipeline, nor overwrite the video's original first-ingested timestamp with the reprocessing time. These database functions wrap `sqlite3.Error` into a new `DatabaseError(VideoDocError)`, for structural DB failures (disk full, locked file) — distinct from a per-video probe/hash failure, which never aborts the whole run. Connections are opened via `contextlib.closing(sqlite3.connect(...))` chained with `sqlite3.Connection`'s own `with conn:` block: `sqlite3.Connection` used bare as a context manager only wraps commit/rollback, it does **not** close the connection on exit — a well-known stdlib gotcha that was actually caught here via a `ResourceWarning: unclosed database` surfaced by the test suite, not by inspection.
- `core/models/video_metadata.py::VideoMetadata` — the schema for each video's `metadata.json`, mirroring `SourceManifest`'s `load`/`save` triad pattern (`OSError`/`json.JSONDecodeError`/`pydantic.ValidationError` → `InvalidVideoMetadataError`) but JSON, not YAML (per README §9.1's own example format). `width`/`height` are typed `int` fields, not a pre-formatted `"1920x1080"` string — consistent with how every other numeric field in this project's Pydantic models is stored. The five `*_path` fields (`audio_path`, `transcript_path`, `frames_path`, `ocr_path`, `chunks_path`) are **project-relative** posix paths, not absolute — they always live inside `workdir/`, which `PathsSection`'s own validator guarantees stays physically inside the project folder (README §8.1.1: a project must remain a self-contained, movable/archivable unit; an absolute path here would silently break the moment the project folder moves). This is a deliberate divergence from `project.db`'s `VideoRow.path`, which **is** absolute — mirroring `sources.yaml`'s already-solved internal-or-external duality for the video's own source file.
- `core/services/ingest_service.py::VideoIngestionService(project_dir, config).run() -> IngestResult` — the orchestration. Order of operations: resolve `videos/` and enumerate files (reusing `resolve_source_path`/`scan_videos`, the same helpers `scan` uses) → if zero video files, raise `NoVideosFoundError` → **then** check `ffprobe` availability (in that order, not the reverse — an empty project should be told about its own emptiness first, not asked to install FFmpeg for nothing to process yet) → `ensure_schema()` → per video (sorted for determinism): derive `video_id = slugify(stem)` (the same function project slugs use — one canonical identifier, not the three different derivations README's own §9.1/§15 illustrative example uses for "the video's name") → collision check → compute the fast file fingerprint → skip immediately if it matches the stored fingerprint (unless `--verify`) → otherwise hash → skip and refresh the stored fingerprint if the hash is unchanged → probe/reingest only when the hash changed → write workdir + `metadata.json` + upsert DB row.
- Collision detection covers **both** same-run duplicates (two new files whose stems both slugify to the same id) and cross-run duplicates (a `project.db` row from a previous run whose `filename` differs from the current file resolving to the same id) — the latter, if unchecked, would silently overwrite an unrelated video's data. Both raise `VideoIdCollisionError` and stop the run; videos already committed earlier in the same run remain valid (each video's DB upsert + `metadata.json` write is independently idempotent — this is a safe partial completion, not an atomic all-or-nothing batch).
- A reingest (hash changed) never deletes a video's existing `workdir/<id>/{audio,frames,...}` contents — only DB/`metadata.json` are updated, and an explicit warning is emitted noting that sibling artifacts may now be stale and should be refreshed by re-running the relevant later pipeline phase. Same "never delete without being asked" precedent already established by `unlink`.
- Per-video failures (unslugifiable name, unreadable file, corrupt/unsupported video) are collected into `IngestResult.errors` and printed as CLI warnings — the run continues with the remaining videos, exit code stays 0. Only structural failures (`NoVideosFoundError`, `ExternalToolNotFoundError`, `VideoIdCollisionError`, `DatabaseError`, plus the existing `ProjectNotFoundError`/`InvalidConfigError`) go through `print_error` + exit code 1.
- `videodoc ingest` CLI: thin wrapper (`ProjectService.load()` → `VideoIngestionService(...).run()`), exposes `--verify` for full SHA-256 verification even when the fast fingerprint matches, and reports counts (`ingested`/`reingested`/`skipped`) plus the database file touched.

## Main files
- `src/videodoc/core/utils/hashing.py` — `file_fingerprint`, `hash_file`.
- `src/videodoc/core/utils/ffprobe.py` — `probe_video`, `VideoProbeResult`, `VideoProbeError`.
- `src/videodoc/core/storage/database.py` — `ensure_schema`, `get_video`, `upsert_video`, `update_video_file_fingerprint`, `VideoRow`.
- `src/videodoc/core/models/video_metadata.py` — `VideoMetadata`.
- `src/videodoc/core/services/ingest_service.py` — `VideoIngestionService`, `IngestResult`.
- `src/videodoc/core/storage/filesystem.py` — `ensure_video_workdir`, `VIDEO_WORKDIR_SUBDIRS`.
- `src/videodoc/cli/commands/ingest.py` — the `videodoc ingest` command.

## Design decisions
- Zero videos found is a hard failure for `ingest` (`NoVideosFoundError`), unlike `scan`, which treats zero videos as a normal report (exit code 0). README §15.1 is explicit that a missing/empty `videos/` means "the project cannot start the RAG pipeline" — `scan`'s own docs already deferred that refusal to whichever step is the first real pipeline phase (`docs/features/scan.md`: *"it's ingestion's job... to refuse to proceed without videos"*); this is that step, not a new decision made in isolation.
- Idempotency now has a cheap first gate and a strong verification fallback: the stored `file_fingerprint` (`size` + `mtime_ns` + `inode`) skips unchanged-looking reruns without reading multi-GB files; when the fingerprint differs, is missing from an older DB row, or `--verify` is passed, ingest streams the full SHA-256 before deciding whether to skip or reingest.
- No new `config.yaml` section was added for this step (e.g. no `ffprobe_path` override) — `ffprobe` is assumed to be on `PATH`, the same assumption already made for FFmpeg generally (README §7.2). Nothing in README's spec requires a configurable override.

## CLI

```bash
videodoc ingest corso-software-x
# Project: corso-software-x
# +----------------+
# | Ingested   | 3 |
# | Reingested | 0 |
# | Skipped    | 5 |
# +----------------+
# Database updated: project.db
```

A per-video problem or a reingest both surface as warnings, never as a failure:

```bash
videodoc ingest corso-software-x
# Project: corso-software-x
# +----------------+
# | Ingested   | 0 |
# | Reingested | 1 |
# | Skipped    | 7 |
# +----------------+
# Database updated: project.db
# Warning: workshop-05: video content changed and was reingested -- workdir/workshop-05/{audio,frames,transcript,ocr,chunks} may still contain artifacts from the previous version (never deleted automatically); re-run the relevant pipeline phase(s) to refresh them.
```

## Tests
- Unit: `tests/core/test_hashing.py` (fast fingerprint shape, digest correctness, chunking invariance, missing file), `tests/core/test_ffprobe.py` (successful parse, `CalledProcessError`, malformed JSON, no video stream — all via a monkeypatched `subprocess.run`, no real `ffprobe` needed), `tests/core/test_database.py` (schema idempotency and migration, insert/update roundtrip, fingerprint persistence/update, `test_upsert_video_update_preserves_title_and_created_at`, `sqlite3.Error` wrapping), `tests/core/test_video_metadata.py` (roundtrip, invalid JSON/missing file/extra field), `tests/core/test_filesystem.py` (`ensure_video_workdir` idempotency), `tests/core/test_ingest_service.py` (zero videos, missing ffprobe, single video, `test_unchanged_video_is_skipped_without_rehashing_or_reprobing` — asserts no `hash_file()` or `probe_video()` call on the second run, plus `--verify` and fingerprint-refresh coverage, proving idempotency is real and not just a matching end state, reingest without workdir deletion, per-video hash/probe errors not blocking others, same-run and cross-run id collisions, external `paths.videos`).
- CLI: `tests/cli/test_cli_ingest_command.py` (success summary format, unknown project, zero videos, missing ffprobe, per-video error printed as warning without failing, reingest warning).
- Manual: end-to-end run against a real `ffprobe` binary and a real (small, generated) `.mp4` — verified `project.db` row content, `metadata.json` content, idempotent skip on rerun, reingest + warning on a modified file, and fail-fast with zero side effects when `ffprobe` is removed from `PATH`.
