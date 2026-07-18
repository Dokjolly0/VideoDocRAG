from pathlib import Path

from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.storage.database import (
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    replace_transcript_segments,
    upsert_video,
)
from videodoc.core.storage.filesystem import ensure_video_workdir

runner = CliRunner()


def _init_project(tmp_path, name="demo"):
    custom = tmp_path / name
    result = runner.invoke(app, ["init", name, "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_transcribed_video(project_dir, config=None):
    config = config or ProjectConfig.load(project_dir / "config.yaml")
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
    workdir_rel = Path(config.paths.workdir) / "demo"
    VideoMetadata(
        video_id="demo",
        video_name="Demo.mp4",
        title=None,
        duration_seconds=120.0,
        language="it",
        hash="hash123",
        format="mov,mp4",
        width=1280,
        height=720,
        codec="h264",
        audio_path=(workdir_rel / "audio").as_posix(),
        transcript_path=(workdir_rel / "transcript" / "demo.json").as_posix(),
        frames_path=(workdir_rel / "frames").as_posix(),
        ocr_path=(workdir_rel / "ocr").as_posix(),
        chunks_path=(workdir_rel / "chunks").as_posix(),
    ).save(video_dir / "metadata.json")
    replace_transcript_segments(
        db_path,
        "demo",
        [
            TranscriptSegmentRow(
                id="demo_seg_0001",
                video_id="demo",
                start_seconds=0.0,
                end_seconds=60.0,
                text="Introduciamo il progetto.",
                confidence=0.9,
            )
        ],
    )
    return video_dir


def test_chunk_success_prints_summary(tmp_path):
    custom = _init_project(tmp_path)
    _seed_transcribed_video(custom)

    result = runner.invoke(app, ["chunk", "demo"])

    assert result.exit_code == 0
    assert "Processed" in result.stdout
    processed_line = next(line for line in result.stdout.splitlines() if "Processed" in line)
    assert "1" in processed_line
    assert (custom / "workdir" / "demo" / "chunks" / "demo.json").is_file()


def test_chunk_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["chunk", "does-not-exist"])
    assert result.exit_code == 1


def test_chunk_no_ingested_videos_fails(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["chunk", "demo"])

    assert result.exit_code == 1
    assert "ingest" in result.output.lower()


def test_chunk_rerun_shows_all_skipped(tmp_path):
    custom = _init_project(tmp_path)
    _seed_transcribed_video(custom)

    runner.invoke(app, ["chunk", "demo"])
    result = runner.invoke(app, ["chunk", "demo"])

    assert result.exit_code == 0
    assert "Skipped" in result.stdout
    skipped_line = next(line for line in result.stdout.splitlines() if "Skipped" in line)
    assert "1" in skipped_line


def test_chunk_accepts_workers_flag(tmp_path):
    custom = _init_project(tmp_path)
    _seed_transcribed_video(custom)

    result = runner.invoke(app, ["chunk", "demo", "--workers", "1"])

    assert result.exit_code == 0
    assert (custom / "workdir" / "demo" / "chunks" / "demo.json").is_file()
