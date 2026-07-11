# Frame and screenshot extraction (`videodoc frames`)

## Summary
`videodoc frames <project>` is README section 18's frame extraction phase. For every video already registered with `videodoc ingest`, it selects interesting timestamps, extracts frames with FFmpeg into `workdir/<id>/frames/frame_NNNN.jpg`, records them in `workdir/<id>/frames/frames.json` and the project's `project.db` (`frames` table), and updates that video's `metadata.json`.

It is idempotent by semantic settings, not just by file presence: an existing `frames.json` is skipped only when its effective `interval_seconds`/`scene_detection`/`keyword_boost` match the current run, and when scene detection is enabled its stored `scene_threshold` also matches. `hwaccel` is deliberately not stored or compared because it only changes performance, not selected timestamps.

Only `id`/`video_id`/`timestamp_seconds`/`image_path`/`perceptual_hash` are populated by this phase. `ocr_text`/`ocr_confidence` stay `NULL` until `videodoc ocr` runs; `contains_code` stays `0` until the future code-detection phase fills it in.

## Timestamp selection
Three signals feed into one merged, deduplicated timestamp list per video (`core/utils/frame_selection.py::select_frame_timestamps`):

- **Fixed interval** (`frames.interval_seconds`, default 8s): always computed; the guaranteed pacing baseline.
- **Scene changes** (`frames.scene_detection`, default on): detected with FFmpeg's `select=gt(scene\,threshold)` filter after downscaling the decode path to 320px wide for speed. The configurable threshold is `frames.scene_threshold` / `--scene-threshold` on FFmpeg's native 0..1 scene-score scale.
- **Transcript keywords** (`frames.keyword_boost`, default on): one candidate per transcript segment containing a README section 18.3 keyword, taken at the segment midpoint.

Candidates are merged chronologically. A candidate within `MIN_FRAME_GAP_SECONDS` (2.0s) of the last kept candidate is dropped unless it has strictly higher priority (keyword > scene > interval), in which case it replaces the kept one. `MAX_FRAMES_PER_VIDEO` still caps pathological configurations.

## Scene detection
`core/utils/scene_detection.py::detect_scene_timestamps` runs FFmpeg directly, streams `metadata=print:file=-` output from stdout, parses `pts_time:` values, and drains stderr on a side thread so long videos cannot deadlock on pipe buffers.

CPU path:

```text
ffmpeg -hide_banner -nostats -loglevel error -threads N -i <video> -an -sn -dn \
  -vf scale=320:-2:flags=fast_bilinear,select=gt(scene\,THR),metadata=print:file=- \
  -f null -
```

CUDA path:

```text
ffmpeg -hide_banner -nostats -loglevel error -hwaccel cuda -hwaccel_output_format cuda -i <video> -an -sn -dn \
  -vf scale_cuda=320:-2,hwdownload,format=nv12,select=gt(scene\,THR),metadata=print:file=- \
  -f null -
```

A scene-detection failure is a per-video warning, not a structural command failure. There is no Python scene-detection package dependency anymore.

## Extraction and matching
`core/utils/ffmpeg.py::extract_frames` still builds one `select='between(t,t0-w,t0+w)+...',showinfo` filter for the merged timestamp list, writes it to `select.filter`, and parses each written frame's real `pts_time` from `showinfo`. The extraction output path and quality (`-qscale:v 2`) are unchanged.

When `hwaccel='cuda'`, `extract_frames` only adds `-hwaccel cuda` before `-i`; it does not force `h264_cuvid` or any codec-specific decoder. `FrameExtractionService` owns the retry policy: CUDA failures are retried once on CPU, with staged partial frame files removed before the CPU retry.

## CUDA scheduling
`frames.hwaccel` / `--hwaccel` accepts `auto`, `cuda`, or `none`.

- `none`: always use CPU decode.
- `auto`: use CUDA only when `ffmpeg -hwaccels` lists `cuda`, a GPU probe succeeds, and a non-blocking GPU decode slot is available; otherwise use CPU.
- `cuda`: try CUDA with a blocking slot acquire, then retry the failed pass once on CPU if FFmpeg fails.

GPU decode concurrency is capped by `FFMPEG_GPU_DECODE_SESSIONS` (currently 3) so a high `--workers` value does not start too many simultaneous NVDEC passes on an 8GB laptop GPU.

## Perceptual hash and adjacent-frame dedup
`core/utils/frame_hash.py::average_hash` computes a spatial aHash plus a brightness suffix. `_dedup_by_hash` now precomputes hashes in parallel for larger batches but preserves the original sequential adjacent comparison: only boosted scene/keyword frames can be dropped as near-duplicates of the immediately preceding kept frame. Interval frames remain the guaranteed baseline.

## Main files
- `src/videodoc/core/utils/scene_detection.py` - FFmpeg scene filter wrapper.
- `src/videodoc/core/utils/ffmpeg.py` - frame extraction and CUDA availability probe.
- `src/videodoc/core/models/frame_manifest.py` - idempotency manifest, including `scene_threshold`.
- `src/videodoc/core/services/frame_extraction_service.py` - orchestration, CUDA slotting, CPU fallback, manifest/DB/metadata writes.
- `src/videodoc/cli/commands/frames.py` - CLI command and overrides.

## Tests
- Unit: `tests/core/test_frame_selection.py`, `test_frame_hash.py`, `test_frame_manifest.py`, `test_scene_detection.py`, `test_ffmpeg.py`.
- Service: `tests/core/test_frame_extraction_service.py`, including settings idempotency, threshold-triggered re-extraction, legacy manifests, CUDA fallback, CPU fallback when GPU slots are saturated, OCR column preservation, and zero-surviving-frames errors.
- CLI: `tests/cli/test_cli_frames_command.py`.