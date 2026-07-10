import os

import pytest

import videodoc.core.storage.filesystem as filesystem_module
from videodoc.core.config import ScanSection
from videodoc.core.storage.filesystem import (
    DEFAULT_EXCLUDES,
    PROJECT_SUBDIRS,
    codebase_is_present,
    ensure_project_structure,
    ensure_sources_yaml,
    resolve_excludes,
    resolve_source_path,
    scan_attachments,
    scan_codebase,
    scan_videos,
    split_excludes,
)


def test_ensure_project_structure_creates_all_subdirs(tmp_path):
    project_dir = tmp_path / "demo"
    ensure_project_structure(project_dir)
    for sub in PROJECT_SUBDIRS:
        assert (project_dir / sub).is_dir()


def test_ensure_project_structure_is_idempotent_and_preserves_content(tmp_path):
    project_dir = tmp_path / "demo"
    ensure_project_structure(project_dir)
    marker = project_dir / "videos" / "keep-me.mp4"
    marker.write_text("fake video", encoding="utf-8")

    ensure_project_structure(project_dir)
    assert marker.read_text(encoding="utf-8") == "fake video"


def test_ensure_sources_yaml_creates_placeholder_once(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    path = ensure_sources_yaml(project_dir)
    assert path.exists()
    assert "scan" in path.read_text(encoding="utf-8")


def test_ensure_sources_yaml_does_not_overwrite_existing(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    path = project_dir / "sources.yaml"
    path.write_text("custom: content\n", encoding="utf-8")

    ensure_sources_yaml(project_dir)
    assert path.read_text(encoding="utf-8") == "custom: content\n"


def test_default_excludes_matches_readme():
    assert DEFAULT_EXCLUDES == (
        ".git/", ".hg/", ".svn/", "node_modules/", "__pycache__/", ".pytest_cache/",
        ".mypy_cache/", ".ruff_cache/", ".venv/", "venv/", "env/", "dist/", "build/",
        "out/", "target/", "coverage/", ".next/", ".nuxt/", ".cache/", ".parcel-cache/",
        ".turbo/", ".vite/", ".DS_Store",
    )
    assert len(DEFAULT_EXCLUDES) == 23


def test_resolve_excludes_default_only():
    excludes = resolve_excludes(ScanSection())
    assert excludes == set(DEFAULT_EXCLUDES)


def test_resolve_excludes_disabled():
    excludes = resolve_excludes(ScanSection(default_excludes=False))
    assert excludes == set()


def test_resolve_excludes_add_and_remove_merge():
    # Replicates the README §8.3 example: tmp/, logs/, *.min.js added; dist/ removed.
    scan = ScanSection(add_excludes=["tmp/", "logs/", "*.min.js"], remove_excludes=["dist/"])
    excludes = resolve_excludes(scan)
    assert "tmp/" in excludes
    assert "logs/" in excludes
    assert "*.min.js" in excludes
    assert "dist/" not in excludes


def test_split_excludes_separates_dirs_from_file_patterns():
    dirs, patterns = split_excludes({"node_modules/", "dist/", ".DS_Store", "*.min.js"})
    assert dirs == {"node_modules", "dist"}
    assert patterns == {".DS_Store", "*.min.js"}


def test_resolve_source_path_relative_goes_under_project_dir(tmp_path):
    resolved = resolve_source_path(tmp_path, "videos")
    assert resolved == (tmp_path / "videos").resolve()


def test_resolve_source_path_absolute_used_directly(tmp_path):
    external = tmp_path / "external-videos"
    resolved = resolve_source_path(tmp_path / "project", str(external))
    assert resolved == external.resolve()


def test_resolve_source_path_missing_absolute_does_not_raise(tmp_path):
    missing = tmp_path / "does-not-exist"
    resolved = resolve_source_path(tmp_path / "project", str(missing))
    assert resolved == missing.resolve()


def test_scan_codebase_collects_walk_errors_without_crashing(tmp_path, monkeypatch):
    """os.walk() silently skips a subdirectory it can't scandir() into (e.g.
    permission denied) unless given an onerror callback. Verifies the walker
    wires one up: real errors are collected, not silently dropped, and the
    scan still returns whatever it *could* find instead of crashing."""
    codebase = tmp_path / "codebase"
    codebase.mkdir()
    (codebase / "ok.py").write_text("x", encoding="utf-8")

    real_walk = os.walk
    blocked_path = str(codebase / "blocked")

    def fake_walk(top, **kwargs):
        onerror = kwargs.get("onerror")
        if onerror is not None:
            exc = OSError(13, "Permission denied", blocked_path)
            onerror(exc)
        yield from real_walk(top, **kwargs)

    monkeypatch.setattr(filesystem_module.os, "walk", fake_walk)

    errors: list[str] = []
    result = scan_codebase(codebase, ScanSection(), errors)

    assert result == [codebase / "ok.py"]
    assert len(errors) == 1
    assert "blocked" in errors[0]


def test_scan_codebase_prunes_node_modules(tmp_path):
    codebase = tmp_path / "codebase"
    (codebase / "node_modules" / "pkg").mkdir(parents=True)
    (codebase / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
    (codebase / "src").mkdir()
    (codebase / "src" / "app.py").write_text("x", encoding="utf-8")

    result = scan_codebase(codebase, ScanSection())
    assert result == [codebase / "src" / "app.py"]


def test_scan_codebase_respects_max_file_size_mb(tmp_path):
    codebase = tmp_path / "codebase"
    codebase.mkdir()
    small = codebase / "small.py"
    small.write_bytes(b"x" * 100)
    large = codebase / "large.py"
    large.write_bytes(b"x" * (2 * 1024 * 1024))

    result = scan_codebase(codebase, ScanSection(max_file_size_mb=1))
    assert result == [small]


def test_scan_codebase_respects_allowed_extensions(tmp_path):
    codebase = tmp_path / "codebase"
    codebase.mkdir()
    (codebase / "app.py").write_text("x", encoding="utf-8")
    (codebase / "app.rb").write_text("x", encoding="utf-8")

    result = scan_codebase(codebase, ScanSection(allowed_code_extensions=[".py"]))
    assert result == [codebase / "app.py"]


def test_scan_codebase_add_excludes_glob_pattern(tmp_path):
    codebase = tmp_path / "codebase"
    codebase.mkdir()
    (codebase / "app.js").write_text("x", encoding="utf-8")
    (codebase / "app.min.js").write_text("x", encoding="utf-8")

    result = scan_codebase(codebase, ScanSection(add_excludes=["*.min.js"]))
    assert result == [codebase / "app.js"]


def test_scan_codebase_remove_excludes_reincludes_dist(tmp_path):
    codebase = tmp_path / "codebase"
    (codebase / "dist").mkdir(parents=True)
    (codebase / "dist" / "bundle.py").write_text("x", encoding="utf-8")

    result = scan_codebase(codebase, ScanSection(remove_excludes=["dist/"]))
    assert result == [codebase / "dist" / "bundle.py"]


def test_scan_videos_filters_by_extension(tmp_path):
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "a.mp4").write_text("x", encoding="utf-8")
    (videos / "b.txt").write_text("x", encoding="utf-8")
    (videos / "c.mkv").write_text("x", encoding="utf-8")

    result = scan_videos(videos, ScanSection())
    assert result == [videos / "a.mp4", videos / "c.mkv"]


def test_scan_videos_case_insensitive_extension(tmp_path):
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "WORKSHOP.MP4").write_text("x", encoding="utf-8")

    result = scan_videos(videos, ScanSection())
    assert result == [videos / "WORKSHOP.MP4"]


def test_scan_videos_respects_custom_allowed_extensions(tmp_path):
    videos = tmp_path / "videos"
    videos.mkdir()
    (videos / "a.mp4").write_text("x", encoding="utf-8")
    (videos / "b.mkv").write_text("x", encoding="utf-8")

    result = scan_videos(videos, ScanSection(allowed_video_extensions=[".mp4"]))
    assert result == [videos / "a.mp4"]


def test_scan_attachments_no_extension_filter(tmp_path):
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    (attachments / "slides.pdf").write_text("x", encoding="utf-8")
    (attachments / "archive.zip").write_text("x", encoding="utf-8")
    (attachments / "noext").write_text("x", encoding="utf-8")

    result = scan_attachments(attachments, ScanSection())
    assert result == [attachments / "archive.zip", attachments / "noext", attachments / "slides.pdf"]


def test_codebase_is_present_false_for_empty_dir(tmp_path):
    codebase = tmp_path / "codebase"
    codebase.mkdir()
    assert codebase_is_present(codebase) is False


def test_codebase_is_present_false_for_nonexistent_dir(tmp_path):
    assert codebase_is_present(tmp_path / "does-not-exist") is False


def test_codebase_is_present_true_even_if_all_content_excluded(tmp_path):
    codebase = tmp_path / "codebase"
    (codebase / "node_modules" / "pkg").mkdir(parents=True)
    (codebase / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")

    assert codebase_is_present(codebase) is True
    assert scan_codebase(codebase, ScanSection()) == []


def test_codebase_is_present_handles_unreadable_directory_without_crashing(tmp_path, monkeypatch):
    """root.is_dir() can succeed (it's a directory by type) while
    os.scandir(root) still raises (e.g. permission denied on an external
    location) -- codebase_is_present must not propagate that, and must
    record it instead of silently returning a plain False."""
    codebase = tmp_path / "codebase"
    codebase.mkdir()

    def fake_scandir(path):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(filesystem_module.os, "scandir", fake_scandir)

    errors: list[str] = []
    assert codebase_is_present(codebase, errors) is False
    assert len(errors) == 1
    assert "Permission denied" in errors[0]


def _make_symlink(link_path, target_path, target_is_directory: bool) -> None:
    try:
        os.symlink(target_path, link_path, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this machine (requires elevation or Developer Mode)")


def test_follow_symlinks_true_follows_symlinked_directory(tmp_path):
    real_dir = tmp_path / "real-codebase"
    real_dir.mkdir()
    (real_dir / "app.py").write_text("x", encoding="utf-8")

    codebase = tmp_path / "codebase"
    codebase.mkdir()
    _make_symlink(codebase / "linked", real_dir, target_is_directory=True)

    result = scan_codebase(codebase, ScanSection(follow_symlinks=True))
    assert result == [codebase / "linked" / "app.py"]


def test_follow_symlinks_false_skips_symlinked_directory(tmp_path):
    real_dir = tmp_path / "real-codebase"
    real_dir.mkdir()
    (real_dir / "app.py").write_text("x", encoding="utf-8")

    codebase = tmp_path / "codebase"
    codebase.mkdir()
    _make_symlink(codebase / "linked", real_dir, target_is_directory=True)

    result = scan_codebase(codebase, ScanSection(follow_symlinks=False))
    assert result == []


def test_scan_codebase_skips_broken_symlink_without_crashing(tmp_path):
    codebase = tmp_path / "codebase"
    codebase.mkdir()
    broken_target = tmp_path / "target-that-will-be-removed.py"
    broken_target.write_text("x", encoding="utf-8")
    link = codebase / "broken.py"
    _make_symlink(link, broken_target, target_is_directory=False)
    broken_target.unlink()  # the symlink now points nowhere -> p.stat() raises OSError

    result = scan_codebase(codebase, ScanSection(follow_symlinks=True))
    assert result == []


def test_follow_symlinks_false_skips_symlinked_file(tmp_path):
    real_file = tmp_path / "real.py"
    real_file.write_text("x", encoding="utf-8")

    codebase = tmp_path / "codebase"
    codebase.mkdir()
    _make_symlink(codebase / "linked.py", real_file, target_is_directory=False)

    result = scan_codebase(codebase, ScanSection(follow_symlinks=False))
    assert result == []
