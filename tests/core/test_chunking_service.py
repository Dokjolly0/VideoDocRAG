import contextlib
import json
import sqlite3
from pathlib import Path

import pytest

from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, NoVideosFoundError
from videodoc.core.models.chunk_manifest import ChunkManifest
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.services.chunking_service import ChunkingService
from videodoc.core.storage.database import (
    ChunkRow,
    CodeBlockRow,
    FrameRow,
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    list_chunks,
    replace_chunks,
    replace_code_blocks,
    replace_frames,
    replace_transcript_segments,
    upsert_video,
)
from videodoc.core.storage.filesystem import ensure_video_workdir


def _config(**chunking_overrides):
    config = ProjectConfig.default(name="Demo", slug="demo")
    if chunking_overrides:
        config = config.model_copy(update={"chunking": config.chunking.model_copy(update=chunking_overrides)})
    return config


def _seed_video(project_dir, config, video_id="demo", filename="Demo.mp4", duration_seconds=600.0):
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


def _seed_transcript(project_dir, config, segments, video_id="demo"):
    rows = [
        TranscriptSegmentRow(
            id=f"{video_id}_seg_{i:04d}",
            video_id=video_id,
            start_seconds=start,
            end_seconds=end,
            text=text,
            confidence=confidence,
        )
        for i, (start, end, text, confidence) in enumerate(segments, start=1)
    ]
    replace_transcript_segments(project_dir / config.paths.database, video_id, rows)
    return rows


def _seed_frames(project_dir, config, entries, video_id="demo"):
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
                timestamp_seconds=entry["timestamp_seconds"],
                image_path=rel_path,
                perceptual_hash=entry.get("perceptual_hash", f"hash-{i}"),
                ocr_text=entry.get("ocr_text"),
                ocr_confidence=entry.get("ocr_confidence"),
                contains_code=entry.get("contains_code", False),
            )
        )
    replace_frames(project_dir / config.paths.database, video_id, rows)
    return rows


def _seed_code(project_dir, config, blocks, video_id="demo"):
    rows = [
        CodeBlockRow(
            id=f"{video_id}_code_{i:04d}",
            video_id=video_id,
            chunk_id=None,
            timestamp_seconds=timestamp,
            language=language,
            code=code,
            source="ocr",
            confidence=confidence,
            verified=verified,
        )
        for i, (timestamp, language, code, confidence, verified) in enumerate(blocks, start=1)
    ]
    replace_code_blocks(project_dir / config.paths.database, video_id, rows)
    return rows


def test_no_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    with pytest.raises(NoVideosFoundError):
        ChunkingService(project_dir, _config()).run()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")
    with pytest.raises(NoVideosFoundError):
        ChunkingService(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()
    with pytest.raises(DatabaseError):
        ChunkingService(project_dir, _config()).run()


def test_video_without_inputs_is_skipped(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)

    result = ChunkingService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert result.processed == ()
    assert result.errors == ()


def test_fresh_chunking_writes_manifest_db_metadata_and_code_chunks(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(min_duration_seconds=30, max_duration_seconds=120)
    video_dir = _seed_video(project_dir, config)
    _seed_transcript(
        project_dir,
        config,
        [
            (0.0, 20.0, "Introduciamo il progetto e prepariamo il terminale.", 0.9),
            (20.0, 70.0, "Lanciamo il comando per creare la app.", 0.8),
            (210.0, 240.0, "Passiamo alla configurazione finale.", 0.85),
        ],
    )
    _seed_frames(
        project_dir,
        config,
        [
            {"timestamp_seconds": 22.0, "ocr_text": "npm create vite@latest my-app", "ocr_confidence": 0.92, "contains_code": True},
            {"timestamp_seconds": 220.0, "ocr_text": "config.yaml", "ocr_confidence": 0.88},
        ],
    )
    _seed_code(project_dir, config, [(22.0, "bash", "npm create vite@latest my-app", 0.92, True)])
    db_path = project_dir / config.paths.database

    result = ChunkingService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert result.errors == ()

    manifest_path = video_dir / "chunks" / "demo.json"
    manifest = ChunkManifest.load(manifest_path)
    assert [chunk.id for chunk in manifest.chunks] == [
        "demo_chunk_0001",
        "demo_chunk_0002",
        "demo_code_0001_chunk",
    ]
    first = manifest.chunks[0]
    assert first.source_type == "transcript_ocr_code"
    assert first.code_blocks[0].code == "npm create vite@latest my-app"
    assert first.metadata["contains_code"] is True

    rows = list_chunks(db_path, "demo")
    assert len(rows) == 3
    assert json.loads(rows[0].metadata_json)["source_type"] == "transcript_ocr_code"

    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["chunks_path"] == "workdir/demo/chunks/demo.json"


def test_skip_when_manifest_matches_self_heals_database_and_metadata(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(min_duration_seconds=30, max_duration_seconds=120)
    video_dir = _seed_video(project_dir, config)
    _seed_transcript(project_dir, config, [(0.0, 20.0, "Introduzione", 0.9), (20.0, 70.0, "Procedura", 0.9)])
    db_path = project_dir / config.paths.database

    ChunkingService(project_dir, config).run()
    replace_chunks(db_path, "demo", [])
    raw = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    raw["chunks_path"] = "workdir/demo/chunks"
    (video_dir / "metadata.json").write_text(json.dumps(raw), encoding="utf-8")

    result = ChunkingService(project_dir, config).run()

    assert result.skipped == ("demo",)
    assert len(list_chunks(db_path, "demo")) == 1
    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["chunks_path"] == "workdir/demo/chunks/demo.json"


def test_transcript_change_triggers_rechunk(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(min_duration_seconds=30, max_duration_seconds=120)
    _seed_video(project_dir, config)
    _seed_transcript(project_dir, config, [(0.0, 20.0, "Prima versione", 0.9), (20.0, 60.0, "Procedura", 0.9)])
    db_path = project_dir / config.paths.database

    ChunkingService(project_dir, config).run()
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE transcript_segments SET text = ? WHERE id = ?", ("Versione aggiornata", "demo_seg_0001"))

    result = ChunkingService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert "Versione aggiornata" in list_chunks(db_path, "demo")[0].transcript


def test_ocr_and_code_without_transcript_still_create_chunks(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(min_duration_seconds=30, max_duration_seconds=120)
    _seed_video(project_dir, config)
    _seed_frames(project_dir, config, [{"timestamp_seconds": 40.0, "ocr_text": "npm run dev", "ocr_confidence": 0.91, "contains_code": True}])
    _seed_code(project_dir, config, [(40.0, "bash", "npm run dev", 0.91, True)])

    result = ChunkingService(project_dir, config).run()

    assert result.processed == ("demo",)
    rows = list_chunks(project_dir / config.paths.database, "demo")
    assert [row.id for row in rows] == ["demo_chunk_0001", "demo_code_0001_chunk"]
    assert rows[0].ocr_text == "npm run dev"


def test_settings_change_triggers_rechunk(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(min_duration_seconds=30, max_duration_seconds=120)
    _seed_video(project_dir, config)
    _seed_transcript(project_dir, config, [(0.0, 20.0, "A", 0.9), (20.0, 80.0, "B", 0.9)])

    ChunkingService(project_dir, config).run()
    updated = _config(min_duration_seconds=20, max_duration_seconds=120)
    result = ChunkingService(project_dir, updated).run()

    assert result.processed == ("demo",)


def test_corrupt_manifest_reports_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    video_dir = _seed_video(project_dir, config)
    _seed_transcript(project_dir, config, [(0.0, 20.0, "Introduzione", 0.9)])
    chunks_dir = video_dir / "chunks"
    chunks_dir.mkdir(exist_ok=True)
    (chunks_dir / "demo.json").write_text("{not valid json", encoding="utf-8")

    result = ChunkingService(project_dir, config).run()

    assert result.processed == ()
    assert result.skipped == ()
    assert len(result.errors) == 1
    assert "could not be read" in result.errors[0]


def test_inputs_removed_after_manifest_clears_chunks(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config(min_duration_seconds=30, max_duration_seconds=120)
    _seed_video(project_dir, config)
    _seed_transcript(project_dir, config, [(0.0, 20.0, "Introduzione", 0.9), (20.0, 70.0, "Procedura", 0.9)])
    db_path = project_dir / config.paths.database

    ChunkingService(project_dir, config).run()
    replace_transcript_segments(db_path, "demo", [])

    result = ChunkingService(project_dir, config).run()

    assert result.processed == ("demo",)
    assert list_chunks(db_path, "demo") == []
