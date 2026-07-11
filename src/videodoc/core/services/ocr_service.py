from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    InvalidFrameManifestError,
    InvalidOCRManifestError,
    InvalidVideoMetadataError,
    NoVideosFoundError,
    OCREngineNotSupportedError,
    OCREngineUnavailableError,
)
from videodoc.core.models.frame_manifest import FrameManifest
from videodoc.core.models.ocr_manifest import OCRManifest, OCRManifestEntry
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import FrameOcrUpdate, FrameRow, VideoRow, ensure_schema, list_frames, list_videos, update_frame_ocr
from videodoc.core.utils.hardware import resolve_cpu_workers, resolve_executor_workers
from videodoc.core.utils.ocr_engine import OCRRunError, load_engine, rapidocr_available, run_ocr
from videodoc.core.utils.progress import ProgressReporter

_SUPPORTED_ENGINES = ("rapidocr",)


@dataclass(frozen=True)
class OCRResult:
    processed: tuple[str, ...]  # videos freshly OCR'd this run
    skipped: tuple[str, ...]  # ocr.json already existed (or no frames yet), engine not invoked
    errors: tuple[str, ...]  # per-video/per-frame OCR, DB, or metadata.json-update failures


@dataclass(frozen=True)
class _OCROutcome:
    video_id: str
    processed: bool = False
    skipped: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _OCRVideoPlan:
    """What _process_plan needs to do for one video, decided up front (in
    run(), sequentially, before any rapidocr availability check or
    thread-pool work) purely from cheap local state: the video's current
    frame rows, whether ocr.json exists, does it parse, and do its stored
    settings/frame-id set match this run's. Mirrors
    FrameExtractionService's own _VideoPlan pre-scan pattern."""
    row: VideoRow
    video_dir: Path
    ocr_dir: Path
    ocr_rel: Path
    manifest_path: Path
    frames: tuple[FrameRow, ...]
    needs_fresh: bool
    manifest: OCRManifest | None = None  # a successfully loaded existing manifest, whether or not its settings/frame-set still match
    load_error: str | None = None  # set instead of manifest when ocr.json exists but fails to parse
    missing_frames_error: str | None = None  # frames/frames.json has entries on disk but the frames table has zero rows for this video -- a DB/table desync, not "videodoc frames was never run"


class OCRService:
    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        *,
        workers_override: int | None = None,
        languages_override: list[str] | None = None,
        min_confidence_override: float | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override
        self.engine = config.ocr.engine
        self.languages = languages_override if languages_override is not None else config.ocr.languages
        self.min_confidence = min_confidence_override if min_confidence_override is not None else config.ocr.min_confidence

    def run(self, progress: ProgressReporter | None = None) -> OCRResult:
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

        # Checked unconditionally, not only when fresh OCR is needed:
        # _process_fresh always instantiates RapidOCR regardless of this
        # setting, so an unnoticed mismatch (e.g. a project's config.yaml
        # still saying the old 'paddleocr' default) would otherwise silently
        # run the wrong engine and write an ocr.json that misreports which
        # engine actually produced its results.
        if self.engine not in _SUPPORTED_ENGINES:
            raise OCREngineNotSupportedError(
                f"OCR engine '{self.engine}' is not supported yet -- only "
                f"{', '.join(_SUPPORTED_ENGINES)} is currently implemented."
            )

        # A project.db created before the frames table existed only has
        # videos/transcript_segments -- ensure_schema is idempotent and must
        # be (re-)run here, same reasoning as FrameExtractionService.
        ensure_schema(db_path)

        ordered_videos = sorted(videos, key=lambda r: r.id)
        total = len(ordered_videos)

        # Classify every video up front -- cheap local I/O only (does
        # ocr.json exist, does it parse, do its settings/frame-id set match
        # this run's) -- before ever requiring rapidocr. A fully processed
        # project must be able to re-run 'videodoc ocr' to self-heal
        # DB/metadata even on a machine that no longer has rapidocr
        # installed, as long as nothing actually needs fresh OCR.
        plans = [self._plan_for(row, db_path) for row in ordered_videos]
        needs_fresh = any(plan.needs_fresh for plan in plans)

        if needs_fresh and not rapidocr_available():
            raise OCREngineUnavailableError(
                "The 'rapidocr' package was not found -- install it (and 'onnxruntime') "
                "before running 'videodoc ocr' -- see RUN.md."
            )

        configured_workers = resolve_cpu_workers(self.config.ocr.workers, self.workers_override)
        executor_workers = resolve_executor_workers(configured_workers, len(videos))

        processed: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        with ThreadPoolExecutor(max_workers=executor_workers) as executor:
            futures = [
                executor.submit(self._process_plan, plan, index, total, progress, db_path)
                for index, plan in enumerate(plans)
            ]
            for future in futures:
                outcome = future.result()
                if outcome.processed:
                    processed.append(outcome.video_id)
                if outcome.skipped:
                    skipped.append(outcome.video_id)
                errors.extend(outcome.errors)

        return OCRResult(tuple(processed), tuple(skipped), tuple(errors))

    def _plan_for(self, row: VideoRow, db_path: Path) -> _OCRVideoPlan:
        video_dir = self.project_dir / self.config.paths.workdir / row.id
        filesystem.ensure_video_workdir(video_dir)  # defensive: workdir may have been deleted manually
        ocr_dir = video_dir / "ocr"
        ocr_rel = Path(self.config.paths.workdir) / row.id / "ocr"
        manifest_path = ocr_dir / f"{row.id}.json"

        frames = tuple(list_frames(db_path, row.id))
        if not frames:
            frames_manifest_path = video_dir / "frames" / "frames.json"
            if frames_manifest_path.is_file():
                try:
                    frame_manifest = FrameManifest.load(frames_manifest_path)
                except InvalidFrameManifestError as exc:
                    # frames/frames.json exists but can't even be parsed, and
                    # the frames table has zero rows for this video -- a real,
                    # fixable broken state (not "videodoc frames was never
                    # run"), so this must not fall through to the silent skip
                    # below: swallowing the parse error here would hide it
                    # identical to a legitimate not-yet-processed video.
                    return _OCRVideoPlan(
                        row, video_dir, ocr_dir, ocr_rel, manifest_path, frames, needs_fresh=False,
                        missing_frames_error=(
                            f"{row.id}: the frames table has no rows for this video, and "
                            f"frames/frames.json could not be read either ({exc}) -- run "
                            f"'videodoc frames' again to rebuild both before running 'videodoc ocr'"
                        ),
                    )
                if frame_manifest.frames:
                    # frames/frames.json has real entries on disk, but the
                    # frames table has zero rows for this video -- a DB/table
                    # desync (e.g. project.db was rebuilt or lost rows), not
                    # "videodoc frames was never run". Silently skipping here
                    # would look identical to a legitimate not-yet-processed
                    # video; 'videodoc frames' itself already self-heals this
                    # exact table from frames.json on any rerun, so surface a
                    # clear, actionable error instead of a silent no-op.
                    return _OCRVideoPlan(
                        row, video_dir, ocr_dir, ocr_rel, manifest_path, frames, needs_fresh=False,
                        missing_frames_error=(
                            f"{row.id}: frames/frames.json has {len(frame_manifest.frames)} frame(s) on disk but "
                            f"the frames table has none for this video -- run 'videodoc frames' again to rebuild "
                            f"the database before running 'videodoc ocr'"
                        ),
                    )
            # Nothing to OCR yet ('videodoc frames' never ran, or produced
            # zero frames) -- not an error, just a no-op for this video.
            return _OCRVideoPlan(row, video_dir, ocr_dir, ocr_rel, manifest_path, frames, needs_fresh=False)

        if not manifest_path.is_file():
            return _OCRVideoPlan(row, video_dir, ocr_dir, ocr_rel, manifest_path, frames, needs_fresh=True)

        try:
            manifest = OCRManifest.load(manifest_path)
        except InvalidOCRManifestError as exc:
            return _OCRVideoPlan(row, video_dir, ocr_dir, ocr_rel, manifest_path, frames, needs_fresh=False, load_error=str(exc))

        settings_match = (
            manifest.engine == self.engine
            and manifest.languages == self.languages
            and manifest.min_confidence == self.min_confidence
        )
        # A settings match alone isn't enough: 'videodoc frames' may have
        # been re-run since the last OCR pass, producing different frame
        # *content* without any OCR setting changing at all -- the OCR-phase-
        # specific idempotency edge frames.json's own settings-only
        # comparison doesn't need to handle. Comparing only the frame-id set
        # is not enough either: ids are assigned densely by position
        # (frame_0001, frame_0002, ...), so a re-run with different settings
        # (e.g. a different --interval-seconds) that happens to land on the
        # same *count* of frames produces the exact same id set over
        # completely different timestamps/images -- comparing each frame's
        # (id, timestamp_seconds, perceptual_hash) triple, not just its id,
        # is what actually detects "this id now points at different content".
        current_signature = {(f.id, f.timestamp_seconds, f.perceptual_hash) for f in frames}
        manifest_signature = {(e.frame_id, e.timestamp_seconds, e.perceptual_hash) for e in manifest.entries}
        frames_match = current_signature == manifest_signature
        return _OCRVideoPlan(
            row, video_dir, ocr_dir, ocr_rel, manifest_path, frames,
            needs_fresh=not (settings_match and frames_match), manifest=manifest,
        )

    def _process_plan(
        self,
        plan: _OCRVideoPlan,
        index: int,
        total: int,
        progress: ProgressReporter,
        db_path: Path,
    ) -> _OCROutcome:
        progress.start_item(plan.row.id, index, total)
        try:
            if not plan.frames:
                if plan.missing_frames_error is not None:
                    return _OCROutcome(plan.row.id, errors=(plan.missing_frames_error,))
                return _OCROutcome(plan.row.id, skipped=True)
            if plan.load_error is not None:
                return _OCROutcome(
                    plan.row.id,
                    errors=(f"{plan.row.id}: OCR already exists but ocr.json could not be read: {plan.load_error}",),
                )
            if not plan.needs_fresh:
                return self._process_existing(plan, db_path)
            return self._process_fresh(plan, db_path, progress)
        finally:
            progress.finish_item(plan.row.id)

    def _process_existing(self, plan: _OCRVideoPlan, db_path: Path) -> _OCROutcome:
        # Already OCR'd in a previous run with matching settings and frame
        # content (timestamp/perceptual_hash per id, not just the id set) --
        # rapidocr is never re-invoked, but the DB rows are always rewritten
        # from the on-disk manifest (cheap per-row UPDATE), so a prior
        # transient DB failure self-heals instead of staying silently empty
        # forever. Mirrors FrameExtractionService._process_existing.
        assert plan.manifest is not None
        row = plan.row
        updates = [
            FrameOcrUpdate(frame_id=e.frame_id, ocr_text=e.ocr_text, ocr_confidence=e.confidence)
            for e in plan.manifest.entries
        ]
        try:
            update_frame_ocr(db_path, row.id, updates)
        except DatabaseError as exc:
            return _OCROutcome(row.id, errors=(f"{row.id}: OCR already exists but database could not be updated: {exc}",))

        if self._reconcile_metadata(plan.video_dir, plan.ocr_rel):
            return _OCROutcome(row.id, skipped=True)
        return _OCROutcome(row.id, errors=(f"{row.id}: OCR already exists but metadata.json could not be updated",))

    def _process_fresh(self, plan: _OCRVideoPlan, db_path: Path, progress: ProgressReporter) -> _OCROutcome:
        row = plan.row
        try:
            engine = load_engine()
        except OCRRunError as exc:
            return _OCROutcome(row.id, errors=(f"{row.id}: {exc}",))

        entries: list[OCRManifestEntry] = []
        updates: list[FrameOcrUpdate] = []
        frame_errors: list[str] = []
        total_frames = len(plan.frames)

        for position, frame in enumerate(plan.frames, start=1):
            image_path = self.project_dir / frame.image_path
            try:
                text, confidence = run_ocr(engine, image_path)
            except OCRRunError as exc:
                # Isolated per-frame failure -- this frame's ocr_text/
                # ocr_confidence are left untouched in the DB (not included
                # in `updates`), which stays NULL/retryable on a future run,
                # and also keeps this frame's id out of the manifest, so the
                # frame-signature comparison in _plan_for will trigger a
                # re-OCR attempt for it next time even if nothing else changes.
                frame_errors.append(f"{row.id}: frame {frame.id}: {exc}")
                progress.update_item(row.id, position / total_frames)
                continue

            kept_text = text if confidence >= self.min_confidence else ""
            entries.append(
                OCRManifestEntry(
                    frame_id=frame.id, ocr_text=kept_text, confidence=confidence,
                    timestamp_seconds=frame.timestamp_seconds, perceptual_hash=frame.perceptual_hash,
                )
            )
            updates.append(FrameOcrUpdate(frame_id=frame.id, ocr_text=kept_text, ocr_confidence=confidence))
            progress.update_item(row.id, position / total_frames)

        manifest = OCRManifest(
            video_id=row.id, entries=entries,
            engine=self.engine, languages=self.languages, min_confidence=self.min_confidence,
        )
        tmp_manifest_path = plan.manifest_path.parent / f"{plan.manifest_path.name}.tmp"
        try:
            manifest.save(tmp_manifest_path)
            tmp_manifest_path.replace(plan.manifest_path)
        except OSError as exc:
            tmp_manifest_path.unlink(missing_ok=True)
            return _OCROutcome(row.id, errors=tuple(frame_errors) + (f"{row.id}: could not finalize ocr.json: {exc}",))

        try:
            update_frame_ocr(db_path, row.id, updates)
        except DatabaseError as exc:
            return _OCROutcome(
                row.id, errors=tuple(frame_errors) + (f"{row.id}: OCR saved to {plan.manifest_path.name} but database update failed: {exc}",)
            )

        if self._reconcile_metadata(plan.video_dir, plan.ocr_rel):
            return _OCROutcome(row.id, processed=True, errors=tuple(frame_errors))
        return _OCROutcome(
            row.id, errors=tuple(frame_errors) + (f"{row.id}: OCR saved to {plan.manifest_path.name} but metadata.json could not be updated",)
        )

    def _reconcile_metadata(self, video_dir: Path, ocr_rel: Path) -> bool:
        """Ensure metadata.json's ocr_path points at the concrete ocr
        directory (ocr_rel, project-relative posix). Returns False -- never
        raises -- if metadata.json can't be loaded or saved, so the caller
        can fold that into a per-video error without aborting the run.
        Mirrors FrameExtractionService._reconcile_metadata exactly."""
        metadata_path = video_dir / "metadata.json"
        try:
            metadata = VideoMetadata.load(metadata_path)
        except InvalidVideoMetadataError:
            return False

        target = ocr_rel.as_posix()
        if metadata.ocr_path == target:
            return True  # already correct, no write needed

        try:
            metadata.model_copy(update={"ocr_path": target}).save(metadata_path)
        except OSError:
            return False
        return True
