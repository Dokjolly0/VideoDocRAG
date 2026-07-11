import io
import subprocess

import pytest

import videodoc.core.utils.ffmpeg as ffmpeg_module
from videodoc.core.utils.ffmpeg import AudioExtractionError, FrameExtractionError, extract_audio, extract_frames, ffmpeg_cuda_available


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


def _stub_ffmpeg_frame_run(output_dir, pts_values):
    """Fakes ffmpeg's real behavior for extract_frames: writes frame_NNNNN.jpg
    files (one per pts value, in order) and returns a CompletedProcess whose
    stderr contains matching 'pts_time:' showinfo lines."""

    def fake_run(args, **kwargs):
        for i, pts in enumerate(pts_values, start=1):
            (output_dir / f"frame_{i:05d}.jpg").write_bytes(b"\xff\xd8fake-jpeg")
        stderr = "\n".join(f"[Parsed_showinfo_1 @ 0x0] n:{i} pts_time:{pts}" for i, pts in enumerate(pts_values))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr=stderr)

    return fake_run


def test_extract_frames_empty_timestamps_skips_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(ffmpeg_module.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run ffmpeg")))
    assert extract_frames(tmp_path / "a.mp4", tmp_path, []) == []


def test_extract_frames_returns_pts_path_pairs_in_order(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    monkeypatch.setattr(ffmpeg_module.subprocess, "run", _stub_ffmpeg_frame_run(output_dir, [7.98, 16.02]))

    result = extract_frames(tmp_path / "a.mp4", output_dir, [8.0, 16.0])

    assert [pts for pts, _path in result] == [7.98, 16.02]
    assert [path.name for _pts, path in result] == ["frame_00001.jpg", "frame_00002.jpg"]


def test_extract_frames_builds_select_filter_script_and_cleans_it_up(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["filter_script_content"] = (output_dir / "select.filter").read_text(encoding="utf-8")
        (output_dir / "frame_00001.jpg").write_bytes(b"fake")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="pts_time:8.0")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)
    extract_frames(tmp_path / "a.mp4", output_dir, [8.0])

    assert "-filter_script:v" in captured["args"]
    assert "select=" in captured["filter_script_content"]
    assert "showinfo" in captured["filter_script_content"]
    assert not (output_dir / "select.filter").exists()  # cleaned up after the call


def test_extract_frames_raises_on_called_process_error(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def _raise(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["ffmpeg"], stderr="unsupported codec")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", _raise)
    with pytest.raises(FrameExtractionError):
        extract_frames(tmp_path / "a.mp4", output_dir, [8.0])


def test_extract_frames_raises_on_oserror(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def _raise(*args, **kwargs):
        raise OSError("binary not found")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", _raise)
    with pytest.raises(FrameExtractionError):
        extract_frames(tmp_path / "a.mp4", output_dir, [8.0])


def test_extract_frames_raises_on_pts_file_count_mismatch(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_run(args, **kwargs):
        (output_dir / "frame_00001.jpg").write_bytes(b"fake")
        (output_dir / "frame_00002.jpg").write_bytes(b"fake")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="pts_time:8.0")  # only one pts for two files

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)
    with pytest.raises(FrameExtractionError):
        extract_frames(tmp_path / "a.mp4", output_dir, [8.0, 16.0])


def test_extract_frames_passes_threads(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        (output_dir / "frame_00001.jpg").write_bytes(b"fake")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="pts_time:8.0")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)
    extract_frames(tmp_path / "a.mp4", output_dir, [8.0], threads=4)

    args = captured["args"]
    assert args[args.index("-threads") + 1] == "4"

def test_extract_frames_hwaccel_cuda_goes_before_input(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        (output_dir / "frame_00001.jpg").write_bytes(b"fake")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="pts_time:8.0")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)
    extract_frames(tmp_path / "a.mp4", output_dir, [8.0], hwaccel="cuda")

    args = captured["args"]
    assert args[args.index("-hwaccel") + 1] == "cuda"
    assert args.index("-hwaccel") < args.index("-i")


def test_extract_frames_default_omits_hwaccel(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        (output_dir / "frame_00001.jpg").write_bytes(b"fake")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="pts_time:8.0")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)
    extract_frames(tmp_path / "a.mp4", output_dir, [8.0])

    assert "-hwaccel" not in captured["args"]


def test_ffmpeg_cuda_available_true_when_ffmpeg_and_gpu_probe_succeed(monkeypatch):
    ffmpeg_cuda_available.cache_clear()

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="Hardware acceleration methods:\n cuda\n", stderr="")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)
    monkeypatch.setattr(ffmpeg_module, "probe_gpu", lambda: object())

    assert ffmpeg_cuda_available() is True
    ffmpeg_cuda_available.cache_clear()


def test_ffmpeg_cuda_available_false_without_cuda_hwaccel(monkeypatch):
    ffmpeg_cuda_available.cache_clear()
    monkeypatch.setattr(
        ffmpeg_module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="Hardware acceleration methods:\n d3d11va\n", stderr=""),
    )
    monkeypatch.setattr(ffmpeg_module, "probe_gpu", lambda: object())

    assert ffmpeg_cuda_available() is False
    ffmpeg_cuda_available.cache_clear()


def test_ffmpeg_cuda_available_false_when_probe_fails(monkeypatch):
    ffmpeg_cuda_available.cache_clear()
    monkeypatch.setattr(
        ffmpeg_module.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout="cuda\n", stderr=""),
    )
    monkeypatch.setattr(ffmpeg_module, "probe_gpu", lambda: None)

    assert ffmpeg_cuda_available() is False
    ffmpeg_cuda_available.cache_clear()


def test_ffmpeg_cuda_available_false_on_ffmpeg_error(monkeypatch):
    ffmpeg_cuda_available.cache_clear()

    def _raise(*args, **kwargs):
        raise OSError("ffmpeg missing")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", _raise)
    monkeypatch.setattr(ffmpeg_module, "probe_gpu", lambda: object())

    assert ffmpeg_cuda_available() is False
    ffmpeg_cuda_available.cache_clear()