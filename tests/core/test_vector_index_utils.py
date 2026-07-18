import pytest

from videodoc.core.utils.vector_index import cosine_similarity, stable_json_hash


def test_stable_json_hash_ignores_dict_order():
    assert stable_json_hash({"a": 1, "b": 2}) == stable_json_hash({"b": 2, "a": 1})


def test_cosine_similarity_scores_identical_and_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_returns_zero():
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_cosine_similarity_dimension_mismatch_raises():
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 0.0])
