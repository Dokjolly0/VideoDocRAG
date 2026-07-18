from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    InvalidEmbeddingManifestError,
    InvalidVectorIndexError,
    NoVideosFoundError,
    VectorIndexNotSupportedError,
)
from videodoc.core.models.embedding_manifest import EmbeddingManifest
from videodoc.core.models.vector_index import VectorIndex, VectorIndexInputSignature, VectorIndexRecord
from videodoc.core.storage.database import ensure_schema, list_videos
from videodoc.core.utils.progress import ProgressReporter
from videodoc.core.utils.vector_index import LOCAL_VECTOR_INDEX_BACKEND, VECTOR_INDEX_DISTANCE, stable_json_hash

_SUPPORTED_VECTOR_DBS = {"qdrant", "local-json"}


@dataclass(frozen=True)
class IndexingResult:
    indexed: bool
    skipped: bool
    records: int
    videos: int
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _EmbeddingInput:
    video_id: str
    path: Path
    manifest: EmbeddingManifest | None
    load_error: str | None = None


class IndexService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.vector_db = config.retrieval.vector_db
        self.index_path = self.project_dir / config.paths.indexes / "vector_index.json"

    def run(self, progress: ProgressReporter | None = None) -> IndexingResult:
        progress = progress or ProgressReporter()
        db_path = self.project_dir / self.config.paths.database
        if not db_path.exists():
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )
        if not db_path.is_file():
            raise DatabaseError(f"{db_path} exists but is not a file.")
        if self.vector_db not in _SUPPORTED_VECTOR_DBS:
            raise VectorIndexNotSupportedError(
                f"Vector DB '{self.vector_db}' is not supported yet -- supported values: "
                f"{', '.join(sorted(_SUPPORTED_VECTOR_DBS))}."
            )

        videos = list_videos(db_path)
        if not videos:
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )
        ensure_schema(db_path)

        inputs = [self._load_embedding_input(row.id) for row in sorted(videos, key=lambda r: r.id)]
        errors = tuple(
            f"{item.video_id}: embedding manifest could not be read: {item.load_error}"
            for item in inputs
            if item.load_error is not None
        )
        manifests = [item.manifest for item in inputs if item.manifest is not None]
        if not manifests:
            return IndexingResult(indexed=False, skipped=True, records=0, videos=0, errors=errors)

        index = _build_index(self.config.project.slug, self.vector_db, manifests)
        if self.index_path.is_file():
            try:
                existing = VectorIndex.load(self.index_path)
            except InvalidVectorIndexError as exc:
                errors = errors + (f"vector index already exists but could not be read: {exc}",)
            else:
                if _index_settings_match(existing, index):
                    return IndexingResult(
                        indexed=False,
                        skipped=True,
                        records=len(existing.records),
                        videos=len(existing.inputs),
                        errors=errors,
                    )

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.index_path.parent / f"{self.index_path.name}.tmp"
        progress.start_item("vector-index", 0, 1)
        try:
            try:
                index.save(tmp_path)
                tmp_path.replace(self.index_path)
            except OSError as exc:
                tmp_path.unlink(missing_ok=True)
                errors = errors + (f"could not finalize vector index: {exc}",)
                return IndexingResult(indexed=False, skipped=False, records=0, videos=len(index.inputs), errors=errors)
            progress.update_item("vector-index", 1.0)
            return IndexingResult(
                indexed=True,
                skipped=False,
                records=len(index.records),
                videos=len(index.inputs),
                errors=errors,
            )
        finally:
            progress.finish_item("vector-index")

    def _load_embedding_input(self, video_id: str) -> _EmbeddingInput:
        path = self.project_dir / self.config.paths.indexes / "embeddings" / f"{video_id}.json"
        if not path.is_file():
            return _EmbeddingInput(video_id, path, None)
        try:
            return _EmbeddingInput(video_id, path, EmbeddingManifest.load(path))
        except InvalidEmbeddingManifestError as exc:
            return _EmbeddingInput(video_id, path, None, load_error=str(exc))


def _build_index(project_id: str, configured_vector_db: str, manifests: list[EmbeddingManifest]) -> VectorIndex:
    dimensions = _resolve_dimensions(manifests)
    inputs = [_input_signature(manifest) for manifest in manifests]
    records = [
        _to_index_record(project_id, manifest, record)
        for manifest in manifests
        for record in manifest.records
    ]
    return VectorIndex(
        backend=LOCAL_VECTOR_INDEX_BACKEND,
        configured_vector_db=configured_vector_db,
        distance=VECTOR_INDEX_DISTANCE,
        dimensions=dimensions,
        inputs=inputs,
        records=records,
    )


def _resolve_dimensions(manifests: list[EmbeddingManifest]) -> int:
    dimensions = {manifest.dimensions for manifest in manifests}
    if len(dimensions) == 1:
        return next(iter(dimensions))
    # Mixed dimensions should not happen in normal runs because config is
    # project-scoped, but keeping the index writable preserves debuggability.
    return max(dimensions)


def _input_signature(manifest: EmbeddingManifest) -> VectorIndexInputSignature:
    records_payload = [
        {
            "id": record.id,
            "chunk_id": record.chunk_id,
            "embedding_type": record.embedding_type,
            "text_hash": record.text_hash,
            "vector_hash": stable_json_hash(record.vector),
            "metadata_hash": stable_json_hash(record.metadata),
        }
        for record in manifest.records
    ]
    return VectorIndexInputSignature(
        video_id=manifest.video_id,
        backend=manifest.backend,
        provider=manifest.provider,
        model=manifest.model,
        dimensions=manifest.dimensions,
        records_hash=stable_json_hash(records_payload),
    )


def _to_index_record(project_id: str, manifest: EmbeddingManifest, record) -> VectorIndexRecord:
    payload = {
        "project_id": project_id,
        "video_id": manifest.video_id,
        "video_name": manifest.video_name,
        "chunk_id": record.chunk_id,
        "embedding_type": record.embedding_type,
        "text": record.text,
        **record.metadata,
    }
    return VectorIndexRecord(id=record.id, vector=record.vector, payload=payload)


def _index_settings_match(existing: VectorIndex, current: VectorIndex) -> bool:
    return (
        existing.backend == current.backend
        and existing.configured_vector_db == current.configured_vector_db
        and existing.distance == current.distance
        and existing.dimensions == current.dimensions
        and existing.inputs == current.inputs
    )
