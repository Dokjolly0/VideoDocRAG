import subprocess

import pytest

import videodoc.core.utils.ffmpeg as ffmpeg_module
from videodoc.core.utils.ffmpeg import AudioExtractionError, extract_audio


def test_extract_audio_invokes_ffmpeg_with_expected_args(tmp_path, monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    video = tmp_path / "a.mp4"
    output = tmp_path / "a.wav.tmp"
    extract_audio(video, output)

    args = captured["args"]
    assert args[0] == "ffmpeg"
    assert "-y" in args
    assert args[args.index("-i") + 1] == str(video)
    assert "-vn" in args
    assert args[args.index("-acodec") + 1] == "pcm_s16le"
    assert args[args.index("-ar") + 1] == "16000"
    assert args[args.index("-ac") + 1] == "1"
    assert args[args.index("-f") + 1] == "wav"
    assert args[-1] == str(output)


def test_extract_audio_raises_on_called_process_error(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["ffmpeg"], stderr="unsupported codec")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", _raise)
    with pytest.raises(AudioExtractionError):
        extract_audio(tmp_path / "a.mp4", tmp_path / "a.wav.tmp")


def test_extract_audio_raises_on_oserror(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("binary not found")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", _raise)
    with pytest.raises(AudioExtractionError):
        extract_audio(tmp_path / "a.mp4", tmp_path / "a.wav.tmp")
