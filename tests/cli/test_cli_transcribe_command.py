from typer.testing import CliRunner

import videodoc.core.services.audio_extraction_service as audio_extraction_service_module
import videodoc.core.services.ingest_service as ingest_service_module
import videodoc.core.services.transcription_service as transcription_service_module
from videodoc.cli.app import app
from videodoc.core.utils.ffprobe import VideoProbeResult
from videodoc.core.utils.transcription import TranscriptSegmentResult, TranscriptionError

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
        lambda path: VideoProbeResult(duration_seconds=10.0, format_name="mov,mp4", width=1280, height=720, codec_name="h264"),
    )
    result = runner.invoke(app, ["ingest", project_name])
    assert result.exit_code == 0


def _extract_audio_via_cli(monkeypatch, project_name):
    monkeypatch.setattr(audio_extraction_service_module.shutil, "which", lambda tool: r"C:\fake\ffmpeg.exe")
    monkeypatch.setattr(
        audio_extraction_service_module, "extract_audio",
        lambda video_path, output_path: output_path.write_bytes(b"RIFF....WAVEfmt "),
    )
    result = runner.invoke(app, ["extract-audio", project_name])
    assert result.exit_code == 0


def _fake_results():
    return [TranscriptSegmentResult(start_seconds=0.0, end_seconds=2.0, text="Ciao a tutti", confidence=0.9)]


def _stub_transcription(monkeypatch, fn=None):
    monkeypatch.setattr(transcription_service_module, "load_whisper_model", lambda model_name: object())

    def default(model, audio_path, *, language, word_timestamps):
        return _fake_results()

    monkeypatch.setattr(transcription_service_module, "transcribe_audio", fn or default)


def test_transcribe_success_prints_summary(tmp_path, monkeypatch):
    custom = _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_audio_via_cli(monkeypatch, "demo")
    _stub_transcription(monkeypatch)

    result = runner.invoke(app, ["transcribe", "demo"])
    assert result.exit_code == 0
    assert "Transcribed: 1, skipped (already transcribed): 0" in result.stdout
    assert (custom / "workdir" / "demo" / "transcript" / "demo.json").is_file()


def test_transcribe_unknown_project_fails(tmp_path):
    result = runner.invoke(app, ["transcribe", "does-not-exist"])
    assert result.exit_code == 1


def test_transcribe_no_ingested_videos_fails(tmp_path):
    custom = tmp_path / "demo"
    runner.invoke(app, ["init", "demo", "--path", str(custom)])

    result = runner.invoke(app, ["transcribe", "demo"])
    assert result.exit_code == 1
    assert "ingest" in result.output.lower()


def test_transcribe_no_extracted_audio_fails(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")

    result = runner.invoke(app, ["transcribe", "demo"])
    assert result.exit_code == 1
    assert "extract-audio" in result.output.lower()


def test_transcribe_unsupported_engine_fails(tmp_path, monkeypatch):
    custom = _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_audio_via_cli(monkeypatch, "demo")

    config_path = custom / "config.yaml"
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("engine: faster-whisper", "engine: whisper.cpp"), encoding="utf-8")

    result = runner.invoke(app, ["transcribe", "demo"])
    assert result.exit_code == 1
    assert "engine" in result.output.lower()


def test_transcribe_per_video_error_warns_without_failing(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_audio_via_cli(monkeypatch, "demo")

    def failing_transcribe(model, audio_path, *, language, word_timestamps):
        raise TranscriptionError("corrupt audio")

    _stub_transcription(monkeypatch, failing_transcribe)

    result = runner.invoke(app, ["transcribe", "demo"])
    assert result.exit_code == 0
    assert "Warning" in result.stdout


def test_transcribe_rerun_shows_all_skipped(tmp_path, monkeypatch):
    _ingest_one_video(tmp_path)
    _ingest_via_cli(monkeypatch, "demo")
    _extract_audio_via_cli(monkeypatch, "demo")
    _stub_transcription(monkeypatch)

    runner.invoke(app, ["transcribe", "demo"])
    result = runner.invoke(app, ["transcribe", "demo"])
    assert result.exit_code == 0
    assert "Transcribed: 0, skipped (already transcribed): 1" in result.stdout
