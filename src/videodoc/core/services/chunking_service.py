from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    InvalidChunkManifestError,
    InvalidVideoMetadataError,
    NoVideosFoundError,
)
from videodoc.core.models.chunk_manifest import (
    ChunkCodeBlock,
    ChunkCodeSignature,
    ChunkFrameSignature,
    ChunkManifest,
    ChunkManifestEntry,
    ChunkTranscriptSignature,
)
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import (
    ChunkRow,
    CodeBlockRow,
    FrameRow,
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    list_code_blocks,
    list_frames,
    list_transcript_segments,
    list_videos,
    replace_chunks,
)
from videodoc.core.utils.hardware import resolve_cpu_workers, resolve_executor_workers
from videodoc.core.utils.progress import ProgressReporter

_PAUSE_SPLIT_SECONDS = 8.0
_NEARBY_FRAME_MARGIN_SECONDS = 5.0
_SUMMARY_LIMIT = 220
_TOPIC_LIMIT = 80


@dataclass(frozen=True)
class ChunkingResult:
    processed: tuple[str, ...]
    skipped: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _ChunkingOutcome:
    video_id: str
    processed: bool = False
    skipped: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ChunkPlan:
    row: VideoRow
    video_dir: Path
    chunks_dir: Path
    chunks_rel: Path
    manifest_path: Path
    transcript_segments: tuple[TranscriptSegmentRow, ...]
    frames: tuple[FrameRow, ...]
    code_blocks: tuple[CodeBlockRow, ...]
    transcript_inputs: tuple[ChunkTranscriptSignature, ...]
    frame_inputs: tuple[ChunkFrameSignature, ...]
    code_inputs: tuple[ChunkCodeSignature, ...]
    has_inputs: bool
    needs_fresh: bool
    manifest: ChunkManifest | None = None
    load_error: str | None = None


@dataclass(frozen=True)
class _Window:
    start_seconds: float
    end_seconds: float
    transcript_segments: tuple[TranscriptSegmentRow, ...] = ()


class ChunkingService:
    def __init__(self, project_dir: Path, config: ProjectConfig, *, workers_override: int | None = None) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override
        self.min_duration_seconds = config.chunking.min_duration_seconds
        self.max_duration_seconds = config.chunking.max_duration_seconds
        self.include_nearby_frames = config.chunking.include_nearby_frames

    def run(self, progress: ProgressReporter | None = None) -> ChunkingResult:
        progress = progress or ProgressReporter()
        db_path = self.project_dir / self.config.paths.database
        if not db_path.exists():
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )
        if not db_path.is_file():
            raise DatabaseError(f"{db_path} exists but is not a file.")

        videos = list_videos(db_path)
        if not videos:
            raise NoVideosFoundError(
                f"No videos registered in {db_path.name} -- run 'videodoc ingest' first."
            )

        ensure_schema(db_path)
        ordered_videos = sorted(videos, key=lambda r: r.id)
        plans = [self._plan_for(row, db_path) for row in ordered_videos]

        configured_workers = resolve_cpu_workers("auto", self.workers_override)
        executor_workers = resolve_executor_workers(configured_workers, len(videos))

        processed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        with ThreadPoolExecutor(max_workers=executor_workers) as executor:
            futures = [
                executor.submit(self._process_plan, plan, index, len(plans), progress, db_path)
                for index, plan in enumerate(plans)
            ]
            for future in futures:
                outcome = future.result()
                if outcome.processed:
                    processed.append(outcome.video_id)
                if outcome.skipped:
                    skipped.append(outcome.video_id)
                errors.extend(outcome.errors)

        return ChunkingResult(tuple(processed), tuple(skipped), tuple(errors))

    def _plan_for(self, row: VideoRow, db_path: Path) -> _ChunkPlan:
        video_dir = self.project_dir / self.config.paths.workdir / row.id
        filesystem.ensure_video_workdir(video_dir)
        chunks_dir = video_dir / "chunks"
        chunks_rel = Path(self.config.paths.workdir) / row.id / "chunks" / f"{row.id}.json"
        manifest_path = chunks_dir / f"{row.id}.json"

        transcript_segments = tuple(list_transcript_segments(db_path, row.id))
        frames = tuple(list_frames(db_path, row.id))
        code_blocks = tuple(list_code_blocks(db_path, row.id))
        transcript_inputs = tuple(_transcript_signature(segment) for segment in transcript_segments)
        frame_inputs = tuple(_frame_signature(frame) for frame in frames)
        code_inputs = tuple(_code_signature(block) for block in code_blocks)
        has_inputs = bool(transcript_segments or any(frame.ocr_text is not None for frame in frames) or code_blocks)

        if not manifest_path.is_file():
            return _ChunkPlan(
                row,
                video_dir,
                chunks_dir,
                chunks_rel,
                manifest_path,
                transcript_segments,
                frames,
                code_blocks,
                transcript_inputs,
                frame_inputs,
                code_inputs,
                has_inputs,
                needs_fresh=has_inputs,
            )

        try:
            manifest = ChunkManifest.load(manifest_path)
        except InvalidChunkManifestError as exc:
            return _ChunkPlan(
                row,
                video_dir,
                chunks_dir,
                chunks_rel,
                manifest_path,
                transcript_segments,
                frames,
                code_blocks,
                transcript_inputs,
                frame_inputs,
                code_inputs,
                has_inputs,
                needs_fresh=False,
                load_error=str(exc),
            )

        settings_match = (
            manifest.min_duration_seconds == self.min_duration_seconds
            and manifest.max_duration_seconds == self.max_duration_seconds
            and manifest.include_nearby_frames == self.include_nearby_frames
        )
        inputs_match = (
            tuple(manifest.transcript_inputs) == transcript_inputs
            and tuple(manifest.frame_inputs) == frame_inputs
            and tuple(manifest.code_inputs) == code_inputs
        )
        return _ChunkPlan(
            row,
            video_dir,
            chunks_dir,
            chunks_rel,
            manifest_path,
            transcript_segments,
            frames,
            code_blocks,
            transcript_inputs,
            frame_inputs,
            code_inputs,
            has_inputs,
            needs_fresh=not (settings_match and inputs_match),
            manifest=manifest,
        )

    def _process_plan(
        self,
        plan: _ChunkPlan,
        index: int,
        total: int,
        progress: ProgressReporter,
        db_path: Path,
    ) -> _ChunkingOutcome:
        progress.start_item(plan.row.id, index, total)
        try:
            if plan.load_error is not None:
                return _ChunkingOutcome(
                    plan.row.id,
                    errors=(f"{plan.row.id}: chunks already exist but chunk manifest could not be read: {plan.load_error}",),
                )
            if not plan.has_inputs and plan.manifest is None:
                return _ChunkingOutcome(plan.row.id, skipped=True)
            if not plan.needs_fresh:
                if plan.manifest is None:
                    return _ChunkingOutcome(plan.row.id, skipped=True)
                return self._process_existing(plan, db_path)
            return self._process_fresh(plan, db_path, progress)
        finally:
            progress.finish_item(plan.row.id)

    def _process_existing(self, plan: _ChunkPlan, db_path: Path) -> _ChunkingOutcome:
        assert plan.manifest is not None
        try:
            replace_chunks(db_path, plan.row.id, _manifest_to_rows(plan.row.id, plan.manifest))
        except DatabaseError as exc:
            return _ChunkingOutcome(plan.row.id, errors=(f"{plan.row.id}: chunks already exist but database could not be updated: {exc}",))

        if self._reconcile_metadata(plan.video_dir, plan.chunks_rel):
            return _ChunkingOutcome(plan.row.id, skipped=True)
        return _ChunkingOutcome(plan.row.id, errors=(f"{plan.row.id}: chunks already exist but metadata.json could not be updated",))

    def _process_fresh(self, plan: _ChunkPlan, db_path: Path, progress: ProgressReporter) -> _ChunkingOutcome:
        manifest = self._build_manifest(plan)
        plan.chunks_dir.mkdir(parents=True, exist_ok=True)
        tmp_manifest_path = plan.manifest_path.parent / f"{plan.manifest_path.name}.tmp"
        try:
            manifest.save(tmp_manifest_path)
            tmp_manifest_path.replace(plan.manifest_path)
        except OSError as exc:
            tmp_manifest_path.unlink(missing_ok=True)
            return _ChunkingOutcome(plan.row.id, errors=(f"{plan.row.id}: could not finalize chunk manifest: {exc}",))

        progress.update_item(plan.row.id, 0.8)
        try:
            replace_chunks(db_path, plan.row.id, _manifest_to_rows(plan.row.id, manifest))
        except DatabaseError as exc:
            return _ChunkingOutcome(
                plan.row.id,
                errors=(f"{plan.row.id}: chunks saved to {plan.manifest_path.name} but database update failed: {exc}",),
            )

        if self._reconcile_metadata(plan.video_dir, plan.chunks_rel):
            return _ChunkingOutcome(plan.row.id, processed=True)
        return _ChunkingOutcome(
            plan.row.id,
            errors=(f"{plan.row.id}: chunks saved to {plan.manifest_path.name} but metadata.json could not be updated",),
        )

    def _build_manifest(self, plan: _ChunkPlan) -> ChunkManifest:
        windows = _build_windows(
            plan.row,
            plan.transcript_segments,
            plan.frames,
            plan.code_blocks,
            min_duration_seconds=self.min_duration_seconds,
            max_duration_seconds=self.max_duration_seconds,
        )
        chunks: list[ChunkManifestEntry] = []
        for window in windows:
            entry = _window_to_chunk(
                plan.row,
                len([chunk for chunk in chunks if chunk.source_type != "code"]) + 1,
                window,
                plan.frames,
                plan.code_blocks,
                include_nearby_frames=self.include_nearby_frames,
            )
            if entry is not None:
                chunks.append(entry)

        for block in sorted(plan.code_blocks, key=lambda b: (b.timestamp_seconds if b.timestamp_seconds is not None else -1.0, b.id)):
            chunks.append(_code_block_to_chunk(plan.row, block))

        return ChunkManifest(
            video_id=plan.row.id,
            video_name=plan.row.filename,
            chunks=chunks,
            transcript_inputs=list(plan.transcript_inputs),
            frame_inputs=list(plan.frame_inputs),
            code_inputs=list(plan.code_inputs),
            min_duration_seconds=self.min_duration_seconds,
            max_duration_seconds=self.max_duration_seconds,
            include_nearby_frames=self.include_nearby_frames,
        )

    def _reconcile_metadata(self, video_dir: Path, chunks_rel: Path) -> bool:
        metadata_path = video_dir / "metadata.json"
        try:
            metadata = VideoMetadata.load(metadata_path)
        except InvalidVideoMetadataError:
            return False

        target = chunks_rel.as_posix()
        if metadata.chunks_path == target:
            return True

        try:
            metadata.model_copy(update={"chunks_path": target}).save(metadata_path)
        except OSError:
            return False
        return True


def _build_windows(
    row: VideoRow,
    transcript_segments: tuple[TranscriptSegmentRow, ...],
    frames: tuple[FrameRow, ...],
    code_blocks: tuple[CodeBlockRow, ...],
    *,
    min_duration_seconds: int,
    max_duration_seconds: int,
) -> list[_Window]:
    if transcript_segments:
        return _transcript_windows(transcript_segments, min_duration_seconds, max_duration_seconds)
    return _event_windows(row, frames, code_blocks, min_duration_seconds, max_duration_seconds)


def _transcript_windows(
    segments: tuple[TranscriptSegmentRow, ...],
    min_duration_seconds: int,
    max_duration_seconds: int,
) -> list[_Window]:
    windows: list[_Window] = []
    current: list[TranscriptSegmentRow] = []

    for segment in sorted(segments, key=lambda s: (s.start_seconds, s.end_seconds, s.id)):
        if not current:
            current = [segment]
            continue

        start = current[0].start_seconds
        current_end = current[-1].end_seconds
        gap = max(0.0, segment.start_seconds - current_end)
        duration_with_segment = segment.end_seconds - start
        current_duration = current_end - start
        should_split = (
            current_duration >= min_duration_seconds
            and (duration_with_segment > max_duration_seconds or gap >= _PAUSE_SPLIT_SECONDS)
        )
        if should_split:
            windows.append(_Window(start, current_end, tuple(current)))
            current = [segment]
        else:
            current.append(segment)

    if current:
        windows.append(_Window(current[0].start_seconds, current[-1].end_seconds, tuple(current)))
    return windows


def _event_windows(
    row: VideoRow,
    frames: tuple[FrameRow, ...],
    code_blocks: tuple[CodeBlockRow, ...],
    min_duration_seconds: int,
    max_duration_seconds: int,
) -> list[_Window]:
    events = sorted(
        {frame.timestamp_seconds for frame in frames if frame.ocr_text is not None}
        | {block.timestamp_seconds for block in code_blocks if block.timestamp_seconds is not None}
    )
    if not events:
        return []

    windows: list[_Window] = []
    start = max(0.0, events[0] - _NEARBY_FRAME_MARGIN_SECONDS)
    end = events[0]
    for event in events[1:]:
        if event - start > max_duration_seconds and end - start >= min_duration_seconds:
            windows.append(_Window(start, min(row.duration_seconds, max(end + _NEARBY_FRAME_MARGIN_SECONDS, start))))
            start = max(0.0, event - _NEARBY_FRAME_MARGIN_SECONDS)
        end = event

    final_end = max(end + _NEARBY_FRAME_MARGIN_SECONDS, start + min_duration_seconds)
    windows.append(_Window(start, min(row.duration_seconds, final_end)))
    return windows


def _window_to_chunk(
    row: VideoRow,
    index: int,
    window: _Window,
    frames: tuple[FrameRow, ...],
    code_blocks: tuple[CodeBlockRow, ...],
    *,
    include_nearby_frames: bool,
) -> ChunkManifestEntry | None:
    margin = _NEARBY_FRAME_MARGIN_SECONDS if include_nearby_frames else 0.0
    transcript = _join_unique(segment.text for segment in window.transcript_segments)
    frames_in_window = [
        frame for frame in frames
        if frame.ocr_text is not None and window.start_seconds - margin <= frame.timestamp_seconds <= window.end_seconds + margin
    ]
    ocr_text = _join_unique(frame.ocr_text or "" for frame in frames_in_window)
    code_in_window = [
        block for block in code_blocks
        if block.timestamp_seconds is not None and window.start_seconds - margin <= block.timestamp_seconds <= window.end_seconds + margin
    ]
    if not transcript and not ocr_text and not code_in_window:
        return None

    code_manifest_blocks = [_to_chunk_code_block(block) for block in code_in_window]
    source_type = _source_type(bool(transcript), bool(ocr_text), bool(code_manifest_blocks))
    confidence = _average_confidence(
        [segment.confidence for segment in window.transcript_segments]
        + [frame.ocr_confidence for frame in frames_in_window]
        + [block.confidence for block in code_in_window]
    )
    metadata = {
        "source_type": source_type,
        "transcript_segment_ids": [segment.id for segment in window.transcript_segments],
        "frame_ids": [frame.id for frame in frames_in_window],
        "code_block_ids": [block.id for block in code_in_window],
        "contains_code": bool(code_manifest_blocks),
        "confidence": confidence,
    }
    summary = _summary(transcript, ocr_text, [block.code for block in code_in_window])
    return ChunkManifestEntry(
        id=f"{row.id}_chunk_{index:04d}",
        source_type=source_type,
        start_seconds=window.start_seconds,
        end_seconds=window.end_seconds,
        topic=_topic(summary, code_manifest_blocks),
        summary=summary,
        transcript=transcript,
        ocr_text=ocr_text,
        code_blocks=code_manifest_blocks,
        video_name=row.filename,
        metadata=metadata,
    )


def _code_block_to_chunk(row: VideoRow, block: CodeBlockRow) -> ChunkManifestEntry:
    start = block.timestamp_seconds or 0.0
    code_block = _to_chunk_code_block(block)
    confidence = block.confidence
    metadata = {
        "source_type": "code",
        "code_block_ids": [block.id],
        "contains_code": True,
        "confidence": confidence,
        "verified": block.verified,
    }
    summary = _truncate(block.code, _SUMMARY_LIMIT)
    return ChunkManifestEntry(
        id=f"{block.id}_chunk",
        source_type="code",
        start_seconds=start,
        end_seconds=start,
        topic=_topic(summary, [code_block]),
        summary=summary,
        transcript="",
        ocr_text="",
        code_blocks=[code_block],
        video_name=row.filename,
        metadata=metadata,
    )


def _to_chunk_code_block(block: CodeBlockRow) -> ChunkCodeBlock:
    return ChunkCodeBlock(
        id=block.id,
        language=block.language,
        code=block.code,
        timestamp_seconds=block.timestamp_seconds,
        confidence=block.confidence,
        verified=block.verified,
    )


def _manifest_to_rows(video_id: str, manifest: ChunkManifest) -> list[ChunkRow]:
    return [
        ChunkRow(
            id=chunk.id,
            video_id=video_id,
            start_seconds=chunk.start_seconds,
            end_seconds=chunk.end_seconds,
            topic=chunk.topic,
            summary=chunk.summary,
            transcript=chunk.transcript,
            ocr_text=chunk.ocr_text,
            metadata_json=json.dumps(chunk.metadata, ensure_ascii=False, sort_keys=True),
        )
        for chunk in manifest.chunks
    ]


def _source_type(has_transcript: bool, has_ocr: bool, has_code: bool) -> str:
    parts = []
    if has_transcript:
        parts.append("transcript")
    if has_ocr:
        parts.append("ocr")
    if has_code:
        parts.append("code")
    return "_".join(parts) if parts else "empty"


def _join_unique(items) -> str:
    seen: set[str] = set()
    kept: list[str] = []
    for item in items:
        normalized = " ".join((item or "").split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        kept.append((item or "").strip())
    return "\n\n".join(kept)


def _summary(transcript: str, ocr_text: str, code_blocks: list[str]) -> str:
    candidate = transcript or ocr_text or "\n".join(code_blocks)
    return _truncate(candidate, _SUMMARY_LIMIT) or "Chunk senza testo leggibile."


def _topic(summary: str, code_blocks: list[ChunkCodeBlock]) -> str:
    if code_blocks and summary:
        prefix = "Codice"
        language = code_blocks[0].language
        if language and language != "other":
            prefix = f"Codice {language}"
        return _truncate(f"{prefix}: {summary}", _TOPIC_LIMIT)
    return _truncate(summary, _TOPIC_LIMIT)


def _truncate(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _average_confidence(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _transcript_signature(segment: TranscriptSegmentRow) -> ChunkTranscriptSignature:
    return ChunkTranscriptSignature(
        id=segment.id,
        start_seconds=segment.start_seconds,
        end_seconds=segment.end_seconds,
        text_hash=_hash_text(segment.text),
        confidence=segment.confidence,
    )


def _frame_signature(frame: FrameRow) -> ChunkFrameSignature:
    return ChunkFrameSignature(
        id=frame.id,
        timestamp_seconds=frame.timestamp_seconds,
        perceptual_hash=frame.perceptual_hash,
        ocr_text_hash=None if frame.ocr_text is None else _hash_text(frame.ocr_text),
        ocr_confidence=frame.ocr_confidence,
        contains_code=frame.contains_code,
    )


def _code_signature(block: CodeBlockRow) -> ChunkCodeSignature:
    return ChunkCodeSignature(
        id=block.id,
        timestamp_seconds=block.timestamp_seconds,
        language=block.language,
        code_hash=_hash_text(block.code),
        confidence=block.confidence,
        verified=block.verified,
    )


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
