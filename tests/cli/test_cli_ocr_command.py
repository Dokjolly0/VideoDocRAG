from typer.testing import CliRunner
from PIL import Image

import videodoc.core.services.frame_extraction_service as frame_extraction_service_module
import videodoc.core.services.ingest_service as ingest_service_module
import videodoc.core.services.ocr_service as ocr_service_module
from videodoc.cli.app import app
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


def _extract_frames_via_cli(monkeypatch, project_name):
    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda tool: r"C:\fake\ffmpeg.exe")

    def fake_extract(video_path, output_dir, timestamps, **kwargs):
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            Image.new("RGB", (16, 16), color=(100, 100, 100)).save(path)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", fake_extract)
    result = runner.invoke(app, ["frames", project_name, "--no-scene-detection", "--no-keyword-boost"])
    assert result.exit_code == 0


def _available_engine(monkeypatch, available=True):
    monkeypatch.setattr(ocr_service_module, "rapidocr_available", lambda: available)


def _stub_engine(monkeypatch, *, text="npm create vite@latest my-app", confidence=0.9):
    monkeypatch.setattr(ocr_service_module, "load_engine", lambda: object())
    monkeypatch.setattr(ocr_service_module, "run_ocr", lambda engine, image_path: (text, confidence))


def test_ocr_success_prints_summary(tmp_path, monkeypatch):
    custom = _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_frames_via_cli(monkeypatch, "demo")
    _available_engine(monkeypatch)
    _stub_engine(monkeypatch)

    result = runner.invoke(app, ["ocr", "demo"])
    assert result.exit_code == 0
    assert "Processed" in result.stdout
    processed_line = next(line for line in result.stdout.splitlines() if "Processed" in line)
    assert "1" in processed_line
    assert (custom / "workdir" / "demo" / "ocr" / "demo.json").is_file()


def test_ocr_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["ocr", "does-not-exist"])
    assert result.exit_code == 1


def test_ocr_no_ingested_videos_fails(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])

    result = runner.invoke(app, ["ocr", "demo"])
    assert result.exit_code == 1
    assert "ingest" in result.output.lower()


def test_ocr_engine_unavailable_fails(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_frames_via_cli(monkeypatch, "demo")
    _available_engine(monkeypatch, available=False)

    result = runner.invoke(app, ["ocr", "demo"])
    assert result.exit_code == 1
    assert "rapidocr" in result.output.lower()


def test_ocr_rerun_shows_all_skipped(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_frames_via_cli(monkeypatch, "demo")
    _available_engine(monkeypatch)
    _stub_engine(monkeypatch)

    runner.invoke(app, ["ocr", "demo"])
    result = runner.invoke(app, ["ocr", "demo"])
    assert result.exit_code == 0
    assert "Skipped" in result.stdout
    skipped_line = next(line for line in result.stdout.splitlines() if "Skipped" in line)
    assert "1" in skipped_line


def test_ocr_unsupported_engine_fails(tmp_path, monkeypatch):
    custom = _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_frames_via_cli(monkeypatch, "demo")
    _available_engine(monkeypatch, available=False)  # must not even be consulted

    config_path = custom / "config.yaml"
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("engine: rapidocr", "engine: paddleocr"), encoding="utf-8")

    result = runner.invoke(app, ["ocr", "demo"])
    assert result.exit_code == 1
    assert "paddleocr" in result.output.lower()


def test_ocr_accepts_workers_language_and_min_confidence_flags(tmp_path, monkeypatch):
    custom = _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_frames_via_cli(monkeypatch, "demo")
    _available_engine(monkeypatch)
    _stub_engine(monkeypatch)

    result = runner.invoke(
        app, ["ocr", "demo", "--workers", "1", "--language", "it", "--language", "en", "--min-confidence", "0.5"],
    )
    assert result.exit_code == 0
    assert (custom / "workdir" / "demo" / "ocr" / "demo.json").is_file()
