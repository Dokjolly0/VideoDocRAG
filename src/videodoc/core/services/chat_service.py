from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, InvalidVectorIndexError, VectorIndexUnavailableError
from videodoc.core.models.chat import ChatMessage, ChatMode, ChatSessionSnapshot, ChatSource
from videodoc.core.models.document_section import GeneratedSectionManifest
from videodoc.core.models.vector_index import VectorIndex, VectorIndexInputSignature, VectorIndexRecord
from videodoc.core.storage.database import (
    ChatMessageRow,
    ChatSessionRow,
    ensure_schema,
    insert_chat_message,
    list_chat_messages,
    upsert_chat_session,
)
from videodoc.core.utils.embedding import HASHING_EMBEDDING_BACKEND, HASHING_EMBEDDING_DIMENSIONS, embed_text_hashing, text_hash
from videodoc.core.utils.vector_index import LOCAL_VECTOR_INDEX_BACKEND, VECTOR_INDEX_DISTANCE, cosine_similarity, stable_json_hash

_TIME_RE = re.compile(r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})$")
_MAX_HISTORY_MESSAGES = 8


@dataclass(frozen=True)
class ChatFilters:
    videos: tuple[str, ...] = ()
    start_seconds: float | None = None
    end_seconds: float | None = None


@dataclass(frozen=True)
class ChatTurnResult:
    session_id: str | None
    answer: str
    sources: tuple[ChatSource, ...]


class DocumentationIndexService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.docs_dir = self.project_dir / config.paths.output
        self.index_path = self.project_dir / config.paths.indexes / "documentation_index.json"

    def build(self) -> VectorIndex:
        records: list[VectorIndexRecord] = []
        signatures = []
        for path in sorted(self.docs_dir.glob("[0-9][0-9]-*.md")):
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                continue
            manifest = _load_section_manifest(self.docs_dir / "sources" / f"{path.stem}.sources.json")
            linked_sources = _linked_sources(manifest)
            payload = {
                "project_id": self.config.project.slug,
                "source_type": "generated_documentation",
                "doc_path": path.relative_to(self.project_dir).as_posix(),
                "section_title": _title_from_markdown(text) or path.stem,
                "text": text,
                "linked_sources": linked_sources,
                "linked_video_names": sorted({item["video_name"] for item in linked_sources if item.get("video_name")}),
            }
            records.append(
                VectorIndexRecord(
                    id=f"doc_{path.stem}",
                    vector=embed_text_hashing(text, dimensions=HASHING_EMBEDDING_DIMENSIONS),
                    payload=payload,
                )
            )
            signatures.append({"path": payload["doc_path"], "text_hash": text_hash(text), "sources_hash": stable_json_hash(linked_sources)})

        index = VectorIndex(
            backend=LOCAL_VECTOR_INDEX_BACKEND,
            configured_vector_db="documentation",
            distance=VECTOR_INDEX_DISTANCE,
            dimensions=HASHING_EMBEDDING_DIMENSIONS,
            inputs=[
                VectorIndexInputSignature(
                    video_id="generated_documentation",
                    backend=HASHING_EMBEDDING_BACKEND,
                    provider=self.config.embedding.provider,
                    model=self.config.embedding.model,
                    dimensions=HASHING_EMBEDDING_DIMENSIONS,
                    records_hash=stable_json_hash(signatures),
                )
            ],
            records=records,
        )
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        index.save(self.index_path)
        return index


class ChatAnswerService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.sessions_dir = self.project_dir / "sessions"
        self.db_path = self.project_dir / config.paths.database
        self.raw_index_path = self.project_dir / config.paths.indexes / "vector_index.json"

    def answer(
        self,
        message: str,
        *,
        mode: ChatMode | None = None,
        filters: ChatFilters | None = None,
        top_k: int | None = None,
        session_id: str | None = None,
        save_session: bool = False,
    ) -> ChatTurnResult:
        normalized = message.strip()
        if not normalized:
            raise ValueError("Question must not be empty.")

        mode = mode or self.config.chat.default_source
        filters = filters or ChatFilters()
        limit = top_k or self.config.chat.default_top_k
        history = self._history(session_id) if session_id else []
        query = _query_with_history(history, normalized)
        sources = self._retrieve(query, mode=mode, filters=filters, top_k=limit)
        answer = _build_chat_answer(sources)

        saved_session_id = None
        if save_session:
            saved_session_id = session_id or _new_session_id()
            self._save_turn(saved_session_id, mode, normalized, answer, sources)

        return ChatTurnResult(session_id=saved_session_id, answer=answer, sources=sources)

    def _retrieve(self, query: str, *, mode: ChatMode, filters: ChatFilters, top_k: int) -> tuple[ChatSource, ...]:
        candidates: list[ChatSource] = []
        doc_records = 0
        if mode in {"docs", "hybrid"}:
            doc_index = DocumentationIndexService(self.project_dir, self.config).build()
            doc_records = len(doc_index.records)
            candidates.extend(_search_index(doc_index, query, filters=filters, top_k=top_k, index_kind="docs"))
        if mode == "docs" and doc_records == 0 and not self.raw_index_path.is_file():
            raise VectorIndexUnavailableError(
                f"No generated documentation or raw vector index found -- run 'videodoc generate' or 'videodoc index' first."
            )
        use_raw = mode in {"raw", "hybrid"} or (mode == "docs" and doc_records == 0 and self.raw_index_path.is_file())
        if use_raw:
            if not self.raw_index_path.is_file():
                raise VectorIndexUnavailableError(
                    f"No vector index found at {self.raw_index_path} -- run 'videodoc index' first."
                )
            raw_index = VectorIndex.load(self.raw_index_path)
            candidates.extend(_search_index(raw_index, query, filters=filters, top_k=top_k, index_kind="raw"))

        candidates.sort(key=lambda source: (-source.score, source.source_type, source.record_id))
        selected = []
        seen: set[tuple[str, str | None, str | None]] = set()
        for source in candidates:
            key = (source.source_type, source.doc_path, source.chunk_id or source.record_id)
            if key in seen:
                continue
            seen.add(key)
            selected.append(source.model_copy(update={"rank": len(selected) + 1}))
            if len(selected) >= top_k:
                break
        return tuple(selected)

    def _history(self, session_id: str | None) -> list[ChatMessageRow]:
        if not session_id or not self.db_path.exists():
            return []
        ensure_schema(self.db_path)
        return list_chat_messages(self.db_path, session_id)[-self.config.chat.max_history_messages:]

    def _save_turn(self, session_id: str, mode: ChatMode, user_message: str, answer: str, sources: tuple[ChatSource, ...]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        ensure_schema(self.db_path)
        title = user_message[:80]
        existing = list_chat_messages(self.db_path, session_id)
        created_at = existing[0].created_at if existing else now
        upsert_chat_session(
            self.db_path,
            ChatSessionRow(id=session_id, title=title, default_source=mode, created_at=created_at, updated_at=now),
        )
        insert_chat_message(
            self.db_path,
            ChatMessageRow(
                id=f"{session_id}_user_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                role="user",
                content=user_message,
                sources_json=None,
                created_at=now,
            ),
        )
        insert_chat_message(
            self.db_path,
            ChatMessageRow(
                id=f"{session_id}_assistant_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                role="assistant",
                content=answer,
                sources_json=json.dumps([source.model_dump(mode="json") for source in sources], ensure_ascii=False),
                created_at=datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._write_session_snapshot(session_id, mode, title, created_at, now)

    def _write_session_snapshot(self, session_id: str, mode: ChatMode, title: str, created_at: str, updated_at: str) -> None:
        messages = []
        for row in list_chat_messages(self.db_path, session_id):
            sources = [ChatSource.model_validate(item) for item in json.loads(row.sources_json or "[]")]
            messages.append(ChatMessage(role=row.role, content=row.content, sources=sources, created_at=row.created_at))
        snapshot = ChatSessionSnapshot(
            id=session_id,
            title=title,
            default_source=mode,
            created_at=created_at,
            updated_at=updated_at,
            messages=messages,
        )
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        snapshot.save(self.sessions_dir / f"{session_id}.json")


def parse_timecode(value: str | None) -> float | None:
    if value is None:
        return None
    match = _TIME_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid timecode '{value}' -- expected HH:MM:SS or MM:SS.")
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return float(hours * 3600 + minutes * 60 + seconds)


def _search_index(index: VectorIndex, query: str, *, filters: ChatFilters, top_k: int, index_kind: str) -> list[ChatSource]:
    if index.backend != LOCAL_VECTOR_INDEX_BACKEND or index.distance != VECTOR_INDEX_DISTANCE:
        raise InvalidVectorIndexError("Chat retrieval only supports local-json cosine indexes.")
    query_vector = embed_text_hashing(query, dimensions=index.dimensions)
    scored: list[ChatSource] = []
    for record in index.records:
        if len(record.vector) != len(query_vector):
            raise InvalidVectorIndexError(f"Vector record '{record.id}' has incompatible dimensions.")
        if not _payload_matches(record.payload, filters, index_kind):
            continue
        score = cosine_similarity(query_vector, record.vector)
        if score <= 0.0:
            continue
        source = _chat_source_from_record(record, score=score, rank=len(scored) + 1, index_kind=index_kind)
        if source.text.strip():
            scored.append(source)
    scored.sort(key=lambda source: (-source.score, source.record_id))
    return scored[:top_k]


def _payload_matches(payload: dict[str, Any], filters: ChatFilters, index_kind: str) -> bool:
    if filters.videos:
        wanted = {item.lower() for item in filters.videos}
        if index_kind == "docs":
            names = {str(item).lower() for item in payload.get("linked_video_names", [])}
            if not names.intersection(wanted):
                return False
        else:
            names = {str(payload.get("video_id", "")).lower(), str(payload.get("video_name", "")).lower()}
            if not names.intersection(wanted):
                return False
    if filters.start_seconds is not None or filters.end_seconds is not None:
        if index_kind == "docs":
            ranges = payload.get("linked_sources", [])
            if not any(_range_overlaps(item.get("start_seconds"), item.get("end_seconds"), filters) for item in ranges):
                return False
        elif not _range_overlaps(payload.get("start_seconds"), payload.get("end_seconds"), filters):
            return False
    return True


def _range_overlaps(start: Any, end: Any, filters: ChatFilters) -> bool:
    start_value = _optional_float(start)
    end_value = _optional_float(end)
    if start_value is None and end_value is None:
        return False
    start_value = start_value or 0.0
    end_value = end_value if end_value is not None else start_value
    if filters.start_seconds is not None and end_value < filters.start_seconds:
        return False
    if filters.end_seconds is not None and start_value > filters.end_seconds:
        return False
    return True


def _chat_source_from_record(record: VectorIndexRecord, *, score: float, rank: int, index_kind: str) -> ChatSource:
    payload = record.payload
    source_type = str(payload.get("source_type") or ("generated_documentation" if index_kind == "docs" else "raw"))
    return ChatSource(
        rank=rank,
        source_type=source_type,
        score=score,
        text=str(payload.get("text", "")),
        record_id=record.id,
        video_id=_optional_str(payload.get("video_id")),
        video_name=_optional_str(payload.get("video_name")),
        chunk_id=_optional_str(payload.get("chunk_id")),
        start_seconds=_optional_float(payload.get("start_seconds")),
        end_seconds=_optional_float(payload.get("end_seconds")),
        doc_path=_optional_str(payload.get("doc_path")),
        section_title=_optional_str(payload.get("section_title")),
        topic=_optional_str(payload.get("topic")),
    )


def _build_chat_answer(sources: tuple[ChatSource, ...]) -> str:
    if not sources:
        return "Non ho trovato informazioni sufficienti nelle fonti del progetto per rispondere."
    lines = ["Risposta basata solo sulle fonti recuperate:"]
    for source in sources[:4]:
        lines.append(f"- {_excerpt(source.text, 300)} [{source.rank}]")
    return "\n".join(lines)


def _query_with_history(history: list[ChatMessageRow], message: str) -> str:
    recent = "\n".join(f"{row.role}: {row.content}" for row in history[-_MAX_HISTORY_MESSAGES:])
    return "\n".join(part for part in [recent, f"user: {message}"] if part.strip())


def _load_section_manifest(path: Path) -> GeneratedSectionManifest | None:
    if not path.is_file():
        return None
    try:
        return GeneratedSectionManifest.load(path)
    except Exception:
        return None


def _linked_sources(manifest: GeneratedSectionManifest | None) -> list[dict[str, Any]]:
    if manifest is None:
        return []
    return [
        {
            "video_name": source.video_name,
            "video_id": source.video_id,
            "start_seconds": source.start_seconds,
            "end_seconds": source.end_seconds,
            "chunk_id": source.chunk_id,
        }
        for source in manifest.sources
    ]


def _title_from_markdown(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _excerpt(text: str, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _new_session_id() -> str:
    return f"chat_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
