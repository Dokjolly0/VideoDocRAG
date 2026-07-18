import json

import pytest

from videodoc.core.errors import InvalidVectorIndexError
from videodoc.core.models.vector_index import VectorIndex, VectorIndexInputSignature, VectorIndexRecord


def _index(**overrides):
    defaults = dict(
        backend="local-json",
        configured_vector_db="qdrant",
        distance="cosine",
        dimensions=256,
        inputs=[
            VectorIndexInputSignature(
                video_id="demo",
                backend="feature-hashing",
                provider="local",
                model="bge-m3",
                dimensions=256,
                records_hash="hash",
            )
        ],
        records=[
            VectorIndexRecord(
                id="demo_chunk_0001_combined",
                vector=[0.0, 1.0],
                payload={"project_id": "demo", "text": "Introduzione"},
            )
        ],
    )
    defaults.update(overrides)
    return VectorIndex(**defaults)


def test_roundtrip(tmp_path):
    index = _index()
    path = tmp_path / "vector_index.json"
    index.save(path)
    assert VectorIndex.load(path) == index


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidVectorIndexError):
        VectorIndex.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "vector_index.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidVectorIndexError):
        VectorIndex.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "vector_index.json"
    raw = _index().model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidVectorIndexError):
        VectorIndex.load(path)


def test_empty_records_roundtrip(tmp_path):
    index = _index(records=[])
    path = tmp_path / "vector_index.json"
    index.save(path)
    assert VectorIndex.load(path) == index
