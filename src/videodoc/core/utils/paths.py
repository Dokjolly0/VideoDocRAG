from __future__ import annotations

from pathlib import PurePath

# VideoDocRAG supports Windows, Linux, and macOS. An absolute path is
# inherently machine-specific data (where a video actually lives on disk
# depends on which computer you're on) -- "is this an absolute path" should
# not give an answer that disagrees with what the real filesystem will do
# when it's eventually resolved. So these helpers default to
# path_class=PurePath, which auto-selects PureWindowsPath or PurePosixPath
# depending on the host OS actually running the code -- not a mixed rule set
# that accepts "either C:\foo or /foo everywhere", which would create real
# ambiguity (e.g. "C:foo" is a perfectly legal relative filename on Linux,
# with the colon as just another character; treating it as a dangerous
# Windows drive-relative form there would simply be wrong).
#
# path_class is explicitly injectable on every function so tests can verify
# BOTH semantics (PureWindowsPath and PurePosixPath) deterministically from a
# single development machine, without needing a real Linux/macOS host to
# trust the logic. Confidence that the code behaves correctly on all three
# OSes comes from the combination of this injection in unit tests plus the
# CI matrix (.github/workflows/tests.yml) that actually runs pytest on all
# three.


def has_any_anchor(value: str, *, path_class: type[PurePath] = PurePath) -> bool:
    """True iff `value` has a drive and/or a root -- any anchored form at
    all. On Windows (PureWindowsPath) this includes both fully absolute
    paths and the ambiguous semi-absolute ones. On POSIX (PurePosixPath)
    there is no such ambiguity: anchor is only ever '/' or '', so this is
    equivalent to is_absolute()."""
    return bool(path_class(value).anchor)


def is_external_source_path(value: str, *, path_class: type[PurePath] = PurePath) -> bool:
    """True iff `value` is a fully absolute path under path_class's rules --
    the only form paths.videos/attachments/codebase treat as an explicit
    external reference."""
    return path_class(value).is_absolute()


def has_parent_traversal(value: str, *, path_class: type[PurePath] = PurePath) -> bool:
    """True iff `value` contains a '..' path segment, which can silently
    escape a directory it gets resolved/joined against. Note: on POSIX the
    backslash is NOT a separator (it's just another filename character), so
    "sub\\..\\outside" under PurePosixPath is a single literal filename, not
    a traversal -- correct behavior, not a gap: on a POSIX host that value
    would never be interpreted as a directory separator by the real
    filesystem either."""
    return ".." in path_class(value).parts


def has_ambiguous_anchor(value: str, *, path_class: type[PurePath] = PurePath) -> bool:
    """True iff `value` has *some* anchor but is not fully absolute -- the
    dangerous forms that exist ONLY on Windows: drive-relative ('C:foo') and
    root-relative ('\\foo', '/foo'). Always False under PurePosixPath: if the
    anchor is '/' there it is automatically absolute too, so the "anchored
    but not absolute" state doesn't exist on POSIX."""
    return bool(path_class(value).anchor) and not is_external_source_path(value, path_class=path_class)
