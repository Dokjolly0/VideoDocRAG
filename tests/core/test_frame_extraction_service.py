import contextlib
import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

import videodoc.core.services.frame_extraction_service as frame_extraction_service_module
from videodoc.core.config import ProjectConfig
from videodoc.core.errors import (
    DatabaseError,
    ExternalToolNotFoundError,
    NoVideosFoundError,
)
from videodoc.core.models.frame_manifest import FrameManifest
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.services.frame_extraction_service import FrameExtractionService
from videodoc.core.storage.database import (
    FrameOcrUpdate,
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    list_frames,
    replace_transcript_segments,
    update_frame_ocr,
    upsert_video,
)
from videodoc.core.storage.filesystem import ensure_video_workdir
from videodoc.core.utils.ffmpeg import FrameExtractionError
from videodoc.core.utils.scene_detection import SceneDetectionError


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _seed_video(project_dir, config, video_id="demo", filename="Demo.mp4", duration_seconds=20.0):
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)

    video_path = project_dir / "videos" / filename
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake video")

    upsert_video(
        db_path,
        VideoRow(
            id=video_id, filename=filename, title=None, duration_seconds=duration_seconds,
            file_hash="hash123", path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )

    video_dir = project_dir / config.paths.workdir / video_id
    ensure_video_workdir(video_dir)
    workdir_rel = Path(config.paths.workdir) / video_id
    VideoMetadata(
        video_id=video_id, video_name=filename, title=None, duration_seconds=duration_seconds,
        language="it", hash="hash123", format="mov,mp4", width=1280, height=720, codec="h264",
        audio_path=(workdir_rel / "audio").as_posix(),
        transcript_path=(workdir_rel / "transcript").as_posix(),
        frames_path=(workdir_rel / "frames").as_posix(),
        ocr_path=(workdir_rel / "ocr").as_posix(),
        chunks_path=(workdir_rel / "chunks").as_posix(),
    ).save(video_dir / "metadata.json")
    return video_path, video_dir


def _available_ffmpeg(monkeypatch):
    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda name: r"C:\fake\ffmpeg.exe")


def _write_pattern_jpeg(path, variant):
    """A 16x16 half-split image (see tests/core/test_frame_hash.py for why a
    flat single color can't be used here: every flat-color image hashes
    identically regardless of its actual color, since aHash thresholds each
    pixel against its own image's mean). variant 0 -> vertical split, any
    other variant -> horizontal split -- two genuinely different average
    hashes, real enough for the service's real (non-stubbed) hash-dedup
    pass to tell apart."""
    img = Image.new("L", (16, 16), color=0)
    if variant == 0:
        for x in range(8, 16):
            for y in range(16):
                img.putpixel((x, y), 255)
    else:
        for x in range(16):
            for y in range(8, 16):
                img.putpixel((x, y), 255)
    img.convert("RGB").save(path)


def _stub_extract_frames(monkeypatch, variant_for_timestamp=None):
    """Fake extract_frames: writes one small real JPEG per requested
    timestamp (so the service's real hash-dedup pass has something genuine
    to hash) and returns (pts, path) pairs using the requested timestamp as
    the pts (i.e. an idealized ffmpeg that always lands exactly on target).

    Defaults every frame to the same pattern variant: harmless when no
    boosted (scene/keyword) candidates exist in a test (interval frames are
    never dropped by hash-dedup regardless of their hash), and exactly the
    "near-duplicate" setup test_hash_dedup_drops_near_duplicate_boosted_frame
    wants when a boosted candidate *is* present."""
    variant_for_timestamp = variant_for_timestamp or (lambda t: 0)

    def fake(video_path, output_dir, timestamps, **kwargs):
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, variant_for_timestamp(t))
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", fake)


def _no_boost_service(project_dir, config, **kwargs):
    """Most tests don't care about scene detection or keyword boost --
    disabling both up front keeps them focused on the extraction/idempotency
    machinery being tested, without needing a scene-detection stub or transcript
    segments."""
    return FrameExtractionService(
        project_dir, config, scene_detection_override=False, keyword_boost_override=False, **kwargs
    )


def test_no_project_db_raises_and_creates_nothing(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(NoVideosFoundError):
        _no_boost_service(project_dir, _config()).run()

    assert not (project_dir / "project.db").exists()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")

    with pytest.raises(NoVideosFoundError):
        _no_boost_service(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()

    with pytest.raises(DatabaseError):
        _no_boost_service(project_dir, _config()).run()


def test_missing_ffmpeg_raises_with_videos_present(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_video(project_dir, _config())
    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda name: None)

    with pytest.raises(ExternalToolNotFoundError):
        _no_boost_service(project_dir, _config()).run()


def test_scene_detection_disabled_skips_detector(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_video(project_dir, _config())
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)
    monkeypatch.setattr(
        frame_extraction_service_module,
        "detect_scene_timestamps",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not be called when scene_detection is disabled")),
    )

    result = _no_boost_service(project_dir, _config()).run()
    assert result.extracted == ("demo",)
def test_single_video_extracted_writes_manifest_db_and_metadata(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    result = _no_boost_service(project_dir, config, interval_seconds_override=8).run()

    assert result.extracted == ("demo",)
    assert result.skipped == ()
    assert result.errors == ()

    manifest_path = video_dir / "frames" / "frames.json"
    assert manifest_path.is_file()
    manifest = FrameManifest.load(manifest_path)
    assert manifest.video_id == "demo"
    assert [f.timestamp_seconds for f in manifest.frames] == [0.0, 8.0, 16.0]
    assert not (video_dir / "frames" / ".staging").exists()

    for entry in manifest.frames:
        assert (project_dir / entry.image_path).is_file()

    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["frames_path"] == "workdir/demo/frames"


def test_skip_when_manifest_exists_self_heals_db(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)

    call_count = {"n": 0}

    def fake(video_path, output_dir, timestamps, **kwargs):
        call_count["n"] += 1
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", fake)
    _no_boost_service(project_dir, config).run()
    assert call_count["n"] == 1

    result = _no_boost_service(project_dir, config).run()
    assert result.skipped == ("demo",)
    assert result.extracted == ()
    assert call_count["n"] == 1  # extract_frames never called again


def test_skip_when_manifest_exists_preserves_ocr_and_code_columns(tmp_path, monkeypatch):
    """Regression test: a plain idempotent 'videodoc frames' rerun (settings
    unchanged, self-heal path only) must never wipe ocr_text/ocr_confidence/
    contains_code -- those belong to OCRService (README §19) and the
    §20 code-detection phase, not to this one, and frames.json itself never
    carries them at all. Rebuilding DB rows from the manifest alone would
    otherwise silently clobber annotations a later phase already wrote for
    these exact same frame ids."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    _no_boost_service(project_dir, config).run()

    db_path = project_dir / config.paths.database
    frame_id = list_frames(db_path, "demo")[0].id
    update_frame_ocr(db_path, "demo", [FrameOcrUpdate(frame_id=frame_id, ocr_text="npm install", ocr_confidence=0.95)])
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE frames SET contains_code = 1 WHERE id = ?", (frame_id,))

    result = _no_boost_service(project_dir, config).run()
    assert result.skipped == ("demo",)

    refreshed = {f.id: f for f in list_frames(db_path, "demo")}
    assert refreshed[frame_id].ocr_text == "npm install"
    assert refreshed[frame_id].ocr_confidence == 0.95
    assert refreshed[frame_id].contains_code is True


def test_one_bad_video_does_not_block_others(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, video_id="bad", filename="Bad.mp4")
    _seed_video(project_dir, config, video_id="good", filename="Good.mp4")
    _available_ffmpeg(monkeypatch)

    def selective(video_path, output_dir, timestamps, **kwargs):
        if video_path.name == "Bad.mp4":
            raise FrameExtractionError("unsupported codec")
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", selective)

    result = _no_boost_service(project_dir, config).run()

    assert result.extracted == ("good",)
    assert len(result.errors) == 1
    assert "bad" in result.errors[0]


def test_scene_detection_failure_folds_into_per_video_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    def failing_detect(video_path, **kwargs):
        raise SceneDetectionError("corrupt video")

    monkeypatch.setattr(frame_extraction_service_module, "detect_scene_timestamps", failing_detect)

    result = FrameExtractionService(project_dir, config, keyword_boost_override=False).run()

    assert result.extracted == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]


def test_keyword_boost_without_transcript_is_not_an_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    result = FrameExtractionService(project_dir, config, scene_detection_override=False).run()

    assert result.errors == ()
    assert result.extracted == ("demo",)


def test_keyword_boost_adds_frame_from_transcript_segment(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config, duration_seconds=100.0)
    db_path = project_dir / config.paths.database
    replace_transcript_segments(
        db_path, "demo",
        [TranscriptSegmentRow(id="demo_seg_0000", video_id="demo", start_seconds=50.0, end_seconds=52.0, text="ora apriamo il terminale", confidence=0.9)],
    )
    _available_ffmpeg(monkeypatch)
    # The keyword-boosted frame at 51.0 must look visually distinct from its
    # neighboring interval frames, or the (real, not stubbed) hash-dedup
    # pass would legitimately drop it as a near-duplicate -- that dedup
    # behavior itself is covered separately by
    # test_hash_dedup_drops_near_duplicate_boosted_frame.
    _stub_extract_frames(monkeypatch, variant_for_timestamp=lambda t: 1 if abs(t - 51.0) < 0.01 else 0)

    result = FrameExtractionService(
        project_dir, config, scene_detection_override=False, interval_seconds_override=8,
    ).run()

    assert result.extracted == ("demo",)
    manifest = FrameManifest.load(video_dir / "frames" / "frames.json")
    assert 51.0 in [f.timestamp_seconds for f in manifest.frames]  # midpoint of the matching segment


def test_hash_dedup_drops_near_duplicate_boosted_frame(tmp_path, monkeypatch):
    """A keyword-boosted candidate that is visually a near-duplicate of the
    immediately preceding kept frame must be dropped by the real hash-dedup
    pass, not persisted as a redundant row -- even when it is far enough
    from any interval tick (>= MIN_FRAME_GAP_SECONDS) to survive candidate
    merging on its own, so this exercises the hash pass specifically, not
    the separate min-gap candidate merge."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config, duration_seconds=20.0)
    db_path = project_dir / config.paths.database
    # Segment midpoint at 11.0s: 3s from the interval tick at 8s and 5s from
    # the one at 16s, both >= MIN_FRAME_GAP_SECONDS (2.0), so it survives
    # candidate merging as its own entry; only the hash pass (identical
    # pattern variant -> identical frame) can then drop it.
    replace_transcript_segments(
        db_path, "demo",
        [TranscriptSegmentRow(id="demo_seg_0000", video_id="demo", start_seconds=10.5, end_seconds=11.5, text="il comando qui", confidence=0.9)],
    )
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)  # default: every frame uses the same pattern variant

    result = FrameExtractionService(
        project_dir, config, scene_detection_override=False, interval_seconds_override=8,
    ).run()

    assert result.extracted == ("demo",)
    manifest = FrameManifest.load(video_dir / "frames" / "frames.json")
    # Without dedup this would be 4 (0, 8, 11.0, 16); the near-duplicate
    # keyword frame at 11.0 must have been dropped.
    assert [f.timestamp_seconds for f in manifest.frames] == [0.0, 8.0, 16.0]


def test_missing_ffmpeg_does_not_raise_when_every_video_is_already_self_healable(tmp_path, monkeypatch):
    """Regression test: a fully processed project must be able to re-run
    'videodoc frames' to self-heal DB/metadata even on a machine that no
    longer has ffmpeg installed, as long as every video's frames.json
    already matches the current run's settings -- ffmpeg must only be
    required when at least one video actually needs fresh extraction."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    service = _no_boost_service(project_dir, config, interval_seconds_override=8)
    first = service.run()
    assert first.extracted == ("demo",)

    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda name: None)  # ffmpeg now "missing"
    second = _no_boost_service(project_dir, config, interval_seconds_override=8).run()
    assert second.skipped == ("demo",)
    assert second.errors == ()


def test_ffmpeg_not_required_when_scene_enabled_and_every_video_is_already_self_healable(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)
    monkeypatch.setattr(frame_extraction_service_module, "detect_scene_timestamps", lambda video_path, **kwargs: [])

    first = FrameExtractionService(project_dir, config, keyword_boost_override=False, interval_seconds_override=8).run()
    assert first.extracted == ("demo",)

    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda name: None)
    second = FrameExtractionService(project_dir, config, keyword_boost_override=False, interval_seconds_override=8).run()
    assert second.skipped == ("demo",)
    assert second.errors == ()
def test_rerun_with_different_interval_reextracts_instead_of_silently_skipping(tmp_path, monkeypatch):
    """Regression test: a frames.json produced under one set of settings
    must not be silently treated as 'done' when the user asks for
    different settings on a rerun -- the previous behavior (skip whenever
    frames.json merely exists) would make --interval-seconds/
    --no-scene-detection/--no-keyword-boost on a rerun a silent no-op."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    first = _no_boost_service(project_dir, config, interval_seconds_override=5).run()
    assert first.extracted == ("demo",)
    first_manifest = FrameManifest.load(video_dir / "frames" / "frames.json")
    assert [f.timestamp_seconds for f in first_manifest.frames] == [0.0, 5.0, 10.0, 15.0]
    assert sorted(p.name for p in (video_dir / "frames").glob("frame_*.jpg")) == [
        "frame_0001.jpg", "frame_0002.jpg", "frame_0003.jpg", "frame_0004.jpg",
    ]

    second = _no_boost_service(project_dir, config, interval_seconds_override=8).run()

    assert second.extracted == ("demo",)  # re-extracted, not silently skipped
    assert second.skipped == ()
    second_manifest = FrameManifest.load(video_dir / "frames" / "frames.json")
    assert [f.timestamp_seconds for f in second_manifest.frames] == [0.0, 8.0, 16.0]
    assert second_manifest.interval_seconds == 8
    # The 4th frame from the first (denser) run must be cleaned up, not left
    # as an orphaned file no longer referenced by the new manifest.
    assert sorted(p.name for p in (video_dir / "frames").glob("frame_*.jpg")) == [
        "frame_0001.jpg", "frame_0002.jpg", "frame_0003.jpg",
    ]


def test_rerun_with_same_settings_still_skips(tmp_path, monkeypatch):
    """Companion to the mismatch test above: identical settings on a rerun
    must still take the cheap self-heal skip path, not re-extract."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)

    call_count = {"n": 0}

    def counting_stub(video_path, output_dir, timestamps, **kwargs):
        call_count["n"] += 1
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", counting_stub)

    _no_boost_service(project_dir, config, interval_seconds_override=8).run()
    assert call_count["n"] == 1

    result = _no_boost_service(project_dir, config, interval_seconds_override=8).run()
    assert result.skipped == ("demo",)
    assert result.extracted == ()
    assert call_count["n"] == 1  # extract_frames never called again


def test_scene_threshold_change_reextracts_when_scene_detection_enabled(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    monkeypatch.setattr(frame_extraction_service_module, "detect_scene_timestamps", lambda video_path, **kwargs: [])
    call_count = {"n": 0}

    def counting_extract(video_path, output_dir, timestamps, **kwargs):
        call_count["n"] += 1
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", counting_extract)

    first = FrameExtractionService(
        project_dir, config, keyword_boost_override=False, interval_seconds_override=8, scene_threshold_override=0.1,
    ).run()
    second = FrameExtractionService(
        project_dir, config, keyword_boost_override=False, interval_seconds_override=8, scene_threshold_override=0.2,
    ).run()

    assert first.extracted == ("demo",)
    assert second.extracted == ("demo",)
    assert call_count["n"] == 2


def test_scene_threshold_change_skips_when_scene_detection_disabled(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    call_count = {"n": 0}

    def counting_extract(video_path, output_dir, timestamps, **kwargs):
        call_count["n"] += 1
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", counting_extract)

    first = _no_boost_service(project_dir, config, interval_seconds_override=8, scene_threshold_override=0.1).run()
    second = _no_boost_service(project_dir, config, interval_seconds_override=8, scene_threshold_override=0.2).run()

    assert first.extracted == ("demo",)
    assert second.skipped == ("demo",)
    assert call_count["n"] == 1


def test_legacy_manifest_without_scene_threshold_reextracts_when_scene_detection_enabled(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    monkeypatch.setattr(frame_extraction_service_module, "detect_scene_timestamps", lambda video_path, **kwargs: [])
    call_count = {"n": 0}

    def counting_extract(video_path, output_dir, timestamps, **kwargs):
        call_count["n"] += 1
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", counting_extract)
    FrameExtractionService(project_dir, config, keyword_boost_override=False, interval_seconds_override=8).run()

    manifest_path = video_dir / "frames" / "frames.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw.pop("scene_threshold")
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    second = FrameExtractionService(project_dir, config, keyword_boost_override=False, interval_seconds_override=8).run()

    assert second.extracted == ("demo",)
    assert call_count["n"] == 2


def test_hwaccel_cuda_scene_detection_falls_back_to_cpu(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)
    calls = []

    def detect(video_path, **kwargs):
        calls.append(kwargs.get("hwaccel"))
        if kwargs.get("hwaccel") == "cuda":
            raise SceneDetectionError("cuda scene failed")
        return []

    monkeypatch.setattr(frame_extraction_service_module, "detect_scene_timestamps", detect)

    result = FrameExtractionService(project_dir, config, keyword_boost_override=False, hwaccel_override="cuda").run()

    assert result.extracted == ("demo",)
    assert calls == ["cuda", "none"]


def test_hwaccel_cuda_frame_extraction_falls_back_to_cpu_and_cleans_partial(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    calls = []

    def extract(video_path, output_dir, timestamps, **kwargs):
        hwaccel = kwargs.get("hwaccel")
        calls.append(hwaccel)
        if hwaccel == "cuda":
            (output_dir / "frame_00001.jpg").write_bytes(b"partial")
            raise FrameExtractionError("cuda decode failed")
        assert not (output_dir / "frame_00001.jpg").exists()
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", extract)

    result = _no_boost_service(project_dir, config, hwaccel_override="cuda").run()

    assert result.extracted == ("demo",)
    assert calls == ["cuda", "none"]


def test_hwaccel_auto_uses_cpu_when_gpu_slots_are_unavailable(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    monkeypatch.setattr(frame_extraction_service_module, "FFMPEG_GPU_DECODE_SESSIONS", 0)
    monkeypatch.setattr(frame_extraction_service_module, "ffmpeg_cuda_available", lambda: True)
    calls = []

    def extract(video_path, output_dir, timestamps, **kwargs):
        calls.append(kwargs.get("hwaccel"))
        result = []
        for i, t in enumerate(sorted(timestamps), start=1):
            path = output_dir / f"frame_{i:05d}.jpg"
            _write_pattern_jpeg(path, 0)
            result.append((t, path))
        return result

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", extract)

    result = _no_boost_service(project_dir, config, hwaccel_override="auto").run()

    assert result.extracted == ("demo",)
    assert calls == ["none"]


def test_hwaccel_does_not_influence_skip(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)
    _stub_extract_frames(monkeypatch)

    first = _no_boost_service(project_dir, config, interval_seconds_override=8, hwaccel_override="none").run()
    assert first.extracted == ("demo",)

    monkeypatch.setattr(frame_extraction_service_module.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        frame_extraction_service_module,
        "extract_frames",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("extract should be skipped")),
    )
    second = _no_boost_service(project_dir, config, interval_seconds_override=8, hwaccel_override="cuda").run()

    assert second.skipped == ("demo",)
    assert second.errors == ()

def test_zero_frames_surviving_extraction_is_reported_as_error(tmp_path, monkeypatch):
    """Regression test: ffmpeg can succeed (matching frame/pts counts) while
    still producing zero usable frames after matching+dedup (e.g. every
    requested window fell outside what ffmpeg could actually decode).
    Silently writing an empty frames.json would report 'Extracted' for a
    video with no usable frames at all -- this must surface as an error."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config, duration_seconds=20.0)
    _available_ffmpeg(monkeypatch)

    def empty_extract(video_path, output_dir, timestamps, **kwargs):
        return []  # ffmpeg "succeeded" but nothing was actually extracted

    monkeypatch.setattr(frame_extraction_service_module, "extract_frames", empty_extract)

    result = _no_boost_service(project_dir, config, interval_seconds_override=8).run()

    assert result.extracted == ()
    assert result.skipped == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]
    assert "0 usable frame" in result.errors[0]
    assert not (video_dir / "frames" / "frames.json").exists()
