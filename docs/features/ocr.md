# OCR of extracted screenshots (`videodoc ocr`)

## Summary
`videodoc ocr <project>` is README §19's "Fase 6 — OCR delle schermate": for every video with frames already extracted (`videodoc frames`), it runs an OCR engine on each frame image, records the recognized text and confidence in `workdir/<id>/ocr/<id>.json` and the project's `project.db` (`frames` table's `ocr_text`/`ocr_confidence` columns), and updates that video's `metadata.json`. It is idempotent by **two** independent conditions, not one: `ocr.json`'s stored settings (`engine`/`languages`/`min_confidence`) must match this run's, **and** every current frame's *content* (`timestamp_seconds`/`perceptual_hash`, not just its id) must match what the manifest was built from. The second condition is this phase's own idempotency edge, absent from `frames.json`'s own settings-only comparison: a `videodoc frames` re-run producing different frame content (e.g. a looser `--interval-seconds`) must trigger re-OCR even when no OCR setting changed at all.

Comparing only the frame-*id* set is not enough on its own — found by code review: frame ids are assigned densely by position (`demo_frame_0001`, `demo_frame_0002`, ...), so a `videodoc frames` re-run with different settings that happens to land on the same *count* of frames produces the exact same id set over completely different timestamps/images. `OCRManifestEntry` therefore also stores each frame's `timestamp_seconds`/`perceptual_hash` *at OCR time*, and `_plan_for` compares the full `(frame_id, timestamp_seconds, perceptual_hash)` signature, not just the id.

A video with no frames yet (`videodoc frames` never ran, or produced zero frames) is not an error — it's silently skipped. `contains_code`/`perceptual_hash` are never touched by this phase: `contains_code` is explicitly reserved for the not-yet-implemented code-detection phase (README §20), and the frames table's own schema comment already documents this boundary.

## Engine: RapidOCR, not PaddleOCR
`config.yaml`'s `ocr.engine` default has been corrected from README's original `"paddleocr"` to `"rapidocr"` (package `rapidocr`, not the abandoned `rapidocr-onnxruntime` predecessor — no release in the last ~18 months as of this writing). PaddleOCR was ruled out with the user up front: its `paddlepaddle` wheel is notoriously difficult to install on Windows (separate CPU/GPU/CUDA-version variants), whereas RapidOCR is a plain `pip install rapidocr onnxruntime` with no system binary — consistent with this project's "local, easy setup" principle (README §4.5).

Verified directly against the installed `rapidocr` 3.9.1:
```python
from rapidocr import RapidOCR
engine = RapidOCR()
result = engine("frame.jpg")
result.txts    # tuple[str, ...] -- one recognized string per detected box
result.scores  # tuple[float, ...] -- matching confidences, 0..1
```
**Both `txts` and `scores` become `None` (not empty tuples) when zero text is detected** — confirmed on a blank test image. `core/utils/ocr_engine.py::run_ocr` treats this as "ran cleanly, found nothing" → `("", 1.0)`, not as a failure.

RapidOCR's default recognition model (`PP-OCRv6`, `lang_type="ch"`) is nominally "Chinese + English", but was verified end-to-end against real screen-quality rendered text (a legible monospace font, realistic size) to also recognize Italian accented characters correctly at ~0.99 confidence (`così è più veloce perché funziona` recognized exactly). An earlier test against a tiny, low-quality bitmap font produced garbled output — a font-rendering artifact, not a language limitation of the model. Given this, `config.ocr.languages` is **not** wired to select a different per-language recognition model (RapidOCR does expose this via `Rec.lang_type`/`Rec.ocr_version`/`Rec.model_type`, but selecting a non-default combination requires passing actual `Enum` values from `rapidocr.utils.typings`, not plain strings, and downloads an extra model from modelscope.cn on first use) — the added fragility and one-time network dependency were not justified by a real accuracy problem. `languages` is still recorded in the OCR manifest and config for idempotency purposes (a future change to it will still correctly trigger re-OCR).

## Confidence filtering semantics
`config.ocr.min_confidence` (default 0.65) is a **filter on text, not a validity flag**: a frame whose OCR confidence falls below the threshold is still recorded in both the manifest and the DB, with `ocr_text=""` and `ocr_confidence=<the real measured score>` — never omitted, never `NULL`. This keeps "OCR ran and found only low-confidence noise" distinguishable from "OCR never ran on this frame at all" (`ocr_text`/`ocr_confidence` stay `NULL` in the DB, which happens only when a single frame's OCR call itself fails — see below).

## Per-frame failure isolation
A single frame's OCR call failing (corrupt image, engine internal error) does not abort the whole video or run: that frame is left out of the manifest's `entries` and the DB update list entirely (so its `ocr_text`/`ocr_confidence` stay whatever they were, `NULL` for a first attempt), and a per-video error string is added to the result. Because that frame's id is then absent from the manifest, the frame-id-set comparison in `_plan_for` will trigger a retry of that specific frame on the next `videodoc ocr` run, even if nothing else changed.

## Concurrency
One RapidOCR engine instance is loaded per video (not shared across the `ThreadPoolExecutor`'s worker threads, and not one per frame): there is no verified evidence that RapidOCR's Python wrapper object is safe for concurrent inference from multiple threads, so parallelism is kept at the video level only, exactly like `FrameExtractionService`. Frames within one video are OCR'd sequentially. `config.ocr.workers` (new field, mirrors `frames.workers`) controls how many videos are processed concurrently.

## What was implemented
- `core/utils/ocr_engine.py` — `rapidocr_available()` (cheap `find_spec` check, following the project's lazy availability pattern), `load_engine()` (one `RapidOCR()` instantiation, wraps any failure in `OCRRunError`), `run_ocr()` (single-image inference, joins `txts`, averages `scores`, handles the `None`/`None` no-detection case).
- `core/models/ocr_manifest.py` — `OCRManifest`/`OCRManifestEntry`, the per-video idempotency sidecar (mirrors `frame_manifest.py`). Stores the effective `engine`/`languages`/`min_confidence` used to produce it (optional, `None` for a manifest predating these fields).
- `core/storage/database.py` — `list_frames()` (mirrors `list_transcript_segments`'s graceful-empty contract) and `update_frame_ocr()` (a partial per-row `UPDATE` of only `ocr_text`/`ocr_confidence` — deliberately not `replace_frames`, which would require reconstructing/risk clobbering `perceptual_hash`/`contains_code`), plus `FrameOcrUpdate`.
- `core/services/ocr_service.py` — `OCRService.run()`: a sequential, rapidocr-free pre-scan (`_plan_for`) classifies every video first (frames present? does `ocr.json` exist/parse? do its settings *and* per-frame content signature match this run's?) before ever checking engine availability, then a per-video `ThreadPoolExecutor` does OCR, manifest/DB/metadata writes, and the self-healing skip path.
- `videodoc ocr` exposes `--workers`, `--language` (repeatable), `--min-confidence`.
- New dependencies: `rapidocr>=3.0,<4.0`, `onnxruntime>=1.15` (the latter was already present transitively via `faster-whisper`, but is now also a direct, explicit dependency since `rapidocr` needs it and does not declare it itself).

## Main files
- `src/videodoc/core/utils/ocr_engine.py` — RapidOCR wrapper, availability check.
- `src/videodoc/core/models/ocr_manifest.py` — idempotency manifest.
- `src/videodoc/core/storage/database.py` — `list_frames`/`update_frame_ocr`.
- `src/videodoc/core/services/ocr_service.py` — orchestration.
- `src/videodoc/cli/commands/ocr.py` — CLI command.

## Design decisions
- No `doctor` check for RapidOCR: availability is checked lazily inside `OCRService` only when a run needs fresh OCR work, via `rapidocr_available()`.
- `contains_code`/`perceptual_hash` are never written by `update_frame_ocr` — enforced by construction (the SQL only ever sets `ocr_text`/`ocr_confidence`), not just by convention, so a future §20 code-detection run's results can never be silently wiped by a `videodoc ocr` re-run.
- `--engine` is deliberately not a CLI override in this phase — only the `config.yaml` default needed correcting (`paddleocr` → `rapidocr`); no second engine is implemented yet to switch to.
- `config.ocr.engine` is validated unconditionally at the start of every run (`OCRService.run()` raises `OCREngineNotSupportedError` if it isn't `"rapidocr"`), not only when fresh OCR is needed — found by code review: `_process_fresh` always instantiates RapidOCR regardless of this setting, so an unnoticed mismatch (e.g. an old project's `config.yaml` still saying the pre-correction `paddleocr` default) would otherwise silently run the wrong engine and write an `ocr.json` that misreports which engine actually produced its results.
- `rapidocr_available()` checks both `rapidocr` and `onnxruntime` — found by code review: `rapidocr` does not declare `onnxruntime` as a hard dependency of its own, so a machine missing only `onnxruntime` would have passed the up-front check and only failed once every video's `load_engine()` call was individually attempted, misreporting a structural, run-wide problem as N separate per-video warnings instead of failing the whole run up front with one clear message.
- A video whose `frames`/`frames.json` has real entries on disk but whose `frames` DB table has zero rows (a DB/table desync, e.g. after a `project.db` rebuild) is *not* treated the same as "`videodoc frames` was never run" — found by code review: silently skipping both cases identically would hide a real, fixable problem. `_plan_for` distinguishes them and reports a clear per-video error pointing at `videodoc frames` instead of a silent no-op. A `frames.json` that exists but fails to parse under this same zero-DB-rows condition gets the same treatment — found by a follow-up review: the original fix caught the "valid manifest, empty DB" case but silently swallowed a parse failure and fell through to the plain skip path instead.
- Idempotency compares each frame's *content*, not just its id — found by a follow-up code review after the frame-id-set check above shipped: since ids are assigned densely by position, a settings-changed `videodoc frames` re-run that happens to produce the same frame count reuses the same id set over different timestamps/images, which the id-only check couldn't distinguish from "nothing changed." `OCRManifestEntry.timestamp_seconds`/`.perceptual_hash` (both optional, `None` for a manifest predating this field so it always safely triggers one re-OCR) close this gap.

## CLI

```bash
videodoc ocr corso-software-x
# Project: corso-software-x
# +---------------+
# | Processed | 8 |
# | Skipped   | 0 |
# +---------------+

videodoc ocr corso-software-x --min-confidence 0.5 --language it --language en
```

## Tests
- Unit: `tests/core/test_ocr_manifest.py` (round-trip, backward-compatible `None` loading, low-confidence-entry-kept-not-omitted), `tests/core/test_ocr_engine.py` (availability check, text-joining/confidence-averaging, the verified `None`/`None` no-detection case, a broken-install/`ImportError` regression test), extended `tests/core/test_database.py`/`test_config.py`.
- Service: `tests/core/test_ocr_service.py`, including structural errors, a video with zero frames treated as a skip (not an error), fresh OCR writing the manifest/DB without touching `perceptual_hash`/`contains_code`, idempotent skip/self-heal with the engine never reloaded, a settings-mismatch rerun, **a frame-set-mismatch rerun** (the OCR-phase-specific idempotency edge), `min_confidence` filtering, per-frame failure isolation, and `OCREngineUnavailableError` raised only when at least one video actually needs fresh OCR.
- CLI: `tests/cli/test_cli_ocr_command.py`.
- Verified end-to-end against the real (non-stubbed) `rapidocr` package: a synthetic FFmpeg-generated video with `drawtext` burned-in terminal text (`npm create vite@latest my-app`), run through the full `init` → `ingest` → `frames` → `ocr` pipeline. Recognized the text exactly at ~0.986 confidence on every extracted frame; `contains_code` confirmed to stay `0`; a second `videodoc ocr` run confirmed idempotent (`Skipped: 1`, engine not reloaded); `videodoc doctor` confirmed to still pass with no RapidOCR-related output.
