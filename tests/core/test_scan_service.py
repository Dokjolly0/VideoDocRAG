import os

import videodoc.core.storage.filesystem as filesystem_module
from videodoc.core.config import ProjectConfig
from videodoc.core.services.scan_service import SourceScanService


def _config(**paths_overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if paths_overrides:
        config = config.model_copy(update={"paths": config.paths.model_copy(update=paths_overrides)})
    return config


def test_scan_internal_videos_found(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "videos" / "a.mp4").write_text("x", encoding="utf-8")
    (project_dir / "attachments").mkdir()
    (project_dir / "codebase").mkdir()

    result = SourceScanService(project_dir, _config()).run()

    assert result.manifest.videos == [(project_dir / "videos" / "a.mp4").resolve().as_posix()]
    assert result.videos_report.is_external is False


def test_scan_external_videos_found(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "attachments").mkdir(parents=True)
    (project_dir / "codebase").mkdir()
    external = tmp_path / "external-videos"
    external.mkdir()
    (external / "a.mp4").write_text("x", encoding="utf-8")
    (external / "b.mp4").write_text("x", encoding="utf-8")

    result = SourceScanService(project_dir, _config(videos=str(external))).run()

    assert len(result.manifest.videos) == 2
    assert result.videos_report.is_external is True
    assert result.videos_report.resolved_path == external.resolve()


def test_scan_external_missing_path_reports_zero_no_crash(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "attachments").mkdir(parents=True)
    (project_dir / "codebase").mkdir()
    missing = tmp_path / "does-not-exist"

    result = SourceScanService(project_dir, _config(videos=str(missing))).run()

    assert result.manifest.videos == []
    assert result.videos_report.exists is False
    assert result.videos_report.is_directory is False


def test_scan_external_path_is_a_file_not_directory(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "attachments").mkdir(parents=True)
    (project_dir / "codebase").mkdir()
    a_file = tmp_path / "not-a-dir.mp4"
    a_file.write_text("x", encoding="utf-8")

    result = SourceScanService(project_dir, _config(videos=str(a_file))).run()

    assert result.manifest.videos == []
    assert result.videos_report.exists is True
    assert result.videos_report.is_directory is False


def test_scan_zero_videos_does_not_fail(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "attachments").mkdir()
    (project_dir / "codebase").mkdir()

    result = SourceScanService(project_dir, _config()).run()
    assert result.manifest.videos == []


def test_scan_codebase_present_with_exclusions(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "attachments").mkdir()
    codebase = project_dir / "codebase"
    (codebase / "node_modules" / "pkg").mkdir(parents=True)
    (codebase / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    (codebase / "main.py").write_text("x", encoding="utf-8")

    result = SourceScanService(project_dir, _config()).run()

    assert result.manifest.codebase.present is True
    assert result.manifest.codebase.files == [(codebase / "main.py").resolve().as_posix()]


def test_scan_codebase_not_present_on_fresh_project(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "attachments").mkdir()
    (project_dir / "codebase").mkdir()

    result = SourceScanService(project_dir, _config()).run()
    assert result.manifest.codebase.present is False


def test_scan_unreadable_codebase_root_does_not_crash(tmp_path, monkeypatch):
    """Regression test: codebase_is_present() used to be able to raise an
    uncaught OSError (e.g. permission denied) before scan_codebase()'s own
    error handling ever ran, crashing the whole scan. Must instead be
    reported like any other scan problem."""
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "videos" / "a.mp4").write_text("x", encoding="utf-8")
    (project_dir / "attachments").mkdir()
    codebase = project_dir / "codebase"
    codebase.mkdir()

    real_scandir = os.scandir

    def fake_scandir(path):
        if str(path) == str(codebase):
            raise PermissionError(13, "Permission denied", str(path))
        return real_scandir(path)

    monkeypatch.setattr(filesystem_module.os, "scandir", fake_scandir)

    result = SourceScanService(project_dir, _config()).run()

    # Videos are unaffected -- only the codebase root itself is unreadable.
    assert result.manifest.videos == [(project_dir / "videos" / "a.mp4").resolve().as_posix()]
    assert result.manifest.codebase.present is False
    assert any(e.startswith("codebase: ") for e in result.manifest.scan_errors)


def test_scan_attachments_no_extension_filter(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "codebase").mkdir()
    attachments = project_dir / "attachments"
    attachments.mkdir()
    (attachments / "slides.pdf").write_text("x", encoding="utf-8")
    (attachments / "archive.zip").write_text("x", encoding="utf-8")

    result = SourceScanService(project_dir, _config()).run()
    assert len(result.manifest.attachments) == 2


def test_sources_yaml_always_regenerated_not_merged(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "attachments").mkdir()
    (project_dir / "codebase").mkdir()
    (project_dir / "sources.yaml").write_text("videos: ['stale-entry']\nunexpected_key: 1\n", encoding="utf-8")

    SourceScanService(project_dir, _config()).run()

    content = (project_dir / "sources.yaml").read_text(encoding="utf-8")
    assert "stale-entry" not in content
    assert "unexpected_key" not in content


def test_scan_errors_are_collected_and_prefixed_by_source(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "attachments").mkdir()
    codebase = project_dir / "codebase"
    codebase.mkdir()
    (codebase / "main.py").write_text("x", encoding="utf-8")

    real_walk = os.walk

    def fake_walk(top, **kwargs):
        onerror = kwargs.get("onerror")
        if onerror is not None and str(codebase) in str(top):
            onerror(OSError(13, "Permission denied", str(codebase / "blocked")))
        yield from real_walk(top, **kwargs)

    monkeypatch.setattr(filesystem_module.os, "walk", fake_walk)

    result = SourceScanService(project_dir, _config()).run()

    assert any(e.startswith("codebase: ") for e in result.manifest.scan_errors)
    assert result.manifest.codebase.files == [(codebase / "main.py").resolve().as_posix()]


def test_manifest_exclusions_reflect_effective_config(tmp_path):
    project_dir = tmp_path / "demo"
    (project_dir / "videos").mkdir(parents=True)
    (project_dir / "attachments").mkdir()
    (project_dir / "codebase").mkdir()

    result = SourceScanService(project_dir, _config()).run()

    assert "node_modules" in result.manifest.exclusions.directories
    assert ".DS_Store" in result.manifest.exclusions.file_patterns
