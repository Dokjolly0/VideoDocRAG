from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import InvalidVectorIndexError, VectorIndexUnavailableError
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.utils.embedding import embed_text_hashing
from videodoc.core.utils.vector_index import LOCAL_VECTOR_INDEX_BACKEND, VECTOR_INDEX_DISTANCE, cosine_similarity

_ANSWER_SOURCE_LIMIT = 3
_ANSWER_EXCERPT_CHARS = 320


@dataclass(frozen=True)
class RetrievedSource:
    rank: int
    record_id: str
    score: float
    video_id: str
    video_name: str
    chunk_id: str
    embedding_type: str
    source_type: str | None
    start_seconds: float | None
    end_seconds: float | None
    topic: str | None
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AskResult:
    question: str
    answer: str
    sources: tuple[RetrievedSource, ...]


class RetrievalService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.index_path = self.project_dir / config.paths.indexes / "vector_index.json"

    def retrieve(self, question: str, *, top_k: int | None = None) -> tuple[RetrievedSource, ...]:
        normalized = question.strip()
        if not normalized:
            raise ValueError("Question must not be empty.")

        index = self._load_index()
        query_vector = embed_text_hashing(normalized, dimensions=index.dimensions)
        if not any(query_vector):
            return ()

        scored: list[tuple[float, VectorIndexRecord]] = []
        for record in index.records:
            try:
                score = cosine_similarity(query_vector, record.vector)
            except ValueError as exc:
                raise InvalidVectorIndexError(
                    f"Vector record '{record.id}' has dimensions incompatible with index dimensions {index.dimensions}."
                ) from exc
            if score > 0.0 and str(record.payload.get("text", "")).strip():
                scored.append((score, record))

        scored.sort(key=lambda item: (-item[0], _sort_key(item[1])))
        limit = top_k if top_k is not None else self.config.retrieval.top_k
        selected = _deduplicate(scored, limit)
        return tuple(_to_source(rank, score, record) for rank, (score, record) in enumerate(selected, start=1))

    def ask(self, question: str, *, top_k: int | None = None) -> AskResult:
        sources = self.retrieve(question, top_k=top_k)
        return AskResult(question=question, answer=_build_answer(sources), sources=sources)

    def _load_index(self) -> VectorIndex:
        if not self.index_path.is_file():
            raise VectorIndexUnavailableError(
                f"No vector index found at {self.index_path} -- run 'videodoc index' first."
            )
        index = VectorIndex.load(self.index_path)
        if index.backend != LOCAL_VECTOR_INDEX_BACKEND:
            raise InvalidVectorIndexError(
                f"Vector index backend '{index.backend}' cannot be searched locally; expected '{LOCAL_VECTOR_INDEX_BACKEND}'."
            )
        if index.distance != VECTOR_INDEX_DISTANCE:
            raise InvalidVectorIndexError(
                f"Vector index distance '{index.distance}' cannot be searched locally; expected '{VECTOR_INDEX_DISTANCE}'."
            )
        return index


def _deduplicate(scored: list[tuple[float, VectorIndexRecord]], limit: int) -> list[tuple[float, VectorIndexRecord]]:
    selected: list[tuple[float, VectorIndexRecord]] = []
    seen_chunks: set[tuple[str, str]] = set()
    for score, record in scored:
        payload = record.payload
        key = (str(payload.get("video_id", "")), str(payload.get("chunk_id", record.id)))
        if key in seen_chunks:
            continue
        seen_chunks.add(key)
        selected.append((score, record))
        if len(selected) >= limit:
            break
    return selected


def _to_source(rank: int, score: float, record: VectorIndexRecord) -> RetrievedSource:
    payload = record.payload
    text = str(payload.get("text", "")).strip()
    metadata = {key: value for key, value in payload.items() if key != "text"}
    return RetrievedSource(
        rank=rank,
        record_id=record.id,
        score=score,
        video_id=str(payload.get("video_id", "")),
        video_name=str(payload.get("video_name") or payload.get("video_id") or ""),
        chunk_id=str(payload.get("chunk_id", record.id)),
        embedding_type=str(payload.get("embedding_type", "")),
        source_type=_optional_str(payload.get("source_type")),
        start_seconds=_optional_float(payload.get("start_seconds")),
        end_seconds=_optional_float(payload.get("end_seconds")),
        topic=_optional_str(payload.get("topic")),
        text=text,
        metadata=metadata,
    )


def _build_answer(sources: tuple[RetrievedSource, ...]) -> str:
    if not sources:
        return (
            "Non ho trovato informazioni sufficienti nelle fonti indicizzate del progetto "
            "per rispondere alla domanda."
        )

    lines = ["Risposta basata solo sulle fonti recuperate:"]
    for source in sources[:_ANSWER_SOURCE_LIMIT]:
        excerpt = _excerpt(source.text, max_chars=_ANSWER_EXCERPT_CHARS)
        if excerpt:
            lines.append(f"- {excerpt} [{source.rank}]")
    return "\n".join(lines)


def _sort_key(record: VectorIndexRecord) -> tuple[str, float, str]:
    payload = record.payload
    return (
        str(payload.get("video_name") or payload.get("video_id") or ""),
        _optional_float(payload.get("start_seconds")) or 0.0,
        record.id,
    )


def _excerpt(text: str, *, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


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
