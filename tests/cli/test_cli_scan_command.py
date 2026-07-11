import os

from typer.testing import CliRunner

import videodoc.core.storage.filesystem as filesystem_module
from videodoc.cli.app import app

runner = CliRunner()


def test_scan_internal_videos_found(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    (custom / "videos" / "a.mp4").write_text("x", encoding="utf-8")
    (custom / "videos" / "b.mp4").write_text("x", encoding="utf-8")

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "Videos" in result.stdout
    assert "2 found" in result.stdout
    assert (custom / "sources.yaml").is_file()


def test_scan_zero_videos_reports_zero_not_failure(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "Videos" in result.stdout
    assert "0 found" in result.stdout


def test_scan_external_videos_reported_with_suffix(tmp_path):
    custom = tmp_path / "demo"
    external = tmp_path / "external-videos"
    external.mkdir()
    (external / "a.mp4").write_text("x", encoding="utf-8")
    runner.invoke(app, ["init", "demo", "--path", str(custom), "--videos", str(external)])

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "1 found (external:" in result.stdout


def test_scan_external_videos_missing_path_warns_not_crashes(tmp_path):
    custom = tmp_path / "demo"
    missing = tmp_path / "does-not-exist"
    runner.invoke(app, ["init", "demo", "--path", str(custom), "--videos", str(missing)])

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout
    assert "external videos path not found" in result.stdout


def test_scan_external_videos_path_is_file_not_directory_warns_distinctly(tmp_path):
    custom = tmp_path / "demo"
    a_file = tmp_path / "not-a-dir.mp4"
    a_file.write_text("x", encoding="utf-8")
    runner.invoke(app, ["init", "demo", "--path", str(custom), "--videos", str(a_file)])

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "external videos path exists but is not a directory" in result.stdout


def test_scan_external_attachments_missing_path_warns(tmp_path):
    custom = tmp_path / "demo"
    missing = tmp_path / "does-not-exist"
    runner.invoke(app, ["init", "demo", "--path", str(custom), "--attachments", str(missing)])

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "external attachments path not found" in result.stdout


def test_scan_external_codebase_missing_path_warns(tmp_path):
    custom = tmp_path / "demo"
    missing = tmp_path / "does-not-exist"
    runner.invoke(app, ["init", "demo", "--path", str(custom), "--codebase", str(missing)])

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "external codebase path not found" in result.stdout


def test_scan_excludes_node_modules_end_to_end(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    (custom / "codebase" / "node_modules" / "pkg").mkdir(parents=True)
    (custom / "codebase" / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    (custom / "codebase" / "main.py").write_text("x", encoding="utf-8")

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "present (1 files)" in result.stdout
    assert "node_modules" in result.stdout


def test_scan_reports_walk_errors_as_warnings_without_failing(tmp_path, monkeypatch):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    codebase = custom / "codebase"
    (codebase / "main.py").write_text("x", encoding="utf-8")

    real_walk = os.walk

    def fake_walk(top, **kwargs):
        onerror = kwargs.get("onerror")
        if onerror is not None and str(codebase) in str(top):
            onerror(OSError(13, "Permission denied", str(codebase / "blocked")))
        yield from real_walk(top, **kwargs)

    monkeypatch.setattr(filesystem_module.os, "walk", fake_walk)

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout
    assert "codebase:" in result.stdout


def test_scan_unreadable_codebase_root_warns_without_crashing(tmp_path, monkeypatch):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    codebase = custom / "codebase"

    real_scandir = os.scandir

    def fake_scandir(path):
        if str(path) == str(codebase):
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(filesystem_module.os, "scandir", fake_scandir)

    result = runner.invoke(app, ["scan", "demo"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout
    assert "codebase:" in result.stdout
    assert "not present" in result.stdout


def test_scan_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["scan", "does-not-exist"])
    assert result.exit_code == 1
