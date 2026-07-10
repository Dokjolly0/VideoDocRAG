from __future__ import annotations

from pathlib import PureWindowsPath

# VideoDocRAG and its config.yaml format are Windows-only for now (see
# README §1, RUN.md §1-2): every path in config.yaml is written and consumed
# on Windows. These helpers therefore always classify paths using Windows
# semantics via PureWindowsPath -- never the platform-dependent Path/PosixPath
# -- so the result is identical regardless of which OS actually runs the
# code. This is the single, shared definition used by both config validation
# (core/config.py) and path resolution (core/storage/filesystem.py,
# core/services/scan_service.py): before this module existed, validation
# used PureWindowsPath while resolution used the platform-dependent Path,
# which is harmless on the current Windows-only deployment (Path *is*
# PureWindowsPath there) but would have silently misclassified a genuine
# Windows absolute path like "D:\Corsi\Workshop" as relative on a
# hypothetical non-Windows host. If VideoDocRAG ever needs to run
# cross-platform, this is the one place to extend the definition (e.g. to
# also accept POSIX-absolute paths) instead of several independent
# implementations drifting apart.


def has_any_anchor(value: str) -> bool:
    """True iff `value` has a drive and/or a root -- any anchored form at
    all, whether a fully absolute path or one of the ambiguous semi-absolute
    ones. Used by fields that must stay purely relative (no anchor allowed
    at all, not even a true absolute path)."""
    return bool(PureWindowsPath(value).anchor)


def is_external_source_path(value: str) -> bool:
    """True iff `value` is a fully absolute Windows path (has both a drive
    and a root, e.g. 'D:\\Corsi\\Workshop', or a UNC path) -- the only form
    paths.videos/attachments/codebase treat as an explicit external
    reference."""
    return PureWindowsPath(value).is_absolute()


def has_parent_traversal(value: str) -> bool:
    """True iff `value` contains a '..' path segment, which can silently
    escape a directory it gets resolved/joined against."""
    return ".." in PureWindowsPath(value).parts


def has_ambiguous_anchor(value: str) -> bool:
    """True iff `value` has *some* anchor (a drive and/or a root) but is not
    a fully absolute path -- the dangerous, ambiguous Windows forms:
    drive-relative ('C:foo') and root-relative ('\\foo', '/foo'). Their
    resolution depends on mutable per-process/per-drive state, so they are
    neither safely relative-to-a-base-directory nor an explicit absolute
    reference."""
    return bool(PureWindowsPath(value).anchor) and not is_external_source_path(value)
