from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    ExternalToolNotFoundError,
    InvalidFrameManifestError,
    InvalidVideoMetadataError,
    NoVideosFoundError,
    SceneDetectionUnavailableError,
)
from videodoc.core.models.frame_manifest import FrameManifest, FrameManifestEntry
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import (
    FrameRow,
    VideoRow,
    ensure_schema,
    list_transcript_segments,
    list_videos,
    replace_frames,
)
from videodoc.core.utils.ffmpeg import FrameExtractionError, extract_frames
from videodoc.core.utils.frame_hash import average_hash, is_near_duplicate
from videodoc.core.utils.frame_selection import (
    INTERVAL_PRIORITY,
    FrameCandidate,
    extract_keyword_timestamps,
    match_frames_to_candidates,
    select_frame_timestamps,
)
from videodoc.core.utils.hardware import resolve_cpu_workers, resolve_executor_workers, resolve_ffmpeg_threads
from videodoc.core.utils.progress import ProgressReporter
from videodoc.core.utils.scene_detection import SceneDetectionError, detect_scene_timestamps, scenedetect_available


@dataclass(frozen=True)
class FrameExtractionResult:
    extracted: tuple[str, ...]  # frames freshly produced this run
    skipped: tuple[str, ...]  # frames/frames.json already existed, ffmpeg not invoked
    errors: tuple[str, ...]  # per-video ffmpeg/scenedetect/DB/metadata.json-update failures


@dataclass(frozen=True)
class _FrameExtractionOutcome:
    video_id: str
    extracted: bool = False
    skipped: bool = False
    errors: tuple[str, ...] = ()


class FrameExtractionService:
    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        *,
        workers_override: int | None = None,
        interval_seconds_override: int | None = None,
        scene_detection_override: bool | None = None,
        keyword_boost_override: bool | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override
        self.interval_seconds = interval_seconds_override if interval_seconds_override is not None else config.frames.interval_seconds
        self.scene_detection = scene_detection_override if scene_detection_override is not None else config.frames.scene_detection
        self.keyword_boost = keyword_boost_override if keyword_boost_override is not None else config.frames.keyword_boost

    def run(self, progress: ProgressReporter | None = None) -> FrameExtractionResult:
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

        if shutil.which("ffmpeg") is None:
            raise ExternalToolNotFoundError(
                "ffmpeg was not found on PATH. Install FFmpeg and make sure ffmpeg is available "
                "before running 'videodoc frames' -- see RUN.md."
            )

        if self.scene_detection and not scenedetect_available():
            raise SceneDetectionUnavailableError(
                "config.frames.scene_detection is enabled but the 'scenedetect' package is not "
                "installed -- run 'pip install scenedetect' or pass --no-scene-detection."
            )

        # A project.db created before the frames table existed only has
        # videos/transcript_segments -- ensure_schema is idempotent and must
        # be (re-)run here, same reasoning as TranscriptionService.
        ensure_schema(db_path)

        configured_workers = resolve_cpu_workers(self.config.frames.workers, self.workers_override)
        executor_workers = resolve_executor_workers(configured_workers, len(videos))
        ffmpeg_threads = resolve_ffmpeg_threads(executor_workers)

        extracted: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        ordered_videos = sorted(videos, key=lambda r: r.id)
        total = len(ordered_videos)
        with ThreadPoolExecutor(max_workers=executor_workers) as executor:
            futures = [
                executor.submit(self._process_video, row, index, total, progress, db_path, ffmpeg_threads)
                for index, row in enumerate(ordered_videos)
            ]
            for future in futures:
                outcome = future.result()
                if outcome.extracted:
                    extracted.append(outcome.video_id)
                if outcome.skipped:
                    skipped.append(outcome.video_id)
                errors.extend(outcome.errors)

        return FrameExtractionResult(tuple(extracted), tuple(skipped), tuple(errors))

    def _process_video(
        self,
        row: VideoRow,
        index: int,
        total: int,
        progress: ProgressReporter,
        db_path: Path,
        ffmpeg_threads: int,
    ) -> _FrameExtractionOutcome:
        progress.start_item(row.id, index, total)
        try:
            video_dir = self.project_dir / self.config.paths.workdir / row.id
            filesystem.ensure_video_workdir(video_dir)  # defensive: workdir may have been deleted manually
            frames_dir = video_dir / "frames"
            frames_rel = Path(self.config.paths.workdir) / row.id / "frames"
            manifest_path = frames_dir / "frames.json"

            if manifest_path.is_file():
                return self._process_existing(row, video_dir, manifest_path, frames_rel, db_path)
            return self._process_fresh(row, video_dir, frames_dir, frames_rel, manifest_path, db_path, progress, ffmpeg_threads)
        finally:
            progress.finish_item(row.id)

    def _process_existing(
        self,
        row: VideoRow,
        video_dir: Path,
        manifest_path: Path,
        frames_rel: Path,
        db_path: Path,
    ) -> _FrameExtractionOutcome:
        # Already extracted in a previous run -- ffmpeg/scenedetect are never
        # re-invoked, but the DB rows are always rewritten from the on-disk
        # manifest (cheap DELETE+INSERT), so a prior transient DB failure
        # self-heals instead of staying silently empty forever once
        # frames.json already exists. Mirrors TranscriptionService exactly.
        try:
            manifest = FrameManifest.load(manifest_path)
        except InvalidFrameManifestError as exc:
            return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: frames already exist but frames.json could not be read: {exc}",))

        try:
            replace_frames(db_path, row.id, _manifest_to_rows(row.id, manifest))
        except DatabaseError as exc:
            return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: frames already exist but database could not be updated: {exc}",))

        if self._reconcile_metadata(video_dir, frames_rel):
            return _FrameExtractionOutcome(row.id, skipped=True)
        return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: frames already exist but metadata.json could not be updated",))

    def _process_fresh(
        self,
        row: VideoRow,
        video_dir: Path,
        frames_dir: Path,
        frames_rel: Path,
        manifest_path: Path,
        db_path: Path,
        progress: ProgressReporter,
        ffmpeg_threads: int,
    ) -> _FrameExtractionOutcome:
        source_video = Path(row.path)
        if not source_video.is_file():
            return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: source video file not found at {source_video}",))

        scene_timestamps: list[float] = []
        if self.scene_detection:
            try:
                scene_timestamps = detect_scene_timestamps(source_video)
            except SceneDetectionError as exc:
                return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: {exc}",))
        progress.update_item(row.id, 0.2)

        keyword_timestamps: list[float] = []
        if self.keyword_boost:
            segments = list_transcript_segments(db_path, row.id)
            keyword_timestamps = extract_keyword_timestamps(
                [(s.start_seconds, s.end_seconds, s.text) for s in segments]
            )

        candidates = select_frame_timestamps(
            row.duration_seconds,
            interval_seconds=self.interval_seconds,
            scene_timestamps=scene_timestamps,
            keyword_timestamps=keyword_timestamps,
        )

        staging_dir = frames_dir / ".staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)  # leftover from a previous crashed/interrupted run
        staging_dir.mkdir(parents=True)

        try:
            if candidates:
                extracted_frames = extract_frames(
                    source_video, staging_dir, [c.timestamp_seconds for c in candidates], threads=ffmpeg_threads,
                )
            else:
                extracted_frames = []
        except FrameExtractionError as exc:
            shutil.rmtree(staging_dir, ignore_errors=True)
            return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: {exc}",))
        progress.update_item(row.id, 0.8)

        matched = match_frames_to_candidates(candidates, extracted_frames)
        kept = self._dedup_by_hash(matched)

        entries: list[FrameManifestEntry] = []
        frame_rows: list[FrameRow] = []
        for position, (pts, path, hash_hex) in enumerate(kept, start=1):
            final_name = f"frame_{position:04d}.jpg"
            final_path = frames_dir / final_name
            path.replace(final_path)
            rel_path = (frames_rel / final_name).as_posix()
            frame_id = f"{row.id}_frame_{position:04d}"
            entries.append(FrameManifestEntry(id=frame_id, timestamp_seconds=pts, image_path=rel_path, perceptual_hash=hash_hex))
            frame_rows.append(
                FrameRow(id=frame_id, video_id=row.id, timestamp_seconds=pts, image_path=rel_path, perceptual_hash=hash_hex)
            )

        shutil.rmtree(staging_dir, ignore_errors=True)  # removes any dropped near-duplicate frames still there

        manifest = FrameManifest(video_id=row.id, frames=entries)
        tmp_manifest_path = manifest_path.parent / f"{manifest_path.name}.tmp"
        try:
            manifest.save(tmp_manifest_path)
            tmp_manifest_path.replace(manifest_path)
        except OSError as exc:
            tmp_manifest_path.unlink(missing_ok=True)
            return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: could not finalize frames.json: {exc}",))

        try:
            replace_frames(db_path, row.id, frame_rows)
        except DatabaseError as exc:
            return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: frames saved to frames.json but database update failed: {exc}",))

        if self._reconcile_metadata(video_dir, frames_rel):
            return _FrameExtractionOutcome(row.id, extracted=True)
        return _FrameExtractionOutcome(row.id, errors=(f"{row.id}: frames saved to frames.json but metadata.json could not be updated",))

    def _dedup_by_hash(self, matched: list[tuple[FrameCandidate, float, Path]]) -> list[tuple[float, Path, str]]:
        """Drop a boosted (scene/keyword) frame that is a near-duplicate of
        the immediately preceding *kept* frame -- interval frames are never
        dropped, they are the guaranteed pacing baseline. This is
        adjacent-frame dedup only (not the content-level dedup that is
        README §20.3's job, a later phase); see core/utils/frame_hash.py."""
        kept: list[tuple[float, Path, str]] = []
        previous_hash: str | None = None
        for candidate, pts, path in matched:
            hash_hex = average_hash(path)
            if candidate.priority > INTERVAL_PRIORITY and previous_hash is not None:
                if is_near_duplicate(hash_hex, previous_hash):
                    path.unlink(missing_ok=True)
                    continue
            kept.append((pts, path, hash_hex))
            previous_hash = hash_hex
        return kept

    def _reconcile_metadata(self, video_dir: Path, frames_rel: Path) -> bool:
        """Ensure metadata.json's frames_path points at the concrete frames
        directory (frames_rel, project-relative posix). Returns False --
        never raises -- if metadata.json can't be loaded or saved, so the
        caller can fold that into a per-video error without aborting the
        run. Mirrors AudioExtractionService/TranscriptionService exactly."""
        metadata_path = video_dir / "metadata.json"
        try:
            metadata = VideoMetadata.load(metadata_path)
        except InvalidVideoMetadataError:
            return False

        target = frames_rel.as_posix()
        if metadata.frames_path == target:
            return True  # already correct, no write needed

        try:
            metadata.model_copy(update={"frames_path": target}).save(metadata_path)
        except OSError:
            return False
        return True


def _manifest_to_rows(video_id: str, manifest: FrameManifest) -> list[FrameRow]:
    return [
        FrameRow(
            id=entry.id, video_id=video_id, timestamp_seconds=entry.timestamp_seconds,
            image_path=entry.image_path, perceptual_hash=entry.perceptual_hash,
        )
        for entry in manifest.frames
    ]
