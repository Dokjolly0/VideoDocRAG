import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import InspectionUnavailableError, NoVideosFoundError
from videodoc.core.models.document_section import GeneratedSectionManifest, GeneratedSectionSource
from videodoc.core.services.inspection_service import TimestampInspectionService
from videodoc.core.storage.database import (
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
    upsert_video,
)
from videodoc.core.utils.embedding import text_hash


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _seed_project(project_dir, config):
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
    replace_transcript_segments(
        db_path,
        "demo",
        [TranscriptSegmentRow("demo_seg_0001", "demo", 10.0, 20.0, "Ora lanciamo il comando npm run dev.", 0.92)],
    )
    replace_frames(
        db_path,
        "demo",
        [FrameRow("demo_frame_0001", "demo", 16.0, "workdir/demo/frames/frame_0001.jpg", "hash", "npm run dev", 0.91, True)],
    )
    replace_code_blocks(
        db_path,
        "demo",
        [CodeBlockRow("demo_code_0001", "demo", None, 16.0, "bash", "npm run dev", "ocr", 0.91, True)],
    )
    replace_chunks(
        db_path,
        "demo",
        [ChunkRow("demo_chunk_0001", "demo", 0.0, 60.0, "Introduzione", "Si avvia il server.", "Ora lanciamo", "npm run dev", "{}")],
    )
    docs_sources = project_dir / config.paths.output / "sources"
    docs_sources.mkdir(parents=True, exist_ok=True)
    GeneratedSectionManifest(
        section_index=1,
        section_title="Introduzione",
        section_slug="introduzione",
        output_path="docs/01-introduzione.md",
        sources=[
            GeneratedSectionSource(
                rank=1,
                record_id="demo_chunk_0001_combined",
                video_id="demo",
                video_name="Demo.mp4",
                chunk_id="demo_chunk_0001",
                start_seconds=0.0,
                end_seconds=60.0,
                score=0.9,
                topic="Introduzione",
                source_type="transcript",
                embedding_type="combined",
                text_hash=text_hash("Ora lanciamo"),
            )
        ],
        code_blocks=[],
    ).save(docs_sources / "01-introduzione.sources.json")


def test_inspect_timestamp_returns_linked_sources(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)

    result = TimestampInspectionService(project_dir, config).inspect(video="Demo.mp4", timestamp_seconds=16.0)

    assert result.video_id == "demo"
    assert result.transcript.text.startswith("Ora lanciamo")
    assert result.frame.ocr_text == "npm run dev"
    assert result.code_blocks[0].block_id == "demo_code_0001"
    assert result.chunk.chunk_id == "demo_chunk_0001"
    assert result.documentation_hits[0].output_path == "docs/01-introduzione.md"


def test_inspect_requires_video_when_multiple_videos(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)
    upsert_video(
        project_dir / config.paths.database,
        VideoRow(
            id="altro",
            filename="Altro.mp4",
            title=None,
            duration_seconds=60.0,
            file_hash="hash",
            path=(project_dir / "videos" / "Altro.mp4").as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )

    with pytest.raises(InspectionUnavailableError, match="--video is required"):
        TimestampInspectionService(project_dir, config).inspect(timestamp_seconds=1.0)


def test_inspect_without_database_raises_no_videos(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(NoVideosFoundError):
        TimestampInspectionService(project_dir, _config()).inspect(timestamp_seconds=1.0)
