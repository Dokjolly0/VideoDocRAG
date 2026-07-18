from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.storage.database import ChunkRow, VideoRow, ensure_schema, replace_chunks, upsert_video

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_ingested_video(project_dir):
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
    return config, db_path


def _seed_chunked_video(project_dir):
    config, db_path = _seed_ingested_video(project_dir)
    replace_chunks(
        db_path,
        "demo",
        [
            ChunkRow(
                id="demo_chunk_0001",
                video_id="demo",
                start_seconds=0.0,
                end_seconds=60.0,
                topic="Introduzione",
                summary="Si introduce il progetto.",
                transcript="Introduciamo il progetto.",
                ocr_text="",
                metadata_json=None,
            )
        ],
    )


def test_outline_success_prints_summary_and_writes_file(tmp_path):
    custom = _init_project(tmp_path)
    _seed_chunked_video(custom)

    result = runner.invoke(app, ["outline", "demo"])

    assert result.exit_code == 0
    assert "Generated" in result.stdout
    assert "Sections" in result.stdout
    assert (custom / "docs" / "outline.md").is_file()


def test_outline_existing_file_is_skipped(tmp_path):
    custom = _init_project(tmp_path)
    outline_path = custom / "docs" / "outline.md"
    outline_path.write_text("# Manuale\n\n## Sezione manuale\n", encoding="utf-8")

    result = runner.invoke(app, ["outline", "demo"])

    assert result.exit_code == 0
    assert "Skipped" in result.stdout
    assert "Sezione manuale" in outline_path.read_text(encoding="utf-8")


def test_outline_force_regenerates_existing_file(tmp_path):
    custom = _init_project(tmp_path)
    _seed_chunked_video(custom)
    outline_path = custom / "docs" / "outline.md"
    outline_path.write_text("# Manuale\n", encoding="utf-8")

    result = runner.invoke(app, ["outline", "demo", "--force"])

    assert result.exit_code == 0
    assert "# Documentazione demo" in outline_path.read_text(encoding="utf-8")


def test_outline_missing_chunks_fails_with_hint(tmp_path):
    custom = _init_project(tmp_path)
    _seed_ingested_video(custom)

    result = runner.invoke(app, ["outline", "demo"])

    assert result.exit_code == 1
    assert "videodoc chunk" in result.output
