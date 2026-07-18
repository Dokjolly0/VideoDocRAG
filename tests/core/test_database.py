import contextlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from videodoc.core.errors import DatabaseError
from videodoc.core.storage.database import (
    CodeBlockRow,
    FrameOcrUpdate,
    FrameRow,
    TranscriptSegmentRow,
    VideoRow,
    ensure_schema,
    get_video,
    list_code_blocks,
    list_frames,
    list_transcript_segments,
    list_videos,
    replace_code_blocks,
    replace_frame_code_flags,
    replace_frames,
    replace_transcript_segments,
    update_frame_ocr,
    update_video_file_fingerprint,
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


def test_ensure_schema_migrates_legacy_videos_table_with_file_fingerprint(tmp_path):
    db_path = tmp_path / "project.db"
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("""
            CREATE TABLE videos (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                title TEXT,
                duration_seconds REAL,
                file_hash TEXT,
                path TEXT,
                created_at TEXT
            )
        """)

    ensure_schema(db_path)

    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(videos)")}
    assert "file_fingerprint" in columns


def test_upsert_video_persists_file_fingerprint(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row(file_fingerprint="size=3;mtime_ns=4;inode=5"))

    assert get_video(db_path, "demo").file_fingerprint == "size=3;mtime_ns=4;inode=5"


def test_update_video_file_fingerprint_preserves_other_video_fields(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row(title="My Title", file_fingerprint="old"))

    update_video_file_fingerprint(db_path, "demo", "new")

    row = get_video(db_path, "demo")
    assert row.file_fingerprint == "new"
    assert row.title == "My Title"
    assert row.file_hash == "abc123"


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

def test_concurrent_short_writes_do_not_raise_operational_error(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)

    def write_one(i):
        upsert_video(db_path, _row(id=f"video-{i:02d}", filename=f"Video {i}.mp4", file_hash=f"hash-{i}"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write_one, range(24)))

    assert len(list_videos(db_path)) == 24


def test_list_transcript_segments_empty_when_table_missing(tmp_path):
    db_path = tmp_path / "project.db"
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (id TEXT)")
    assert list_transcript_segments(db_path, "demo") == []


def test_list_transcript_segments_empty_when_video_has_none(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    assert list_transcript_segments(db_path, "demo") == []


def test_list_transcript_segments_returns_only_requested_video_ordered_by_id(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    upsert_video(db_path, _row(id="other", filename="Other.mp4"))
    replace_transcript_segments(
        db_path, "demo",
        [_segment(id="demo_seg_0001", start_seconds=2.5, end_seconds=5.0), _segment(id="demo_seg_0000")],
    )
    replace_transcript_segments(db_path, "other", [_segment(id="other_seg_0000", video_id="other")])

    rows = list_transcript_segments(db_path, "demo")
    assert [r.id for r in rows] == ["demo_seg_0000", "demo_seg_0001"]


def test_list_transcript_segments_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        list_transcript_segments(db_path, "demo")


def _frame(**overrides) -> FrameRow:
    defaults = dict(
        id="demo_frame_0000", video_id="demo", timestamp_seconds=8.0,
        image_path="workdir/demo/frames/frame_0001.jpg", perceptual_hash="abc123",
    )
    defaults.update(overrides)
    return FrameRow(**defaults)


def _fetch_frames(db_path, video_id):
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        return conn.execute(
            "SELECT id, video_id, timestamp_seconds, image_path, perceptual_hash, "
            "ocr_text, ocr_confidence, contains_code FROM frames WHERE video_id = ? ORDER BY id",
            (video_id,),
        ).fetchall()


def test_ensure_schema_also_creates_frames_table(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    ensure_schema(db_path)  # idempotent
    assert _fetch_frames(db_path, "demo") == []


def test_replace_frames_inserts_with_ocr_fields_defaulted(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_frames(db_path, "demo", [_frame(), _frame(id="demo_frame_0001", timestamp_seconds=16.0)])

    rows = _fetch_frames(db_path, "demo")
    assert [r[0] for r in rows] == ["demo_frame_0000", "demo_frame_0001"]
    # ocr_text/ocr_confidence stay NULL until OCR; contains_code stays 0 until videodoc code.
    assert rows[0][5] is None
    assert rows[0][6] is None
    assert rows[0][7] == 0


def test_replace_frames_replaces_not_appends(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_frames(db_path, "demo", [_frame()])
    replace_frames(db_path, "demo", [_frame(perceptual_hash="updated")])

    rows = _fetch_frames(db_path, "demo")
    assert len(rows) == 1
    assert rows[0][4] == "updated"


def test_replace_frames_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        replace_frames(db_path, "demo", [_frame()])


def test_list_frames_returns_empty_when_table_missing(tmp_path):
    db_path = tmp_path / "project.db"
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("SELECT 1")  # create the file without ever calling ensure_schema
    assert list_frames(db_path, "demo") == []


def test_list_frames_orders_by_id(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_frames(db_path, "demo", [
        _frame(id="demo_frame_0002", timestamp_seconds=16.0),
        _frame(id="demo_frame_0001", timestamp_seconds=8.0),
    ])

    rows = list_frames(db_path, "demo")
    assert [r.id for r in rows] == ["demo_frame_0001", "demo_frame_0002"]


def test_update_frame_ocr_updates_only_ocr_columns(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_frames(db_path, "demo", [_frame(perceptual_hash="original-hash")])
    # Seed contains_code=True directly, since replace_frames' own FrameRow
    # default is False -- simulates a §20 code-detection run having
    # already set it, which update_frame_ocr must never clobber.
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE frames SET contains_code = 1 WHERE id = ?", ("demo_frame_0000",))

    update_frame_ocr(db_path, "demo", [FrameOcrUpdate(frame_id="demo_frame_0000", ocr_text="hello world", ocr_confidence=0.91)])

    rows = _fetch_frames(db_path, "demo")
    assert rows[0][4] == "original-hash"  # perceptual_hash untouched
    assert rows[0][5] == "hello world"  # ocr_text updated
    assert rows[0][6] == 0.91  # ocr_confidence updated
    assert rows[0][7] == 1  # contains_code untouched


def test_update_frame_ocr_wraps_sqlite_error(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        update_frame_ocr(db_path, "demo", [FrameOcrUpdate(frame_id="demo_frame_0000", ocr_text="x", ocr_confidence=0.5)])


def test_replace_frame_code_flags_updates_only_contains_code(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_frames(db_path, "demo", [
        _frame(id="demo_frame_0000", ocr_text="npm run dev", ocr_confidence=0.9, perceptual_hash="h1"),
        _frame(id="demo_frame_0001", ocr_text="plain text", ocr_confidence=0.8, perceptual_hash="h2"),
    ])

    replace_frame_code_flags(db_path, "demo", {"demo_frame_0000"})

    rows = _fetch_frames(db_path, "demo")
    assert rows[0][4] == "h1"
    assert rows[0][5] == "npm run dev"
    assert rows[0][6] == 0.9
    assert rows[0][7] == 1
    assert rows[1][5] == "plain text"
    assert rows[1][7] == 0


def test_replace_frame_code_flags_clears_stale_true_flags(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_frames(db_path, "demo", [_frame(), _frame(id="demo_frame_0001")])
    replace_frame_code_flags(db_path, "demo", {"demo_frame_0000", "demo_frame_0001"})
    replace_frame_code_flags(db_path, "demo", {"demo_frame_0001"})

    rows = _fetch_frames(db_path, "demo")
    assert [row[7] for row in rows] == [0, 1]


def test_replace_and_list_code_blocks_roundtrip(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_code_blocks(
        db_path,
        "demo",
        [
            CodeBlockRow(
                id="demo_code_0001",
                video_id="demo",
                chunk_id=None,
                timestamp_seconds=8.0,
                language="bash",
                code="npm run dev",
                source="ocr",
                confidence=0.91,
                verified=True,
            )
        ],
    )

    rows = list_code_blocks(db_path, "demo")
    assert rows == [
        CodeBlockRow(
            id="demo_code_0001",
            video_id="demo",
            chunk_id=None,
            timestamp_seconds=8.0,
            language="bash",
            code="npm run dev",
            source="ocr",
            confidence=0.91,
            verified=True,
        )
    ]


def test_replace_code_blocks_replaces_not_appends(tmp_path):
    db_path = tmp_path / "project.db"
    ensure_schema(db_path)
    upsert_video(db_path, _row())
    replace_code_blocks(
        db_path,
        "demo",
        [CodeBlockRow("demo_code_0001", "demo", None, 8.0, "bash", "npm run dev", "ocr", 0.9, True)],
    )
    replace_code_blocks(
        db_path,
        "demo",
        [CodeBlockRow("demo_code_0002", "demo", None, 16.0, "python", "print('ok')", "ocr", 0.95, True)],
    )

    rows = list_code_blocks(db_path, "demo")
    assert [row.id for row in rows] == ["demo_code_0002"]


def test_code_block_helpers_wrap_sqlite_errors(tmp_path):
    db_path = tmp_path / "not-a-file"
    db_path.mkdir()
    with pytest.raises(DatabaseError):
        replace_frame_code_flags(db_path, "demo", {"demo_frame_0000"})
    with pytest.raises(DatabaseError):
        replace_code_blocks(db_path, "demo", [])
    with pytest.raises(DatabaseError):
        list_code_blocks(db_path, "demo")
