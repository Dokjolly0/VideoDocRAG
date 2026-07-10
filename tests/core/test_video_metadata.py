import json

import pytest

from videodoc.core.errors import InvalidVideoMetadataError
from videodoc.core.models.video_metadata import VideoMetadata


def _metadata(**overrides) -> VideoMetadata:
    defaults = dict(
        video_id="demo", video_name="Demo.mp4", title=None, duration_seconds=12.5,
        language="it", hash="abc123", format="mov,mp4", width=1920, height=1080, codec="h264",
        audio_path="workdir/demo/audio", transcript_path="workdir/demo/transcript",
        frames_path="workdir/demo/frames", ocr_path="workdir/demo/ocr", chunks_path="workdir/demo/chunks",
    )
    defaults.update(overrides)
    return VideoMetadata(**defaults)


def test_roundtrip(tmp_path):
    metadata = _metadata()
    path = tmp_path / "metadata.json"
    metadata.save(path)
    assert VideoMetadata.load(path) == metadata


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidVideoMetadataError):
        VideoMetadata.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "metadata.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidVideoMetadataError):
        VideoMetadata.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "metadata.json"
    metadata = _metadata()
    raw = metadata.model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidVideoMetadataError):
        VideoMetadata.load(path)
