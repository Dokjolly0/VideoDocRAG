from types import SimpleNamespace

import pytest

import videodoc.core.services.pipeline_service as pipeline_service_module
from videodoc.core.config import ProjectConfig
from videodoc.core.errors import NoVideosFoundError
from videodoc.core.services.pipeline_service import PipelineService


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _patch_service(monkeypatch, name, calls, result):
    class DummyService:
        def __init__(self, *args, **kwargs):
            self.init_args = args
            self.init_kwargs = kwargs

        def run(self, *args, **kwargs):
            calls.append((name, "run", args, kwargs))
            return result

    monkeypatch.setattr(pipeline_service_module, name, DummyService)


def _patch_build_service(monkeypatch, name, calls, result):
    class DummyService:
        def __init__(self, *args, **kwargs):
            self.init_args = args
            self.init_kwargs = kwargs

        def build(self, *args, **kwargs):
            calls.append((name, "build", args, kwargs))
            return result

    monkeypatch.setattr(pipeline_service_module, name, DummyService)


def _patch_pipeline(monkeypatch, calls):
    _patch_service(
        monkeypatch,
        "SourceScanService",
        calls,
        SimpleNamespace(
            manifest=SimpleNamespace(
                videos=["videos/demo.mp4"],
                attachments=[],
                codebase=SimpleNamespace(files=["codebase/app.py"]),
                scan_errors=(),
            )
        ),
    )
    _patch_service(
        monkeypatch,
        "VideoIngestionService",
        calls,
        SimpleNamespace(ingested=("demo",), reingested=(), skipped=(), errors=(), warnings=()),
    )
    _patch_service(
        monkeypatch,
        "CodebaseSyncService",
        calls,
        SimpleNamespace(synced=True, skipped=False, files=1, snippets=1, added=1, modified=0, removed=0, errors=()),
    )
    _patch_service(monkeypatch, "AudioExtractionService", calls, SimpleNamespace(extracted=("demo",), skipped=(), errors=()))
    _patch_service(monkeypatch, "TranscriptionService", calls, SimpleNamespace(transcribed=("demo",), skipped=(), errors=()))
    _patch_service(monkeypatch, "FrameExtractionService", calls, SimpleNamespace(extracted=("demo",), skipped=(), errors=()))
    _patch_service(monkeypatch, "OCRService", calls, SimpleNamespace(processed=("demo",), skipped=(), errors=()))
    _patch_service(monkeypatch, "CodeService", calls, SimpleNamespace(processed=("demo",), skipped=(), errors=()))
    _patch_service(monkeypatch, "ChunkingService", calls, SimpleNamespace(processed=("demo",), skipped=(), errors=()))
    _patch_service(monkeypatch, "EmbeddingService", calls, SimpleNamespace(processed=("demo",), skipped=(), errors=()))
    _patch_service(monkeypatch, "IndexService", calls, SimpleNamespace(indexed=True, skipped=False, records=3, videos=1, errors=()))
    _patch_service(monkeypatch, "OutlineService", calls, SimpleNamespace(generated=True, skipped=False, sections=2, warnings=()))
    _patch_service(monkeypatch, "DocumentationService", calls, SimpleNamespace(generated=("section",), skipped=(), warnings=()))
    _patch_service(monkeypatch, "DocumentationReviewService", calls, SimpleNamespace(sections=1, issues=0, errors=0, warnings=0))
    _patch_service(
        monkeypatch,
        "DocumentationExportService",
        calls,
        SimpleNamespace(format="mkdocs", files=("index.md",), output_path="exports/mkdocs"),
    )
    _patch_build_service(monkeypatch, "DocumentationIndexService", calls, SimpleNamespace(records=("doc",), inputs=("input",)))


def test_pipeline_runs_steps_in_readme_order(monkeypatch, tmp_path):
    calls = []
    _patch_pipeline(monkeypatch, calls)

    result = PipelineService(tmp_path, _config()).run()

    assert [step.name for step in result.steps] == [
        "scan",
        "ingest",
        "sync-codebase",
        "extract-audio",
        "transcribe",
        "frames",
        "ocr",
        "code",
        "chunk",
        "embed",
        "index",
        "outline",
        "generate",
        "review",
        "export",
        "index-docs",
    ]
    assert [name for name, _, _, _ in calls] == [
        "SourceScanService",
        "VideoIngestionService",
        "CodebaseSyncService",
        "AudioExtractionService",
        "TranscriptionService",
        "FrameExtractionService",
        "OCRService",
        "CodeService",
        "ChunkingService",
        "EmbeddingService",
        "IndexService",
        "OutlineService",
        "DocumentationService",
        "DocumentationReviewService",
        "DocumentationExportService",
        "DocumentationIndexService",
    ]
    assert result.export_format == "mkdocs"


def test_pipeline_marks_per_item_errors_as_warnings(monkeypatch, tmp_path):
    calls = []
    _patch_pipeline(monkeypatch, calls)
    _patch_service(
        monkeypatch,
        "AudioExtractionService",
        calls,
        SimpleNamespace(extracted=("demo",), skipped=(), errors=("demo: ffmpeg failed",)),
    )

    result = PipelineService(tmp_path, _config()).run()

    audio_step = next(step for step in result.steps if step.name == "extract-audio")
    assert audio_step.status == "warning"
    assert audio_step.warnings == ("demo: ffmpeg failed",)


def test_pipeline_stops_when_a_structural_step_fails(monkeypatch, tmp_path):
    calls = []
    _patch_pipeline(monkeypatch, calls)

    class FailingIngestService:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, *args, **kwargs):
            calls.append(("VideoIngestionService", "run", args, kwargs))
            raise NoVideosFoundError("No video files found")

    monkeypatch.setattr(pipeline_service_module, "VideoIngestionService", FailingIngestService)

    with pytest.raises(NoVideosFoundError):
        PipelineService(tmp_path, _config()).run()

    assert [name for name, _, _, _ in calls] == ["SourceScanService", "VideoIngestionService"]
