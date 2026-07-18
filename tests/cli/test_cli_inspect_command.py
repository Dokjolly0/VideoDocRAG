from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.storage.database import (
    CodeBlockRow,
    FrameRow,
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    replace_code_blocks,
    replace_frames,
    replace_transcript_segments,
    upsert_video,
)

runner = CliRunner()


def _init_project(tmp_path):
    custom = tmp_path / "demo"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def _seed_inspection_data(project_dir):
    config = ProjectConfig.load(project_dir / "config.yaml")
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
        [TranscriptSegmentRow("demo_seg_0001", "demo", 10.0, 20.0, "Ora lanciamo npm run dev.", 0.9)],
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


def test_inspect_prints_timestamp_context(tmp_path):
    custom = _init_project(tmp_path)
    _seed_inspection_data(custom)

    result = runner.invoke(app, ["inspect", "demo", "--video", "Demo.mp4", "--timestamp", "00:00:16"])

    assert result.exit_code == 0
    assert "Project: demo" in result.stdout
    assert "Transcript" in result.stdout
    assert "npm run dev" in result.stdout


def test_inspect_invalid_timestamp_fails(tmp_path):
    _init_project(tmp_path)

    result = runner.invoke(app, ["inspect", "demo", "--timestamp", "bad"])

    assert result.exit_code == 1
    assert "Invalid timecode" in result.output
