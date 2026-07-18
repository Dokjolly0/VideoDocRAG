# Retrieval and extractive RAG (`videodoc ask`)

## Summary
`videodoc ask <project> "question"` implements README §24, "Fase 11 — Retrieval e RAG", on top of the local vector index written by `videodoc index`.

The current answerer is deliberately extractive and local: it embeds the question with the same deterministic feature-hashing backend used by `videodoc embed`, searches `indexes/vector_index.json` with cosine similarity, deduplicates multiple embedding records that point to the same chunk, and prints a grounded answer composed only from retrieved source excerpts.

This is a bootstrap RAG layer, not yet a full LLM generation layer. It enforces the README anti-hallucination rule by refusing to invent missing procedures: when no source has a positive retrieval score, the command says that the indexed sources do not contain enough information.

## Retrieval Flow

1. Load `indexes/vector_index.json`.
2. Embed the user question with `feature-hashing` using the index dimensions.
3. Score every indexed record with cosine similarity.
4. Drop zero/negative matches and records without text.
5. Sort by score and deduplicate by `(video_id, chunk_id)`.
6. Build a short answer using only the top retrieved source excerpts.
7. Print numbered sources with video, timestamp range, score, chunk id, embedding type, source type and topic.

## CLI

```bash
videodoc ask corso-software-x "Come si configura il database?" --top-k 5
# Project: corso-software-x
# Answer:
# Risposta basata solo sulle fonti recuperate:
# - La configurazione del database ... [1]
# Sources:
# [1] workshop_03_database.mp4 00:12:10-00:18:45 score=0.842 chunk=workshop_03_chunk_0004 type=combined source=transcript topic=Database
#     La configurazione del database ...
```

If the vector index is missing, the command fails with an actionable hint to run `videodoc index` first.

## Main Files
- `src/videodoc/core/services/retrieval_service.py` — local retrieval, source ranking and extractive answer building.
- `src/videodoc/cli/commands/ask.py` — CLI command and source rendering.
- `src/videodoc/core/errors.py` — `VectorIndexUnavailableError` for missing retrieval indexes.

## Tests
- Service: `tests/core/test_retrieval_service.py`, covering ranking, deduplication, missing indexes, no-source answers and malformed vector dimensions.
- CLI: `tests/cli/test_cli_ask_command.py`, covering successful answer/source output and error paths.
