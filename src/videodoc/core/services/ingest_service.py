from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import ExternalToolNotFoundError, NoVideosFoundError, VideoIdCollisionError
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import VideoRow, ensure_schema, get_video, upsert_video
from videodoc.core.utils.ffprobe import VideoProbeError, probe_video
from videodoc.core.utils.hashing import hash_file
from videodoc.core.utils.progress import ProgressReporter
from videodoc.core.utils.slug import slugify


@dataclass(frozen=True)
class IngestResult:
    database_path: Path
    ingested: tuple[str, ...]  # brand-new video ids
    reingested: tuple[str, ...]  # hash changed since last ingest, reprocessed
    skipped: tuple[str, ...]  # hash unchanged, not reprocessed (probe_video not even called)
    errors: tuple[str, ...]  # per-video hash/probe failures -- video skipped, run continues
    warnings: tuple[str, ...]  # advisory notices, e.g. possibly-stale workdir artifacts after a reingest


class VideoIngestionService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config

    def run(self, progress: ProgressReporter | None = None) -> IngestResult:
        progress = progress or ProgressReporter()
        walk_errors: list[str] = []
        video_files = self._resolve_video_files(walk_errors)
        if not video_files:
            reason = f" ({len(walk_errors)} path(s) could not be read: {'; '.join(walk_errors)})" if walk_errors else ""
            raise NoVideosFoundError(
                f"No video files found in paths.videos ({self.config.paths.videos!r}){reason}. "
                f"The videos/ source is required to start the ingestion pipeline (README §15.1) -- "
                f"run 'videodoc scan' first if you're unsure what was detected."
            )

        # Checked once, up front, after (not before) the zero-videos check:
        # an empty project should be told about its own emptiness first,
        # not asked to go install FFmpeg for nothing to process yet.
        if shutil.which("ffprobe") is None:
            raise ExternalToolNotFoundError(
                "ffprobe (part of FFmpeg) was not found on PATH. Install FFmpeg and make sure "
                "ffprobe is available before running 'videodoc ingest' -- see RUN.md."
            )

        db_path = self.project_dir / self.config.paths.database
        ensure_schema(db_path)

        ingested: list[str] = []
        reingested: list[str] = []
        skipped: list[str] = []
        errors: list[str] = list(walk_errors)  # a partially-unreadable videos/ still surfaces here, never silently
        warnings: list[str] = []
        seen_this_run: dict[str, str] = {}  # video_id -> filename, for same-run collision detection

        sorted_video_files = sorted(video_files)
        total = len(sorted_video_files)
        for index, video_file in enumerate(sorted_video_files):
            progress.start_item(video_file.name, index, total)
            try:
                try:
                    video_id = slugify(video_file.stem)
                except ValueError as exc:
                    errors.append(f"{video_file.name}: {exc}")
                    continue

                existing_row = get_video(db_path, video_id)
                # A collision is any case where video_id already means a
                # *different* file -- either earlier in this same run, or from a
                # previous run's project.db. The normal reingest-on-hash-change
                # case (same filename, different content) is explicitly not a
                # collision. This is fatal (stops the run): earlier videos
                # already committed in this run stay committed -- each one's DB
                # upsert + metadata.json write is independently idempotent, this
                # is a safe partial completion, not a rollback.
                if video_id in seen_this_run and seen_this_run[video_id] != video_file.name:
                    raise VideoIdCollisionError(
                        f"'{video_file.name}' and '{seen_this_run[video_id]}' both resolve to video id "
                        f"'{video_id}' in this run -- rename one of the files to avoid ambiguity."
                    )
                if existing_row is not None and existing_row.filename != video_file.name:
                    raise VideoIdCollisionError(
                        f"'{video_file.name}' resolves to video id '{video_id}', which is already "
                        f"registered in {db_path.name} for a different file ('{existing_row.filename}') -- "
                        f"rename one of the files to avoid ambiguity."
                    )
                seen_this_run[video_id] = video_file.name

                try:
                    file_hash = hash_file(
                        video_file,
                        progress_callback=lambda fraction, name=video_file.name: progress.update_item(name, fraction),
                    )
                except OSError as exc:
                    errors.append(f"{video_file.name}: {exc}")
                    continue

                if existing_row is not None and existing_row.file_hash == file_hash:
                    # Unchanged: not reprocessed at all, not even probed --
                    # this is what makes "must not be processed again" real.
                    skipped.append(video_id)
                    continue

                try:
                    probe = probe_video(video_file)
                except VideoProbeError as exc:
                    errors.append(f"{video_file.name}: {exc}")
                    continue

                video_dir = self.project_dir / self.config.paths.workdir / video_id
                filesystem.ensure_video_workdir(video_dir)

                created_at = existing_row.created_at if existing_row is not None else datetime.now(timezone.utc).isoformat()
                title = existing_row.title if existing_row is not None else None

                upsert_video(
                    db_path,
                    VideoRow(
                        id=video_id,
                        filename=video_file.name,
                        title=title,
                        duration_seconds=probe.duration_seconds,
                        file_hash=file_hash,
                        path=video_file.as_posix(),
                        created_at=created_at,
                    ),
                )

                workdir_rel = Path(self.config.paths.workdir) / video_id
                VideoMetadata(
                    video_id=video_id,
                    video_name=video_file.name,
                    title=title,
                    duration_seconds=probe.duration_seconds,
                    language=self.config.project.language,
                    hash=file_hash,
                    format=probe.format_name,
                    width=probe.width,
                    height=probe.height,
                    codec=probe.codec_name,
                    audio_path=(workdir_rel / "audio").as_posix(),
                    transcript_path=(workdir_rel / "transcript").as_posix(),
                    frames_path=(workdir_rel / "frames").as_posix(),
                    ocr_path=(workdir_rel / "ocr").as_posix(),
                    chunks_path=(workdir_rel / "chunks").as_posix(),
                ).save(video_dir / "metadata.json")

                if existing_row is None:
                    ingested.append(video_id)
                else:
                    reingested.append(video_id)
                    warnings.append(
                        f"{video_id}: video content changed and was reingested -- "
                        f"workdir/{video_id}/{{audio,frames,transcript,ocr,chunks}} may still contain "
                        f"artifacts from the previous version (never deleted automatically); re-run the "
                        f"relevant pipeline phase(s) to refresh them."
                    )
            finally:
                progress.finish_item(video_file.name)

        return IngestResult(
            database_path=db_path,
            ingested=tuple(ingested), reingested=tuple(reingested), skipped=tuple(skipped),
            errors=tuple(errors), warnings=tuple(warnings),
        )

    def _resolve_video_files(self, errors: list[str]) -> list[Path]:
        try:
            videos_root = filesystem.resolve_source_path(self.project_dir, self.config.paths.videos)
            is_directory = videos_root.is_dir()
        except OSError:
            # e.g. a disconnected drive on Windows -> never a crash: treated
            # the same as "0 video files found", matching SourceScanService.
            is_directory = False
        if not is_directory:
            return []
        return filesystem.scan_videos(videos_root, self.config.scan, errors)
