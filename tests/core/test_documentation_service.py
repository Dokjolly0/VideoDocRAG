import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DocumentationOutlineUnavailableError, VectorIndexUnavailableError
from videodoc.core.models.document_section import GeneratedSectionManifest
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.services.documentation_service import DocumentationService
from videodoc.core.storage.database import CodeBlockRow, VideoRow, ensure_schema, replace_code_blocks, upsert_video
from videodoc.core.utils.embedding import embed_text_hashing


def _config():
    return ProjectConfig.default(name="Demo Software", slug="demo")


def _seed_project(project_dir, config):
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)
    video_path = project_dir / "videos" / "Demo.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake video")
    upsert_video(
        db_path,
        VideoRow(
            id="demo",
            filename="Demo.mp4",
            title=None,
            duration_seconds=120.0,
            file_hash="hash123",
            path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )
    replace_code_blocks(
        db_path,
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


def _seed_outline(project_dir):
    docs = project_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "outline.md").write_text(
        "# Documentazione Demo Software\n\n"
        "## 1. Configurazione ambiente\n\n"
        "Obiettivo: descrivere la configurazione del database.\n",
        encoding="utf-8",
    )


def _seed_index(project_dir, config):
    text = "La configurazione del database usa PostgreSQL nel file config.yaml con database_url."
    path = project_dir / config.paths.indexes / "vector_index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    VectorIndex(
        backend="local-json",
        configured_vector_db="qdrant",
        distance="cosine",
        dimensions=32,
        inputs=[],
        records=[
            VectorIndexRecord(
                id="demo_chunk_0001_combined",
                vector=embed_text_hashing(text, dimensions=32),
                payload={
                    "project_id": "demo",
                    "video_id": "demo",
                    "video_name": "Demo.mp4",
                    "chunk_id": "demo_chunk_0001",
                    "embedding_type": "combined",
                    "source_type": "transcript",
                    "start_seconds": 10.0,
                    "end_seconds": 40.0,
                    "topic": "Configurazione database",
                    "text": text,
                },
            )
        ],
    ).save(path)


def test_generate_writes_section_and_source_manifest(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)
    _seed_outline(project_dir)
    _seed_index(project_dir, config)

    result = DocumentationService(project_dir, config).run(top_k=1)

    assert len(result.generated) == 1
    section_path = project_dir / "docs" / "01-configurazione-ambiente.md"
    content = section_path.read_text(encoding="utf-8")
    assert "# Configurazione ambiente" in content
    assert "Fonti utilizzate" in content
    assert "Demo.mp4" in content
    assert "database_url: postgresql://localhost" in content
    manifest = GeneratedSectionManifest.load(project_dir / "docs" / "sources" / "01-configurazione-ambiente.sources.json")
    assert manifest.sources[0].chunk_id == "demo_chunk_0001"
    assert manifest.code_blocks[0].id == "demo_code_0001"


def test_existing_section_is_preserved_without_force(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)
    _seed_outline(project_dir)
    _seed_index(project_dir, config)
    section_path = project_dir / "docs" / "01-configurazione-ambiente.md"
    section_path.write_text("# Manuale\n", encoding="utf-8")

    result = DocumentationService(project_dir, config).run()

    assert result.skipped == (section_path,)
    assert section_path.read_text(encoding="utf-8") == "# Manuale\n"


def test_force_regenerates_existing_section(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)
    _seed_outline(project_dir)
    _seed_index(project_dir, config)
    section_path = project_dir / "docs" / "01-configurazione-ambiente.md"
    section_path.write_text("# Manuale\n", encoding="utf-8")

    result = DocumentationService(project_dir, config).run(force=True)

    assert len(result.generated) == 1
    assert "# Configurazione ambiente" in section_path.read_text(encoding="utf-8")


def test_missing_outline_raises_actionable_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(DocumentationOutlineUnavailableError, match="videodoc outline"):
        DocumentationService(project_dir, _config()).run()


def test_missing_index_raises_actionable_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)
    _seed_outline(project_dir)

    with pytest.raises(VectorIndexUnavailableError, match="videodoc index"):
        DocumentationService(project_dir, config).run()


def test_regenerate_section_only_rewrites_matching_section(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)
    _seed_index(project_dir, config)
    docs = project_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "outline.md").write_text(
        "# Documentazione Demo Software\n\n"
        "## 1. Configurazione ambiente\n\n"
        "Obiettivo: descrivere la configurazione del database.\n\n"
        "## 2. Deploy\n\n"
        "Obiettivo: descrivere il deploy.\n",
        encoding="utf-8",
    )
    first = docs / "01-configurazione-ambiente.md"
    second = docs / "02-deploy.md"
    first.write_text("# Vecchia configurazione\n", encoding="utf-8")
    second.write_text("# Manuale deploy\n", encoding="utf-8")

    result = DocumentationService(project_dir, config).run(force=True, section="Configurazione ambiente")

    assert len(result.generated) == 1
    assert "# Configurazione ambiente" in first.read_text(encoding="utf-8")
    assert second.read_text(encoding="utf-8") == "# Manuale deploy\n"


def test_regenerate_unknown_section_raises_actionable_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_project(project_dir, config)
    _seed_outline(project_dir)
    _seed_index(project_dir, config)

    with pytest.raises(DocumentationOutlineUnavailableError, match="Available sections"):
        DocumentationService(project_dir, config).run(force=True, section="Missing")
