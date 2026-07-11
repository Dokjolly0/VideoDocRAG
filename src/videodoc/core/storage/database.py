from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from videodoc.core.errors import DatabaseError

# README §31 -- lean, lookup-oriented schema: no project_id (a project's own
# project.db already implies its identity, README §8.1.1), no
# format/resolution/codec columns (those, plus the *_path pointers, belong
# in each video's workdir/<id>/metadata.json -- the raw-vs-structured-data
# split already established by README §4.6).
_CREATE_VIDEOS_TABLE = """
CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    title TEXT,
    duration_seconds REAL,
    file_hash TEXT,
    path TEXT,
    created_at TEXT
);
"""

# README §31/§30.2 -- see core/models/transcript.py for the note on why this
# shape (start_seconds/end_seconds REAL) was chosen over the other two
# inconsistent shapes README shows elsewhere for a transcript segment.
_CREATE_TRANSCRIPT_SEGMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS transcript_segments (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    start_seconds REAL NOT NULL,
    end_seconds REAL NOT NULL,
    text TEXT NOT NULL,
    confidence REAL,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path, timeout=30)


@dataclass(frozen=True)
class VideoRow:
    id: str
    filename: str
    title: str | None
    duration_seconds: float
    file_hash: str
    path: str  # absolute posix -- mirrors sources.yaml's internal-or-external duality
    created_at: str  # ISO 8601 UTC; only actually applied on first INSERT, see upsert_video


@dataclass(frozen=True)
class TranscriptSegmentRow:
    id: str  # "<video_id>_seg_<0001>" -- globally unique, this table's id is a single PK, not composite
    video_id: str
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None


def ensure_schema(db_path: Path) -> None:
    """Create every project.db table if it doesn't exist yet. Idempotent."""
    try:
        # sqlite3.Connection's own context-manager protocol only wraps
        # commit/rollback -- it does NOT close the connection on exit
        # (a well-known stdlib gotcha). closing(...) is what actually
        # releases the file handle; chaining ", conn" keeps the
        # commit-on-success/rollback-on-error behavior on top of that.
        with closing(_connect(db_path)) as conn, conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_VIDEOS_TABLE)
            conn.execute(_CREATE_TRANSCRIPT_SEGMENTS_TABLE)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot initialize schema in {db_path}: {exc}") from exc


def get_video(db_path: Path, video_id: str) -> VideoRow | None:
    try:
        with closing(_connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT id, filename, title, duration_seconds, file_hash, path, created_at "
                "FROM videos WHERE id = ?",
                (video_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot read video '{video_id}' from {db_path}: {exc}") from exc
    return VideoRow(*row) if row is not None else None


def list_videos(db_path: Path) -> list[VideoRow]:
    """All registered videos, ordered by id for determinism -- mirrors how
    ingest processes sorted(video_files), needed by any batch operation
    over every already-ingested video (e.g. audio extraction).

    Returns an empty list, rather than raising, if the videos table
    doesn't exist yet (a project.db file created but never fully
    schema-initialized) -- equivalent to "nothing has been ingested",
    which the caller is expected to treat as NoVideosFoundError, not as a
    structural database problem."""
    try:
        with closing(_connect(db_path)) as conn, conn:
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='videos'"
            ).fetchone()
            if table_exists is None:
                return []
            rows = conn.execute(
                "SELECT id, filename, title, duration_seconds, file_hash, path, created_at "
                "FROM videos ORDER BY id"
            ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot list videos in {db_path}: {exc}") from exc
    return [VideoRow(*row) for row in rows]


def upsert_video(db_path: Path, row: VideoRow) -> None:
    # ON CONFLICT deliberately omits title/created_at from the update
    # clause: a reingest triggered by a changed file hash must never clobber
    # a title set elsewhere in the pipeline, nor overwrite the video's
    # original first-ingested timestamp with the reprocessing time.
    try:
        with closing(_connect(db_path)) as conn, conn:
            conn.execute(
                """
                INSERT INTO videos (id, filename, title, duration_seconds, file_hash, path, created_at)
                VALUES (:id, :filename, :title, :duration_seconds, :file_hash, :path, :created_at)
                ON CONFLICT(id) DO UPDATE SET
                    filename = excluded.filename,
                    duration_seconds = excluded.duration_seconds,
                    file_hash = excluded.file_hash,
                    path = excluded.path
                """,
                {
                    "id": row.id,
                    "filename": row.filename,
                    "title": row.title,
                    "duration_seconds": row.duration_seconds,
                    "file_hash": row.file_hash,
                    "path": row.path,
                    "created_at": row.created_at,
                },
            )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot write video '{row.id}' to {db_path}: {exc}") from exc


def replace_transcript_segments(db_path: Path, video_id: str, segments: list[TranscriptSegmentRow]) -> None:
    """Full replace, not an incremental upsert: deletes any existing rows
    for video_id, then inserts the given set, in one transaction. A
    re-transcription is a wholesale regeneration, not a merge -- matches
    how sources.yaml is always fully regenerated on scan, never merged.

    Called on both the fresh-transcription path and the skip-because-
    already-transcribed path (see TranscriptionService): cheap enough
    (DELETE+INSERT of already-known rows) to call every run, which lets a
    prior transient DB failure self-heal instead of staying silently
    empty forever once the transcript JSON file already exists."""
    try:
        with closing(_connect(db_path)) as conn, conn:
            conn.execute("DELETE FROM transcript_segments WHERE video_id = ?", (video_id,))
            conn.executemany(
                "INSERT INTO transcript_segments (id, video_id, start_seconds, end_seconds, text, confidence) "
                "VALUES (:id, :video_id, :start_seconds, :end_seconds, :text, :confidence)",
                [
                    {
                        "id": seg.id, "video_id": seg.video_id, "start_seconds": seg.start_seconds,
                        "end_seconds": seg.end_seconds, "text": seg.text, "confidence": seg.confidence,
                    }
                    for seg in segments
                ],
            )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot write transcript segments for video '{video_id}' to {db_path}: {exc}") from exc
