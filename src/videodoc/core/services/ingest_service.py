from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import ExternalToolNotFoundError, NoVideosFoundError, VideoIdCollisionError
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import VideoRow, ensure_schema, get_video, upsert_video
from videodoc.core.utils.ffprobe import VideoProbeError, VideoProbeResult, probe_video
from videodoc.core.utils.hardware import resolve_cpu_workers, resolve_executor_workers
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


@dataclass(frozen=True)
class _IngestWorkItem:
    index: int
    video_file: Path
    source_key: str
    video_id: str
    existing_row: VideoRow | None


@dataclass(frozen=True)
class _IngestOutcome:
    item: _IngestWorkItem
    file_hash: str | None = None
    probe: VideoProbeResult | None = None
    skipped: bool = False
    error: str | None = None


class VideoIngestionService:
    def __init__(self, project_dir: Path, config: ProjectConfig, *, workers_override: int | None = None) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override

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

        errors: list[str] = list(walk_errors)  # a partially-unreadable videos/ still surfaces here, never silently
        work_items = self._prepare_work_items(sorted(video_files), db_path, errors)

        ingested: list[str] = []
        reingested: list[str] = []
        skipped: list[str] = []
        warnings: list[str] = []

        if not work_items:
            return IngestResult(db_path, tuple(ingested), tuple(reingested), tuple(skipped), tuple(errors), tuple(warnings))

        configured_workers = resolve_cpu_workers(self.config.ingest.workers, self.workers_override)
        executor_workers = resolve_executor_workers(configured_workers, len(work_items))
        total = len(work_items)

        with ThreadPoolExecutor(max_workers=executor_workers) as executor:
            futures = [executor.submit(self._process_item, item, total, progress) for item in work_items]
            for future in futures:
                outcome = future.result()
                if outcome.error is not None:
                    errors.append(outcome.error)
                    continue
                if outcome.skipped:
                    skipped.append(outcome.item.video_id)
                    continue

                warning = self._commit_outcome(db_path, outcome)
                if outcome.item.existing_row is None:
                    ingested.append(outcome.item.video_id)
                else:
                    reingested.append(outcome.item.video_id)
                    warnings.append(warning)

        return IngestResult(
            database_path=db_path,
            ingested=tuple(ingested), reingested=tuple(reingested), skipped=tuple(skipped),
            errors=tuple(errors), warnings=tuple(warnings),
        )

    def _prepare_work_items(self, video_files: list[Path], db_path: Path, errors: list[str]) -> list[_IngestWorkItem]:
        work_items: list[_IngestWorkItem] = []
        seen_this_run: dict[str, tuple[str, str]] = {}  # video_id -> (source_key, display_name)

        for video_file in video_files:
            try:
                video_id = slugify(video_file.stem)
            except ValueError as exc:
                errors.append(f"{video_file.name}: {exc}")
                continue

            try:
                source_key = video_file.resolve().as_posix()
            except OSError as exc:
                errors.append(f"{video_file.name}: {exc}")
                continue

            previous = seen_this_run.get(video_id)
            if previous is not None and previous[0] != source_key:
                raise VideoIdCollisionError(
                    f"'{source_key}' and '{previous[1]}' both resolve to video id "
                    f"'{video_id}' in this run -- rename one of the files to avoid ambiguity."
                )

            existing_row = get_video(db_path, video_id)
            if existing_row is not None and self._is_existing_row_for_different_source(existing_row, source_key, video_file):
                registered = existing_row.path or existing_row.filename
                raise VideoIdCollisionError(
                    f"'{source_key}' resolves to video id '{video_id}', which is already "
                    f"registered in {db_path.name} for a different file ('{registered}') -- "
                    f"rename one of the files to avoid ambiguity."
                )

            seen_this_run[video_id] = (source_key, source_key)
            work_items.append(_IngestWorkItem(len(work_items), video_file, source_key, video_id, existing_row))

        return work_items

    def _process_item(self, item: _IngestWorkItem, total: int, progress: ProgressReporter) -> _IngestOutcome:
        progress.start_item(item.source_key, item.index, total)
        try:
            try:
                file_hash = hash_file(
                    item.video_file,
                    progress_callback=lambda fraction, source_key=item.source_key: progress.update_item(source_key, fraction),
                )
            except OSError as exc:
                return _IngestOutcome(item, error=f"{item.video_file.name}: {exc}")

            if item.existing_row is not None and item.existing_row.file_hash == file_hash:
                # Unchanged: not reprocessed at all, not even probed --
                # this is what makes "must not be processed again" real.
                return _IngestOutcome(item, file_hash=file_hash, skipped=True)

            try:
                probe = probe_video(item.video_file)
            except VideoProbeError as exc:
                return _IngestOutcome(item, file_hash=file_hash, error=f"{item.video_file.name}: {exc}")

            return _IngestOutcome(item, file_hash=file_hash, probe=probe)
        finally:
            progress.finish_item(item.source_key)

    def _commit_outcome(self, db_path: Path, outcome: _IngestOutcome) -> str:
        item = outcome.item
        assert outcome.file_hash is not None
        assert outcome.probe is not None

        video_dir = self.project_dir / self.config.paths.workdir / item.video_id
        filesystem.ensure_video_workdir(video_dir)

        created_at = item.existing_row.created_at if item.existing_row is not None else datetime.now(timezone.utc).isoformat()
        title = item.existing_row.title if item.existing_row is not None else None

        upsert_video(
            db_path,
            VideoRow(
                id=item.video_id,
                filename=item.video_file.name,
                title=title,
                duration_seconds=outcome.probe.duration_seconds,
                file_hash=outcome.file_hash,
                path=item.source_key,
                created_at=created_at,
            ),
        )

        workdir_rel = Path(self.config.paths.workdir) / item.video_id
        VideoMetadata(
            video_id=item.video_id,
            video_name=item.video_file.name,
            title=title,
            duration_seconds=outcome.probe.duration_seconds,
            language=self.config.project.language,
            hash=outcome.file_hash,
            format=outcome.probe.format_name,
            width=outcome.probe.width,
            height=outcome.probe.height,
            codec=outcome.probe.codec_name,
            audio_path=(workdir_rel / "audio").as_posix(),
            transcript_path=(workdir_rel / "transcript").as_posix(),
            frames_path=(workdir_rel / "frames").as_posix(),
            ocr_path=(workdir_rel / "ocr").as_posix(),
            chunks_path=(workdir_rel / "chunks").as_posix(),
        ).save(video_dir / "metadata.json")

        return (
            f"{item.video_id}: video content changed and was reingested -- "
            f"workdir/{item.video_id}/{{audio,frames,transcript,ocr,chunks}} may still contain "
            f"artifacts from the previous version (never deleted automatically); re-run the "
            f"relevant pipeline phase(s) to refresh them."
        )

    def _is_existing_row_for_different_source(self, existing_row: VideoRow, source_key: str, video_file: Path) -> bool:
        if existing_row.path:
            try:
                return Path(existing_row.path).resolve().as_posix() != source_key
            except OSError:
                return existing_row.path != source_key
        return existing_row.filename != video_file.name

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
