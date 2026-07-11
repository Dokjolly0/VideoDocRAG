from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    InvalidTranscriptError,
    InvalidVideoMetadataError,
    NoVideosFoundError,
    TranscriptionEngineError,
)
from videodoc.core.models.transcript import Transcript, TranscriptSegment
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import TranscriptSegmentRow, VideoRow, ensure_schema, list_videos, replace_transcript_segments
from videodoc.core.utils.hardware import (
    resolve_compute_type,
    resolve_cpu_threads,
    resolve_device,
    resolve_executor_workers,
    resolve_transcription_batch_size,
    resolve_transcription_mode,
    resolve_transcription_workers,
)
from videodoc.core.utils.progress import ProgressReporter
from videodoc.core.utils.transcription import (
    TranscriptionError,
    TranscriptSegmentResult,
    build_batched_pipeline,
    load_whisper_model,
    transcribe_audio,
)

_SUPPORTED_ENGINES = ("faster-whisper",)


@dataclass(frozen=True)
class TranscriptionResult:
    transcribed: tuple[str, ...]  # transcripts freshly produced this run
    skipped: tuple[str, ...]  # transcript/<id>.json already existed, engine not invoked
    errors: tuple[str, ...]  # per-video transcription, DB, or metadata.json-update failures


@dataclass(frozen=True)
class _TranscriptionWorkItem:
    index: int
    row: VideoRow


@dataclass(frozen=True)
class _TranscriptionRuntime:
    engine: Any
    mode: Literal["standard", "batched"]
    word_timestamps: bool
    batch_size: int | None
    beam_size: int
    best_of: int
    vad_filter: bool
    chunk_length_seconds: int
    condition_on_previous_text: bool


@dataclass(frozen=True)
class _FreshTranscriptionOutcome:
    row: VideoRow
    segments: tuple[TranscriptSegment, ...] = ()
    error: str | None = None


class TranscriptionService:
    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        *,
        workers_override: int | None = None,
        device_override: Literal["auto", "cpu", "cuda"] | None = None,
        compute_type_override: str | None = None,
        mode_override: Literal["auto", "standard", "batched"] | None = None,
        batch_size_override: int | None = None,
        beam_size_override: int | None = None,
        word_timestamps_override: bool | None = None,
    ) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override
        self.device_override = device_override
        self.compute_type_override = compute_type_override
        self.mode_override = mode_override
        self.batch_size_override = batch_size_override
        self.beam_size_override = beam_size_override
        self.word_timestamps_override = word_timestamps_override

    def run(self, progress: ProgressReporter | None = None) -> TranscriptionResult:
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

        errors: list[str] = []
        candidates = []
        for row in videos:
            audio_path = self.project_dir / self.config.paths.workdir / row.id / "audio" / f"{row.id}.wav"
            if audio_path.is_file():
                candidates.append(row)
            else:
                errors.append(f"{row.id}: no extracted audio found -- run 'videodoc extract-audio' first")

        if not candidates:
            raise NoVideosFoundError(
                "No videos have extracted audio yet -- run 'videodoc extract-audio' first."
            )

        engine = self.config.transcription.engine
        if engine not in _SUPPORTED_ENGINES:
            raise TranscriptionEngineError(
                f"Transcription engine '{engine}' is not supported yet -- only "
                f"{', '.join(_SUPPORTED_ENGINES)} is currently implemented."
            )

        # A project.db created by ingest before transcript_segments existed
        # (an older run, or one from before this feature shipped) only has
        # the videos table -- ensure_schema is idempotent (CREATE TABLE IF
        # NOT EXISTS) and must be (re-)run here rather than assumed to have
        # already provisioned this table, or every write below fails with
        # "no such table: transcript_segments" and never self-heals.
        ensure_schema(db_path)

        transcribed: list[str] = []
        skipped: list[str] = []
        fresh_items: list[_TranscriptionWorkItem] = []

        ordered_candidates = sorted(candidates, key=lambda r: r.id)
        total = len(ordered_candidates)
        for index, row in enumerate(ordered_candidates):
            transcript_rel = Path(self.config.paths.workdir) / row.id / "transcript" / f"{row.id}.json"
            final_path = self.project_dir / transcript_rel
            if final_path.is_file():
                skipped_ok, error = self._process_existing_transcript(row, transcript_rel, index, total, db_path, progress)
                if skipped_ok:
                    skipped.append(row.id)
                elif error is not None:
                    errors.append(error)
            else:
                fresh_items.append(_TranscriptionWorkItem(index, row))

        if fresh_items:
            device = resolve_device(self.config.transcription.device, self.device_override)
            mode = resolve_transcription_mode(self.config.transcription.mode, self.mode_override, device=device)
            compute_type = resolve_compute_type(self.config.transcription.compute_type, device, self.compute_type_override)
            configured_workers = resolve_transcription_workers(
                self.config.transcription.workers,
                self.workers_override,
                device=device,
                mode=mode,
            )
            executor_workers = resolve_executor_workers(configured_workers, len(fresh_items))
            cpu_threads = resolve_cpu_threads(
                self.config.transcription.cpu_threads,
                None,
                device=device,
                workers=executor_workers,
            )
            batch_size = resolve_transcription_batch_size(
                self.config.transcription.batch_size,
                self.batch_size_override,
                device=device,
                mode=mode,
            )
            word_timestamps = (
                self.word_timestamps_override
                if self.word_timestamps_override is not None
                else self.config.transcription.word_timestamps
            )
            beam_size = self.beam_size_override or self.config.transcription.beam_size

            # faster-whisper deliberately disables its own download progress
            # bar (see faster_whisper.utils.download_model's tqdm_class=
            # disabled_tqdm) -- on a first-time, multi-GB model download this
            # call can block for minutes with zero output otherwise, easily
            # mistaken for a hang. This is the only feedback available short
            # of reimplementing huggingface_hub's download ourselves.
            progress.announce(
                f"Loading transcription model '{self.config.transcription.model}' "
                f"(device={device}, compute_type={compute_type}, mode={mode}, workers={executor_workers}, "
                f"batch_size={batch_size or '-'}, beam_size={beam_size}, word_timestamps={word_timestamps}, "
                f"vad_filter={self.config.transcription.vad_filter}, cpu_threads={cpu_threads}) -- first use may "
                f"download several GB from Hugging Face and show no progress while doing so."
            )
            try:
                model = load_whisper_model(
                    self.config.transcription.model,
                    device=device,
                    compute_type=compute_type,
                    cpu_threads=cpu_threads,
                    num_workers=executor_workers,
                )
                transcription_engine = build_batched_pipeline(model) if mode == "batched" else model
            except TranscriptionError as exc:
                raise TranscriptionEngineError(
                    f"Could not load transcription engine (model '{self.config.transcription.model}'): {exc}"
                ) from exc

            runtime = _TranscriptionRuntime(
                engine=transcription_engine,
                mode=mode,
                word_timestamps=word_timestamps,
                batch_size=batch_size,
                beam_size=beam_size,
                best_of=self.config.transcription.best_of,
                vad_filter=self.config.transcription.vad_filter,
                chunk_length_seconds=self.config.transcription.chunk_length_seconds,
                condition_on_previous_text=self.config.transcription.condition_on_previous_text,
            )

            with ThreadPoolExecutor(max_workers=executor_workers) as executor:
                futures = [executor.submit(self._transcribe_fresh, item, total, progress, runtime) for item in fresh_items]
                for future in futures:
                    outcome = future.result()
                    if outcome.error is not None:
                        errors.append(outcome.error)
                        continue
                    error = self._commit_fresh_transcript(db_path, outcome)
                    if error is None:
                        transcribed.append(outcome.row.id)
                    else:
                        errors.append(error)

        return TranscriptionResult(tuple(transcribed), tuple(skipped), tuple(errors))

    def _process_existing_transcript(
        self,
        row: VideoRow,
        transcript_rel: Path,
        index: int,
        total: int,
        db_path: Path,
        progress: ProgressReporter,
    ) -> tuple[bool, str | None]:
        progress.start_item(row.id, index, total)
        try:
            video_dir = self.project_dir / self.config.paths.workdir / row.id
            filesystem.ensure_video_workdir(video_dir)  # defensive: workdir may have been deleted manually
            final_path = self.project_dir / transcript_rel

            # Already transcribed in a previous run -- the engine is never
            # re-invoked, but the DB rows are always rewritten from the
            # on-disk JSON (cheap DELETE+INSERT), so a prior transient DB
            # failure self-heals instead of staying silently empty forever
            # once the JSON file exists.
            try:
                transcript = Transcript.load(final_path)
            except InvalidTranscriptError as exc:
                return False, f"{row.id}: transcript already exists but could not be read: {exc}"
            try:
                replace_transcript_segments(db_path, row.id, _to_rows(row.id, transcript.segments))
            except DatabaseError as exc:
                return False, f"{row.id}: transcript already exists but database could not be updated: {exc}"
            if self._reconcile_metadata(video_dir, transcript_rel):
                return True, None
            return False, f"{row.id}: transcript already exists but metadata.json could not be updated"
        finally:
            progress.finish_item(row.id)

    def _transcribe_fresh(
        self,
        item: _TranscriptionWorkItem,
        total: int,
        progress: ProgressReporter,
        runtime: _TranscriptionRuntime,
    ) -> _FreshTranscriptionOutcome:
        row = item.row
        progress.start_item(row.id, item.index, total)
        try:
            video_dir = self.project_dir / self.config.paths.workdir / row.id
            filesystem.ensure_video_workdir(video_dir)  # defensive: workdir may have been deleted manually
            audio_path = video_dir / "audio" / f"{row.id}.wav"
            try:
                results = transcribe_audio(
                    runtime.engine,
                    audio_path,
                    language=self.config.transcription.language,
                    word_timestamps=runtime.word_timestamps,
                    mode=runtime.mode,
                    batch_size=runtime.batch_size,
                    beam_size=runtime.beam_size,
                    best_of=runtime.best_of,
                    vad_filter=runtime.vad_filter,
                    chunk_length_seconds=runtime.chunk_length_seconds,
                    condition_on_previous_text=runtime.condition_on_previous_text,
                    progress_callback=lambda fraction, video_id=row.id: progress.update_item(video_id, fraction),
                )
            except TranscriptionError as exc:
                return _FreshTranscriptionOutcome(row, error=f"{row.id}: {exc}")

            segments = tuple(_to_segments(row.id, results))
            return _FreshTranscriptionOutcome(row, segments=segments)
        finally:
            progress.finish_item(row.id)

    def _commit_fresh_transcript(self, db_path: Path, outcome: _FreshTranscriptionOutcome) -> str | None:
        row = outcome.row
        video_dir = self.project_dir / self.config.paths.workdir / row.id
        transcript_rel = Path(self.config.paths.workdir) / row.id / "transcript" / f"{row.id}.json"
        final_path = self.project_dir / transcript_rel
        transcript = Transcript(
            video_id=row.id, engine=self.config.transcription.engine, model=self.config.transcription.model,
            language=self.config.transcription.language, segments=list(outcome.segments),
        )

        tmp_path = final_path.parent / f"{final_path.name}.tmp"
        try:
            transcript.save(tmp_path)
            tmp_path.replace(final_path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            return f"{row.id}: could not finalize transcript file: {exc}"

        try:
            replace_transcript_segments(db_path, row.id, _to_rows(row.id, list(outcome.segments)))
        except DatabaseError as exc:
            return f"{row.id}: transcript saved to {final_path.name} but database update failed: {exc}"

        if self._reconcile_metadata(video_dir, transcript_rel):
            return None
        return f"{row.id}: transcript saved to {final_path.name} but metadata.json could not be updated"

    def _reconcile_metadata(self, video_dir: Path, transcript_rel: Path) -> bool:
        """Ensure metadata.json's transcript_path points at the concrete
        transcript file (transcript_rel, project-relative posix). Returns
        False -- never raises -- if metadata.json can't be loaded or saved,
        so the caller can fold that into a per-video error without
        aborting the run. Mirrors AudioExtractionService._reconcile_metadata
        exactly."""
        metadata_path = video_dir / "metadata.json"
        try:
            metadata = VideoMetadata.load(metadata_path)
        except InvalidVideoMetadataError:
            return False

        target = transcript_rel.as_posix()
        if metadata.transcript_path == target:
            return True  # already correct, no write needed

        try:
            metadata.model_copy(update={"transcript_path": target}).save(metadata_path)
        except OSError:
            return False
        return True


def _to_segments(video_id: str, results: list[TranscriptSegmentResult]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            id=f"{video_id}_seg_{i:04d}", start_seconds=r.start_seconds, end_seconds=r.end_seconds,
            text=r.text, confidence=r.confidence,
        )
        for i, r in enumerate(results)
    ]


def _to_rows(video_id: str, segments: list[TranscriptSegment]) -> list[TranscriptSegmentRow]:
    return [
        TranscriptSegmentRow(
            id=seg.id, video_id=video_id, start_seconds=seg.start_seconds,
            end_seconds=seg.end_seconds, text=seg.text, confidence=seg.confidence,
        )
        for seg in segments
    ]
