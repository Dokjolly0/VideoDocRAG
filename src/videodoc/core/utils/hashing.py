from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable


def file_fingerprint(path: Path) -> str:
    """Return a cheap identity fingerprint from filesystem metadata.

    This is intentionally not a content hash: ingest uses it only as a fast
    unchanged-file guard before falling back to hash_file() when it differs,
    is missing, or the caller asks for verification.
    """
    stat = path.stat()
    return f"size={stat.st_size};mtime_ns={stat.st_mtime_ns};inode={stat.st_ino}"


def hash_file(
    path: Path,
    *,
    chunk_size: int = 1_048_576,
    progress_callback: Callable[[float], None] | None = None,
) -> str:
    """Stream a file's content through SHA-256 and return the hex digest.

    Reads in `chunk_size`-byte blocks rather than loading the whole file at
    once -- videos are routinely hundreds of MB to multiple GB. Raises a
    bare OSError on read failure (missing file, permission denied), the
    same un-wrapped precedent already used by scan_codebase()'s .stat()
    call: hashing is a low-level utility, not a domain boundary.

    progress_callback, if given, is invoked with bytes-hashed-so-far / total
    size after each chunk -- the file is already being streamed in chunks
    for memory reasons, so reporting a fraction from that is free. Size is
    read once via stat() before opening; a file that is empty or whose size
    can't meaningfully drive a fraction (0 bytes) just never calls back."""
    total_size = path.stat().st_size
    digest = hashlib.sha256()
    bytes_read = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
            if progress_callback is not None and total_size:
                bytes_read += len(chunk)
                progress_callback(min(1.0, bytes_read / total_size))
    return digest.hexdigest()
