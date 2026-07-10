import subprocess
from dataclasses import dataclass

import pytest

import videodoc.core.utils.ffprobe as ffprobe_module
from videodoc.core.utils.ffprobe import VideoProbeError, probe_video


@dataclass
class _FakeCompletedProcess:
    stdout: str


def _valid_json() -> str:
    return (
        '{"format": {"duration": "12.5", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"}, '
        '"streams": [{"codec_type": "audio", "codec_name": "aac"}, '
        '{"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264"}]}'
    )


def test_probe_video_parses_duration_format_resolution_codec(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ffprobe_module.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(stdout=_valid_json())
    )
    result = probe_video(tmp_path / "a.mp4")
    assert result.duration_seconds == 12.5
    assert result.format_name == "mov,mp4,m4a,3gp,3g2,mj2"
    assert result.width == 1920
    assert result.height == 1080
    assert result.codec_name == "h264"


def test_probe_video_raises_on_called_process_error(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["ffprobe"], stderr="bad file")

    monkeypatch.setattr(ffprobe_module.subprocess, "run", _raise)
    with pytest.raises(VideoProbeError):
        probe_video(tmp_path / "a.mp4")


def test_probe_video_raises_on_malformed_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ffprobe_module.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(stdout="not json"))
    with pytest.raises(VideoProbeError):
        probe_video(tmp_path / "a.mp4")


def test_probe_video_raises_when_no_video_stream(tmp_path, monkeypatch):
    audio_only = '{"format": {"duration": "1.0", "format_name": "wav"}, "streams": [{"codec_type": "audio"}]}'
    monkeypatch.setattr(ffprobe_module.subprocess, "run", lambda *a, **k: _FakeCompletedProcess(stdout=audio_only))
    with pytest.raises(VideoProbeError):
        probe_video(tmp_path / "a.mp4")
