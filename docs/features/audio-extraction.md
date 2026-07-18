# Audio extraction (`videodoc extract-audio`)

## Summary
`videodoc extract-audio <project>` is README §16's "Fase 3 — Estrazione audio": for every video already registered in `project.db` (by `videodoc ingest`), extract mono 16kHz PCM WAV audio via FFmpeg — the standard input format for speech-to-text models — into `workdir/<video_id>/audio/<video_id>.wav`, then update that video's `metadata.json` (`audio_path`) to point at the concrete file. It is idempotent: if the audio file already exists, FFmpeg is never re-invoked for that video. This command implements README §11.1's `AudioExtractionService` and feeds the separate `TranscriptionService`.

## What was implemented
- `core/utils/ffmpeg.py::extract_audio()` — mirrors `core/utils/ffprobe.py`'s exact pattern: a module-level function, a plain-`Exception` subclass (`AudioExtractionError`, deliberately **not** a `VideoDocError` — the same per-item-failure rationale as `VideoProbeError`), built on `subprocess.run([...], capture_output=True, text=True, check=True)` catching `(subprocess.CalledProcessError, OSError)`. Runs `ffmpeg -y -i <video> -vn -acodec pcm_s16le -ar 16000 -ac 1 -f wav <output>` — README §16's exact invocation, plus an explicit `-f wav` because the caller always targets a temporary path ending in `.tmp`, not `.wav`, so FFmpeg's extension-based format auto-detection can't be relied on.
- `core/storage/database.py::list_videos()` — new: every registered video, ordered by id for determinism (mirrors how `ingest` processes `sorted(video_files)`). Returns an empty list, rather than raising, if the `videos` table doesn't exist yet (a `project.db` file present but never fully initialized) — the caller treats that identically to "ingest was never run," not as a structural database error.
- `core/services/audio_extraction_service.py::AudioExtractionService.run() -> AudioExtractionResult` (`extracted`, `skipped`, `errors` tuples). Order of checks: `project.db` doesn't exist → `NoVideosFoundError` (checked via `Path.exists()` **before** any `sqlite3.connect()` call — connecting first would silently create an empty `project.db` file even on this "nothing to do" path, violating the same no-partial-state-on-error rule already established for `ingest`); `project.db` exists but isn't a file (e.g. a directory) → `DatabaseError`; zero rows in `videos` → `NoVideosFoundError`; **then** (after, not before, the emptiness checks — same ordering `ingest` already established) `shutil.which("ffmpeg") is None` → `ExternalToolNotFoundError`.
- **Atomic write, not a direct write to the final path.** FFmpeg writes to `<id>.wav.tmp`, and only `Path.replace()` (atomic on both POSIX and Windows when source/destination share a directory) moves it onto `<id>.wav`, only after FFmpeg exits successfully. Without this, an FFmpeg process interrupted mid-write (Ctrl+C, disk full, crash) would leave a partial/corrupt file at exactly the path the idempotency check looks at — from that point on it would be read as "already extracted" forever, with no CLI-level way to detect or fix it (this project has no `--force` flag anywhere, by design). On any failure (FFmpeg itself, or the `replace()` call), the `.tmp` leftover is removed (`unlink(missing_ok=True)`) so a future run retries cleanly instead of being fooled by a stray partial file.
- **Idempotency is "does the final file exist," not "is metadata.json already correct."** When `<id>.wav` already exists, FFmpeg is never re-invoked, but `metadata.json` is still reconciled: if `audio_path` already points at the concrete file, nothing is written; if it still holds `ingest`'s original folder-only placeholder (`workdir/<id>/audio`) or any other stale value, it's corrected in place — "skipped" means the on-disk state is fully correct, not just "we didn't bother." If `metadata.json` can't be loaded (missing/corrupt) or saved (e.g. permission denied) during this reconciliation, the video is reported in `errors` instead of `skipped`, with a message noting the audio file itself is fine.
- A `metadata.json` failure **after a successful fresh extraction** is handled the same way: not counted as `extracted` (the unit of work — audio produced *and* metadata pointing at it — isn't complete), reported in `errors`, and explicitly worded to make clear the `.wav` file itself was written correctly. **Documented trade-off**: because the final `.wav` now exists, the *next* run's idempotency check will skip re-running FFmpeg for that video — the metadata-reconciliation attempt still runs (see previous point), so a transient permission problem self-heals on a later run, but a persistent one (e.g. `metadata.json` genuinely corrupted) resurfaces the identical warning every time until the user repairs it manually. Same "skip means skip, no automatic destructive retry" philosophy already applied to `ingest`'s own unchanged-hash skip (not even reprobed).
- Per-video FFmpeg failures (corrupt/unsupported source video) are collected into `errors` and printed as CLI warnings — the run continues with the remaining videos, exit code stays 0. Only structural failures (`NoVideosFoundError`, `ExternalToolNotFoundError`, `DatabaseError`, plus the existing `ProjectNotFoundError`/`InvalidConfigError`) are fatal (exit 1).
- No new `config.yaml` section: FFmpeg's sample rate/channels/format/container stay hardcoded exactly as README §16 specifies. Nothing in the spec requests them configurable, and no analogous config section (unlike `TranscriptionSection`/`FramesSection`/`OCRSection`) exists anywhere for this phase.
- `videodoc extract-audio` CLI: thin wrapper (`ProjectService.load()` → `AudioExtractionService(...).run()`), reports counts (`extracted`/`skipped`) and prints each `errors` entry as a warning.

## Main files
- `src/videodoc/core/utils/ffmpeg.py` — `extract_audio`, `AudioExtractionError`.
- `src/videodoc/core/storage/database.py` — `list_videos` (new).
- `src/videodoc/core/services/audio_extraction_service.py` — `AudioExtractionService`, `AudioExtractionResult`.
- `src/videodoc/cli/commands/extract_audio.py` — the `videodoc extract-audio` command.

## Design decisions
- Audio filename = `<video_id>.wav` (the same `slugify()`-derived canonical id already used for the DB primary key and the workdir folder name since `ingest`), not the fuller filename stem README's own §9.1 example inconsistently mixes in. One identifier throughout, not a second naming scheme.
- No `--force`/`--overwrite` flag to re-trigger extraction for a video whose `.wav` already exists — deleting the file manually is the only explicit way to request re-extraction, consistent with the rest of this CLI's no-destructive-defaults design.
- A video whose source hash changed via `ingest`'s reingest path is not specially detected here — `ingest` already warns on reingest that sibling workdir artifacts (including `audio/`) may be stale; re-extracting requires manually deleting the old `.wav` first.

## CLI

```bash
videodoc extract-audio corso-software-x
# Project: corso-software-x
# +---------------+
# | Extracted | 8 |
# | Skipped   | 0 |
# +---------------+

videodoc extract-audio corso-software-x
# Project: corso-software-x
# +---------------+
# | Extracted | 0 |
# | Skipped   | 8 |
# +---------------+
```

A missing `project.db` (ingest never run) or a missing `ffmpeg` binary both fail fast with zero side effects:

```bash
videodoc extract-audio corso-software-x
# Error: No videos registered in project.db -- run 'videodoc ingest' first.
```

## Tests
- Unit: `tests/core/test_ffmpeg.py` (expected FFmpeg argv including `-f wav`, `CalledProcessError`/`OSError` → `AudioExtractionError`), `tests/core/test_database.py` (`list_videos` empty/ordered/missing-table/`DatabaseError`), `tests/core/test_audio_extraction_service.py` (no `project.db` yet creates nothing, empty DB, `project.db` as a directory, missing ffmpeg with zero side effects, single video updates `metadata.json`, skip-with-zero-`extract_audio`-calls, skip reconciling a stale placeholder, one bad video doesn't block others, a partial-write failure leaves no stray `.wav`, missing/corrupt `metadata.json` after successful extraction still counts the `.wav` as written, `Path.replace()` failure cleans up the `.tmp`, `VideoMetadata.save()` failure reported as an error).
- CLI: `tests/cli/test_cli_extract_audio_command.py` (success summary, unknown project, no ingested videos, missing ffmpeg, per-video error as a non-fatal warning, rerun shows everything skipped).
- Manual: end-to-end run against real `ffmpeg`/`ffprobe` binaries and a small generated `.mp4` — verified the produced `.wav` (`pcm_s16le`, 16000 Hz, mono via `ffprobe`), `metadata.json`'s updated `audio_path`, and idempotent skip on rerun.
