from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.models.embedding_manifest import EmbeddingChunkSignature, EmbeddingManifest, EmbeddingRecord
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_embedded_video(project_dir):
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
    path = project_dir / "indexes" / "embeddings" / "demo.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    EmbeddingManifest(
        video_id="demo",
        video_name="Demo.mp4",
        backend="feature-hashing",
        provider="local",
        model="bge-m3",
        dimensions=2,
        batch_size=32,
        chunk_inputs=[
            EmbeddingChunkSignature(
                id="demo_chunk_0001",
                source_type="transcript",
                start_seconds=0.0,
                end_seconds=60.0,
                topic_hash="topic",
                summary_hash="summary",
                transcript_hash="transcript",
                ocr_hash="ocr",
                code_hash="code",
                metadata_hash="metadata",
            )
        ],
        records=[
            EmbeddingRecord(
                id="demo_chunk_0001_combined",
                chunk_id="demo_chunk_0001",
                embedding_type="combined",
                text="Introduzione",
                text_hash="hash",
                vector=[1.0, 0.0],
                dimensions=2,
                metadata={"source_type": "transcript"},
            )
        ],
    ).save(path)


def test_index_success_prints_summary(tmp_path):
    custom = _init_project(tmp_path)
    _seed_embedded_video(custom)

    result = runner.invoke(app, ["index", "demo"])

    assert result.exit_code == 0
    assert "Records" in result.stdout
    records_line = next(line for line in result.stdout.splitlines() if "Records" in line)
    assert "1" in records_line
    assert (custom / "indexes" / "vector_index.json").is_file()


def test_index_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["index", "does-not-exist"])
    assert result.exit_code == 1


def test_index_no_ingested_videos_fails(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["index", "demo"])

    assert result.exit_code == 1
    assert "ingest" in result.output.lower()


def test_index_rerun_shows_skipped(tmp_path):
    custom = _init_project(tmp_path)
    _seed_embedded_video(custom)

    runner.invoke(app, ["index", "demo"])
    result = runner.invoke(app, ["index", "demo"])

    assert result.exit_code == 0
    assert "Skipped" in result.stdout
    skipped_line = next(line for line in result.stdout.splitlines() if "Skipped" in line)
    assert "yes" in skipped_line
