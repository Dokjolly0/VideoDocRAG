# Vector indexing (`videodoc index`)

## Summary
`videodoc index <project>` implements README §23, "Fase 10 — Indicizzazione nel vector database". It reads per-video embedding manifests from `indexes/embeddings/<id>.json` and writes one project-level index at `indexes/vector_index.json`.

The current backend is `local-json` with cosine distance. `config.retrieval.vector_db` is still recorded as `configured_vector_db` (default `qdrant`) so the configuration remains aligned with the README target, but this implementation does not start or require Qdrant yet.

## Record Shape
Each indexed record contains:

- id: inherited from the embedding record
- vector
- payload

Payload includes:

- `project_id`
- `video_id`
- `video_name`
- `chunk_id`
- `embedding_type`
- `text`
- chunk metadata copied from the embedding record, such as start/end seconds, topic, `source_type`, `contains_code`, `language`, and confidence when available

This mirrors the payload shape recommended by README §23/§32 while keeping the storage local and easy to inspect.

## Idempotency
`VectorIndex.inputs` stores one signature per embedding manifest:

- video id
- embedding backend/provider/model/dimensions
- hash of every embedding record id, chunk id, embedding type, text hash, vector hash and metadata hash

If the existing `indexes/vector_index.json` has the same backend, configured vector DB, distance, dimensions and input signatures, `videodoc index` skips rewriting. If any embedding manifest changes, the index is rebuilt atomically.

A corrupt existing index is reported as a warning and then replaced when valid embedding manifests are available. A corrupt embedding manifest is reported per-video and does not block indexing other videos.

## Main Files
- `src/videodoc/core/models/vector_index.py` — local index model, records and input signatures.
- `src/videodoc/core/utils/vector_index.py` — stable JSON hashing and cosine similarity helper.
- `src/videodoc/core/services/index_service.py` — project-level indexing and idempotency.
- `src/videodoc/cli/commands/index.py` — CLI command.

## CLI

```bash
videodoc index corso-software-x
# Project: corso-software-x
# +-----------------+
# | Indexed | yes   |
# | Skipped | no    |
# | Videos  | 8     |
# | Records | 120   |
# +-----------------+
```

## Tests
- Unit: `tests/core/test_vector_index_utils.py` and `tests/core/test_vector_index_model.py`.
- Service: `tests/core/test_index_service.py`, covering structural errors, unsupported vector DB values, no-embedding skips, fresh index writes, idempotent reruns, embedding-change reindexing, corrupt embedding manifests and corrupt-index replacement.
- CLI: `tests/cli/test_cli_index_command.py`.
