import subprocess

import pytest

import videodoc.core.utils.scene_detection as scene_detection_module
from videodoc.core.utils.scene_detection import SceneDetectionError, detect_scene_timestamps


class _FakeProcess:
    def __init__(self, stdout_lines, stderr_lines=None, returncode=0):
        self.stdout = iter(stdout_lines)
        self.stderr = iter(stderr_lines or [])
        self._returncode = returncode

    def wait(self):
        return self._returncode


def test_detect_scene_timestamps_parses_pts_times_and_reports_progress(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")

    def fake_popen(args, **kwargs):
        return _FakeProcess([
            "frame:0 pts:50 pts_time:2\n",
            "lavfi.scene_score=0.42\n",
            "frame:1 pts:212 pts_time:8.5\n",
        ])

    monkeypatch.setattr(scene_detection_module.subprocess, "Popen", fake_popen)
    fractions = []

    assert detect_scene_timestamps(video, threshold=0.2, total_duration_seconds=10.0, progress_callback=fractions.append) == [2.0, 8.5]
    assert fractions == [0.2, 0.85]


def test_detect_scene_timestamps_empty_output_returns_empty(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(scene_detection_module.subprocess, "Popen", lambda *a, **k: _FakeProcess([]))

    assert detect_scene_timestamps(video) == []


def test_detect_scene_timestamps_wraps_nonzero_exit(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(
        scene_detection_module.subprocess,
        "Popen",
        lambda *a, **k: _FakeProcess([], ["unsupported codec\n"], returncode=1),
    )

    with pytest.raises(SceneDetectionError, match="unsupported codec"):
        detect_scene_timestamps(video)


def test_detect_scene_timestamps_wraps_oserror(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")

    def _raise(*args, **kwargs):
        raise OSError("binary not found")

    monkeypatch.setattr(scene_detection_module.subprocess, "Popen", _raise)
    with pytest.raises(SceneDetectionError, match="binary not found"):
        detect_scene_timestamps(video)


def test_detect_scene_timestamps_builds_cpu_args(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return _FakeProcess([])

    monkeypatch.setattr(scene_detection_module.subprocess, "Popen", fake_popen)
    detect_scene_timestamps(video, threshold=0.2, threads=4)

    args = captured["args"]
    assert args[args.index("-threads") + 1] == "4"
    assert args.index("-threads") < args.index("-i")
    vf = args[args.index("-vf") + 1]
    assert "scale=320:-2:flags=fast_bilinear" in vf
    assert "select=gt(scene\\,0.2)" in vf
    assert "metadata=print:file=-" in vf


def test_detect_scene_timestamps_builds_gpu_args(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        return _FakeProcess([])

    monkeypatch.setattr(scene_detection_module.subprocess, "Popen", fake_popen)
    detect_scene_timestamps(video, threshold=0.1, hwaccel="cuda", threads=4)

    args = captured["args"]
    assert args[args.index("-hwaccel") + 1] == "cuda"
    assert args[args.index("-hwaccel_output_format") + 1] == "cuda"
    assert "-threads" not in args
    vf = args[args.index("-vf") + 1]
    assert "scale_cuda=320:-2" in vf
    assert "hwdownload" in vf
    assert "format=nv12" in vf
    assert "select=gt(scene\\,0.1)" in vf


def test_detect_scene_timestamps_rejects_invalid_knobs(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(scene_detection_module.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")))

    with pytest.raises(ValueError):
        detect_scene_timestamps(video, threshold=0.0)
    with pytest.raises(ValueError):
        detect_scene_timestamps(video, hwaccel="auto")
    with pytest.raises(ValueError):
        detect_scene_timestamps(video, threads=0)