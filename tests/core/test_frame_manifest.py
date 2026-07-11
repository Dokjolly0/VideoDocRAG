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
        interval_seconds=8, scene_detection=True, keyword_boost=True, scene_threshold=0.1,
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


def test_manifest_without_settings_fields_loads_with_none_defaults(tmp_path):
    """Regression test: a frames.json written before the settings fields
    existed must still load (as 'settings unknown', not a corrupt
    manifest) -- FrameExtractionService treats None the same as 'always
    re-extract', which is the safe behavior for any pre-existing manifest."""
    path = tmp_path / "frames.json"
    raw = {
        "video_id": "demo",
        "frames": [
            {"id": "demo_frame_0001", "timestamp_seconds": 0.0, "image_path": "workdir/demo/frames/frame_0001.jpg", "perceptual_hash": "abc123"},
        ],
    }
    path.write_text(json.dumps(raw), encoding="utf-8")

    manifest = FrameManifest.load(path)
    assert manifest.interval_seconds is None
    assert manifest.scene_detection is None
    assert manifest.keyword_boost is None
    assert manifest.scene_threshold is None


def test_manifest_settings_fields_roundtrip(tmp_path):
    manifest = _manifest(interval_seconds=5, scene_detection=False, keyword_boost=True, scene_threshold=0.2)
    path = tmp_path / "frames.json"
    manifest.save(path)
    loaded = FrameManifest.load(path)
    assert loaded.interval_seconds == 5
    assert loaded.scene_detection is False
    assert loaded.keyword_boost is True
    assert loaded.scene_threshold == 0.2
