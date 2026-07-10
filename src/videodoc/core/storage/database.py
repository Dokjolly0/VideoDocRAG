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


@dataclass(frozen=True)
class VideoRow:
    id: str
    filename: str
    title: str | None
    duration_seconds: float
    file_hash: str
    path: str  # absolute posix -- mirrors sources.yaml's internal-or-external duality
    created_at: str  # ISO 8601 UTC; only actually applied on first INSERT, see upsert_video


def ensure_schema(db_path: Path) -> None:
    """Create the videos table if it doesn't exist yet. Idempotent."""
    try:
        # sqlite3.Connection's own context-manager protocol only wraps
        # commit/rollback -- it does NOT close the connection on exit
        # (a well-known stdlib gotcha). closing(...) is what actually
        # releases the file handle; chaining ", conn" keeps the
        # commit-on-success/rollback-on-error behavior on top of that.
        with closing(sqlite3.connect(db_path)) as conn, conn:
            conn.execute(_CREATE_VIDEOS_TABLE)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot initialize schema in {db_path}: {exc}") from exc


def get_video(db_path: Path, video_id: str) -> VideoRow | None:
    try:
        with closing(sqlite3.connect(db_path)) as conn, conn:
            row = conn.execute(
                "SELECT id, filename, title, duration_seconds, file_hash, path, created_at "
                "FROM videos WHERE id = ?",
                (video_id,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot read video '{video_id}' from {db_path}: {exc}") from exc
    return VideoRow(*row) if row is not None else None


def upsert_video(db_path: Path, row: VideoRow) -> None:
    # ON CONFLICT deliberately omits title/created_at from the update
    # clause: a reingest triggered by a changed file hash must never clobber
    # a title set elsewhere in the pipeline, nor overwrite the video's
    # original first-ingested timestamp with the reprocessing time.
    try:
        with closing(sqlite3.connect(db_path)) as conn, conn:
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
