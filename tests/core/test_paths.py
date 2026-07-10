from pathlib import PurePosixPath, PureWindowsPath

import pytest

from videodoc.core.utils.paths import has_ambiguous_anchor, has_any_anchor, has_parent_traversal, is_external_source_path

# Every test in this file pins path_class explicitly (PureWindowsPath or
# PurePosixPath) rather than relying on the default path_class=PurePath --
# the default auto-selects based on the *host actually running pytest*, so a
# test asserting "'C:foo' is ambiguous" would silently pass on a Windows dev
# machine and silently FAIL on Linux/macOS CI (where 'C:foo' is just a
# harmless relative filename, not ambiguous at all -- see core/utils/paths.py).
# An earlier version of this file made exactly that mistake: the
# "Windows semantics" tests below had no explicit path_class and broke on the
# ubuntu-latest/macos-latest CI jobs the first time the workflow actually ran.
# Pinning path_class on every single test makes each one deterministic and
# platform-independent regardless of which OS pytest itself runs on.


@pytest.mark.parametrize("value", ["D:\\Corsi\\Workshop", "D:/Corsi/Workshop", "\\\\server\\share\\videos"])
def test_windows_is_external_source_path_true_for_true_absolute(value):
    assert is_external_source_path(value, path_class=PureWindowsPath) is True


@pytest.mark.parametrize("value", ["videos", "sub/dir", "C:foo", "\\foo", "/foo"])
def test_windows_is_external_source_path_false_for_relative_and_ambiguous(value):
    assert is_external_source_path(value, path_class=PureWindowsPath) is False


@pytest.mark.parametrize("value", ["../outside", "sub/../../outside", "..\\outside"])
def test_windows_has_parent_traversal_true(value):
    assert has_parent_traversal(value, path_class=PureWindowsPath) is True


@pytest.mark.parametrize("value", ["videos", "sub/dir"])
def test_windows_has_parent_traversal_false(value):
    assert has_parent_traversal(value, path_class=PureWindowsPath) is False


def test_windows_has_parent_traversal_true_even_inside_true_absolute():
    # has_parent_traversal is a purely syntactic check: it does not know or
    # care whether the value is absolute. The "'..' is fine inside an
    # already-absolute path" exception lives in the config.py validator
    # (which only calls this after checking is_external_source_path), not
    # in this low-level primitive.
    assert has_parent_traversal("D:\\Corsi\\..\\Workshop", path_class=PureWindowsPath) is True


@pytest.mark.parametrize("value", ["C:foo", "\\foo", "/foo"])
def test_windows_has_ambiguous_anchor_true_for_semi_absolute_forms(value):
    assert has_ambiguous_anchor(value, path_class=PureWindowsPath) is True


@pytest.mark.parametrize("value", ["videos", "D:\\Corsi\\Workshop"])
def test_windows_has_ambiguous_anchor_false_for_relative_and_true_absolute(value):
    assert has_ambiguous_anchor(value, path_class=PureWindowsPath) is False


@pytest.mark.parametrize("value", ["videos", "C:foo", "\\foo", "D:\\Corsi\\Workshop"])
def test_windows_has_any_anchor_matches_is_external_or_ambiguous(value):
    # has_any_anchor must be true for every case that is either a true
    # absolute path OR an ambiguous semi-absolute form, and false only for
    # genuinely clean relative values.
    assert has_any_anchor(value, path_class=PureWindowsPath) == (
        is_external_source_path(value, path_class=PureWindowsPath)
        or has_ambiguous_anchor(value, path_class=PureWindowsPath)
    )


# --- Default path_class (host-native) -----------------------------------


def test_default_path_class_matches_host_platform():
    # A single smoke test that the *default* (no path_class argument) really
    # does resolve to the host's own pathlib.Path.__class__ -- the property
    # every other test in this module deliberately bypasses by pinning
    # path_class explicitly, but that production code (config.py,
    # filesystem.py, scan_service.py) relies on implicitly.
    from pathlib import Path

    assert is_external_source_path("videos") == Path("videos").is_absolute()
    assert has_parent_traversal("../outside") == (".." in Path("../outside").parts)


# --- POSIX semantics (explicit injection) -----------------------------


@pytest.mark.parametrize("value", ["/home/user/videos", "/mnt/videos"])
def test_posix_is_external_source_path_true_for_leading_slash(value):
    assert is_external_source_path(value, path_class=PurePosixPath) is True


def test_posix_is_external_source_path_false_for_clean_relative():
    assert is_external_source_path("videos", path_class=PurePosixPath) is False


def test_posix_windows_absolute_path_is_not_external():
    # A value that is a true absolute path under Windows rules is just a
    # relative filename (with a literal colon) under POSIX rules -- absolute
    # paths are not portable across OSes by nature, this is correct, not a bug.
    assert is_external_source_path("D:\\Corsi\\Workshop", path_class=PurePosixPath) is False


@pytest.mark.parametrize("value", ["C:foo", "\\foo", "/foo"])
def test_posix_has_ambiguous_anchor_always_false(value):
    # The Windows-only ambiguous-anchor category is structurally empty under
    # POSIX rules: "/foo" is unambiguously absolute there (see the test
    # above/below), and "C:foo"/"\foo" are unambiguously relative filenames.
    assert has_ambiguous_anchor(value, path_class=PurePosixPath) is False


def test_posix_leading_slash_is_unambiguously_external_not_ambiguous():
    assert is_external_source_path("/foo", path_class=PurePosixPath) is True


def test_posix_has_parent_traversal_true_for_forward_slash_form():
    assert has_parent_traversal("../outside", path_class=PurePosixPath) is True


def test_posix_has_parent_traversal_false_for_backslash_form():
    # Backslash is not a path separator under POSIX -- it's just another
    # filename character. "sub\..\outside" is therefore a single literal
    # component, not a traversal, which matches what a real POSIX filesystem
    # would do with that same string.
    assert has_parent_traversal("sub\\..\\outside", path_class=PurePosixPath) is False


@pytest.mark.parametrize("value", ["videos", "/home/user/videos", "C:foo", "../outside"])
def test_posix_has_any_anchor_matches_is_external_source_path(value):
    # Under POSIX, "has an anchor" and "is absolute" always coincide, because
    # has_ambiguous_anchor is structurally always False there.
    assert has_any_anchor(value, path_class=PurePosixPath) == is_external_source_path(value, path_class=PurePosixPath)
