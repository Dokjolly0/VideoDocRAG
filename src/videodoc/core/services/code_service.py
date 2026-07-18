from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, InvalidCodeManifestError, NoVideosFoundError
from videodoc.core.models.code_manifest import (
    CodeInputFrameSignature,
    CodeManifest,
    CodeManifestEntry,
    CodeSourceFrame,
    CodeValidation,
)
from videodoc.core.storage import filesystem
from videodoc.core.storage.database import (
    CodeBlockRow,
    FrameRow,
    VideoRow,
    ensure_schema,
    list_frames,
    list_videos,
    replace_code_blocks,
    replace_frame_code_flags,
)
from videodoc.core.utils.code_detection import analyze_ocr_text, is_code_like
from videodoc.core.utils.hardware import resolve_cpu_workers, resolve_executor_workers
from videodoc.core.utils.progress import ProgressReporter


@dataclass(frozen=True)
class CodeExtractionResult:
    processed: tuple[str, ...]
    skipped: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class _CodeOutcome:
    video_id: str
    processed: bool = False
    skipped: bool = False
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class _CodePlan:
    row: VideoRow
    video_dir: Path
    code_dir: Path
    manifest_path: Path
    frames: tuple[FrameRow, ...]
    input_frames: tuple[CodeInputFrameSignature, ...]
    needs_fresh: bool
    manifest: CodeManifest | None = None
    load_error: str | None = None


@dataclass
class _PendingBlock:
    content_type: str
    language: str
    code: str
    normalized_hash: str
    verified: bool
    validation_status: str
    validation_error: str | None
    source_frames: list[CodeSourceFrame]
    confidence: float | None
    review_reasons: set[str]


class CodeService:
    def __init__(self, project_dir: Path, config: ProjectConfig, *, workers_override: int | None = None) -> None:
        self.project_dir = project_dir
        self.config = config
        self.workers_override = workers_override
        self.extract_from_ocr = config.code.extract_from_ocr
        self.strict_mode = config.code.strict_mode
        self.mark_uncertain_code = config.code.mark_uncertain_code

    def run(self, progress: ProgressReporter | None = None) -> CodeExtractionResult:
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

        return CodeExtractionResult(tuple(processed), tuple(skipped), tuple(errors))

    def _plan_for(self, row: VideoRow, db_path: Path) -> _CodePlan:
        video_dir = self.project_dir / self.config.paths.workdir / row.id
        filesystem.ensure_video_workdir(video_dir)
        code_dir = video_dir / "code"
        manifest_path = code_dir / f"{row.id}.json"
        frames = tuple(list_frames(db_path, row.id))
        input_frames = tuple(_frame_signature(frame) for frame in frames)

        if not self.extract_from_ocr:
            return _CodePlan(row, video_dir, code_dir, manifest_path, frames, input_frames, needs_fresh=False)

        has_ocr_result = any(frame.ocr_text is not None for frame in frames)
        if not manifest_path.is_file():
            return _CodePlan(
                row,
                video_dir,
                code_dir,
                manifest_path,
                frames,
                input_frames,
                needs_fresh=bool(frames and has_ocr_result),
            )

        try:
            manifest = CodeManifest.load(manifest_path)
        except InvalidCodeManifestError as exc:
            return _CodePlan(row, video_dir, code_dir, manifest_path, frames, input_frames, needs_fresh=False, load_error=str(exc))

        settings_match = (
            manifest.extract_from_ocr == self.extract_from_ocr
            and manifest.strict_mode == self.strict_mode
            and manifest.mark_uncertain_code == self.mark_uncertain_code
        )
        input_match = tuple(manifest.input_frames) == input_frames
        return _CodePlan(
            row,
            video_dir,
            code_dir,
            manifest_path,
            frames,
            input_frames,
            needs_fresh=not (settings_match and input_match),
            manifest=manifest,
        )

    def _process_plan(
        self,
        plan: _CodePlan,
        index: int,
        total: int,
        progress: ProgressReporter,
        db_path: Path,
    ) -> _CodeOutcome:
        progress.start_item(plan.row.id, index, total)
        try:
            if plan.load_error is not None:
                return _CodeOutcome(
                    plan.row.id,
                    errors=(f"{plan.row.id}: code already exists but code manifest could not be read: {plan.load_error}",),
                )
            if not plan.frames or not self.extract_from_ocr:
                return _CodeOutcome(plan.row.id, skipped=True)
            if not plan.needs_fresh:
                if plan.manifest is None:
                    return _CodeOutcome(plan.row.id, skipped=True)
                return self._process_existing(plan, db_path)
            return self._process_fresh(plan, db_path, progress)
        finally:
            progress.finish_item(plan.row.id)

    def _process_existing(self, plan: _CodePlan, db_path: Path) -> _CodeOutcome:
        assert plan.manifest is not None
        try:
            replace_code_blocks(db_path, plan.row.id, _manifest_to_rows(plan.row.id, plan.manifest))
            replace_frame_code_flags(db_path, plan.row.id, _manifest_code_frame_ids(plan.manifest))
        except DatabaseError as exc:
            return _CodeOutcome(plan.row.id, errors=(f"{plan.row.id}: code already exists but database could not be updated: {exc}",))

        if self._write_review_report(plan.code_dir, plan.row.filename, plan.manifest):
            return _CodeOutcome(plan.row.id, skipped=True)
        return _CodeOutcome(plan.row.id, errors=(f"{plan.row.id}: code already exists but review report could not be updated",))

    def _process_fresh(self, plan: _CodePlan, db_path: Path, progress: ProgressReporter) -> _CodeOutcome:
        pending: dict[str, _PendingBlock] = {}
        code_frame_ids: set[str] = set()
        frames_with_ocr = [frame for frame in plan.frames if frame.ocr_text is not None]
        total = max(len(frames_with_ocr), 1)

        for position, frame in enumerate(frames_with_ocr, start=1):
            analysis = analyze_ocr_text(
                frame.ocr_text or "",
                ocr_confidence=frame.ocr_confidence,
                strict_mode=self.strict_mode,
                mark_uncertain_code=self.mark_uncertain_code,
            )
            progress.update_item(plan.row.id, position / total)
            if analysis is None or not is_code_like(analysis.content_type):
                continue

            code_frame_ids.add(frame.id)
            key = f"{analysis.content_type}:{analysis.language}:{analysis.normalized_hash}"
            source_frame = CodeSourceFrame(
                frame_id=frame.id,
                timestamp_seconds=frame.timestamp_seconds,
                ocr_confidence=frame.ocr_confidence,
            )
            if key not in pending:
                pending[key] = _PendingBlock(
                    content_type=analysis.content_type,
                    language=analysis.language,
                    code=analysis.code,
                    normalized_hash=analysis.normalized_hash,
                    verified=analysis.verified,
                    validation_status=analysis.validation_status,
                    validation_error=analysis.validation_error,
                    source_frames=[source_frame],
                    confidence=frame.ocr_confidence,
                    review_reasons=set(analysis.review_reasons),
                )
                continue

            block = pending[key]
            block.source_frames.append(source_frame)
            block.review_reasons.update(analysis.review_reasons)
            if frame.ocr_confidence is not None:
                block.confidence = frame.ocr_confidence if block.confidence is None else max(block.confidence, frame.ocr_confidence)

        entries = _pending_to_entries(plan.row.id, pending)
        manifest = CodeManifest(
            video_id=plan.row.id,
            entries=entries,
            input_frames=list(plan.input_frames),
            extract_from_ocr=self.extract_from_ocr,
            strict_mode=self.strict_mode,
            mark_uncertain_code=self.mark_uncertain_code,
        )

        plan.code_dir.mkdir(parents=True, exist_ok=True)
        tmp_manifest_path = plan.manifest_path.parent / f"{plan.manifest_path.name}.tmp"
        try:
            manifest.save(tmp_manifest_path)
            tmp_manifest_path.replace(plan.manifest_path)
        except OSError as exc:
            tmp_manifest_path.unlink(missing_ok=True)
            return _CodeOutcome(plan.row.id, errors=(f"{plan.row.id}: could not finalize code manifest: {exc}",))

        try:
            replace_code_blocks(db_path, plan.row.id, _manifest_to_rows(plan.row.id, manifest))
            replace_frame_code_flags(db_path, plan.row.id, code_frame_ids)
        except DatabaseError as exc:
            return _CodeOutcome(
                plan.row.id,
                errors=(f"{plan.row.id}: code saved to {plan.manifest_path.name} but database update failed: {exc}",),
            )

        if self._write_review_report(plan.code_dir, plan.row.filename, manifest):
            return _CodeOutcome(plan.row.id, processed=True)
        return _CodeOutcome(
            plan.row.id,
            errors=(f"{plan.row.id}: code saved to {plan.manifest_path.name} but review report could not be updated",),
        )

    def _write_review_report(self, code_dir: Path, video_name: str, manifest: CodeManifest) -> bool:
        review_entries = [entry for entry in manifest.entries if entry.needs_review]
        lines = ["# Blocchi di codice da verificare", ""]
        if not review_entries:
            lines.append("Nessun blocco richiede revisione.")
        for entry in review_entries:
            timestamp = _format_timestamp(entry.timestamp_seconds)
            confidence = "-" if entry.confidence is None else f"{entry.confidence:.2f}"
            frames = ", ".join(frame.frame_id for frame in entry.source_frames)
            language = entry.language if entry.language != "other" else "text"
            lines.extend([
                f"## {video_name} - {timestamp}",
                "",
                f"Frame: `{frames}`",
                f"Tipo: `{entry.content_type}`",
                f"Linguaggio: `{entry.language}`",
                f"Confidenza OCR: {confidence}",
                "",
                "Motivo revisione:",
                *[f"- {reason}" for reason in entry.review_reasons],
                "",
                f"```{language}",
                entry.code,
                "```",
                "",
            ])
        try:
            code_dir.mkdir(parents=True, exist_ok=True)
            (code_dir / "code_review_report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        except OSError:
            return False
        return True


def _frame_signature(frame: FrameRow) -> CodeInputFrameSignature:
    text_hash = None if frame.ocr_text is None else hashlib.sha256(frame.ocr_text.encode("utf-8")).hexdigest()
    return CodeInputFrameSignature(
        frame_id=frame.id,
        timestamp_seconds=frame.timestamp_seconds,
        perceptual_hash=frame.perceptual_hash,
        ocr_text_hash=text_hash,
        ocr_confidence=frame.ocr_confidence,
    )


def _pending_to_entries(video_id: str, pending: dict[str, _PendingBlock]) -> list[CodeManifestEntry]:
    ordered = sorted(
        pending.values(),
        key=lambda block: (min(frame.timestamp_seconds for frame in block.source_frames), block.normalized_hash),
    )
    entries: list[CodeManifestEntry] = []
    for index, block in enumerate(ordered, start=1):
        source_frames = sorted(block.source_frames, key=lambda frame: (frame.timestamp_seconds, frame.frame_id))
        review_reasons = sorted(block.review_reasons)
        entries.append(
            CodeManifestEntry(
                id=f"{video_id}_code_{index:04d}",
                content_type=block.content_type,
                language=block.language,
                code=block.code,
                normalized_hash=block.normalized_hash,
                timestamp_seconds=source_frames[0].timestamp_seconds,
                end_timestamp_seconds=source_frames[-1].timestamp_seconds if len(source_frames) > 1 else None,
                source="ocr",
                confidence=block.confidence,
                verified=block.verified,
                validation=CodeValidation(status=block.validation_status, error=block.validation_error),
                source_frames=source_frames,
                needs_review=bool(review_reasons),
                review_reasons=review_reasons,
            )
        )
    return entries


def _manifest_to_rows(video_id: str, manifest: CodeManifest) -> list[CodeBlockRow]:
    return [
        CodeBlockRow(
            id=entry.id,
            video_id=video_id,
            chunk_id=None,
            timestamp_seconds=entry.timestamp_seconds,
            language=entry.language,
            code=entry.code,
            source=entry.source,
            confidence=entry.confidence,
            verified=entry.verified,
        )
        for entry in manifest.entries
    ]


def _manifest_code_frame_ids(manifest: CodeManifest) -> set[str]:
    return {frame.frame_id for entry in manifest.entries for frame in entry.source_frames}


def _format_timestamp(seconds: float) -> str:
    total = max(int(seconds), 0)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
