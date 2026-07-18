from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, InvalidSourceManifestError, InvalidVectorIndexError
from videodoc.core.models.source_manifest import SourceManifest
from videodoc.core.models.vector_index import VectorIndex
from videodoc.core.storage.database import (
    list_chat_sessions,
    list_chunks,
    list_code_blocks,
    list_frames,
    list_transcript_segments,
    list_videos,
)


@dataclass(frozen=True)
class VideoPipelineStatus:
    video_id: str
    filename: str
    audio: bool
    transcript: bool
    transcript_segments: int
    frames: bool
    frame_rows: int
    ocr: bool
    code: bool
    code_blocks: int
    chunks: bool
    chunk_rows: int
    embeddings: bool


@dataclass(frozen=True)
class SourceScanStatus:
    scanned: bool
    videos: int = 0
    attachments: int = 0
    codebase_files: int = 0


@dataclass(frozen=True)
class IndexStatus:
    present: bool
    valid: bool
    records: int = 0
    inputs: int = 0


@dataclass(frozen=True)
class DocumentationStatus:
    outline: bool
    sections: int
    source_manifests: int
    review_report: bool
    review_json: bool
    export_formats: tuple[str, ...]


@dataclass(frozen=True)
class PipelineStatusResult:
    project_slug: str
    project_dir: Path
    database_path: Path
    sources: SourceScanStatus
    videos: tuple[VideoPipelineStatus, ...]
    raw_index: IndexStatus
    documentation_index: IndexStatus
    documentation: DocumentationStatus
    chat_sessions: int
    warnings: tuple[str, ...]


class PipelineStatusService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.db_path = self.project_dir / config.paths.database
        self.workdir = self.project_dir / config.paths.workdir
        self.indexes_dir = self.project_dir / config.paths.indexes
        self.docs_dir = self.project_dir / config.paths.output

    def run(self) -> PipelineStatusResult:
        warnings: list[str] = []
        sources = self._source_status(warnings)
        videos = self._video_statuses()
        raw_index = self._index_status(self.indexes_dir / "vector_index.json", warnings, label="vector index")
        docs_index = self._index_status(
            self.indexes_dir / "documentation_index.json",
            warnings,
            label="documentation index",
        )
        documentation = self._documentation_status()
        chat_sessions = self._chat_sessions()

        return PipelineStatusResult(
            project_slug=self.config.project.slug,
            project_dir=self.project_dir,
            database_path=self.db_path,
            sources=sources,
            videos=tuple(videos),
            raw_index=raw_index,
            documentation_index=docs_index,
            documentation=documentation,
            chat_sessions=chat_sessions,
            warnings=tuple(warnings),
        )

    def _source_status(self, warnings: list[str]) -> SourceScanStatus:
        manifest_path = self.project_dir / "sources.yaml"
        if not manifest_path.is_file():
            return SourceScanStatus(scanned=False)
        try:
            manifest = SourceManifest.load(manifest_path)
        except InvalidSourceManifestError as exc:
            warnings.append(f"sources.yaml could not be read: {exc}")
            return SourceScanStatus(scanned=False)
        return SourceScanStatus(
            scanned=True,
            videos=len(manifest.videos),
            attachments=len(manifest.attachments),
            codebase_files=len(manifest.codebase.files) if manifest.codebase.present else 0,
        )

    def _video_statuses(self) -> list[VideoPipelineStatus]:
        if not self.db_path.exists():
            return []
        if not self.db_path.is_file():
            raise DatabaseError(f"{self.db_path} exists but is not a file.")

        rows = list_videos(self.db_path)
        statuses: list[VideoPipelineStatus] = []
        for row in rows:
            video_dir = self.workdir / row.id
            statuses.append(
                VideoPipelineStatus(
                    video_id=row.id,
                    filename=row.filename,
                    audio=(video_dir / "audio" / f"{row.id}.wav").is_file(),
                    transcript=(video_dir / "transcript" / f"{row.id}.json").is_file(),
                    transcript_segments=len(list_transcript_segments(self.db_path, row.id)),
                    frames=(video_dir / "frames" / "frames.json").is_file(),
                    frame_rows=len(list_frames(self.db_path, row.id)),
                    ocr=(video_dir / "ocr" / f"{row.id}.json").is_file(),
                    code=(video_dir / "code" / f"{row.id}.json").is_file(),
                    code_blocks=len(list_code_blocks(self.db_path, row.id)),
                    chunks=(video_dir / "chunks" / f"{row.id}.json").is_file(),
                    chunk_rows=len(list_chunks(self.db_path, row.id)),
                    embeddings=(self.indexes_dir / "embeddings" / f"{row.id}.json").is_file(),
                )
            )
        return statuses

    def _index_status(self, path: Path, warnings: list[str], *, label: str) -> IndexStatus:
        if not path.is_file():
            return IndexStatus(present=False, valid=False)
        try:
            index = VectorIndex.load(path)
        except InvalidVectorIndexError as exc:
            warnings.append(f"{label} could not be read: {exc}")
            return IndexStatus(present=True, valid=False)
        return IndexStatus(present=True, valid=True, records=len(index.records), inputs=len(index.inputs))

    def _documentation_status(self) -> DocumentationStatus:
        sections = tuple(sorted(self.docs_dir.glob("[0-9][0-9]-*.md"))) if self.docs_dir.is_dir() else ()
        sources_dir = self.docs_dir / "sources"
        source_manifests = tuple(sorted(sources_dir.glob("*.sources.json"))) if sources_dir.is_dir() else ()
        return DocumentationStatus(
            outline=(self.docs_dir / "outline.md").is_file(),
            sections=len(sections),
            source_manifests=len(source_manifests),
            review_report=(self.docs_dir / "review_report.md").is_file(),
            review_json=(self.docs_dir / "review_report.json").is_file(),
            export_formats=_export_formats(self.project_dir / "exports"),
        )

    def _chat_sessions(self) -> int:
        if not self.db_path.exists():
            return 0
        if not self.db_path.is_file():
            raise DatabaseError(f"{self.db_path} exists but is not a file.")
        return len(list_chat_sessions(self.db_path))


def _export_formats(exports_dir: Path) -> tuple[str, ...]:
    if not exports_dir.is_dir():
        return ()
    formats = []
    for child in sorted(exports_dir.iterdir(), key=lambda path: path.name):
        if child.is_dir() and any(path.is_file() for path in child.rglob("*")):
            formats.append(child.name)
    return tuple(formats)
