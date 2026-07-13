import json
import os

import pytest

import videodoc.core.services.ingest_service as ingest_service_module
from videodoc.core.config import ProjectConfig
from videodoc.core.errors import ExternalToolNotFoundError, NoVideosFoundError, VideoIdCollisionError
from videodoc.core.services.ingest_service import VideoIngestionService
from videodoc.core.storage.database import get_video
from videodoc.core.utils.ffprobe import VideoProbeError, VideoProbeResult


def _config(**paths_overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if paths_overrides:
        config = config.model_copy(update={"paths": config.paths.model_copy(update=paths_overrides)})
    return config


def _fake_probe_result() -> VideoProbeResult:
    return VideoProbeResult(duration_seconds=10.0, format_name="mov,mp4", width=1280, height=720, codec_name="h264")


def _make_video(project_dir, name: str, content: bytes = b"fake video content"):
    videos_dir = project_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    path = videos_dir / name
    path.write_bytes(content)
    return path


def _available_ffprobe(monkeypatch):
    monkeypatch.setattr(ingest_service_module.shutil, "which", lambda name: r"C:\fake\ffprobe.exe")


def _stub_probe(monkeypatch, fn=None):
    monkeypatch.setattr(ingest_service_module, "probe_video", fn or (lambda path: _fake_probe_result()))


def test_zero_videos_raises_and_creates_nothing(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "videos").mkdir()

    with pytest.raises(NoVideosFoundError):
        VideoIngestionService(project_dir, _config()).run()

    assert not (project_dir / "project.db").exists()
    assert not (project_dir / "workdir").exists()


def test_missing_ffprobe_raises_with_videos_present(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "a.mp4")
    monkeypatch.setattr(ingest_service_module.shutil, "which", lambda name: None)

    with pytest.raises(ExternalToolNotFoundError):
        VideoIngestionService(project_dir, _config()).run()

    assert not (project_dir / "project.db").exists()
    assert not (project_dir / "workdir").exists()


def test_single_video_ingested(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Demo.mp4")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    result = VideoIngestionService(project_dir, _config()).run()

    assert result.ingested == ("demo",)
    assert result.reingested == ()
    assert result.skipped == ()
    assert result.errors == ()

    row = get_video(result.database_path, "demo")
    assert row.filename == "Demo.mp4"
    assert row.duration_seconds == 10.0

    video_dir = project_dir / "workdir" / "demo"
    for sub in ("audio", "frames", "transcript", "ocr", "chunks"):
        assert (video_dir / sub).is_dir()
    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["video_id"] == "demo"
    assert metadata["width"] == 1280
    assert metadata["height"] == 720
    assert metadata["audio_path"] == "workdir/demo/audio"


def test_unchanged_video_is_skipped_without_rehashing_or_reprobing(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Demo.mp4")
    _available_ffprobe(monkeypatch)

    call_count = {"n": 0}

    def counting_probe(path):
        call_count["n"] += 1
        return _fake_probe_result()

    _stub_probe(monkeypatch, counting_probe)
    VideoIngestionService(project_dir, _config()).run()
    assert call_count["n"] == 1

    def fail_hash(path, **kwargs):
        raise AssertionError("unchanged rerun should use the fast fingerprint, not SHA-256")

    monkeypatch.setattr(ingest_service_module, "hash_file", fail_hash)

    # Second run, file unchanged: neither hash_file nor probe_video should be
    # called again -- the fast size+mtime+inode guard is enough.
    result = VideoIngestionService(project_dir, _config()).run()
    assert result.skipped == ("demo",)
    assert result.ingested == ()
    assert call_count["n"] == 1


def test_verify_rehashes_even_when_fast_fingerprint_matches(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Demo.mp4")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)
    VideoIngestionService(project_dir, _config()).run()

    real_hash_file = ingest_service_module.hash_file
    hash_count = {"n": 0}

    def counting_hash(path, **kwargs):
        hash_count["n"] += 1
        return real_hash_file(path, **kwargs)

    def fail_probe(path):
        raise AssertionError("verified unchanged content should still skip probing")

    monkeypatch.setattr(ingest_service_module, "hash_file", counting_hash)
    _stub_probe(monkeypatch, fail_probe)

    result = VideoIngestionService(project_dir, _config(), verify_hashes=True).run()

    assert result.skipped == ("demo",)
    assert result.reingested == ()
    assert hash_count["n"] == 1


def test_same_hash_after_fingerprint_change_skips_and_refreshes_fingerprint(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    video_path = _make_video(project_dir, "Demo.mp4", content=b"same bytes")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)
    result1 = VideoIngestionService(project_dir, _config()).run()
    first_fingerprint = get_video(result1.database_path, "demo").file_fingerprint

    stat = video_path.stat()
    os.utime(video_path, ns=(stat.st_atime_ns + 10_000_000_000, stat.st_mtime_ns + 10_000_000_000))

    real_hash_file = ingest_service_module.hash_file
    hash_count = {"n": 0}

    def counting_hash(path, **kwargs):
        hash_count["n"] += 1
        return real_hash_file(path, **kwargs)

    def fail_probe(path):
        raise AssertionError("same content with a new fingerprint should not be reprobed")

    monkeypatch.setattr(ingest_service_module, "hash_file", counting_hash)
    _stub_probe(monkeypatch, fail_probe)

    result2 = VideoIngestionService(project_dir, _config()).run()
    refreshed = get_video(result2.database_path, "demo").file_fingerprint

    assert result2.skipped == ("demo",)
    assert result2.reingested == ()
    assert hash_count["n"] == 1
    assert refreshed != first_fingerprint


def test_changed_video_is_reingested_and_warns_without_deleting_workdir(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Demo.mp4", content=b"version one")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)
    VideoIngestionService(project_dir, _config()).run()

    marker = project_dir / "workdir" / "demo" / "audio" / "keep-me.wav"
    marker.write_text("previous audio artifact", encoding="utf-8")

    _make_video(project_dir, "Demo.mp4", content=b"version two, changed content")
    result = VideoIngestionService(project_dir, _config()).run()

    assert result.reingested == ("demo",)
    assert result.ingested == ()
    assert len(result.warnings) == 1
    assert "demo" in result.warnings[0]
    assert marker.read_text(encoding="utf-8") == "previous audio artifact"  # never deleted


def test_one_bad_video_does_not_block_others(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Bad.mp4")
    _make_video(project_dir, "Good.mp4")
    _available_ffprobe(monkeypatch)

    def selective_probe(path):
        if path.name == "Bad.mp4":
            raise VideoProbeError("corrupt file")
        return _fake_probe_result()

    _stub_probe(monkeypatch, selective_probe)
    result = VideoIngestionService(project_dir, _config()).run()

    assert result.ingested == ("good",)
    assert len(result.errors) == 1
    assert "Bad.mp4" in result.errors[0]


def test_cross_run_id_collision_raises_and_does_not_overwrite(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Demo.mp4")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)
    result1 = VideoIngestionService(project_dir, _config()).run()
    assert result1.ingested == ("demo",)

    (project_dir / "videos" / "Demo.mp4").unlink()
    _make_video(project_dir, "demo!!!.mkv")

    with pytest.raises(VideoIdCollisionError):
        VideoIngestionService(project_dir, _config()).run()

    row = get_video(project_dir / "project.db", "demo")
    assert row.filename == "Demo.mp4"  # untouched by the colliding run


def test_same_run_id_collision_raises(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Demo.mp4")
    _make_video(project_dir, "demo!!!.mkv")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    with pytest.raises(VideoIdCollisionError):
        VideoIngestionService(project_dir, _config()).run()


def test_external_videos_path_ingests_with_absolute_row_path(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    external = tmp_path / "external-videos"
    external.mkdir()
    (external / "Demo.mp4").write_bytes(b"external content")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    result = VideoIngestionService(project_dir, _config(videos=str(external))).run()

    assert result.ingested == ("demo",)
    row = get_video(result.database_path, "demo")
    assert row.path == (external / "Demo.mp4").resolve().as_posix()


def test_missing_videos_path_raises_no_videos_found(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    missing = tmp_path / "does-not-exist"

    with pytest.raises(NoVideosFoundError):
        VideoIngestionService(project_dir, _config(videos=str(missing))).run()


def test_unslugifiable_video_name_reported_as_error_others_continue(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "!!!.mp4")
    _make_video(project_dir, "Good.mp4")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    result = VideoIngestionService(project_dir, _config()).run()

    assert result.ingested == ("good",)
    assert len(result.errors) == 1
    assert "!!!.mp4" in result.errors[0]


def test_hash_failure_reported_as_error_others_continue(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _make_video(project_dir, "Bad.mp4")
    _make_video(project_dir, "Good.mp4")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    real_hash_file = ingest_service_module.hash_file

    def selective_hash(path, **kwargs):
        if path.name == "Bad.mp4":
            raise OSError("simulated read failure")
        return real_hash_file(path, **kwargs)

    monkeypatch.setattr(ingest_service_module, "hash_file", selective_hash)

    result = VideoIngestionService(project_dir, _config()).run()

    assert result.ingested == ("good",)
    assert len(result.errors) == 1
    assert "Bad.mp4" in result.errors[0]

def test_same_run_collision_with_same_basename_in_different_folders_raises(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    first = project_dir / "videos" / "one" / "Demo.mp4"
    second = project_dir / "videos" / "two" / "Demo.mp4"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)

    with pytest.raises(VideoIdCollisionError):
        VideoIngestionService(project_dir, _config()).run()

    assert get_video(project_dir / "project.db", "demo") is None


def test_cross_run_collision_with_same_basename_different_folder_raises(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    first = project_dir / "videos" / "one" / "Demo.mp4"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"one")
    _available_ffprobe(monkeypatch)
    _stub_probe(monkeypatch)
    result1 = VideoIngestionService(project_dir, _config()).run()
    assert result1.ingested == ("demo",)

    first.unlink()
    second = project_dir / "videos" / "two" / "Demo.mp4"
    second.parent.mkdir(parents=True)
    second.write_bytes(b"two")

    with pytest.raises(VideoIdCollisionError):
        VideoIngestionService(project_dir, _config()).run()

    row = get_video(project_dir / "project.db", "demo")
    assert row.path == first.resolve().as_posix()
