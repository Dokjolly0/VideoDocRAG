import io
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


def test_extract_audio_without_duration_ignores_progress_callback_and_uses_run(tmp_path, monkeypatch):
    """progress_callback alone (no total_duration_seconds) has nothing
    meaningful to report a fraction against -- extract_audio must fall back
    to the plain blocking subprocess.run path, never touch Popen."""
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)
    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Popen should not be used")))

    extract_audio(tmp_path / "a.mp4", tmp_path / "a.wav.tmp", progress_callback=lambda f: None)

    assert "args" in captured


class _FakeProgressProcess:
    def __init__(self, args, stdout_lines, returncode=0, stderr_text=""):
        self.args = args
        self.stdout = iter(stdout_lines)
        self.stderr = io.StringIO(stderr_text)
        self._returncode = returncode

    def wait(self):
        return self._returncode


def test_extract_audio_with_progress_streams_increasing_fractions(tmp_path, monkeypatch):
    captured = {}
    lines = ["out_time_ms=1000000\n", "out_time_ms=5000000\n", "progress=end\n"]

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return _FakeProgressProcess(args, lines)

    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", fake_popen)

    fractions = []
    extract_audio(
        tmp_path / "a.mp4", tmp_path / "a.wav.tmp",
        total_duration_seconds=10.0,
        progress_callback=fractions.append,
    )

    assert fractions == [0.1, 0.5]
    assert "-progress" in captured["args"]
    assert "pipe:1" in captured["args"]


def test_extract_audio_with_progress_raises_on_nonzero_exit(tmp_path, monkeypatch):
    def fake_popen(args, **kwargs):
        return _FakeProgressProcess(args, ["out_time_ms=1000000\n"], returncode=1, stderr_text="unsupported codec")

    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", fake_popen)

    with pytest.raises(AudioExtractionError, match="unsupported codec"):
        extract_audio(
            tmp_path / "a.mp4", tmp_path / "a.wav.tmp",
            total_duration_seconds=10.0,
            progress_callback=lambda f: None,
        )


def test_extract_audio_with_progress_raises_on_oserror(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise OSError("binary not found")

    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", _raise)
    with pytest.raises(AudioExtractionError):
        extract_audio(
            tmp_path / "a.mp4", tmp_path / "a.wav.tmp",
            total_duration_seconds=10.0,
            progress_callback=lambda f: None,
        )

def test_extract_audio_passes_threads_to_ffmpeg_run(tmp_path, monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    extract_audio(tmp_path / "a.mp4", tmp_path / "a.wav.tmp", threads=3)

    args = captured["args"]
    assert args[args.index("-threads") + 1] == "3"


def test_extract_audio_with_progress_passes_threads_to_ffmpeg_popen(tmp_path, monkeypatch):
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return _FakeProgressProcess(args, ["progress=end\n"])

    monkeypatch.setattr(ffmpeg_module.subprocess, "Popen", fake_popen)

    extract_audio(
        tmp_path / "a.mp4", tmp_path / "a.wav.tmp",
        total_duration_seconds=10.0,
        progress_callback=lambda f: None,
        threads=2,
    )

    args = captured["args"]
    assert args[args.index("-threads") + 1] == "2"
