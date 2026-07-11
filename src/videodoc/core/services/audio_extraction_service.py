from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, ExternalToolNotFoundError, InvalidVideoMetadataError, NoVideosFoundError
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import list_videos
from videodoc.core.utils.ffmpeg import AudioExtractionError, extract_audio
from videodoc.core.utils.progress import ProgressReporter


@dataclass(frozen=True)
class AudioExtractionResult:
    extracted: tuple[str, ...]  # audio freshly produced this run
    skipped: tuple[str, ...]  # audio/<id>.wav already existed, ffmpeg not invoked
    errors: tuple[str, ...]  # per-video ffmpeg or metadata.json-update failures


class AudioExtractionService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config

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

        extracted: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        total = len(videos)
        for index, row in enumerate(videos):
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
                        skipped.append(row.id)
                    else:
                        errors.append(f"{row.id}: audio already extracted but metadata.json could not be updated")
                    continue

                tmp_path = final_path.parent / f"{final_path.name}.tmp"
                try:
                    extract_audio(
                        Path(row.path), tmp_path,
                        total_duration_seconds=row.duration_seconds,
                        progress_callback=lambda fraction, video_id=row.id: progress.update_item(video_id, fraction),
                    )
                except AudioExtractionError as exc:
                    errors.append(f"{row.id}: {exc}")
                    tmp_path.unlink(missing_ok=True)
                    continue

                try:
                    tmp_path.replace(final_path)
                except OSError as exc:
                    errors.append(f"{row.id}: could not finalize audio file: {exc}")
                    tmp_path.unlink(missing_ok=True)
                    continue

                if self._reconcile_metadata(video_dir, audio_rel):
                    extracted.append(row.id)
                else:
                    errors.append(
                        f"{row.id}: audio extracted to {final_path.name} but metadata.json could not be updated"
                    )
            finally:
                progress.finish_item(row.id)

        return AudioExtractionResult(tuple(extracted), tuple(skipped), tuple(errors))

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
