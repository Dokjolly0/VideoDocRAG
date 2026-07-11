from typer.testing import CliRunner
from PIL import Image

import videodoc.core.services.frame_extraction_service as frame_extraction_service_module
import videodoc.core.services.ingest_service as ingest_service_module
from videodoc.cli.app import app
from videodoc.core.utils.ffmpeg import FrameExtractionError
from videodoc.core.utils.ffprobe import VideoProbeResult

runner = CliRunner()


def _ingest_one_video(tmp_path, name="demo"):
    custom = tmp_path / name
    runner.invoke(app, ["init", name, "--path", str(custom)])
    (custom / "videos" / "Demo.mp4").write_bytes(b"fake video")  # slugifies to video_id "demo"
    return custom


def _ingest_via_cli(monkeypatch, project_name):
    monkeypatch.setattr(ingest_service_module.shutil, "which", lambda tool: r"C:\fake\ffprobe.exe")
    monkeypatch.setattr(
        ingest_service_module, "probe_video",
        lambda path: VideoProbeResult(duration_seconds=20.0, format_name="mov,mp4", width=1280, height=720, codec_name="h264"),
    )
    result = runner.invoke(app, ["ingest", project_name])
    assert result.exit_code == 0


def _available_ffmpeg(monkeypatch):
    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda tool: r"C:\fake\ffmpeg.exe")


def _stub_extract_frames(monkeypatch, fn=None):
    def default(video_path, output_dir, timestamps, **kwargs):
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            Image.new("RGB", (16, 16), color=(100, 100, 100)).save(path)  # real JPEG: average_hash decodes it for real
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", fn or default)


def test_frames_success_prints_summary(tmp_path, monkeypatch):
    custom = _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    result = runner.invoke(app, ["frames", "demo", "--no-scene-detection", "--no-keyword-boost"])
    assert result.exit_code == 0
    assert "Extracted" in result.stdout
    extracted_line = next(line for line in result.stdout.splitlines() if "Extracted" in line)
    assert "1" in extracted_line
    assert (custom / "workdir" / "demo" / "frames" / "frames.json").is_file()


def test_frames_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["frames", "does-not-exist"])
    assert result.exit_code == 1


def test_frames_no_ingested_videos_fails(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])

    result = runner.invoke(app, ["frames", "demo"])
    assert result.exit_code == 1
    assert "ingest" in result.output.lower()


def test_frames_missing_ffmpeg_fails(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda tool: None)

    result = runner.invoke(app, ["frames", "demo", "--no-scene-detection", "--no-keyword-boost"])
    assert result.exit_code == 1
    assert "ffmpeg" in result.output.lower()


def test_frames_per_video_error_warns_without_failing(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _available_ffmpeg(monkeypatch)

    def failing_extract(video_path, output_dir, timestamps, **kwargs):
        raise FrameExtractionError("unsupported codec")

    _stub_extract_frames(monkeypatch, failing_extract)

    result = runner.invoke(app, ["frames", "demo", "--no-scene-detection", "--no-keyword-boost"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout


def test_frames_rerun_shows_all_skipped(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    runner.invoke(app, ["frames", "demo", "--no-scene-detection", "--no-keyword-boost"])
    result = runner.invoke(app, ["frames", "demo", "--no-scene-detection", "--no-keyword-boost"])
    assert result.exit_code == 0
    assert "Skipped" in result.stdout
    skipped_line = next(line for line in result.stdout.splitlines() if "Skipped" in line)
    assert "1" in skipped_line


def test_frames_accepts_interval_and_workers_flags(tmp_path, monkeypatch):
    custom = _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    result = runner.invoke(
        app, ["frames", "demo", "--no-scene-detection", "--no-keyword-boost", "--interval-seconds", "5", "--workers", "1", "--scene-threshold", "0.2", "--hwaccel", "none"],
    )
    assert result.exit_code == 0
    assert (custom / "workdir" / "demo" / "frames" / "frames.json").is_file()
