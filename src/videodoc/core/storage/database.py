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
    created_at TEXT,
    file_fingerprint TEXT
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

# README §31/§30.3 -- ocr_text/ocr_confidence are filled in by OCRService
# (README §19, via update_frame_ocr -- a partial UPDATE, not replace_frames)
# once 'videodoc ocr' runs; contains_code stays 0 until the code-detection
# phase (§20, videodoc code) fills it in. FrameExtractionService (this table's
# INSERT writer, via replace_frames) only ever populates
# id/video_id/timestamp_seconds/image_path/perceptual_hash, leaving the rest
# at their column defaults.
_CREATE_FRAMES_TABLE = """
CREATE TABLE IF NOT EXISTS frames (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    timestamp_seconds REAL NOT NULL,
    image_path TEXT NOT NULL,
    perceptual_hash TEXT,
    ocr_text TEXT,
    ocr_confidence REAL,
    contains_code INTEGER DEFAULT 0,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
"""

_CREATE_CODE_BLOCKS_TABLE = """
CREATE TABLE IF NOT EXISTS code_blocks (
    id TEXT PRIMARY KEY,
    video_id TEXT NOT NULL,
    chunk_id TEXT,
    timestamp_seconds REAL,
    language TEXT,
    code TEXT NOT NULL,
    source TEXT,
    confidence REAL,
    verified INTEGER DEFAULT 0,
    FOREIGN KEY(video_id) REFERENCES videos(id)
);
"""


def _connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path, timeout=30)


_VIDEO_SELECT_COLUMNS = "id, filename, title, duration_seconds, file_hash, path, created_at, file_fingerprint"
_LEGACY_VIDEO_SELECT_COLUMNS = "id, filename, title, duration_seconds, file_hash, path, created_at, NULL AS file_fingerprint"


def _video_table_columns(conn: sqlite3.Connection) -> set[str]:
    return {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}


def _video_select_columns(conn: sqlite3.Connection) -> str:
    if "file_fingerprint" in _video_table_columns(conn):
        return _VIDEO_SELECT_COLUMNS
    return _LEGACY_VIDEO_SELECT_COLUMNS


def _ensure_videos_columns(conn: sqlite3.Connection) -> None:
    columns = _video_table_columns(conn)
    if "file_fingerprint" not in columns:
        conn.execute("ALTER TABLE videos ADD COLUMN file_fingerprint TEXT")


@dataclass(frozen=True)
class VideoRow:
    id: str
    filename: str
    title: str | None
    duration_seconds: float
    file_hash: str
    path: str  # absolute posix -- mirrors sources.yaml's internal-or-external duality
    created_at: str  # ISO 8601 UTC; only actually applied on first INSERT, see upsert_video
    file_fingerprint: str | None = None  # cheap size+mtime+inode guard for fast ingest reruns


@dataclass(frozen=True)
class TranscriptSegmentRow:
    id: str  # "<video_id>_seg_<0001>" -- globally unique, this table's id is a single PK, not composite
    video_id: str
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None


@dataclass(frozen=True)
class FrameRow:
    id: str  # "<video_id>_frame_<0001>" -- globally unique, mirrors TranscriptSegmentRow.id
    video_id: str
    timestamp_seconds: float
    image_path: str  # project-relative posix, e.g. "workdir/<id>/frames/frame_0001.jpg"
    perceptual_hash: str | None
    ocr_text: str | None = None  # filled by the OCR phase (README §19)
    ocr_confidence: float | None = None  # filled by the OCR phase (README §19)
    contains_code: bool = False  # filled by videodoc code (README §20)


@dataclass(frozen=True)
class FrameOcrUpdate:
    frame_id: str
    ocr_text: str | None
    ocr_confidence: float | None


@dataclass(frozen=True)
class CodeBlockRow:
    id: str
    video_id: str
    chunk_id: str | None
    timestamp_seconds: float | None
    language: str | None
    code: str
    source: str | None
    confidence: float | None
    verified: bool = False


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
            _ensure_videos_columns(conn)
            conn.execute(_CREATE_TRANSCRIPT_SEGMENTS_TABLE)
            conn.execute(_CREATE_FRAMES_TABLE)
            conn.execute(_CREATE_CODE_BLOCKS_TABLE)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot initialize schema in {db_path}: {exc}") from exc


def get_video(db_path: Path, video_id: str) -> VideoRow | None:
    try:
        with closing(_connect(db_path)) as conn, conn:
            columns = _video_select_columns(conn)
            row = conn.execute(
                f"SELECT {columns} FROM videos WHERE id = ?",
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
            columns = _video_select_columns(conn)
            rows = conn.execute(
                f"SELECT {columns} FROM videos ORDER BY id"
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
                INSERT INTO videos (
                    id, filename, title, duration_seconds, file_hash, path, created_at, file_fingerprint
                )
                VALUES (
                    :id, :filename, :title, :duration_seconds, :file_hash, :path, :created_at, :file_fingerprint
                )
                ON CONFLICT(id) DO UPDATE SET
                    filename = excluded.filename,
                    duration_seconds = excluded.duration_seconds,
                    file_hash = excluded.file_hash,
                    path = excluded.path,
                    file_fingerprint = excluded.file_fingerprint
                """,
                {
                    "id": row.id,
                    "filename": row.filename,
                    "title": row.title,
                    "duration_seconds": row.duration_seconds,
                    "file_hash": row.file_hash,
                    "path": row.path,
                    "created_at": row.created_at,
                    "file_fingerprint": row.file_fingerprint,
                },
            )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot write video '{row.id}' to {db_path}: {exc}") from exc


def update_video_file_fingerprint(db_path: Path, video_id: str, file_fingerprint: str) -> None:
    try:
        with closing(_connect(db_path)) as conn, conn:
            conn.execute(
                "UPDATE videos SET file_fingerprint = ? WHERE id = ?",
                (file_fingerprint, video_id),
            )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot update video '{video_id}' fingerprint in {db_path}: {exc}") from exc


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


def list_transcript_segments(db_path: Path, video_id: str) -> list[TranscriptSegmentRow]:
    """All transcript segments for a single video, ordered by id (i.e.
    chronologically, since ids are zero-padded sequential). Returns an empty
    list -- never raises -- if the table doesn't exist yet or the video has
    no segments, same "graceful empty" contract as list_videos: the frame
    extraction service's keyword boost treats "no transcript yet" as
    "contribute zero extra candidates", not as a structural problem."""
    try:
        with closing(_connect(db_path)) as conn, conn:
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='transcript_segments'"
            ).fetchone()
            if table_exists is None:
                return []
            rows = conn.execute(
                "SELECT id, video_id, start_seconds, end_seconds, text, confidence "
                "FROM transcript_segments WHERE video_id = ? ORDER BY id",
                (video_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot list transcript segments for video '{video_id}' in {db_path}: {exc}") from exc
    return [TranscriptSegmentRow(*row) for row in rows]


def replace_frames(db_path: Path, video_id: str, frames: list[FrameRow]) -> None:
    """Full replace, not an incremental upsert: deletes any existing rows for
    video_id, then inserts the given set, in one transaction -- mirrors
    replace_transcript_segments exactly, including being called on both the
    fresh-extraction path and the skip-because-already-extracted path (see
    FrameExtractionService), so a prior transient DB failure self-heals once
    frames.json already exists on disk."""
    try:
        with closing(_connect(db_path)) as conn, conn:
            conn.execute("DELETE FROM frames WHERE video_id = ?", (video_id,))
            conn.executemany(
                "INSERT INTO frames (id, video_id, timestamp_seconds, image_path, perceptual_hash, "
                "ocr_text, ocr_confidence, contains_code) "
                "VALUES (:id, :video_id, :timestamp_seconds, :image_path, :perceptual_hash, "
                ":ocr_text, :ocr_confidence, :contains_code)",
                [
                    {
                        "id": f.id, "video_id": f.video_id, "timestamp_seconds": f.timestamp_seconds,
                        "image_path": f.image_path, "perceptual_hash": f.perceptual_hash,
                        "ocr_text": f.ocr_text, "ocr_confidence": f.ocr_confidence,
                        "contains_code": int(f.contains_code),
                    }
                    for f in frames
                ],
            )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot write frames for video '{video_id}' to {db_path}: {exc}") from exc


def list_frames(db_path: Path, video_id: str) -> list[FrameRow]:
    """All frame rows for a single video, ordered by id (i.e. chronologically,
    since ids are zero-padded sequential frame_NNNN). Returns an empty list --
    never raises -- if the table doesn't exist yet, same graceful-empty
    contract as list_transcript_segments: OCRService treats "no frames row
    for this video yet" as "run 'videodoc frames' first" (a no-op skip, not
    a structural database problem it needs to handle specially itself)."""
    try:
        with closing(_connect(db_path)) as conn, conn:
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='frames'"
            ).fetchone()
            if table_exists is None:
                return []
            rows = conn.execute(
                "SELECT id, video_id, timestamp_seconds, image_path, perceptual_hash, "
                "ocr_text, ocr_confidence, contains_code FROM frames WHERE video_id = ? ORDER BY id",
                (video_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot list frames for video '{video_id}' in {db_path}: {exc}") from exc
    return [FrameRow(*row[:7], contains_code=bool(row[7])) for row in rows]


def update_frame_ocr(db_path: Path, video_id: str, updates: list[FrameOcrUpdate]) -> None:
    """Per-row UPDATE of ONLY ocr_text/ocr_confidence for the given frame ids,
    in one transaction -- deliberately NOT replace_frames, which would
    require reconstructing perceptual_hash/contains_code for every row just
    to avoid clobbering them, and could wipe a contains_code already set by a
    §20 code-detection run that hasn't re-run yet. video_id is used in
    the WHERE clause defensively (frame ids are already globally unique
    across the whole project.db, mirroring FrameRow.id's own comment)."""
    try:
        with closing(_connect(db_path)) as conn, conn:
            conn.executemany(
                "UPDATE frames SET ocr_text = :ocr_text, ocr_confidence = :ocr_confidence "
                "WHERE id = :id AND video_id = :video_id",
                [
                    {
                        "id": u.frame_id, "video_id": video_id,
                        "ocr_text": u.ocr_text, "ocr_confidence": u.ocr_confidence,
                    }
                    for u in updates
                ],
            )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot update OCR results for video '{video_id}' in {db_path}: {exc}") from exc


def replace_frame_code_flags(db_path: Path, video_id: str, frame_ids: set[str]) -> None:
    """Replace ONLY frames.contains_code for one video.

    This is the code-detection equivalent of update_frame_ocr(): it must not
    rewrite full frame rows, because that would risk clobbering OCR text,
    OCR confidence, or perceptual hashes owned by earlier phases. A full
    replace of the boolean flag is intentional, though: if OCR/code
    detection changes its mind on a later rerun, stale true flags must be
    cleared as well as new ones set.
    """
    try:
        with closing(_connect(db_path)) as conn, conn:
            conn.execute("UPDATE frames SET contains_code = 0 WHERE video_id = ?", (video_id,))
            if frame_ids:
                conn.executemany(
                    "UPDATE frames SET contains_code = 1 WHERE id = :id AND video_id = :video_id",
                    [{"id": frame_id, "video_id": video_id} for frame_id in sorted(frame_ids)],
                )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot update code flags for video '{video_id}' in {db_path}: {exc}") from exc


def replace_code_blocks(db_path: Path, video_id: str, blocks: list[CodeBlockRow]) -> None:
    """Full replace of deduplicated OCR code blocks for one video."""
    try:
        with closing(_connect(db_path)) as conn, conn:
            conn.execute("DELETE FROM code_blocks WHERE video_id = ?", (video_id,))
            conn.executemany(
                "INSERT INTO code_blocks (id, video_id, chunk_id, timestamp_seconds, language, code, source, confidence, verified) "
                "VALUES (:id, :video_id, :chunk_id, :timestamp_seconds, :language, :code, :source, :confidence, :verified)",
                [
                    {
                        "id": b.id,
                        "video_id": b.video_id,
                        "chunk_id": b.chunk_id,
                        "timestamp_seconds": b.timestamp_seconds,
                        "language": b.language,
                        "code": b.code,
                        "source": b.source,
                        "confidence": b.confidence,
                        "verified": int(b.verified),
                    }
                    for b in blocks
                ],
            )
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot write code blocks for video '{video_id}' to {db_path}: {exc}") from exc


def list_code_blocks(db_path: Path, video_id: str) -> list[CodeBlockRow]:
    try:
        with closing(_connect(db_path)) as conn, conn:
            table_exists = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='code_blocks'"
            ).fetchone()
            if table_exists is None:
                return []
            rows = conn.execute(
                "SELECT id, video_id, chunk_id, timestamp_seconds, language, code, source, confidence, verified "
                "FROM code_blocks WHERE video_id = ? ORDER BY id",
                (video_id,),
            ).fetchall()
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot list code blocks for video '{video_id}' in {db_path}: {exc}") from exc
    return [CodeBlockRow(*row[:8], verified=bool(row[8])) for row in rows]
