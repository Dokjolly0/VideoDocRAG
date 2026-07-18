from datetime import datetime, timezone

from videodoc.core.config import ProjectConfig
from videodoc.core.models.source_manifest import CodebaseManifest, ExclusionsManifest, SourceManifest
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.services.status_service import PipelineStatusService
from videodoc.core.storage.database import (
    ChatSessionRow,
    ChunkRow,
    CodeBlockRow,
    FrameRow,
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    replace_chunks,
    replace_code_blocks,
    replace_frames,
    replace_transcript_segments,
    upsert_chat_session,
    upsert_video,
)


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _seed_video(project_dir, config):
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)
    upsert_video(
        db_path,
        VideoRow(
            id="demo",
            filename="Demo.mp4",
            title=None,
            duration_seconds=120.0,
            file_hash="hash",
            path=(project_dir / "videos" / "Demo.mp4").as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    return db_path


def test_status_reports_empty_project_without_creating_database(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()

    result = PipelineStatusService(project_dir, config).run()

    assert result.sources.scanned is False
    assert result.videos == ()
    assert result.raw_index.present is False
    assert result.database_path.exists() is False


def test_status_counts_pipeline_artifacts(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    db_path = _seed_video(project_dir, config)

    SourceManifest(
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        videos=["videos/Demo.mp4"],
        attachments=["attachments/slides.pdf"],
        codebase=CodebaseManifest(present=True, files=["codebase/app.py"]),
        exclusions=ExclusionsManifest(directories=[".git"], file_patterns=[]),
    ).save(project_dir / "sources.yaml")

    video_dir = project_dir / config.paths.workdir / "demo"
    for path in [
        video_dir / "audio" / "demo.wav",
        video_dir / "transcript" / "demo.json",
        video_dir / "frames" / "frames.json",
        video_dir / "ocr" / "demo.json",
        video_dir / "code" / "demo.json",
        video_dir / "chunks" / "demo.json",
        project_dir / config.paths.indexes / "embeddings" / "demo.json",
        project_dir / config.paths.output / "outline.md",
        project_dir / config.paths.output / "01-introduzione.md",
        project_dir / config.paths.output / "sources" / "01-introduzione.sources.json",
        project_dir / config.paths.output / "review_report.md",
        project_dir / config.paths.output / "review_report.json",
        project_dir / "exports" / "html" / "index.html",
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")

    replace_transcript_segments(
        db_path,
        "demo",
        [TranscriptSegmentRow("demo_seg_0001", "demo", 0.0, 10.0, "Introduzione", 0.9)],
    )
    replace_frames(
        db_path,
        "demo",
        [FrameRow("demo_frame_0001", "demo", 8.0, "workdir/demo/frames/frame_0001.jpg", "hash", "npm run dev", 0.91, True)],
    )
    replace_code_blocks(
        db_path,
        "demo",
        [CodeBlockRow("demo_code_0001", "demo", None, 8.0, "bash", "npm run dev", "ocr", 0.91, True)],
    )
    replace_chunks(
        db_path,
        "demo",
        [ChunkRow("demo_chunk_0001", "demo", 0.0, 60.0, "Intro", "Summary", "Transcript", "OCR", "{}")],
    )
    upsert_chat_session(
        db_path,
        ChatSessionRow("chat_1", "Domanda", "docs", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"),
    )
    VectorIndex(
        backend="local-json",
        configured_vector_db="qdrant",
        distance="cosine",
        dimensions=2,
        inputs=[],
        records=[VectorIndexRecord(id="demo_chunk_0001_combined", vector=[1.0, 0.0], payload={"text": "Intro"})],
    ).save(project_dir / config.paths.indexes / "vector_index.json")
    VectorIndex(
        backend="local-json",
        configured_vector_db="qdrant",
        distance="cosine",
        dimensions=2,
        inputs=[],
        records=[VectorIndexRecord(id="doc_0001", vector=[1.0, 0.0], payload={"text": "Doc"})],
    ).save(project_dir / config.paths.indexes / "documentation_index.json")

    result = PipelineStatusService(project_dir, config).run()

    assert result.sources.scanned is True
    assert result.sources.codebase_files == 1
    assert result.videos[0].audio is True
    assert result.videos[0].transcript_segments == 1
    assert result.videos[0].code_blocks == 1
    assert result.raw_index.valid is True
    assert result.raw_index.records == 1
    assert result.documentation.sections == 1
    assert result.documentation.export_formats == ("html",)
    assert result.chat_sessions == 1
