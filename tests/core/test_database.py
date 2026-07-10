import pytest

from videodoc.core.errors import DatabaseError
from videodoc.core.storage.database import VideoRow, ensure_schema, get_video, upsert_video


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
