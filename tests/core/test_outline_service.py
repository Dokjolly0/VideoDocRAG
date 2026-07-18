from datetime import UTC, datetime

import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import NoVideosFoundError, OutlineSourceUnavailableError
from videodoc.core.models.source_manifest import CodebaseManifest, ExclusionsManifest, SourceManifest
from videodoc.core.services.outline_service import OutlineService
from videodoc.core.storage.database import (
    ChunkRow,
    CodeBlockRow,
    VideoRow,
    ensure_schema,
    replace_chunks,
    replace_code_blocks,
    upsert_video,
)


def _config():
    return ProjectConfig.default(name="Demo Software", slug="demo")


def _seed_video(project_dir, config, video_id="demo", filename="Demo.mp4", title=None):
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)
    video_path = project_dir / "videos" / filename
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake video")
    upsert_video(
        db_path,
        VideoRow(
            id=video_id,
            filename=filename,
            title=title,
            duration_seconds=120.0,
            file_hash="hash123",
            path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )


def _seed_chunks(project_dir, config, video_id="demo"):
    replace_chunks(
        project_dir / config.paths.database,
        video_id,
        [
            ChunkRow(
                id=f"{video_id}_chunk_0001",
                video_id=video_id,
                start_seconds=10.0,
                end_seconds=40.0,
                topic="Configurazione database",
                summary="Mostra come configurare PostgreSQL nel file config.yaml.",
                transcript="Apriamo config.yaml e impostiamo database_url.",
                ocr_text="database_url: postgresql://localhost",
                metadata_json=None,
            ),
            ChunkRow(
                id=f"{video_id}_chunk_0002",
                video_id=video_id,
                start_seconds=50.0,
                end_seconds=90.0,
                topic="Debug errori",
                summary="Spiega come diagnosticare un errore di connessione.",
                transcript="Se compare un errore controlliamo log e variabili.",
                ocr_text="ConnectionError",
                metadata_json=None,
            ),
        ],
    )


def test_fresh_outline_writes_markdown_from_chunks_code_and_sources(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, title="Workshop database")
    _seed_chunks(project_dir, config)
    replace_code_blocks(
        project_dir / config.paths.database,
        "demo",
        [
            CodeBlockRow(
                id="demo_code_0001",
                video_id="demo",
                chunk_id="demo_chunk_0001",
                timestamp_seconds=20.0,
                language="yaml",
                code="database_url: postgresql://localhost",
                source="ocr",
                confidence=0.94,
                verified=True,
            )
        ],
    )
    SourceManifest(
        scanned_at=datetime(2026, 1, 1, tzinfo=UTC),
        videos=[],
        attachments=["D:/course/slides_intro.pdf"],
        codebase=CodebaseManifest(present=True, files=["D:/course/codebase/src/app.py"]),
        exclusions=ExclusionsManifest(),
    ).save(project_dir / "sources.yaml")

    result = OutlineService(project_dir, config).run()

    assert result.generated is True
    assert result.sections == 8
    content = (project_dir / "docs" / "outline.md").read_text(encoding="utf-8")
    assert "# Documentazione Demo Software" in content
    assert "## 3. Configurazione ambiente" in content
    assert "Workshop database 00:00:10-00:00:40" in content
    assert "database_url" in content
    assert "slides_intro.pdf" in content
    assert "D:/course/codebase/src/app.py" in content


def test_existing_outline_is_preserved_without_force(tmp_path):
    project_dir = tmp_path / "demo"
    outline_path = project_dir / "docs" / "outline.md"
    outline_path.parent.mkdir(parents=True)
    outline_path.write_text("# Manuale\n\n## Sezione manuale\n", encoding="utf-8")

    result = OutlineService(project_dir, _config()).run()

    assert result.skipped is True
    assert result.generated is False
    assert outline_path.read_text(encoding="utf-8") == "# Manuale\n\n## Sezione manuale\n"


def test_force_rewrites_existing_outline(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    outline_path = project_dir / "docs" / "outline.md"
    outline_path.parent.mkdir(parents=True)
    outline_path.write_text("# Manuale\n", encoding="utf-8")
    _seed_video(project_dir, config)
    _seed_chunks(project_dir, config)

    result = OutlineService(project_dir, config).run(force=True)

    assert result.generated is True
    assert "# Documentazione Demo Software" in outline_path.read_text(encoding="utf-8")


def test_missing_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    with pytest.raises(NoVideosFoundError):
        OutlineService(project_dir, _config()).run()


def test_no_chunks_raise_actionable_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)

    with pytest.raises(OutlineSourceUnavailableError, match="videodoc chunk"):
        OutlineService(project_dir, config).run()
