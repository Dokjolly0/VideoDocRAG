from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from videodoc.core.storage.database import TranscriptSegmentRow, ensure_schema, list_videos, replace_transcript_segments
from videodoc.core.utils.progress import ProgressReporter
from videodoc.core.utils.transcription import TranscriptionError, load_whisper_model, transcribe_audio

_SUPPORTED_ENGINES = ("faster-whisper",)


@dataclass(frozen=True)
class TranscriptionResult:
    transcribed: tuple[str, ...]  # transcripts freshly produced this run
    skipped: tuple[str, ...]  # transcript/<id>.json already existed, engine not invoked
    errors: tuple[str, ...]  # per-video transcription, DB, or metadata.json-update failures


class TranscriptionService:
    def __init__(self, project_dir: Path, config: ProjectConfig) -> None:
        self.project_dir = project_dir
        self.config = config

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

        # Determined up front so the (expensive, possibly multi-GB-download)
        # model is loaded only if at least one candidate actually needs
        # fresh transcription -- a fully-skipped rerun never pays that cost.
        needs_transcription = [
            row for row in candidates
            if not (self.project_dir / self.config.paths.workdir / row.id / "transcript" / f"{row.id}.json").is_file()
        ]

        model = None
        if needs_transcription:
            try:
                model = load_whisper_model(self.config.transcription.model)
            except TranscriptionError as exc:
                raise TranscriptionEngineError(
                    f"Could not load transcription engine (model '{self.config.transcription.model}'): {exc}"
                ) from exc

        transcribed: list[str] = []
        skipped: list[str] = []

        ordered_candidates = sorted(candidates, key=lambda r: r.id)
        total = len(ordered_candidates)
        for index, row in enumerate(ordered_candidates):
            progress.start_item(row.id, index, total)
            try:
                video_dir = self.project_dir / self.config.paths.workdir / row.id
                filesystem.ensure_video_workdir(video_dir)  # defensive: workdir may have been deleted manually

                transcript_rel = Path(self.config.paths.workdir) / row.id / "transcript" / f"{row.id}.json"
                final_path = self.project_dir / transcript_rel

                if final_path.is_file():
                    # Already transcribed in a previous run -- the engine is
                    # never re-invoked, but the DB rows are always rewritten
                    # from the on-disk JSON (cheap DELETE+INSERT), so a prior
                    # transient DB failure self-heals instead of staying
                    # silently empty forever once the JSON file exists.
                    try:
                        transcript = Transcript.load(final_path)
                    except InvalidTranscriptError as exc:
                        errors.append(f"{row.id}: transcript already exists but could not be read: {exc}")
                        continue
                    try:
                        replace_transcript_segments(db_path, row.id, _to_rows(row.id, transcript.segments))
                    except DatabaseError as exc:
                        errors.append(f"{row.id}: transcript already exists but database could not be updated: {exc}")
                        continue
                    if self._reconcile_metadata(video_dir, transcript_rel):
                        skipped.append(row.id)
                    else:
                        errors.append(f"{row.id}: transcript already exists but metadata.json could not be updated")
                    continue

                audio_path = video_dir / "audio" / f"{row.id}.wav"
                try:
                    results = transcribe_audio(
                        model, audio_path,
                        language=self.config.transcription.language,
                        word_timestamps=self.config.transcription.word_timestamps,
                        progress_callback=lambda fraction, video_id=row.id: progress.update_item(video_id, fraction),
                    )
                except TranscriptionError as exc:
                    errors.append(f"{row.id}: {exc}")
                    continue

                segments = [
                    TranscriptSegment(
                        id=f"{row.id}_seg_{i:04d}", start_seconds=r.start_seconds, end_seconds=r.end_seconds,
                        text=r.text, confidence=r.confidence,
                    )
                    for i, r in enumerate(results)
                ]
                transcript = Transcript(
                    video_id=row.id, engine=engine, model=self.config.transcription.model,
                    language=self.config.transcription.language, segments=segments,
                )

                tmp_path = final_path.parent / f"{final_path.name}.tmp"
                try:
                    transcript.save(tmp_path)
                    tmp_path.replace(final_path)
                except OSError as exc:
                    errors.append(f"{row.id}: could not finalize transcript file: {exc}")
                    tmp_path.unlink(missing_ok=True)
                    continue

                try:
                    replace_transcript_segments(db_path, row.id, _to_rows(row.id, segments))
                except DatabaseError as exc:
                    errors.append(f"{row.id}: transcript saved to {final_path.name} but database update failed: {exc}")
                    continue

                if self._reconcile_metadata(video_dir, transcript_rel):
                    transcribed.append(row.id)
                else:
                    errors.append(
                        f"{row.id}: transcript saved to {final_path.name} but metadata.json could not be updated"
                    )
            finally:
                progress.finish_item(row.id)

        return TranscriptionResult(tuple(transcribed), tuple(skipped), tuple(errors))

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


def _to_rows(video_id: str, segments: list[TranscriptSegment]) -> list[TranscriptSegmentRow]:
    return [
        TranscriptSegmentRow(
            id=seg.id, video_id=video_id, start_seconds=seg.start_seconds,
            end_seconds=seg.end_seconds, text=seg.text, confidence=seg.confidence,
        )
        for seg in segments
    ]
