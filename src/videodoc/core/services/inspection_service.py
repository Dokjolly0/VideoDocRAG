from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    InspectionUnavailableError,
    InvalidDocumentationSectionManifestError,
    NoVideosFoundError,
)
from videodoc.core.models.document_section import GeneratedSectionManifest
from videodoc.core.storage.database import (
    ChunkRow,
    CodeBlockRow,
    FrameRow,
    TranscriptSegmentRow,
    VideoRow,
    list_chunks,
    list_code_blocks,
    list_frames,
    list_transcript_segments,
    list_videos,
)


@dataclass(frozen=True)
class InspectedTranscript:
    segment_id: str
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None
    distance_seconds: float


@dataclass(frozen=True)
class InspectedFrame:
    frame_id: str
    timestamp_seconds: float
    image_path: str
    ocr_text: str | None
    ocr_confidence: float | None
    contains_code: bool
    distance_seconds: float


@dataclass(frozen=True)
class InspectedCodeBlock:
    block_id: str
    timestamp_seconds: float | None
    language: str | None
    code: str
    source: str | None
    confidence: float | None
    verified: bool
    distance_seconds: float | None


@dataclass(frozen=True)
class InspectedChunk:
    chunk_id: str
    start_seconds: float
    end_seconds: float
    topic: str | None
    summary: str | None
    distance_seconds: float


@dataclass(frozen=True)
class InspectionDocumentationHit:
    section_title: str
    output_path: str
    rank: int
    chunk_id: str
    start_seconds: float | None
    end_seconds: float | None
    topic: str | None


@dataclass(frozen=True)
class InspectionResult:
    project_slug: str
    video_id: str
    video_name: str
    timestamp_seconds: float
    transcript: InspectedTranscript | None
    frame: InspectedFrame | None
    code_blocks: tuple[InspectedCodeBlock, ...]
    chunk: InspectedChunk | None
    documentation_hits: tuple[InspectionDocumentationHit, ...]
    warnings: tuple[str, ...]


class TimestampInspectionService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config
        self.db_path = self.project_dir / config.paths.database
        self.docs_sources_dir = self.project_dir / config.paths.output / "sources"

    def inspect(self, *, timestamp_seconds: float, video: str | None = None) -> InspectionResult:
        if timestamp_seconds < 0:
            raise ValueError("Timestamp must be zero or positive.")
        row = self._resolve_video(video)
        transcript = _inspect_transcript(list_transcript_segments(self.db_path, row.id), timestamp_seconds)
        frame = _inspect_frame(list_frames(self.db_path, row.id), timestamp_seconds)
        code_blocks = _inspect_code_blocks(list_code_blocks(self.db_path, row.id), timestamp_seconds)
        chunk = _inspect_chunk(list_chunks(self.db_path, row.id), timestamp_seconds)
        hits, warnings = self._documentation_hits(row, timestamp_seconds)
        return InspectionResult(
            project_slug=self.config.project.slug,
            video_id=row.id,
            video_name=row.filename,
            timestamp_seconds=timestamp_seconds,
            transcript=transcript,
            frame=frame,
            code_blocks=code_blocks,
            chunk=chunk,
            documentation_hits=hits,
            warnings=warnings,
        )

    def _resolve_video(self, selector: str | None) -> VideoRow:
        if not self.db_path.exists():
            raise NoVideosFoundError(f"No videos registered in {self.db_path.name} -- run 'videodoc ingest' first.")
        if not self.db_path.is_file():
            raise DatabaseError(f"{self.db_path} exists but is not a file.")

        videos = list_videos(self.db_path)
        if not videos:
            raise NoVideosFoundError(f"No videos registered in {self.db_path.name} -- run 'videodoc ingest' first.")
        if selector is None:
            if len(videos) == 1:
                return videos[0]
            raise InspectionUnavailableError(
                f"--video is required because project '{self.config.project.slug}' has {len(videos)} videos."
            )

        wanted = selector.strip().lower()
        matches = [
            row for row in videos
            if wanted in {row.id.lower(), row.filename.lower(), Path(row.filename).stem.lower()}
        ]
        if not matches:
            raise InspectionUnavailableError(f"Video '{selector}' is not registered in project '{self.config.project.slug}'.")
        if len(matches) > 1:
            ids = ", ".join(row.id for row in matches)
            raise InspectionUnavailableError(f"Video selector '{selector}' is ambiguous; matches: {ids}.")
        return matches[0]

    def _documentation_hits(
        self,
        row: VideoRow,
        timestamp_seconds: float,
    ) -> tuple[tuple[InspectionDocumentationHit, ...], tuple[str, ...]]:
        if not self.docs_sources_dir.is_dir():
            return (), ()
        hits: list[InspectionDocumentationHit] = []
        warnings: list[str] = []
        for path in sorted(self.docs_sources_dir.glob("*.sources.json")):
            try:
                manifest = GeneratedSectionManifest.load(path)
            except InvalidDocumentationSectionManifestError as exc:
                warnings.append(f"{path.name} could not be read: {exc}")
                continue
            for source in manifest.sources:
                same_video = source.video_id == row.id or source.video_name == row.filename
                if same_video and _interval_distance(source.start_seconds, source.end_seconds, timestamp_seconds) == 0.0:
                    hits.append(
                        InspectionDocumentationHit(
                            section_title=manifest.section_title,
                            output_path=manifest.output_path,
                            rank=source.rank,
                            chunk_id=source.chunk_id,
                            start_seconds=source.start_seconds,
                            end_seconds=source.end_seconds,
                            topic=source.topic,
                        )
                    )
        hits.sort(key=lambda hit: (hit.output_path, hit.rank))
        return tuple(hits), tuple(warnings)


def _inspect_transcript(segments: list[TranscriptSegmentRow], timestamp_seconds: float) -> InspectedTranscript | None:
    if not segments:
        return None
    segment = min(
        segments,
        key=lambda item: (_interval_distance(item.start_seconds, item.end_seconds, timestamp_seconds), item.start_seconds, item.id),
    )
    return InspectedTranscript(
        segment_id=segment.id,
        start_seconds=segment.start_seconds,
        end_seconds=segment.end_seconds,
        text=segment.text,
        confidence=segment.confidence,
        distance_seconds=_interval_distance(segment.start_seconds, segment.end_seconds, timestamp_seconds),
    )


def _inspect_frame(frames: list[FrameRow], timestamp_seconds: float) -> InspectedFrame | None:
    if not frames:
        return None
    frame = min(frames, key=lambda item: (abs(item.timestamp_seconds - timestamp_seconds), item.timestamp_seconds, item.id))
    return InspectedFrame(
        frame_id=frame.id,
        timestamp_seconds=frame.timestamp_seconds,
        image_path=frame.image_path,
        ocr_text=frame.ocr_text,
        ocr_confidence=frame.ocr_confidence,
        contains_code=frame.contains_code,
        distance_seconds=abs(frame.timestamp_seconds - timestamp_seconds),
    )


def _inspect_code_blocks(blocks: list[CodeBlockRow], timestamp_seconds: float) -> tuple[InspectedCodeBlock, ...]:
    timed = [block for block in blocks if block.timestamp_seconds is not None]
    ordered = sorted(timed, key=lambda item: (abs((item.timestamp_seconds or 0.0) - timestamp_seconds), item.timestamp_seconds or 0.0, item.id))
    selected = ordered[:3]
    return tuple(
        InspectedCodeBlock(
            block_id=block.id,
            timestamp_seconds=block.timestamp_seconds,
            language=block.language,
            code=block.code,
            source=block.source,
            confidence=block.confidence,
            verified=block.verified,
            distance_seconds=None if block.timestamp_seconds is None else abs(block.timestamp_seconds - timestamp_seconds),
        )
        for block in selected
    )


def _inspect_chunk(chunks: list[ChunkRow], timestamp_seconds: float) -> InspectedChunk | None:
    if not chunks:
        return None
    chunk = min(
        chunks,
        key=lambda item: (_interval_distance(item.start_seconds, item.end_seconds, timestamp_seconds), item.start_seconds, item.id),
    )
    return InspectedChunk(
        chunk_id=chunk.id,
        start_seconds=chunk.start_seconds,
        end_seconds=chunk.end_seconds,
        topic=chunk.topic,
        summary=chunk.summary,
        distance_seconds=_interval_distance(chunk.start_seconds, chunk.end_seconds, timestamp_seconds),
    )


def _interval_distance(start_seconds: float | None, end_seconds: float | None, timestamp_seconds: float) -> float:
    if start_seconds is None and end_seconds is None:
        return float("inf")
    start = 0.0 if start_seconds is None else start_seconds
    end = start if end_seconds is None else end_seconds
    if start <= timestamp_seconds <= end:
        return 0.0
    return min(abs(timestamp_seconds - start), abs(timestamp_seconds - end))
