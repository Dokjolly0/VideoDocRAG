import contextlib
import sqlite3

import pytest

from videodoc.core.errors import DatabaseError
from videodoc.core.storage.database import (
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    get_video,
    list_videos,
    replace_transcript_segments,
    upsert_video,
)


def _row(**overrides) -> VideoRow:
    defaults = dict(
        id="demo", filename="Demo.mp4", title=None, duration_seconds=12.5,
        file_hash="abc123", path="/videos/Demo.mp4", created_at="2026-01-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    return VideoRow(**defaults)


def test_ensure_schema_is_idempotent(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    ensure_schema(db_path)  # must not raise


def test_get_video_returns_none_when_absent(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    assert get_video(db_path, "demo") is None


def test_upsert_video_insert_then_get_roundtrip(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    assert get_video(db_path, "demo") == _row()


def test_upsert_video_update_preserves_title_and_created_at(tmp_path):
    """Regression test: a reingest triggered by a changed file hash must
    never clobber a title set elsewhere in the pipeline, nor overwrite the
    video's original first-ingested timestamp with the reprocessing time."""
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row(title="My Title", created_at="2026-01-01T00:00:00+00:00"))

    # Simulate a reingest: caller passes the *old* title/created_at through
    # (as VideoIngestionService does), but the SQL UPSERT itself must be the
    # one enforcing they're never actually overwritten even if it didn't.
    upsert_video(
        db_path,
        _row(
            title="Ignored New Title", created_at="2099-01-01T00:00:00+00:00",
            duration_seconds=99.9, file_hash="newhash", path="/videos/Demo.mp4",
        ),
    )

    row = get_video(db_path, "demo")
    assert row.title == "My Title"
    assert row.created_at == "2026-01-01T00:00:00+00:00"
    assert row.duration_seconds == 99.9
    assert row.file_hash == "newhash"


def test_ensure_schema_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()  # a directory where sqlite3 expects to open a file
    with pytest.raises(DatabaseError):
        ensure_schema(db_path)


def test_get_video_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        get_video(db_path, "demo")


def test_upsert_video_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        upsert_video(db_path, _row())


def test_list_videos_empty_after_schema_created(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    assert list_videos(db_path) == []


def test_list_videos_returns_empty_when_table_missing(tmp_path):
    """A project.db file that exists but was never fully schema-initialized
    (e.g. created by something other than ensure_schema) must read as 'no
    videos', not as a structural database error -- the caller treats this
    the same as 'ingest was never run'."""
    db_path = tmp_path / "project.db"
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (id TEXT)")
    assert list_videos(db_path) == []


def test_list_videos_ordered_by_id(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row(id="zeta", filename="Zeta.mp4"))
    upsert_video(db_path, _row(id="alpha", filename="Alpha.mp4"))
    upsert_video(db_path, _row(id="mid", filename="Mid.mp4"))

    rows = list_videos(db_path)
    assert [r.id for r in rows] == ["alpha", "mid", "zeta"]


def test_list_videos_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        list_videos(db_path)


def _segment(**overrides) -> TranscriptSegmentRow:
    defaults = dict(
        id="demo_seg_0000", video_id="demo", start_seconds=0.0, end_seconds=2.5,
        text="Ciao a tutti", confidence=0.9,
    )
    defaults.update(overrides)
    return TranscriptSegmentRow(**defaults)


def _fetch_segments(db_path, video_id):
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        return conn.execute(
            "SELECT id, video_id, start_seconds, end_seconds, text, confidence "
            "FROM transcript_segments WHERE video_id = ? ORDER BY id",
            (video_id,),
        ).fetchall()


def test_ensure_schema_also_creates_transcript_segments_table(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    ensure_schema(db_path)  # idempotent
    assert _fetch_segments(db_path, "demo") == []


def test_replace_transcript_segments_inserts(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_transcript_segments(db_path, "demo", [_segment(), _segment(id="demo_seg_0001", start_seconds=2.5, end_seconds=5.0)])

    rows = _fetch_segments(db_path, "demo")
    assert [r[0] for r in rows] == ["demo_seg_0000", "demo_seg_0001"]


def test_replace_transcript_segments_replaces_not_appends(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_transcript_segments(db_path, "demo", [_segment()])
    replace_transcript_segments(db_path, "demo", [_segment(id="demo_seg_0000", text="updated text")])

    rows = _fetch_segments(db_path, "demo")
    assert len(rows) == 1
    assert rows[0][4] == "updated text"


def test_replace_transcript_segments_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        replace_transcript_segments(db_path, "demo", [_segment()])
