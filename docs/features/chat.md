# Chat and filtered ask (`videodoc ask`, `videodoc chat`)

## Summary
README §29, "Fase 16 — Chat sulla documentazione e sui video", is implemented as a local extractive chat layer.

`videodoc ask` is the one-shot command. It now supports:

- `--source docs|raw|hybrid`
- repeated `--video`
- `--from HH:MM:SS`
- `--to HH:MM:SS`
- `--top-k N`

`videodoc chat` saves turns as a session. It can run interactively, or as a single saved turn with `--message`.

## Retrieval Modes

`docs` is the default. It builds `indexes/documentation_index.json` from generated Markdown sections in `docs/[0-9][0-9]-*.md`, with payloads using `source_type = generated_documentation` and linked video/timestamp references from `docs/sources/*.sources.json`.

`raw` searches the original local vector index at `indexes/vector_index.json`.

`hybrid` searches both documentation and raw chunk indexes, then deduplicates and ranks the combined sources.

If docs mode is requested before generated documentation exists, but the raw vector index is available, `ask` falls back to raw sources so partially-built projects remain queryable.

## Sessions
Chat sessions are stored in two places:

- `project.db`: `chat_sessions` and `chat_messages`
- `sessions/<session_id>.json`: inspectable snapshot with messages and sources

When continuing a session with `--session`, recent messages are included in the retrieval query so follow-up questions can use conversation context.

## CLI

```bash
videodoc ask corso-software-x "Come si configura il database?" --source hybrid --video workshop_03_database.mp4
```

```bash
videodoc chat corso-software-x --message "Come si configura il database?" --source docs
```

Interactive mode:

```bash
videodoc chat corso-software-x
```

## Main Files
- `src/videodoc/core/services/chat_service.py` — documentation indexing, filtered retrieval, extractive answers and session persistence.
- `src/videodoc/core/models/chat.py` — chat source/session snapshot models.
- `src/videodoc/cli/commands/ask.py` — one-shot Q&A with source/video/time filters.
- `src/videodoc/cli/commands/chat.py` — saved chat sessions.
- `src/videodoc/core/storage/database.py` — chat session/message tables and helpers.

## Tests
- Service: `tests/core/test_chat_service.py`.
- CLI: `tests/cli/test_cli_chat_command.py` and updated `tests/cli/test_cli_ask_command.py`.
- Storage: chat helper coverage in `tests/core/test_database.py`.
