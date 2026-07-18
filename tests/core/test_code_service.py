import contextlib
import sqlite3
from pathlib import Path

import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, NoVideosFoundError
from videodoc.core.models.code_manifest import CodeManifest
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.services.code_service import CodeService
from videodoc.core.storage.database import (
    FrameRow,
    VideoRow,
    ensure_schema,
    list_code_blocks,
    replace_code_blocks,
    replace_frame_code_flags,
    replace_frames,
    upsert_video,
)
from videodoc.core.storage.filesystem import ensure_video_workdir


def _config(**code_overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if code_overrides:
        config = config.model_copy(update={"code": config.code.model_copy(update=code_overrides)})
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
            id=video_id,
            filename=filename,
            title=None,
            duration_seconds=duration_seconds,
            file_hash="hash123",
            path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )

    video_dir = project_dir / config.paths.workdir / video_id
    ensure_video_workdir(video_dir)
    workdir_rel = Path(config.paths.workdir) / video_id
    VideoMetadata(
        video_id=video_id,
        video_name=filename,
        title=None,
        duration_seconds=duration_seconds,
        language="it",
        hash="hash123",
        format="mov,mp4",
        width=1280,
        height=720,
        codec="h264",
        audio_path=(workdir_rel / "audio").as_posix(),
        transcript_path=(workdir_rel / "transcript").as_posix(),
        frames_path=(workdir_rel / "frames").as_posix(),
        ocr_path=(workdir_rel / "ocr").as_posix(),
        chunks_path=(workdir_rel / "chunks").as_posix(),
    ).save(video_dir / "metadata.json")
    return video_dir


def _seed_frames(project_dir, config, entries, video_id="demo"):
    db_path = project_dir / config.paths.database
    frames_dir = project_dir / config.paths.workdir / video_id / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, entry in enumerate(entries, start=1):
        image_path = frames_dir / f"frame_{i:04d}.jpg"
        image_path.write_bytes(b"fake jpeg")
        rel_path = (Path(config.paths.workdir) / video_id / "frames" / f"frame_{i:04d}.jpg").as_posix()
        rows.append(
            FrameRow(
                id=f"{video_id}_frame_{i:04d}",
                video_id=video_id,
                timestamp_seconds=float(i * 8),
                image_path=rel_path,
                perceptual_hash=entry.get("perceptual_hash", f"hash-{i}"),
                ocr_text=entry.get("ocr_text"),
                ocr_confidence=entry.get("ocr_confidence"),
            )
        )
    replace_frames(db_path, video_id, rows)
    return rows


def _frame_flags(db_path, video_id="demo"):
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        return conn.execute(
            "SELECT id, contains_code FROM frames WHERE video_id = ? ORDER BY id",
            (video_id,),
        ).fetchall()


def test_no_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    with pytest.raises(NoVideosFoundError):
        CodeService(project_dir, _config()).run()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")
    with pytest.raises(NoVideosFoundError):
        CodeService(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()
    with pytest.raises(DatabaseError):
        CodeService(project_dir, _config()).run()


def test_video_without_frames_is_skipped(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)

    result = CodeService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert result.processed == ()
    assert result.errors == ()


def test_frames_without_ocr_are_skipped(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, [{"ocr_text": None, "ocr_confidence": None}])

    result = CodeService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert result.processed == ()


def test_fresh_code_detection_deduplicates_writes_manifest_db_flags_and_report(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    video_dir = _seed_video(project_dir, config)
    _seed_frames(
        project_dir,
        config,
        [
            {"ocr_text": "npm create vite@latest my-app", "ocr_confidence": 0.91},
            {"ocr_text": "$ npm create vite@latest my-app", "ocr_confidence": 0.93},
            {"ocr_text": "In questa lezione configuriamo il progetto", "ocr_confidence": 0.95},
        ],
    )
    db_path = project_dir / config.paths.database

    result = CodeService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert result.errors == ()

    manifest_path = video_dir / "code" / "demo.json"
    assert manifest_path.is_file()
    manifest = CodeManifest.load(manifest_path)
    assert len(manifest.entries) == 1
    assert manifest.entries[0].code == "npm create vite@latest my-app"
    assert manifest.entries[0].language == "bash"
    assert [frame.frame_id for frame in manifest.entries[0].source_frames] == ["demo_frame_0001", "demo_frame_0002"]

    blocks = list_code_blocks(db_path, "demo")
    assert len(blocks) == 1
    assert blocks[0].code == "npm create vite@latest my-app"
    assert blocks[0].verified is True

    assert _frame_flags(db_path) == [
        ("demo_frame_0001", 1),
        ("demo_frame_0002", 1),
        ("demo_frame_0003", 0),
    ]
    assert "Nessun blocco richiede revisione" in (video_dir / "code" / "code_review_report.md").read_text(encoding="utf-8")


def test_skip_when_manifest_matches_self_heals_database_and_report(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    video_dir = _seed_video(project_dir, config)
    _seed_frames(project_dir, config, [{"ocr_text": "npm run dev", "ocr_confidence": 0.9}])
    db_path = project_dir / config.paths.database

    CodeService(project_dir, config).run()
    replace_code_blocks(db_path, "demo", [])
    replace_frame_code_flags(db_path, "demo", set())
    (video_dir / "code" / "code_review_report.md").unlink()

    result = CodeService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert len(list_code_blocks(db_path, "demo")) == 1
    assert _frame_flags(db_path) == [("demo_frame_0001", 1)]
    assert (video_dir / "code" / "code_review_report.md").is_file()


def test_ocr_text_change_triggers_reprocess(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, [{"ocr_text": "npm run dev", "ocr_confidence": 0.9}])
    db_path = project_dir / config.paths.database

    CodeService(project_dir, config).run()
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE frames SET ocr_text = ? WHERE id = ?", ("python -m pytest", "demo_frame_0001"))

    result = CodeService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert list_code_blocks(db_path, "demo")[0].code == "python -m pytest"


def test_low_confidence_command_is_saved_and_marked_for_review(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    video_dir = _seed_video(project_dir, config)
    _seed_frames(project_dir, config, [{"ocr_text": "npm run dev", "ocr_confidence": 0.7}])

    CodeService(project_dir, config).run()

    manifest = CodeManifest.load(video_dir / "code" / "demo.json")
    assert manifest.entries[0].needs_review is True
    report = (video_dir / "code" / "code_review_report.md").read_text(encoding="utf-8")
    assert "OCR confidence" in report


def test_corrupt_manifest_reports_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    video_dir = _seed_video(project_dir, config)
    _seed_frames(project_dir, config, [{"ocr_text": "npm run dev", "ocr_confidence": 0.9}])
    code_dir = video_dir / "code"
    code_dir.mkdir()
    (code_dir / "demo.json").write_text("{not valid json", encoding="utf-8")

    result = CodeService(project_dir, config).run()

    assert result.processed == ()
    assert result.skipped == ()
    assert len(result.errors) == 1
    assert "could not be read" in result.errors[0]


def test_extract_from_ocr_disabled_skips_without_touching_existing_code(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(extract_from_ocr=False)
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, [{"ocr_text": "npm run dev", "ocr_confidence": 0.9}])

    result = CodeService(project_dir, config).run()

    assert result.skipped == ("demo",)
