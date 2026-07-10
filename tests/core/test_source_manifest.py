from datetime import datetime, timezone

import pytest

from videodoc.core.errors import InvalidSourceManifestError
from videodoc.core.models.source_manifest import CodebaseManifest, ExclusionsManifest, SourceManifest


def test_roundtrip(tmp_path):
    manifest = SourceManifest(
        scanned_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        videos=["D:/proj/videos/a.mp4"],
        attachments=["D:/proj/attachments/slides.pdf"],
        codebase=CodebaseManifest(present=True, files=["D:/proj/codebase/main.py"]),
        exclusions=ExclusionsManifest(directories=["node_modules"], file_patterns=["*.min.js"]),
    )
    path = tmp_path / "sources.yaml"
    manifest.save(path)
    reloaded = SourceManifest.load(path)
    assert reloaded == manifest


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidSourceManifestError):
        SourceManifest.load(tmp_path / "does-not-exist.yaml")


def test_load_invalid_yaml_raises(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("videos: [unclosed", encoding="utf-8")
    with pytest.raises(InvalidSourceManifestError):
        SourceManifest.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("scanned_at: '2026-01-01T00:00:00+00:00'\nfoo: bar\n", encoding="utf-8")
    with pytest.raises(InvalidSourceManifestError):
        SourceManifest.load(path)


def test_load_missing_scanned_at_raises(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text("videos: []\n", encoding="utf-8")
    with pytest.raises(InvalidSourceManifestError):
        SourceManifest.load(path)
