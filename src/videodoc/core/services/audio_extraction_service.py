from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, ExternalToolNotFoundError, InvalidVideoMetadataError, NoVideosFoundError
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import VideoRow, list_videos
from videodoc.core.utils.ffmpeg import AudioExtractionError, extract_audio
from videodoc.core.utils.hardware import resolve_cpu_workers, resolve_executor_workers, resolve_ffmpeg_threads
from videodoc.core.utils.progress import ProgressReporter


@dataclass(frozen=True)
class AudioExtractionResult:
    extracted: tuple[str, ...]  # audio freshly produced this run
    skipped: tuple[str, ...]  # audio/<id>.wav already existed, ffmpeg not invoked
    errors: tuple[str, ...]  # per-video ffmpeg or metadata.json-update failures


@dataclass(frozen=True)
class _AudioExtractionOutcome:
    video_id: str
    extracted: bool = False
    skipped: bool = False
    errors: tuple[str, ...] = ()


class AudioExtractionService:
    def __init__(self, project_dir: Path, config: ProjectConfig, *, workers_override: int | None = None) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override

    def run(self, progress: ProgressReporter | None = None) -> AudioExtractionResult:
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

        # Checked after (not before) the "anything to do" check, same
        # ordering already established for ingest: an empty project is
        # told about its own emptiness first, not asked to install ffmpeg
        # for nothing to process yet.
        if shutil.which("ffmpeg") is None:
            raise ExternalToolNotFoundError(
                "ffmpeg was not found on PATH. Install FFmpeg and make sure ffmpeg is available "
                "before running 'videodoc extract-audio' -- see RUN.md."
            )

        configured_workers = resolve_cpu_workers(self.config.audio.workers, self.workers_override)
        executor_workers = resolve_executor_workers(configured_workers, len(videos))
        ffmpeg_threads = resolve_ffmpeg_threads(executor_workers)

        extracted: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        total = len(videos)
        with ThreadPoolExecutor(max_workers=executor_workers) as executor:
            futures = [
                executor.submit(self._process_video, row, index, total, progress, ffmpeg_threads)
                for index, row in enumerate(videos)
            ]
            for future in futures:
                outcome = future.result()
                if outcome.extracted:
                    extracted.append(outcome.video_id)
                if outcome.skipped:
                    skipped.append(outcome.video_id)
                errors.extend(outcome.errors)

        return AudioExtractionResult(tuple(extracted), tuple(skipped), tuple(errors))

    def _process_video(
        self,
        row: VideoRow,
        index: int,
        total: int,
        progress: ProgressReporter,
        ffmpeg_threads: int,
    ) -> _AudioExtractionOutcome:
        progress.start_item(row.id, index, total)
        try:
            video_dir = self.project_dir / self.config.paths.workdir / row.id
            filesystem.ensure_video_workdir(video_dir)  # defensive: workdir may have been deleted manually

            audio_rel = Path(self.config.paths.workdir) / row.id / "audio" / f"{row.id}.wav"
            final_path = self.project_dir / audio_rel

            if final_path.is_file():
                # Already extracted in a previous run -- ffmpeg is never
                # re-invoked, but metadata.json is reconciled in case it
                # still holds ingest's folder-only placeholder (or is
                # otherwise stale), so "skipped" still means fully correct
                # on-disk state, not just "we didn't bother".
                if self._reconcile_metadata(video_dir, audio_rel):
                    return _AudioExtractionOutcome(row.id, skipped=True)
                return _AudioExtractionOutcome(
                    row.id,
                    errors=(f"{row.id}: audio already extracted but metadata.json could not be updated",),
                )

            tmp_path = final_path.parent / f"{final_path.name}.tmp"
            try:
                extract_audio(
                    Path(row.path), tmp_path,
                    total_duration_seconds=row.duration_seconds,
                    progress_callback=lambda fraction, video_id=row.id: progress.update_item(video_id, fraction),
                    threads=ffmpeg_threads,
                )
            except AudioExtractionError as exc:
                tmp_path.unlink(missing_ok=True)
                return _AudioExtractionOutcome(row.id, errors=(f"{row.id}: {exc}",))

            try:
                tmp_path.replace(final_path)
            except OSError as exc:
                tmp_path.unlink(missing_ok=True)
                return _AudioExtractionOutcome(row.id, errors=(f"{row.id}: could not finalize audio file: {exc}",))

            if self._reconcile_metadata(video_dir, audio_rel):
                return _AudioExtractionOutcome(row.id, extracted=True)
            return _AudioExtractionOutcome(
                row.id,
                errors=(f"{row.id}: audio extracted to {final_path.name} but metadata.json could not be updated",),
            )
        finally:
            progress.finish_item(row.id)

    def _reconcile_metadata(self, video_dir: Path, audio_rel: Path) -> bool:
        """Ensure metadata.json's audio_path points at the concrete audio
        file (audio_rel, project-relative posix). Returns False -- never
        raises -- if metadata.json can't be loaded or saved, so the caller
        can fold that into a per-video error without aborting the run."""
        metadata_path = video_dir / "metadata.json"
        try:
            metadata = VideoMetadata.load(metadata_path)
        except InvalidVideoMetadataError:
            return False

        target = audio_rel.as_posix()
        if metadata.audio_path == target:
            return True  # already correct, no write needed

        try:
            metadata.model_copy(update={"audio_path": target}).save(metadata_path)
        except OSError:
            return False
        return True
