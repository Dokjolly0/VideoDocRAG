import contextlib
import json
import sqlite3
from pathlib import Path

import pytest

import videodoc.core.services.ocr_service as ocr_service_module
from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, NoVideosFoundError, OCREngineNotSupportedError, OCREngineUnavailableError
from videodoc.core.models.frame_manifest import FrameManifest, FrameManifestEntry
from videodoc.core.models.ocr_manifest import OCRManifest
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.services.ocr_service import OCRService
from videodoc.core.storage.database import FrameRow, VideoRow, ensure_schema, replace_frames, upsert_video
from videodoc.core.storage.filesystem import ensure_video_workdir


def _config(**overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if overrides:
        config = config.model_copy(update={"ocr": config.ocr.model_copy(update=overrides)})
    return config


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


def _seed_frames(project_dir, config, video_id="demo", count=2, timestamp_seconds_fn=None, perceptual_hash="abc"):
    db_path = project_dir / config.paths.database
    frames_dir = project_dir / config.paths.workdir / video_id / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    timestamp_seconds_fn = timestamp_seconds_fn or (lambda i: float(i * 8))
    rows = []
    for i in range(1, count + 1):
        image_path = frames_dir / f"frame_{i:04d}.jpg"
        image_path.write_bytes(b"fake jpeg")
        rel_path = (Path(config.paths.workdir) / video_id / "frames" / f"frame_{i:04d}.jpg").as_posix()
        rows.append(FrameRow(
            id=f"{video_id}_frame_{i:04d}", video_id=video_id, timestamp_seconds=timestamp_seconds_fn(i),
            image_path=rel_path, perceptual_hash=perceptual_hash,
        ))
    replace_frames(db_path, video_id, rows)
    return rows


def _stub_engine(monkeypatch, *, text="npm create vite@latest my-app", confidence=0.9):
    """Fake load_engine/run_ocr pair: load_engine returns a sentinel object
    (counting calls, so tests can assert it's loaded once per video and
    never again once a video is fully self-healable), run_ocr returns a
    fixed (text, confidence) for every frame."""
    load_calls = {"n": 0}

    def fake_load_engine():
        load_calls["n"] += 1
        return object()

    def fake_run_ocr(engine, image_path):
        return text, confidence

    monkeypatch.setattr(ocr_service_module, "load_engine", fake_load_engine)
    monkeypatch.setattr(ocr_service_module, "run_ocr", fake_run_ocr)
    return load_calls


def _available_engine(monkeypatch, available=True):
    monkeypatch.setattr(ocr_service_module, "rapidocr_available", lambda: available)


def test_no_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    with pytest.raises(NoVideosFoundError):
        OCRService(project_dir, _config()).run()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")
    with pytest.raises(NoVideosFoundError):
        OCRService(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()
    with pytest.raises(DatabaseError):
        OCRService(project_dir, _config()).run()


def test_video_without_frames_is_skipped_not_errored(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _available_engine(monkeypatch, available=False)  # must never even be consulted

    result = OCRService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert result.processed == ()
    assert result.errors == ()


def test_fresh_ocr_writes_manifest_and_db_without_touching_other_columns(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=2)
    db_path = project_dir / config.paths.database

    # Simulate a §20 code-detection run having already set
    # contains_code -- OCRService must never touch it.
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE frames SET contains_code = 1 WHERE id = ?", ("demo_frame_0001",))

    _available_engine(monkeypatch, available=True)
    _stub_engine(monkeypatch, text="npm create vite@latest my-app", confidence=0.9)

    result = OCRService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert result.errors == ()

    manifest_path = video_dir / "ocr" / "demo.json"
    assert manifest_path.is_file()
    manifest = OCRManifest.load(manifest_path)
    assert len(manifest.entries) == 2
    assert manifest.entries[0].ocr_text == "npm create vite@latest my-app"
    assert manifest.entries[0].confidence == 0.9
    assert manifest.engine == "rapidocr"

    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        row = conn.execute(
            "SELECT ocr_text, ocr_confidence, contains_code, perceptual_hash FROM frames WHERE id = ?",
            ("demo_frame_0001",),
        ).fetchone()
    assert row[0] == "npm create vite@latest my-app"
    assert row[1] == 0.9
    assert row[2] == 1  # contains_code untouched
    assert row[3] == "abc"  # perceptual_hash untouched

    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["ocr_path"] == "workdir/demo/ocr"


def test_skip_when_manifest_matches_self_heals_db_without_invoking_engine(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=1)
    _available_engine(monkeypatch, available=True)
    load_calls = _stub_engine(monkeypatch)

    OCRService(project_dir, config).run()
    assert load_calls["n"] == 1

    # Second run: rapidocr_available would raise if actually consulted for a
    # run that needs nothing fresh -- confirms the up-front check is only
    # reached when at least one video needs fresh OCR.
    monkeypatch.setattr(ocr_service_module, "rapidocr_available", lambda: (_ for _ in ()).throw(AssertionError("must not be called")))

    result = OCRService(project_dir, config).run()
    assert result.skipped == ("demo",)
    assert result.processed == ()
    assert load_calls["n"] == 1  # engine never loaded again


def test_settings_mismatch_triggers_reocr(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=1)
    _available_engine(monkeypatch, available=True)
    load_calls = _stub_engine(monkeypatch)

    OCRService(project_dir, config).run()
    assert load_calls["n"] == 1

    result = OCRService(project_dir, config, min_confidence_override=0.99).run()
    assert result.processed == ("demo",)
    assert load_calls["n"] == 2


def test_frame_set_change_triggers_reocr(tmp_path, monkeypatch):
    """OCR-phase-specific idempotency edge: 'videodoc frames' re-run
    producing a different frame-id set (e.g. a looser interval) must
    trigger re-OCR even though no OCR setting changed at all."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=1)
    _available_engine(monkeypatch, available=True)
    load_calls = _stub_engine(monkeypatch)

    OCRService(project_dir, config).run()
    assert load_calls["n"] == 1

    _seed_frames(project_dir, config, count=2)  # frames re-run with a new frame set
    result = OCRService(project_dir, config).run()
    assert result.processed == ("demo",)
    assert load_calls["n"] == 2


def test_min_confidence_filters_text_but_keeps_confidence(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(min_confidence=0.8)
    video_dir_pair = _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=1)
    _available_engine(monkeypatch, available=True)
    _stub_engine(monkeypatch, text="garbled noise", confidence=0.4)

    OCRService(project_dir, config).run()

    manifest = OCRManifest.load(video_dir_pair[1] / "ocr" / "demo.json")
    assert manifest.entries[0].ocr_text == ""
    assert manifest.entries[0].confidence == 0.4


def test_per_frame_failure_isolated(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=2)
    _available_engine(monkeypatch, available=True)

    def fake_load_engine():
        return object()

    def fake_run_ocr(engine, image_path):
        from videodoc.core.utils.ocr_engine import OCRRunError
        if "0001" in image_path.name:
            raise OCRRunError("stubbed failure")
        return "ok text", 0.9

    monkeypatch.setattr(ocr_service_module, "load_engine", fake_load_engine)
    monkeypatch.setattr(ocr_service_module, "run_ocr", fake_run_ocr)

    result = OCRService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert len(result.errors) == 1
    assert "demo_frame_0001" in result.errors[0]

    manifest = OCRManifest.load(video_dir / "ocr" / "demo.json")
    assert [e.frame_id for e in manifest.entries] == ["demo_frame_0002"]


def test_engine_unavailable_raises_only_when_fresh_ocr_needed(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=1)
    _available_engine(monkeypatch, available=False)

    with pytest.raises(OCREngineUnavailableError):
        OCRService(project_dir, config).run()


def test_unsupported_engine_raises_even_with_nothing_to_do(tmp_path, monkeypatch):
    """Regression test: OCRService always instantiates RapidOCR regardless
    of config.ocr.engine's value -- an old project whose config.yaml still
    says the pre-correction 'paddleocr' default must not silently run
    RapidOCR anyway and write a manifest that misreports which engine
    produced it. Checked unconditionally, even when there is no video at
    all needing fresh OCR (an empty project), since this is a configuration
    problem, not an availability one."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(engine="paddleocr")
    _seed_video(project_dir, config)  # no frames seeded at all -- nothing needs fresh OCR
    _available_engine(monkeypatch, available=False)  # must not even be consulted

    with pytest.raises(OCREngineNotSupportedError):
        OCRService(project_dir, config).run()


def test_frames_db_desync_reports_error_instead_of_silent_skip(tmp_path, monkeypatch):
    """Regression test: frames/frames.json can have real entries on disk
    (e.g. after a project.db rebuild or a lost table) while the frames
    table itself has zero rows for that video -- this must be surfaced as a
    clear, actionable per-video error telling the user to rerun
    'videodoc frames', not silently treated the same as "videodoc frames
    was never run at all"."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_engine(monkeypatch, available=False)  # must not even be consulted -- no fresh OCR is attempted

    frames_dir = video_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    FrameManifest(
        video_id="demo",
        frames=[FrameManifestEntry(id="demo_frame_0001", timestamp_seconds=8.0, image_path="workdir/demo/frames/frame_0001.jpg", perceptual_hash="abc")],
    ).save(frames_dir / "frames.json")
    # Deliberately no corresponding row inserted into the frames DB table.

    result = OCRService(project_dir, config).run()

    assert result.skipped == ()
    assert result.processed == ()
    assert len(result.errors) == 1
    assert "rebuild the database" in result.errors[0]
    assert "demo_frame_0001" not in result.errors[0]  # count-based message, not a per-frame listing


def test_corrupt_frames_manifest_with_no_db_rows_reports_error_instead_of_silent_skip(tmp_path, monkeypatch):
    """Regression test: if the frames table has zero rows for a video AND
    frames/frames.json exists but fails to parse, that must not be swallowed
    and fall through to the same silent skip as 'videodoc frames' never
    having run at all -- it's a real, fixable broken state (the manifest is
    corrupt), and hiding it is worse than surfacing a clear error."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _available_engine(monkeypatch, available=False)  # must not even be consulted

    frames_dir = video_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    (frames_dir / "frames.json").write_text("{not valid json", encoding="utf-8")
    # Deliberately no corresponding row inserted into the frames DB table.

    result = OCRService(project_dir, config).run()

    assert result.skipped == ()
    assert result.processed == ()
    assert len(result.errors) == 1
    assert "could not be read" in result.errors[0]


def test_same_frame_ids_different_content_triggers_reocr(tmp_path, monkeypatch):
    """Regression test: frame ids are assigned densely by position
    (demo_frame_0001, demo_frame_0002, ...), so a 'videodoc frames' re-run
    with different settings that happens to land on the same *count* of
    frames produces the exact same id set over completely different
    timestamps/images. Comparing only the frame-id set (an earlier version
    of this idempotency check) would treat this as unchanged and silently
    reapply stale OCR text to new frame content -- the manifest must also
    compare each entry's timestamp_seconds/perceptual_hash."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, count=2, perceptual_hash="hash-v1")
    _available_engine(monkeypatch, available=True)
    load_calls = _stub_engine(monkeypatch)

    OCRService(project_dir, config).run()
    assert load_calls["n"] == 1

    # Same video, same frame count, same resulting id set -- but different
    # perceptual content (as if 'videodoc frames' re-ran with different
    # settings and happened to produce the same number of frames).
    _seed_frames(project_dir, config, count=2, perceptual_hash="hash-v2")

    result = OCRService(project_dir, config).run()
    assert result.processed == ("demo",)
    assert load_calls["n"] == 2
