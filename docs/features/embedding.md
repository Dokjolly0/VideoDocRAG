# Chunk embeddings (`videodoc embed`)

## Summary
`videodoc embed <project>` implements README §22, "Fase 9 — Creazione degli embedding". It reads chunk manifests from `workdir/<id>/chunks/<id>.json` and writes per-video embedding manifests to `indexes/embeddings/<id>.json`.

For every chunk it can create separate embedding records for:

- `transcript`
- `ocr`
- `code`
- `summary`
- `combined`

Empty fields are skipped, so a code-only chunk produces `code`, `summary`, and `combined`, while a transcript-only chunk produces transcript/summary/combined.

## Backend
The current backend is deterministic local feature hashing:

- backend: `feature-hashing`
- dimensions: 256
- no network
- no model download
- no new runtime dependency

This is deliberately a bootstrap embedding backend, not a claim that feature hashing has the semantic quality of a real multilingual embedding model. `config.embedding.provider` and `config.embedding.model` are still recorded in the manifest (`local` / `bge-m3` by default) so changing the intended embedding configuration invalidates stale manifests and leaves a clear upgrade path for a future model-backed local engine.

## Output Shape
Each `EmbeddingRecord` stores:

- id: `<chunk_id>_<embedding_type>`
- chunk id
- embedding type
- original text
- text hash
- vector
- dimensions
- metadata copied from the chunk, plus video/timestamp/topic/source fields and language when available

The vector-indexing phase ingests this manifest directly without recomputing text assembly.

## Idempotency
`EmbeddingManifest.chunk_inputs` stores signatures for every input chunk:

- chunk id/source type
- start/end seconds
- topic/summary/transcript/OCR/code hashes
- metadata hash

A rerun is skipped only when the backend/provider/model/dimensions/batch size and all chunk signatures match. If chunking changes upstream, `videodoc embed` regenerates the manifest. If a chunk manifest becomes empty after an embedding manifest exists, the command writes an empty embedding manifest so stale records do not survive.

## Main Files
- `src/videodoc/core/utils/embedding.py` — deterministic feature-hashing vectorizer.
- `src/videodoc/core/models/embedding_manifest.py` — embedding manifest, records, input signatures.
- `src/videodoc/core/services/embedding_service.py` — per-video planning, idempotency and manifest writes.
- `src/videodoc/cli/commands/embed.py` — CLI command.

## CLI

```bash
videodoc embed corso-software-x
# Project: corso-software-x
# +---------------+
# | Processed | 8 |
# | Skipped   | 0 |
# +---------------+

videodoc embed corso-software-x --workers 1
```

## Tests
- Unit: `tests/core/test_embedding_utils.py` and `tests/core/test_embedding_manifest.py`.
- Service: `tests/core/test_embedding_service.py`, covering structural errors, unsupported providers, no-chunk skips, fresh embedding output, idempotent reruns, chunk-change reprocessing, corrupt manifests and stale-record clearing when chunks become empty.
- CLI: `tests/cli/test_cli_embed_command.py`.
