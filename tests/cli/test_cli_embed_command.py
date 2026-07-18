from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.models.chunk_manifest import ChunkManifest, ChunkManifestEntry
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video
from videodoc.core.storage.filesystem import ensure_video_workdir

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_chunked_video(project_dir):
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
    video_dir = project_dir / config.paths.workdir / "demo"
    ensure_video_workdir(video_dir)
    ChunkManifest(
        video_id="demo",
        video_name="Demo.mp4",
        chunks=[
            ChunkManifestEntry(
                id="demo_chunk_0001",
                source_type="transcript",
                start_seconds=0.0,
                end_seconds=60.0,
                topic="Introduzione",
                summary="Si introduce il progetto.",
                transcript="Introduciamo il progetto.",
                video_name="Demo.mp4",
            )
        ],
        min_duration_seconds=90,
        max_duration_seconds=480,
        include_nearby_frames=True,
    ).save(video_dir / "chunks" / "demo.json")


def test_embed_success_prints_summary(tmp_path):
    custom = _init_project(tmp_path)
    _seed_chunked_video(custom)

    result = runner.invoke(app, ["embed", "demo"])

    assert result.exit_code == 0
    assert "Processed" in result.stdout
    processed_line = next(line for line in result.stdout.splitlines() if "Processed" in line)
    assert "1" in processed_line
    assert (custom / "indexes" / "embeddings" / "demo.json").is_file()


def test_embed_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["embed", "does-not-exist"])
    assert result.exit_code == 1


def test_embed_no_ingested_videos_fails(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["embed", "demo"])

    assert result.exit_code == 1
    assert "ingest" in result.output.lower()


def test_embed_rerun_shows_all_skipped(tmp_path):
    custom = _init_project(tmp_path)
    _seed_chunked_video(custom)

    runner.invoke(app, ["embed", "demo"])
    result = runner.invoke(app, ["embed", "demo"])

    assert result.exit_code == 0
    assert "Skipped" in result.stdout
    skipped_line = next(line for line in result.stdout.splitlines() if "Skipped" in line)
    assert "1" in skipped_line


def test_embed_accepts_workers_flag(tmp_path):
    custom = _init_project(tmp_path)
    _seed_chunked_video(custom)

    result = runner.invoke(app, ["embed", "demo", "--workers", "1"])

    assert result.exit_code == 0
    assert (custom / "indexes" / "embeddings" / "demo.json").is_file()
