# Intelligent chunking (`videodoc chunk`)

## Summary
`videodoc chunk <project>` implements README §21, "Fase 8 — Chunking intelligente". It reads structured data already in `project.db`:

- transcript segments from `transcript_segments`
- OCR text/confidence from `frames`
- deduplicated code from `code_blocks`

For each video it writes `workdir/<id>/chunks/<id>.json`, replaces that video's rows in the `chunks` table, and updates `metadata.json` (`chunks_path`) to the concrete manifest file.

## Main Chunking Algorithm
The first implementation is deterministic and local. It does not call an LLM.

When transcript segments are present, they are the timing backbone. Consecutive segments are grouped until either:

- adding the next segment would exceed `chunking.max_duration_seconds`, and the current chunk is already at least `chunking.min_duration_seconds`; or
- there is a pause of at least 8 seconds after a chunk that already reached the minimum duration.

Defaults come from `config.chunking`: 90 seconds minimum, 480 seconds maximum. A single long segment is kept whole rather than split mid-segment.

When there is no transcript yet, the service falls back to OCR/code event timestamps. It creates time windows around frames with OCR text and code block timestamps so visual-only material can still be chunked, rather than making transcription an absolute prerequisite.

Each primary chunk is enriched with:

- transcript text from included segments
- unique OCR text from frames inside the interval
- code blocks whose timestamps land inside the interval
- metadata: transcript segment ids, frame ids, code block ids, `source_type`, `contains_code`, and aggregate confidence

If `chunking.include_nearby_frames` is true, OCR/code lookup uses a 5-second margin around the chunk boundary so a frame sampled just before/after a spoken segment is still included.

## Code-Specific Chunks
README §21.3 recommends indexing code separately. `videodoc chunk` therefore creates one extra chunk per row in `code_blocks`:

- id: `<code_block_id>_chunk`
- `source_type`: `code`
- start/end: the code block timestamp
- transcript/OCR: empty
- `code_blocks`: the single code block payload

The code still appears inside its surrounding primary chunk when timestamps overlap, but the extra code chunk lets the embedding/indexing phase treat code as a precise standalone retrieval document.

## Idempotency and Self-Heal
`ChunkManifest` stores input signatures for every transcript segment, frame and code block:

- transcript: id, start/end, text hash, confidence
- frame: id, timestamp, perceptual hash, OCR text hash, OCR confidence, `contains_code`
- code: id, timestamp, language, code hash, confidence, verified flag

A rerun is skipped only when these signatures and the effective chunking settings all match. On the skip path, the DB rows and `metadata.json` are still rewritten from the manifest, so a transient DB failure after a successful JSON write repairs itself on the next run.

If the inputs disappear after a manifest exists, a fresh empty manifest is written and the video's `chunks` rows are cleared. That avoids stale chunks surviving a manual DB rebuild or an upstream rerun that removed transcript/OCR/code inputs.

## Database Boundaries
- `replace_chunks()` fully replaces only rows in `chunks` for the current video.
- Transcript, frame, OCR and code tables are read-only from this phase.
- `metadata_json` in the DB row mirrors the manifest metadata for downstream embedding/indexing.

## Main Files
- `src/videodoc/core/models/chunk_manifest.py` — manifest, chunk entries, input signatures.
- `src/videodoc/core/services/chunking_service.py` — deterministic chunk planning, enrichment, idempotency and metadata reconciliation.
- `src/videodoc/core/storage/database.py` — `chunks`, `ChunkRow`, `replace_chunks()`, `list_chunks()`.
- `src/videodoc/cli/commands/chunk.py` — CLI command.

## CLI

```bash
videodoc chunk corso-software-x
# Project: corso-software-x
# +---------------+
# | Processed | 8 |
# | Skipped   | 0 |
# +---------------+

videodoc chunk corso-software-x --workers 1
```

## Tests
- Unit: `tests/core/test_chunk_manifest.py`, plus extended `tests/core/test_database.py`.
- Service: `tests/core/test_chunking_service.py`, covering structural errors, no-input skips, fresh chunk creation, code-specific chunks, DB/metadata self-heal, input-change reprocessing, OCR/code-only fallback, settings-change reprocessing, corrupt manifest errors, and input-removal clearing.
- CLI: `tests/cli/test_cli_chunk_command.py`.
