# Frame and screenshot extraction (`videodoc frames`)

## Summary
`videodoc frames <project>` is README §18's "Fase 5 — Estrazione frame e screenshot": for every video already registered with `videodoc ingest`, it selects a set of interesting timestamps, extracts the corresponding frames with FFmpeg into `workdir/<id>/frames/frame_NNNN.jpg`, records them in `workdir/<id>/frames/frames.json` and the project's `project.db` (`frames` table), and updates that video's `metadata.json`. It is idempotent: if `frames.json` already exists, neither FFmpeg nor PySceneDetect is invoked for that video.

Only `id`/`video_id`/`timestamp_seconds`/`image_path`/`perceptual_hash` are populated by this phase. `ocr_text`/`ocr_confidence`/`contains_code` stay `NULL`/`0` until the OCR (README §19) and code-detection (README §20) phases fill them in.

## Timestamp selection
Three signals feed into one merged, deduplicated list of extraction timestamps per video (`core/utils/frame_selection.py::select_frame_timestamps`):

- **Fixed interval** (`frames.interval_seconds`, default 8s) — always computed; the guaranteed pacing baseline.
- **Scene changes** (`frames.scene_detection`, default on) — detected with PySceneDetect's `ContentDetector` (`core/utils/scene_detection.py`), not a hand-rolled ffmpeg filter: README §7.2 recommends PySceneDetect explicitly, and its Python API is more precise than threshold-tuning ffmpeg's own `scene` filter by hand.
- **Transcript keywords** (`frames.keyword_boost`, default on) — one candidate per transcript segment (from `transcript_segments`, if `videodoc transcribe` already ran for that video) containing a word from README §18.3's list (`codice`, `comando`, `terminale`, `funzione`, `classe`, `file`, `configurazione`, `errore`, `copiamo`, `incolliamo`, `eseguiamo`), taken at the segment's midpoint.

Candidates are merged chronologically: a candidate within `MIN_FRAME_GAP_SECONDS` (2.0s) of the last *kept* candidate is dropped unless it has strictly higher priority (keyword > scene > interval), in which case it replaces the kept one. A defensive `MAX_FRAMES_PER_VIDEO` cap (2000) keeps the highest-priority candidates first if a pathological config would otherwise request too many.

## Extraction and matching
`core/utils/ffmpeg.py::extract_frames` builds one `select='between(t,t0-w,t0+w)+...',showinfo` filter for the whole merged timestamp list (one FFmpeg call per video, not one per timestamp) and parses each written frame's real `pts_time` back out of `showinfo`'s stderr output — the authoritative timestamp, since the nearest actual frame does not always land exactly on the requested time. The filter expression is written to a script file and passed via `-filter_script:v` instead of inline, to stay well under OS command-line length limits even at the `MAX_FRAMES_PER_VIDEO` cap.

Because the `between(...)` window can match more than one real frame (e.g. a high-fps source), `core/utils/frame_selection.py::match_frames_to_candidates` reduces the raw extracted set back down to one frame per candidate (nearest match within the shared `FRAME_MATCH_WINDOW_SECONDS` window); a candidate with no frame in range (e.g. past the last decodable frame) is simply dropped, not an error.

## Perceptual hash and adjacent-frame dedup
`core/utils/frame_hash.py::average_hash` computes a 64-bit spatial aHash (Pillow-decoded 8x8 grayscale thumbnail, one bit per pixel relative to the thumbnail's own mean) plus an 8-bit quantized mean-brightness suffix. The brightness suffix exists because plain aHash has a real blind spot this phase actually hits: any perfectly flat image (a blank terminal, a solid-color slide — common in screen recordings) has every pixel equal to its own mean, so two *different* flat colors hash identically on spatial bits alone.

`is_near_duplicate(hash_a, hash_b)` decides "same frame" with two separate checks, not one Hamming distance over the whole concatenated hash: spatial Hamming distance `<= HASH_DEDUP_MAX_DISTANCE` (4/64 bits) **and** brightness difference `<= BRIGHTNESS_DEDUP_MAX_DELTA` (10/255), compared numerically. This split matters: raw bit-XOR distance on a magnitude value (the brightness byte) does not correlate with numeric closeness (e.g. two brightness values that differ by dozens can still differ in only a handful of bits), so folding brightness into a single combined Hamming distance would have silently let two visually very different flat-colored frames (discovered via a real red-to-blue hard-cut test video) count as duplicates.

`FrameExtractionService._dedup_by_hash` only ever drops a *boosted* (scene/keyword) frame that is near-duplicate of the immediately preceding *kept* frame — an interval frame is never dropped, since it is the guaranteed baseline. This is adjacent-frame dedup only; content-level dedup across the whole video is README §20.3's job, a later phase.

## What was implemented
- `core/utils/frame_selection.py` — `FrameCandidate`, `select_frame_timestamps`, `match_frames_to_candidates`, `extract_keyword_timestamps`, the hardcoded README §18.3 keyword list.
- `core/utils/scene_detection.py` — `detect_scene_timestamps` (PySceneDetect `ContentDetector`), `scenedetect_available` (checked once per run, not once per video).
- `core/utils/frame_hash.py` — `average_hash`, `hamming_distance`, `is_near_duplicate`.
- `core/utils/ffmpeg.py` — `extract_frames` (single-call `select`+`showinfo` extraction), `FrameExtractionError`.
- `core/models/frame_manifest.py` — `FrameManifest`/`FrameManifestEntry`, the per-video idempotency sidecar (mirrors `transcript.py`).
- `core/storage/database.py` — `frames` table (README §31/§30.3), `FrameRow`, `replace_frames`, `list_transcript_segments` (needed by the keyword boost).
- `core/services/frame_extraction_service.py` — `FrameExtractionService.run()`: per-video `ThreadPoolExecutor`, staging-then-finalize extraction, manifest/DB/metadata writes, self-healing skip path.
- `videodoc frames` exposes `--workers`, `--interval-seconds`, `--scene-detection/--no-scene-detection`, `--keyword-boost/--no-keyword-boost`.
- New dependencies: `scenedetect` (pulls in `opencv-python` as of scenedetect 0.7 — no longer a separate extra) and `Pillow`.

## Main files
- `src/videodoc/core/utils/frame_selection.py` — candidate selection/merge algorithm, frame-to-candidate matching.
- `src/videodoc/core/utils/scene_detection.py` — PySceneDetect wrapper.
- `src/videodoc/core/utils/frame_hash.py` — perceptual hash and near-duplicate decision.
- `src/videodoc/core/utils/ffmpeg.py` — `extract_frames`.
- `src/videodoc/core/models/frame_manifest.py` — idempotency manifest.
- `src/videodoc/core/storage/database.py` — `frames` table and its CRUD.
- `src/videodoc/core/services/frame_extraction_service.py` — orchestration.
- `src/videodoc/cli/commands/frames.py` — CLI command.

## Design decisions
- Scene detection uses PySceneDetect rather than ffmpeg's own `scene` filter — chosen with the user over the lighter ffmpeg-only alternative, following README §7.2's explicit recommendation.
- The keyword list and every tuning threshold (scene detector threshold, min candidate gap, hash-dedup thresholds) are hardcoded module constants, not new `config.yaml` fields — same precedent as `core/storage/filesystem.py::DEFAULT_EXCLUDES`. The only config addition is `frames.workers`, mirroring `audio.workers`/`transcription.workers`.
- `scenedetect` importability is checked once per run (`SceneDetectionUnavailableError`), not once per video — mirrors the existing `shutil.which("ffmpeg")` up-front check.
- A per-video failure (bad codec, corrupt file, scene detection failure) is folded into the result's `errors` tuple and skips that video; it never aborts the whole run.
- No automatic cleanup of stale frames after a video is reingested with different content — same principle already applied to audio/transcripts: delete `frames.json` manually to force re-extraction.

## CLI

```bash
videodoc frames corso-software-x
# Project: corso-software-x
# +---------------+
# | Extracted | 8 |
# | Skipped   | 0 |
# +---------------+

videodoc frames corso-software-x --interval-seconds 5 --no-scene-detection
```

## Tests
- Unit: `tests/core/test_frame_selection.py`, `test_frame_hash.py`, `test_frame_manifest.py`, `test_scene_detection.py`, extended `test_ffmpeg.py`/`test_database.py`.
- Service: `tests/core/test_frame_extraction_service.py`, including structural errors, fresh extraction, idempotent skip/self-heal, per-video error isolation, keyword-boost graceful degradation, and the real (non-stubbed) hash-dedup pass.
- CLI: `tests/cli/test_cli_frames_command.py`.
- Verified end-to-end against real `ffmpeg`/PySceneDetect with a synthetic test video (including a hard color-cut clip, which is what surfaced the flat-image hashing bug fixed by the brightness suffix).
