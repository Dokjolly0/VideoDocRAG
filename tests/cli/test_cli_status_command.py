from typer.testing import CliRunner

from videodoc.cli.app import app
from videodoc.core.config import ProjectConfig
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video

runner = CliRunner()


def _init_project(tmp_path):
    custom = tmp_path / "demo"
    result = runner.invoke(app, ["init", "demo", "--path", str(custom)])
    assert result.exit_code == 0
    return custom


def test_status_prints_project_summary(tmp_path):
    custom = _init_project(tmp_path)
    config = ProjectConfig.load(custom / "config.yaml")
    db_path = custom / config.paths.database
    ensure_schema(db_path)
    upsert_video(
        db_path,
        VideoRow(
            id="demo",
            filename="Demo.mp4",
            title=None,
            duration_seconds=120.0,
            file_hash="hash",
            path=(custom / "videos" / "Demo.mp4").as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )

    result = runner.invoke(app, ["status", "demo"])

    assert result.exit_code == 0
    assert "Project: demo" in result.stdout
    assert "Videos" in result.stdout
    assert "Audio extracted" in result.stdout


def test_status_unknown_project_fails():
    result = runner.invoke(app, ["status", "missing"])

    assert result.exit_code == 1
    assert "Error:" in result.output
