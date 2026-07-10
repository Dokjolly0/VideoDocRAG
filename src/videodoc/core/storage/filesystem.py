from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterator

from videodoc.core.config import ScanSection
from videodoc.core.utils.paths import is_external_source_path

# Order matches the "expected output" tree in README §14 (project.db excluded:
# it is created later, during ingestion, once a schema is actually needed).
PROJECT_SUBDIRS = ("videos", "attachments", "codebase", "workdir", "indexes", "sessions", "docs")

# README §8.3 -- entries ending in "/" are directory names (matched by exact
# component name at any depth); entries without "/" are file patterns
# (fnmatch, so plain names like ".DS_Store" and globs like "*.min.js" both work).
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git/", ".hg/", ".svn/", "node_modules/", "__pycache__/", ".pytest_cache/",
    ".mypy_cache/", ".ruff_cache/", ".venv/", "venv/", "env/", "dist/", "build/",
    "out/", "target/", "coverage/", ".next/", ".nuxt/", ".cache/", ".parcel-cache/",
    ".turbo/", ".vite/", ".DS_Store",
)


def resolve_excludes(scan: ScanSection) -> set[str]:
    excludes = set(DEFAULT_EXCLUDES) if scan.default_excludes else set()
    excludes |= set(scan.add_excludes)
    excludes -= set(scan.remove_excludes)
    return excludes


def split_excludes(excludes: set[str]) -> tuple[set[str], set[str]]:
    """Split directory exclusions (trailing '/', matched by exact name) from
    file patterns (fnmatch on the filename: exact names like '.DS_Store' and
    globs like '*.min.js' alike)."""
    dir_names = {e.rstrip("/") for e in excludes if e.endswith("/")}
    file_patterns = {e for e in excludes if not e.endswith("/")}
    return dir_names, file_patterns


def resolve_source_path(project_dir: Path, configured: str) -> Path:
    """Resolve paths.videos/attachments/codebase (the three potentially-
    external fields). Absolute -> used directly (an external source,
    referenced not copied). Relative -> resolved under project_dir. Does not
    check existence: the caller (SourceScanService) decides how to treat a
    missing path (0 files + warning, never a crash).

    Uses is_external_source_path (core/utils/paths.py, PureWindowsPath-based)
    rather than a bare Path(configured).is_absolute() -- the same helper the
    config validator uses, so "does config.yaml consider this external" and
    "does resolution treat this as external" can never silently disagree."""
    resolved = Path(configured) if is_external_source_path(configured) else (project_dir / configured)
    return resolved.resolve()


def _walk_files(root: Path, *, dir_excludes: set[str], file_excludes: set[str],
                 follow_symlinks: bool, errors: list[str]) -> Iterator[Path]:
    def _onerror(exc: OSError) -> None:
        # os.walk silently skips a subdirectory it can't scandir() into (e.g.
        # permission denied) unless given an onerror callback -- without this,
        # a scan could produce an incomplete result with zero indication
        # anything was skipped. Collected here instead of raised, so one
        # inaccessible subdirectory doesn't abort the whole scan (consistent
        # with this module's "report, don't crash" policy for scan-time
        # problems), but it's never silently lost either: SourceScanService
        # surfaces these in sources.yaml and as CLI warnings.
        errors.append(str(exc))

    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks, onerror=_onerror):
        dirnames[:] = [d for d in dirnames if d not in dir_excludes]  # in-place pruning
        for fname in filenames:
            if any(fnmatch.fnmatch(fname, pat) for pat in file_excludes):
                continue
            full = Path(dirpath) / fname
            # os.walk(followlinks=...) only controls descending into symlinked
            # directories: a file that is itself a symlink still shows up in
            # `filenames` regardless of followlinks. With follow_symlinks
            # False we want "don't follow links" to apply to individual files
            # too, so it's excluded explicitly here.
            if not follow_symlinks and full.is_symlink():
                continue
            yield full


def scan_videos(root: Path, scan: ScanSection, errors: list[str] | None = None) -> list[Path]:
    dir_ex, file_ex = split_excludes(resolve_excludes(scan))
    allowed = {e.lower() for e in scan.allowed_video_extensions}
    walk_errors = errors if errors is not None else []
    return sorted(
        p for p in _walk_files(root, dir_excludes=dir_ex, file_excludes=file_ex,
                                follow_symlinks=scan.follow_symlinks, errors=walk_errors)
        if p.suffix.lower() in allowed
    )


def scan_attachments(root: Path, scan: ScanSection, errors: list[str] | None = None) -> list[Path]:
    dir_ex, file_ex = split_excludes(resolve_excludes(scan))
    walk_errors = errors if errors is not None else []
    # No extension filter: attachments/ is already a folder the user chose
    # for heterogeneous supporting material (PDFs, slides, zips, notes...).
    return sorted(_walk_files(root, dir_excludes=dir_ex, file_excludes=file_ex,
                               follow_symlinks=scan.follow_symlinks, errors=walk_errors))


def codebase_is_present(root: Path, errors: list[str] | None = None) -> bool:
    """True iff root exists and has at least one entry. codebase/ is always
    created empty by ensure_project_structure -- without this check
    (independent of exclusions), every project would look 'present' from day
    one, or a real codebase made entirely of node_modules/ would look
    'not present'.

    root.is_dir() succeeding only means the entry is a directory by type; it
    does not guarantee it can actually be listed (e.g. permission denied on
    an external/network location). Without catching OSError here, that would
    propagate uncaught and crash the whole `videodoc scan` before
    scan_codebase()'s own onerror-based error collection ever runs. Treated
    as 'not present' (with the problem recorded, never silently dropped) --
    consistent with this module's "report, don't crash" policy."""
    if not root.is_dir():
        return False
    walk_errors = errors if errors is not None else []
    try:
        with os.scandir(root) as it:  # os.scandir holds an open directory handle
            return next(it, None) is not None  # that must be closed explicitly, not left to the GC
    except OSError as exc:
        walk_errors.append(str(exc))
        return False


def scan_codebase(root: Path, scan: ScanSection, errors: list[str] | None = None) -> list[Path]:
    dir_ex, file_ex = split_excludes(resolve_excludes(scan))
    allowed = {e.lower() for e in scan.allowed_code_extensions}
    max_bytes = scan.max_file_size_mb * 1024 * 1024
    walk_errors = errors if errors is not None else []
    results = []
    for p in _walk_files(root, dir_excludes=dir_ex, file_excludes=file_ex,
                          follow_symlinks=scan.follow_symlinks, errors=walk_errors):
        if p.suffix.lower() not in allowed:
            continue
        try:
            if p.stat().st_size > max_bytes:
                continue
        except OSError:
            continue  # e.g. broken symlink: skip the single file, don't crash the scan
        results.append(p)
    return sorted(results)


def ensure_project_structure(project_dir: Path) -> None:
    """Create project_dir and all standard subfolders. Idempotent: never
    errors if folders already exist, never touches existing files."""
    project_dir.mkdir(parents=True, exist_ok=True)
    for sub in PROJECT_SUBDIRS:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)


def ensure_sources_yaml(project_dir: Path) -> Path:
    """Create an empty placeholder sources.yaml only if it doesn't exist yet;
    never overwrites an existing file. The real schema for sources.yaml will
    be defined by the 'scan' step (README §15.1) — not anticipated here."""
    path = project_dir / "sources.yaml"
    if not path.exists():
        path.write_text("# Populated by 'videodoc scan'\n", encoding="utf-8")
    return path
