from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DocumentationExportFormatError
from videodoc.core.services.audio_extraction_service import AudioExtractionService
from videodoc.core.services.chat_service import DocumentationIndexService
from videodoc.core.services.chunking_service import ChunkingService
from videodoc.core.services.code_service import CodeService
from videodoc.core.services.codebase_sync_service import CodebaseSyncService
from videodoc.core.services.documentation_service import DocumentationService
from videodoc.core.services.embedding_service import EmbeddingService
from videodoc.core.services.export_service import DocumentationExportService, SUPPORTED_EXPORT_FORMATS
from videodoc.core.services.frame_extraction_service import FrameExtractionService
from videodoc.core.services.index_service import IndexService
from videodoc.core.services.ingest_service import VideoIngestionService
from videodoc.core.services.ocr_service import OCRService
from videodoc.core.services.outline_service import OutlineService
from videodoc.core.services.review_service import DocumentationReviewService
from videodoc.core.services.scan_service import SourceScanService
from videodoc.core.services.transcription_service import TranscriptionService
from videodoc.core.utils.progress import ProgressReporter

PipelineStepStatus = Literal["completed", "skipped", "warning"]


@dataclass(frozen=True)
class PipelineStepResult:
    name: str
    status: PipelineStepStatus
    detail: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineRunResult:
    steps: tuple[PipelineStepResult, ...]
    export_format: str


class PipelineService:
    def __init__(
        self,
        project_dir: Path,
        config: ProjectConfig,
        *,
        export_format: str = "mkdocs",
        top_k: int | None = None,
    ) -> None:
        normalized_export_format = export_format.lower()
        if normalized_export_format not in SUPPORTED_EXPORT_FORMATS:
            raise DocumentationExportFormatError(
                f"Export format '{export_format}' is not supported -- choose one of: "
                f"{', '.join(SUPPORTED_EXPORT_FORMATS)}."
            )
        self.project_dir = project_dir
        self.config = config
        self.export_format = normalized_export_format
        self.top_k = top_k

    def run(self, progress: ProgressReporter | None = None) -> PipelineRunResult:
        progress = progress or ProgressReporter()
        steps: list[PipelineStepResult] = []

        scan = SourceScanService(self.project_dir, self.config).run()
        steps.append(
            _step(
                "scan",
                f"videos={len(scan.manifest.videos)}, attachments={len(scan.manifest.attachments)}, "
                f"codebase_files={len(scan.manifest.codebase.files)}",
                warnings=tuple(scan.manifest.scan_errors),
            )
        )

        ingest = VideoIngestionService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "ingest",
                f"ingested={len(ingest.ingested)}, reingested={len(ingest.reingested)}, skipped={len(ingest.skipped)}",
                processed=len(ingest.ingested) + len(ingest.reingested),
                skipped=len(ingest.skipped),
                warnings=ingest.errors + ingest.warnings,
            )
        )

        codebase = CodebaseSyncService(self.project_dir, self.config).run()
        steps.append(
            _processed_step(
                "sync-codebase",
                f"files={codebase.files}, snippets={codebase.snippets}, "
                f"added={codebase.added}, modified={codebase.modified}, removed={codebase.removed}",
                processed=1 if codebase.synced else 0,
                skipped=1 if codebase.skipped else 0,
                warnings=codebase.errors,
            )
        )

        audio = AudioExtractionService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "extract-audio",
                f"extracted={len(audio.extracted)}, skipped={len(audio.skipped)}",
                processed=len(audio.extracted),
                skipped=len(audio.skipped),
                warnings=audio.errors,
            )
        )

        transcribe = TranscriptionService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "transcribe",
                f"transcribed={len(transcribe.transcribed)}, skipped={len(transcribe.skipped)}",
                processed=len(transcribe.transcribed),
                skipped=len(transcribe.skipped),
                warnings=transcribe.errors,
            )
        )

        frames = FrameExtractionService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "frames",
                f"extracted={len(frames.extracted)}, skipped={len(frames.skipped)}",
                processed=len(frames.extracted),
                skipped=len(frames.skipped),
                warnings=frames.errors,
            )
        )

        ocr = OCRService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "ocr",
                f"processed={len(ocr.processed)}, skipped={len(ocr.skipped)}",
                processed=len(ocr.processed),
                skipped=len(ocr.skipped),
                warnings=ocr.errors,
            )
        )

        code = CodeService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "code",
                f"processed={len(code.processed)}, skipped={len(code.skipped)}",
                processed=len(code.processed),
                skipped=len(code.skipped),
                warnings=code.errors,
            )
        )

        chunks = ChunkingService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "chunk",
                f"processed={len(chunks.processed)}, skipped={len(chunks.skipped)}",
                processed=len(chunks.processed),
                skipped=len(chunks.skipped),
                warnings=chunks.errors,
            )
        )

        embeddings = EmbeddingService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "embed",
                f"processed={len(embeddings.processed)}, skipped={len(embeddings.skipped)}",
                processed=len(embeddings.processed),
                skipped=len(embeddings.skipped),
                warnings=embeddings.errors,
            )
        )

        index = IndexService(self.project_dir, self.config).run(progress=progress)
        steps.append(
            _processed_step(
                "index",
                f"records={index.records}, videos={index.videos}",
                processed=1 if index.indexed else 0,
                skipped=1 if index.skipped else 0,
                warnings=index.errors,
            )
        )

        outline = OutlineService(self.project_dir, self.config).run(force=False)
        steps.append(
            _processed_step(
                "outline",
                f"sections={outline.sections}",
                processed=1 if outline.generated else 0,
                skipped=1 if outline.skipped else 0,
                warnings=outline.warnings,
            )
        )

        docs = DocumentationService(self.project_dir, self.config).run(force=False, top_k=self.top_k)
        steps.append(
            _processed_step(
                "generate",
                f"generated={len(docs.generated)}, skipped={len(docs.skipped)}",
                processed=len(docs.generated),
                skipped=len(docs.skipped),
                warnings=docs.warnings,
            )
        )

        review = DocumentationReviewService(self.project_dir, self.config).run()
        steps.append(
            _step(
                "review",
                f"sections={review.sections}, issues={review.issues}, errors={review.errors}, warnings={review.warnings}",
                warnings=_review_warnings(review.errors, review.warnings),
            )
        )

        export = DocumentationExportService(self.project_dir, self.config).run(self.export_format)
        steps.append(_step("export", f"format={export.format}, files={len(export.files)}, output={export.output_path}"))

        documentation_index = DocumentationIndexService(self.project_dir, self.config).build()
        steps.append(_step("index-docs", f"records={len(documentation_index.records)}, inputs={len(documentation_index.inputs)}"))

        return PipelineRunResult(steps=tuple(steps), export_format=self.export_format)


def _step(name: str, detail: str, *, warnings: tuple[str, ...] = ()) -> PipelineStepResult:
    return PipelineStepResult(name=name, status="warning" if warnings else "completed", detail=detail, warnings=warnings)


def _processed_step(
    name: str,
    detail: str,
    *,
    processed: int,
    skipped: int,
    warnings: tuple[str, ...] = (),
) -> PipelineStepResult:
    if warnings:
        status: PipelineStepStatus = "warning"
    elif processed == 0 and skipped > 0:
        status = "skipped"
    else:
        status = "completed"
    return PipelineStepResult(name=name, status=status, detail=detail, warnings=warnings)


def _review_warnings(errors: int, warnings: int) -> tuple[str, ...]:
    messages: list[str] = []
    if errors:
        messages.append(f"review reported {errors} error(s)")
    if warnings:
        messages.append(f"review reported {warnings} warning(s)")
    return tuple(messages)
