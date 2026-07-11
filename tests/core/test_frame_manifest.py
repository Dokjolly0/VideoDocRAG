import json

import pytest

from videodoc.core.errors import InvalidFrameManifestError
from videodoc.core.models.frame_manifest import FrameManifest, FrameManifestEntry


def _manifest(**overrides) -> FrameManifest:
    defaults = dict(
        video_id="demo",
        frames=[
            FrameManifestEntry(id="demo_frame_0001", timestamp_seconds=0.0, image_path="workdir/demo/frames/frame_0001.jpg", perceptual_hash="abc123"),
            FrameManifestEntry(id="demo_frame_0002", timestamp_seconds=8.0, image_path="workdir/demo/frames/frame_0002.jpg", perceptual_hash=None),
        ],
    )
    defaults.update(overrides)
    return FrameManifest(**defaults)


def test_roundtrip(tmp_path):
    manifest = _manifest()
    path = tmp_path / "frames.json"
    manifest.save(path)
    assert FrameManifest.load(path) == manifest


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidFrameManifestError):
        FrameManifest.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "frames.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidFrameManifestError):
        FrameManifest.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "frames.json"
    raw = _manifest().model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidFrameManifestError):
        FrameManifest.load(path)


def test_empty_frames_list_roundtrips(tmp_path):
    manifest = FrameManifest(video_id="demo", frames=[])
    path = tmp_path / "frames.json"
    manifest.save(path)
    assert FrameManifest.load(path) == manifest
