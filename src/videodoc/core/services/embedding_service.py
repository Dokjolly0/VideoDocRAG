from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    EmbeddingEngineNotSupportedError,
    InvalidChunkManifestError,
    InvalidEmbeddingManifestError,
    NoVideosFoundError,
)
from videodoc.core.models.chunk_manifest import ChunkManifest, ChunkManifestEntry
from videodoc.core.models.embedding_manifest import EmbeddingChunkSignature, EmbeddingManifest, EmbeddingRecord
from videodoc.core.storage.database import ensure_schema, list_videos
from videodoc.core.utils.embedding import (
    HASHING_EMBEDDING_BACKEND,
    HASHING_EMBEDDING_DIMENSIONS,
    embed_text_hashing,
    text_hash,
)
from videodoc.core.utils.hardware import resolve_cpu_workers, resolve_executor_workers
from videodoc.core.utils.progress import ProgressReporter

_SUPPORTED_PROVIDERS = {"local"}


@dataclass(frozen=True)
class EmbeddingResult:
    processed: tuple[str, ...]
    skipped: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _EmbeddingOutcome:
    video_id: str
    processed: bool = False
    skipped: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _EmbeddingPlan:
    video_id: str
    video_name: str
    chunk_manifest_path: Path
    embedding_manifest_path: Path
    chunk_manifest: ChunkManifest | None
    chunk_inputs: tuple[EmbeddingChunkSignature, ...]
    has_chunks: bool
    needs_fresh: bool
    manifest: EmbeddingManifest | None = None
    chunk_load_error: str | None = None
    embedding_load_error: str | None = None


class EmbeddingService:
    def __init__(self, project_dir: Path, config: ProjectConfig, *, workers_override: int | None = None) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override
        self.provider = config.embedding.provider
        self.model = config.embedding.model
        self.batch_size = config.embedding.batch_size
        self.dimensions = HASHING_EMBEDDING_DIMENSIONS

    def run(self, progress: ProgressReporter | None = None) -> EmbeddingResult:
        progress = progress or ProgressReporter()
        db_path = self.project_dir / self.config.paths.database
        if not db_path.exists():
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )
        if not db_path.is_file():
            raise DatabaseError(f"{db_path} exists but is not a file.")
        if self.provider not in _SUPPORTED_PROVIDERS:
            raise EmbeddingEngineNotSupportedError(
                f"Embedding provider '{self.provider}' is not supported yet -- only 'local' is currently implemented."
            )

        videos = list_videos(db_path)
        if not videos:
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )

        ensure_schema(db_path)
        plans = [self._plan_for(row.id, row.filename) for row in sorted(videos, key=lambda r: r.id)]
        configured_workers = resolve_cpu_workers("auto", self.workers_override)
        executor_workers = resolve_executor_workers(configured_workers, len(videos))

        processed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        with ThreadPoolExecutor(max_workers=executor_workers) as executor:
            futures = [
                executor.submit(self._process_plan, plan, index, len(plans), progress)
                for index, plan in enumerate(plans)
            ]
            for future in futures:
                outcome = future.result()
                if outcome.processed:
                    processed.append(outcome.video_id)
                if outcome.skipped:
                    skipped.append(outcome.video_id)
                errors.extend(outcome.errors)

        return EmbeddingResult(tuple(processed), tuple(skipped), tuple(errors))

    def _plan_for(self, video_id: str, video_name: str) -> _EmbeddingPlan:
        chunk_manifest_path = self.project_dir / self.config.paths.workdir / video_id / "chunks" / f"{video_id}.json"
        embedding_manifest_path = self.project_dir / self.config.paths.indexes / "embeddings" / f"{video_id}.json"

        chunk_manifest: ChunkManifest | None = None
        chunk_inputs: tuple[EmbeddingChunkSignature, ...] = ()
        chunk_load_error: str | None = None
        if chunk_manifest_path.is_file():
            try:
                chunk_manifest = ChunkManifest.load(chunk_manifest_path)
                chunk_inputs = tuple(_chunk_signature(chunk) for chunk in chunk_manifest.chunks)
            except InvalidChunkManifestError as exc:
                chunk_load_error = str(exc)

        has_chunks = bool(chunk_manifest and chunk_manifest.chunks)
        if chunk_load_error is not None:
            return _EmbeddingPlan(
                video_id,
                video_name,
                chunk_manifest_path,
                embedding_manifest_path,
                chunk_manifest,
                chunk_inputs,
                has_chunks=False,
                needs_fresh=False,
                chunk_load_error=chunk_load_error,
            )

        if not embedding_manifest_path.is_file():
            return _EmbeddingPlan(
                video_id,
                video_name,
                chunk_manifest_path,
                embedding_manifest_path,
                chunk_manifest,
                chunk_inputs,
                has_chunks,
                needs_fresh=has_chunks,
            )

        try:
            manifest = EmbeddingManifest.load(embedding_manifest_path)
        except InvalidEmbeddingManifestError as exc:
            return _EmbeddingPlan(
                video_id,
                video_name,
                chunk_manifest_path,
                embedding_manifest_path,
                chunk_manifest,
                chunk_inputs,
                has_chunks,
                needs_fresh=False,
                embedding_load_error=str(exc),
            )

        settings_match = (
            manifest.backend == HASHING_EMBEDDING_BACKEND
            and manifest.provider == self.provider
            and manifest.model == self.model
            and manifest.dimensions == self.dimensions
            and manifest.batch_size == self.batch_size
        )
        inputs_match = tuple(manifest.chunk_inputs) == chunk_inputs
        return _EmbeddingPlan(
            video_id,
            video_name,
            chunk_manifest_path,
            embedding_manifest_path,
            chunk_manifest,
            chunk_inputs,
            has_chunks,
            needs_fresh=not (settings_match and inputs_match),
            manifest=manifest,
        )

    def _process_plan(
        self,
        plan: _EmbeddingPlan,
        index: int,
        total: int,
        progress: ProgressReporter,
    ) -> _EmbeddingOutcome:
        progress.start_item(plan.video_id, index, total)
        try:
            if plan.chunk_load_error is not None:
                return _EmbeddingOutcome(
                    plan.video_id,
                    errors=(f"{plan.video_id}: chunk manifest could not be read: {plan.chunk_load_error}",),
                )
            if plan.embedding_load_error is not None:
                return _EmbeddingOutcome(
                    plan.video_id,
                    errors=(f"{plan.video_id}: embeddings already exist but manifest could not be read: {plan.embedding_load_error}",),
                )
            if not plan.has_chunks and plan.chunk_manifest is None:
                return _EmbeddingOutcome(plan.video_id, skipped=True)
            if not plan.needs_fresh:
                return _EmbeddingOutcome(plan.video_id, skipped=True)
            return self._process_fresh(plan, progress)
        finally:
            progress.finish_item(plan.video_id)

    def _process_fresh(self, plan: _EmbeddingPlan, progress: ProgressReporter) -> _EmbeddingOutcome:
        assert plan.chunk_manifest is not None
        records = []
        chunks = plan.chunk_manifest.chunks
        total_chunks = max(len(chunks), 1)
        for position, chunk in enumerate(chunks, start=1):
            records.extend(_records_for_chunk(chunk, dimensions=self.dimensions))
            progress.update_item(plan.video_id, position / total_chunks)

        manifest = EmbeddingManifest(
            video_id=plan.video_id,
            video_name=plan.video_name,
            backend=HASHING_EMBEDDING_BACKEND,
            provider=self.provider,
            model=self.model,
            dimensions=self.dimensions,
            batch_size=self.batch_size,
            chunk_inputs=list(plan.chunk_inputs),
            records=records,
        )

        plan.embedding_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = plan.embedding_manifest_path.parent / f"{plan.embedding_manifest_path.name}.tmp"
        try:
            manifest.save(tmp_path)
            tmp_path.replace(plan.embedding_manifest_path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            return _EmbeddingOutcome(plan.video_id, errors=(f"{plan.video_id}: could not finalize embedding manifest: {exc}",))

        return _EmbeddingOutcome(plan.video_id, processed=True)


def _records_for_chunk(chunk: ChunkManifestEntry, *, dimensions: int) -> list[EmbeddingRecord]:
    code_text = "\n\n".join(block.code for block in chunk.code_blocks if block.code.strip())
    texts = {
        "transcript": chunk.transcript,
        "ocr": chunk.ocr_text,
        "code": code_text,
        "summary": chunk.summary,
        "combined": _combined_text(chunk, code_text),
    }
    records: list[EmbeddingRecord] = []
    base_metadata = {
        "video_name": chunk.video_name,
        "start_seconds": chunk.start_seconds,
        "end_seconds": chunk.end_seconds,
        "topic": chunk.topic,
        "source_type": chunk.source_type,
        **chunk.metadata,
    }
    first_language = next((block.language for block in chunk.code_blocks if block.language), None)
    if first_language is not None:
        base_metadata["language"] = first_language

    for embedding_type, text in texts.items():
        normalized = text.strip()
        if not normalized:
            continue
        records.append(
            EmbeddingRecord(
                id=f"{chunk.id}_{embedding_type}",
                chunk_id=chunk.id,
                embedding_type=embedding_type,
                text=normalized,
                text_hash=text_hash(normalized),
                vector=embed_text_hashing(normalized, dimensions=dimensions),
                dimensions=dimensions,
                metadata={**base_metadata, "embedding_type": embedding_type},
            )
        )
    return records


def _combined_text(chunk: ChunkManifestEntry, code_text: str) -> str:
    return "\n\n".join(
        part for part in [chunk.topic, chunk.summary, chunk.transcript, chunk.ocr_text, code_text] if part.strip()
    )


def _chunk_signature(chunk: ChunkManifestEntry) -> EmbeddingChunkSignature:
    code_text = "\n\n".join(block.code for block in chunk.code_blocks if block.code.strip())
    metadata_json = json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True)
    return EmbeddingChunkSignature(
        id=chunk.id,
        source_type=chunk.source_type,
        start_seconds=chunk.start_seconds,
        end_seconds=chunk.end_seconds,
        topic_hash=text_hash(chunk.topic),
        summary_hash=text_hash(chunk.summary),
        transcript_hash=text_hash(chunk.transcript),
        ocr_hash=text_hash(chunk.ocr_text),
        code_hash=text_hash(code_text),
        metadata_hash=text_hash(metadata_json),
    )
