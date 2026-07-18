from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.models.vector_index import VectorIndex, VectorIndexRecord
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video
from videodoc.core.utils.embedding import embed_text_hashing

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_ready_project(project_dir):
    config = ProjectConfig.load(project_dir / "config.yaml")
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)
    video_path = project_dir / "videos" / "Demo.mp4"
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
    docs = project_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "outline.md").write_text(
        "# Documentazione demo\n\n## 1. Introduzione\n\nObiettivo: presentare il progetto.\n",
        encoding="utf-8",
    )
    text = "Introduciamo il progetto e la configurazione iniziale."
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
                    "start_seconds": 0.0,
                    "end_seconds": 60.0,
                    "topic": "Introduzione",
                    "text": text,
                },
            )
        ],
    ).save(path)


def test_generate_success_prints_summary_and_writes_section(tmp_path):
    custom = _init_project(tmp_path)
    _seed_ready_project(custom)

    result = runner.invoke(app, ["generate", "demo", "--top-k", "1"])

    assert result.exit_code == 0
    assert "Generated" in result.stdout
    assert (custom / "docs" / "01-introduzione.md").is_file()
    assert (custom / "docs" / "sources" / "01-introduzione.sources.json").is_file()


def test_generate_existing_section_is_skipped(tmp_path):
    custom = _init_project(tmp_path)
    _seed_ready_project(custom)
    section_path = custom / "docs" / "01-introduzione.md"
    section_path.write_text("# Manuale\n", encoding="utf-8")

    result = runner.invoke(app, ["generate", "demo"])

    assert result.exit_code == 0
    assert "Skipped" in result.stdout
    assert section_path.read_text(encoding="utf-8") == "# Manuale\n"


def test_generate_missing_outline_fails_with_hint(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["generate", "demo"])

    assert result.exit_code == 1
    assert "videodoc outline" in result.output
