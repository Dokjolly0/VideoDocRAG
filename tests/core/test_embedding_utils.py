import math

import pytest

from videodoc.core.utils.embedding import HASHING_EMBEDDING_DIMENSIONS, embed_text_hashing, text_hash


def test_hashing_embedding_is_deterministic_and_normalized():
    first = embed_text_hashing("npm create vite")
    second = embed_text_hashing("npm create vite")

    assert first == second
    assert len(first) == HASHING_EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0, rel_tol=1e-6)


def test_empty_text_returns_zero_vector():
    vector = embed_text_hashing("")
    assert len(vector) == HASHING_EMBEDDING_DIMENSIONS
    assert all(value == 0.0 for value in vector)


def test_custom_dimensions_are_supported():
    assert len(embed_text_hashing("testo", dimensions=16)) == 16


def test_invalid_dimensions_raise():
    with pytest.raises(ValueError):
        embed_text_hashing("testo", dimensions=0)


def test_text_hash_is_stable():
    assert text_hash("abc") == text_hash("abc")
    assert text_hash("abc") != text_hash("abcd")
