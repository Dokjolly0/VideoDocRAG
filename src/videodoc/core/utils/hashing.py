from __future__ import annotations

import hashlib
from pathlib import Path


def hash_file(path: Path, *, chunk_size: int = 1_048_576) -> str:
    """Stream a file's content through SHA-256 and return the hex digest.

    Reads in `chunk_size`-byte blocks rather than loading the whole file at
    once -- videos are routinely hundreds of MB to multiple GB. Raises a
    bare OSError on read failure (missing file, permission denied), the
    same un-wrapped precedent already used by scan_codebase()'s .stat()
    call: hashing is a low-level utility, not a domain boundary."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()
