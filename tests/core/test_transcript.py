import json

import pytest

from videodoc.core.errors import InvalidTranscriptError
from videodoc.core.models.transcript import Transcript, TranscriptSegment


def _transcript(**overrides) -> Transcript:
    defaults = dict(
        video_id="demo", engine="faster-whisper", model="tiny", language="it",
        segments=[
            TranscriptSegment(id="demo_seg_0000", start_seconds=0.0, end_seconds=2.5, text="Ciao", confidence=0.9),
            TranscriptSegment(id="demo_seg_0001", start_seconds=2.5, end_seconds=5.0, text="a tutti", confidence=None),
        ],
    )
    defaults.update(overrides)
    return Transcript(**defaults)


def test_roundtrip(tmp_path):
    transcript = _transcript()
    path = tmp_path / "demo.json"
    transcript.save(path)
    assert Transcript.load(path) == transcript


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidTranscriptError):
        Transcript.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidTranscriptError):
        Transcript.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "demo.json"
    raw = _transcript().model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidTranscriptError):
        Transcript.load(path)
