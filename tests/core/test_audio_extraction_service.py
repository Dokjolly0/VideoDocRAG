import json
from pathlib import Path

import pytest

import videodoc.core.services.audio_extraction_service as audio_extraction_service_module
from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, ExternalToolNotFoundError, NoVideosFoundError
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.services.audio_extraction_service import AudioExtractionService
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video
from videodoc.core.storage.filesystem import ensure_video_workdir
from videodoc.core.utils.ffmpeg import AudioExtractionError


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _seed_video(project_dir, config, video_id="demo", filename="Demo.mp4", video_content=b"fake video"):
    """Reproduces exactly the on-disk/DB state VideoIngestionService leaves
    behind for one video, without invoking the full ingest pipeline (ffprobe
    isn't relevant to audio extraction) -- keeps these tests focused and fast."""
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)

    video_path = project_dir / "videos" / filename
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(video_content)

    upsert_video(
        db_path,
        VideoRow(
            id=video_id, filename=filename, title=None, duration_seconds=10.0,
            file_hash="hash123", path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )

    video_dir = project_dir / config.paths.workdir / video_id
    ensure_video_workdir(video_dir)
    workdir_rel = Path(config.paths.workdir) / video_id
    VideoMetadata(
        video_id=video_id, video_name=filename, title=None, duration_seconds=10.0,
        language="it", hash="hash123", format="mov,mp4", width=1280, height=720, codec="h264",
        audio_path=(workdir_rel / "audio").as_posix(),
        transcript_path=(workdir_rel / "transcript").as_posix(),
        frames_path=(workdir_rel / "frames").as_posix(),
        ocr_path=(workdir_rel / "ocr").as_posix(),
        chunks_path=(workdir_rel / "chunks").as_posix(),
    ).save(video_dir / "metadata.json")
    return video_path, video_dir


def _available_ffmpeg(monkeypatch):
    monkeypatch.setattr(audio_extraction_service_module.shutil, "which", lambda name: r"C:\fake\ffmpeg.exe")


def _stub_extract(monkeypatch, fn=None):
    def default(video_path, output_path, **kwargs):
        output_path.write_bytes(b"RIFF....WAVEfmt ")

    monkeypatch.setattr(audio_extraction_service_module, "extract_audio", fn or default)


def test_no_project_db_raises_and_creates_nothing(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(NoVideosFoundError):
        AudioExtractionService(project_dir, _config()).run()

    assert not (project_dir / "project.db").exists()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")

    with pytest.raises(NoVideosFoundError):
        AudioExtractionService(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()

    with pytest.raises(DatabaseError):
        AudioExtractionService(project_dir, _config()).run()


def test_missing_ffmpeg_raises_with_videos_present(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_video(project_dir, _config())
    monkeypatch.setattr(audio_extraction_service_module.shutil, "which", lambda name: None)

    with pytest.raises(ExternalToolNotFoundError):
        AudioExtractionService(project_dir, _config()).run()

    audio_dir = project_dir / "workdir" / "demo" / "audio"
    assert list(audio_dir.iterdir()) == []


def test_single_video_extracted_updates_metadata(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)
    _stub_extract(monkeypatch)

    result = AudioExtractionService(project_dir, config).run()

    assert result.extracted == ("demo",)
    assert result.skipped == ()
    assert result.errors == ()

    final_wav = video_dir / "audio" / "demo.wav"
    assert final_wav.is_file()
    assert not (video_dir / "audio" / "demo.wav.tmp").exists()

    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["audio_path"] == "workdir/demo/audio/demo.wav"


def test_skip_when_wav_exists_and_metadata_already_correct(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)

    call_count = {"n": 0}

    def counting_extract(video_path, output_path, **kwargs):
        call_count["n"] += 1
        output_path.write_bytes(b"RIFF")

    _stub_extract(monkeypatch, counting_extract)
    AudioExtractionService(project_dir, config).run()
    assert call_count["n"] == 1

    result = AudioExtractionService(project_dir, config).run()
    assert result.skipped == ("demo",)
    assert result.extracted == ()
    assert call_count["n"] == 1  # extract_audio never called again


def test_skip_reconciles_stale_metadata_placeholder(tmp_path, monkeypatch):
    """A .wav already exists (e.g. from a run of an earlier version of this
    tool) but metadata.json still holds ingest's folder-only placeholder --
    extraction must not re-run ffmpeg, but must still fix metadata.json."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    audio_dir = video_dir / "audio"
    (audio_dir / "demo.wav").write_bytes(b"RIFF already here")
    _available_ffmpeg(monkeypatch)

    call_count = {"n": 0}
    _stub_extract(monkeypatch, lambda video_path, output_path, **kwargs: call_count.__setitem__("n", call_count["n"] + 1))

    result = AudioExtractionService(project_dir, config).run()

    assert call_count["n"] == 0
    assert result.skipped == ("demo",)
    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["audio_path"] == "workdir/demo/audio/demo.wav"


def test_one_bad_video_does_not_block_others(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, video_id="bad", filename="Bad.mp4")
    _seed_video(project_dir, config, video_id="good", filename="Good.mp4")
    _available_ffmpeg(monkeypatch)

    def selective_extract(video_path, output_path, **kwargs):
        if video_path.name == "Bad.mp4":
            raise AudioExtractionError("unsupported codec")
        output_path.write_bytes(b"RIFF")

    _stub_extract(monkeypatch, selective_extract)
    result = AudioExtractionService(project_dir, config).run()

    assert result.extracted == ("good",)
    assert len(result.errors) == 1
    assert "bad" in result.errors[0]

    bad_audio_dir = project_dir / "workdir" / "bad" / "audio"
    assert not (bad_audio_dir / "bad.wav").exists()
    assert not (bad_audio_dir / "bad.wav.tmp").exists()


def test_partial_ffmpeg_failure_leaves_no_stray_wav(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)

    def partial_then_fail(video_path, output_path, **kwargs):
        output_path.write_bytes(b"RIFF partial")
        raise AudioExtractionError("ffmpeg killed mid-write")

    _stub_extract(monkeypatch, partial_then_fail)
    result = AudioExtractionService(project_dir, config).run()

    assert result.extracted == ()
    assert len(result.errors) == 1
    audio_dir = video_dir / "audio"
    assert not (audio_dir / "demo.wav").exists()
    assert not (audio_dir / "demo.wav.tmp").exists()


def test_missing_metadata_json_reported_as_error_wav_still_written(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    (video_dir / "metadata.json").unlink()
    _available_ffmpeg(monkeypatch)
    _stub_extract(monkeypatch)

    result = AudioExtractionService(project_dir, config).run()

    assert result.extracted == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]
    assert "metadata.json" in result.errors[0]
    assert (video_dir / "audio" / "demo.wav").is_file()


def test_corrupt_metadata_json_reported_as_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    (video_dir / "metadata.json").write_text("{not valid json", encoding="utf-8")
    _available_ffmpeg(monkeypatch)
    _stub_extract(monkeypatch)

    result = AudioExtractionService(project_dir, config).run()

    assert result.extracted == ()
    assert len(result.errors) == 1
    assert (video_dir / "audio" / "demo.wav").is_file()


def test_replace_failure_reports_error_and_cleans_tmp(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)
    _stub_extract(monkeypatch)

    real_replace = Path.replace

    def failing_replace(self, target):
        if self.name.endswith(".wav.tmp"):
            raise OSError("simulated replace failure")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    result = AudioExtractionService(project_dir, config).run()

    assert result.extracted == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]
    audio_dir = video_dir / "audio"
    assert not (audio_dir / "demo.wav").exists()
    assert not (audio_dir / "demo.wav.tmp").exists()


def test_skip_with_corrupt_metadata_reports_error(tmp_path, monkeypatch):
    """A .wav already exists but metadata.json is corrupt -- the video is
    neither 'extracted' (nothing was done this run) nor silently 'skipped'
    (the on-disk state is not fully correct); it must be reported."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    (video_dir / "audio" / "demo.wav").write_bytes(b"RIFF already here")
    (video_dir / "metadata.json").write_text("{not valid json", encoding="utf-8")
    _available_ffmpeg(monkeypatch)
    _stub_extract(monkeypatch)

    result = AudioExtractionService(project_dir, config).run()

    assert result.skipped == ()
    assert result.extracted == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]
    assert "metadata.json" in result.errors[0]


def test_metadata_save_failure_reported_as_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)
    _stub_extract(monkeypatch)

    def failing_save(self, path):
        raise OSError("simulated save failure")

    monkeypatch.setattr(VideoMetadata, "save", failing_save)

    result = AudioExtractionService(project_dir, config).run()

    assert result.extracted == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]
    assert (video_dir / "audio" / "demo.wav").is_file()
