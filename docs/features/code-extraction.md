# OCR code extraction (`videodoc code`)

## Summary
`videodoc code <project>` implements README §20, "Fase 7 — Riconoscimento ed estrazione del codice". It consumes the OCR already written by `videodoc ocr`, classifies each frame's `ocr_text`, extracts code-like blocks, deduplicates repeated blocks across nearby or repeated frames, writes a per-video manifest in `workdir/<id>/code/<id>.json`, replaces the video's rows in `project.db`'s `code_blocks` table, and rewrites only `frames.contains_code`.

The command never reads frame image pixels and never invokes RapidOCR. A video with no frames, or frames that have no OCR result yet (`ocr_text IS NULL` for every row), is skipped rather than treated as an error. That keeps the pipeline friendly to incremental use: `videodoc code` can be run before `ocr` without damaging anything.

## Classification and language detection
Classification is deterministic and conservative:

- `terminal_command` — shell prompts (`$`, `#`, `>`, PowerShell, Windows `C:\...>`) and known command names such as `npm`, `git`, `python`, `docker`, `kubectl`, `pip`, `ffmpeg`, `pytest`.
- `configuration` — JSON/YAML/Dockerfile-like content.
- `source_code` — Python, JavaScript, TypeScript, HTML, CSS, and SQL heuristics.
- `error_message` — traceback/error/failure diagnostics.
- `file_path` — common POSIX/Windows relative or absolute paths and source/config extensions.
- `plain_text` / `ui_label` — recognized but not saved as code blocks.

Language detection is similarly rule-based. JSON, YAML and Python have parser validation; terminal commands, file paths and error messages are considered rule-verified. JavaScript/TypeScript/HTML/CSS/SQL/Dockerfile are classified now but remain non-parser-verified, so in strict mode they are marked for review until a dedicated parser/validator is added.

## Deduplication
The extracted `code` text is normalized by trimming outer whitespace, normalizing line endings, dropping repeated blank lines, and removing terminal prompts for shell commands. Deduplication uses a SHA-256 hash over that normalized text plus the detected content type/language. The first saved block keeps every source frame that showed the same normalized content, preserving timestamps and OCR confidence for future chunking and review.

## Validation and review report
Every saved block records:

- `content_type`
- `language`
- normalized `code`
- `confidence`
- `verified`
- `validation.status` / `validation.error`
- `source_frames`
- `needs_review` / `review_reasons`

`workdir/<id>/code/code_review_report.md` is regenerated on every fresh or self-heal run. Blocks are listed there when OCR confidence is below `0.80`, parser validation fails, or strict mode cannot verify the block by parser/simple rule. This implements the review-report shape described in README §34 without letting uncertain OCR silently flow into later documentation generation.

## Idempotency
`CodeManifest.input_frames` stores a signature for every current frame: `frame_id`, `timestamp_seconds`, `perceptual_hash`, `ocr_text_hash`, and `ocr_confidence`. A skip/self-heal path is used only when all three settings match (`code.extract_from_ocr`, `code.strict_mode`, `code.mark_uncertain_code`) and the full input frame signature is unchanged.

This matters because frame ids are dense and positional (`demo_frame_0001`, `demo_frame_0002`, ...). A rerun of `videodoc frames` can produce the same frame ids over different timestamps/images, and a rerun of `videodoc ocr` can change text/confidence without changing frame ids. Both cases must trigger fresh code extraction.

On the skip path, `videodoc code` still rewrites `code_blocks`, `frames.contains_code`, and the review report from the manifest. This mirrors the earlier frame/OCR self-healing pattern: a transient DB failure after a successful JSON write is repaired by the next run.

## Database boundaries
- `replace_code_blocks()` fully replaces only rows in `code_blocks` for the current video.
- `replace_frame_code_flags()` rewrites only `frames.contains_code` for the current video, never `ocr_text`, `ocr_confidence`, `image_path`, or `perceptual_hash`.
- `FrameExtractionService._process_existing()` already preserves `contains_code` when it rebuilds frame rows from `frames.json`, so code flags survive a pure frame self-heal.
- `OCRService` still never writes `contains_code`, so OCR reruns cannot wipe code detection results.

## Main files
- `src/videodoc/core/utils/code_detection.py` — deterministic OCR-text classification, language detection, normalization, validation.
- `src/videodoc/core/models/code_manifest.py` — per-video manifest and input-frame signature.
- `src/videodoc/core/services/code_service.py` — orchestration, idempotency, DB writes, review report.
- `src/videodoc/core/storage/database.py` — `code_blocks`, `replace_code_blocks()`, `list_code_blocks()`, `replace_frame_code_flags()`.
- `src/videodoc/cli/commands/code.py` — CLI command.

## CLI

```bash
videodoc code corso-software-x
# Project: corso-software-x
# +---------------+
# | Processed | 8 |
# | Skipped   | 0 |
# +---------------+

videodoc code corso-software-x --workers 1
```

## Tests
- Unit: `tests/core/test_code_detection.py`, `tests/core/test_code_manifest.py`, and extended `tests/core/test_database.py`.
- Service: `tests/core/test_code_service.py`, including structural errors, no-frame/no-OCR skips, fresh extraction with deduplication, self-healing, OCR-text-change reprocessing, review-report generation, corrupt manifest warnings, and `code.extract_from_ocr=false`.
- CLI: `tests/cli/test_cli_code_command.py`, with a stubbed `init -> ingest -> frames -> ocr -> code` flow.
