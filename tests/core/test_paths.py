import pytest

from videodoc.core.utils.paths import has_ambiguous_anchor, has_any_anchor, has_parent_traversal, is_external_source_path


@pytest.mark.parametrize("value", ["D:\\Corsi\\Workshop", "D:/Corsi/Workshop", "\\\\server\\share\\videos"])
def test_is_external_source_path_true_for_true_absolute(value):
    assert is_external_source_path(value) is True


@pytest.mark.parametrize("value", ["videos", "sub/dir", "C:foo", "\\foo", "/foo"])
def test_is_external_source_path_false_for_relative_and_ambiguous(value):
    assert is_external_source_path(value) is False


@pytest.mark.parametrize("value", ["../outside", "sub/../../outside", "..\\outside"])
def test_has_parent_traversal_true(value):
    assert has_parent_traversal(value) is True


@pytest.mark.parametrize("value", ["videos", "sub/dir"])
def test_has_parent_traversal_false(value):
    assert has_parent_traversal(value) is False


def test_has_parent_traversal_true_even_inside_true_absolute():
    # has_parent_traversal is a purely syntactic check: it does not know or
    # care whether the value is absolute. The "'..' is fine inside an
    # already-absolute path" exception lives in the config.py validator
    # (which only calls this after checking is_external_source_path), not
    # in this low-level primitive.
    assert has_parent_traversal("D:\\Corsi\\..\\Workshop") is True


@pytest.mark.parametrize("value", ["C:foo", "\\foo", "/foo"])
def test_has_ambiguous_anchor_true_for_semi_absolute_forms(value):
    assert has_ambiguous_anchor(value) is True


@pytest.mark.parametrize("value", ["videos", "D:\\Corsi\\Workshop"])
def test_has_ambiguous_anchor_false_for_relative_and_true_absolute(value):
    assert has_ambiguous_anchor(value) is False


@pytest.mark.parametrize("value", ["videos", "C:foo", "\\foo", "D:\\Corsi\\Workshop"])
def test_has_any_anchor_matches_is_external_or_ambiguous(value):
    # has_any_anchor must be true for every case that is either a true
    # absolute path OR an ambiguous semi-absolute form, and false only for
    # genuinely clean relative values.
    assert has_any_anchor(value) == (is_external_source_path(value) or has_ambiguous_anchor(value))
