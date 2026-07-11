from typer.testing import CliRunner

import videodoc.core.services.ingest_service as ingest_service_module
from videodoc.cli.app import app
from videodoc.core.utils.ffprobe import VideoProbeError, VideoProbeResult

runner = CliRunner()


def _fake_probe_result() -> VideoProbeResult:
    return VideoProbeResult(duration_seconds=10.0, format_name="mov,mp4", width=1280, height=720, codec_name="h264")


def _available_ffprobe(monkeypatch):
    monkeypatch.setattr(ingest_service_module.shutil, "which", lambda name: r"C:\fake\ffprobe.exe")


def _stub_probe(monkeypatch, fn=None):
    monkeypatch.setattr(ingest_service_module, "probe_video", fn or (lambda path: _fake_probe_result()))


def test_ingest_success_prints_summary(tmp_path, monkeypatch):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    (custom / "videos" / "a.mp4").write_bytes(b"fake video")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    result = runner.invoke(app, ["ingest", "demo"])
    assert result.exit_code == 0
    assert "Ingested" in result.stdout
    assert "Reingested" in result.stdout
    assert "Skipped" in result.stdout
    ingested_line = next(line for line in result.stdout.splitlines() if "Ingested" in line)
    assert "1" in ingested_line
    assert "Database updated: project.db" in result.stdout
    assert (custom / "project.db").is_file()


def test_ingest_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["ingest", "does-not-exist"])
    assert result.exit_code == 1


def test_ingest_zero_videos_fails(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])

    result = runner.invoke(app, ["ingest", "demo"])
    assert result.exit_code == 1
    assert "videos" in result.output.lower()


def test_ingest_missing_ffprobe_fails(tmp_path, monkeypatch):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    (custom / "videos" / "a.mp4").write_bytes(b"fake video")
    monkeypatch.setattr(ingest_service_module.shutil, "which", lambda name: None)

    result = runner.invoke(app, ["ingest", "demo"])
    assert result.exit_code == 1
    assert "ffprobe" in result.output.lower()


def test_ingest_per_video_error_warns_without_failing(tmp_path, monkeypatch):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    (custom / "videos" / "bad.mp4").write_bytes(b"fake video")
    _available_ffprobe(monkeypatch)

    def failing_probe(path):
        raise VideoProbeError("corrupt file")

    _stub_probe(monkeypatch, failing_probe)

    result = runner.invoke(app, ["ingest", "demo"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout
    assert "bad.mp4" in result.stdout


def test_ingest_reingest_prints_stale_artifact_warning(tmp_path, monkeypatch):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    video_path = custom / "videos" / "a.mp4"
    video_path.write_bytes(b"version one")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)
    runner.invoke(app, ["ingest", "demo"])

    video_path.write_bytes(b"version two, changed")
    result = runner.invoke(app, ["ingest", "demo"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout
    assert "reingested" in result.stdout.lower() or "changed" in result.stdout.lower()

def test_ingest_accepts_workers_flag(tmp_path, monkeypatch):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])
    (custom / "videos" / "a.mp4").write_bytes(b"fake video")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    result = runner.invoke(app, ["ingest", "demo", "--workers", "1"])
    assert result.exit_code == 0
    assert "Ingested" in result.stdout
