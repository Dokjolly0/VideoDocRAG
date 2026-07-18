import json

import pytest

from videodoc.core.errors import InvalidEmbeddingManifestError
from videodoc.core.models.embedding_manifest import EmbeddingChunkSignature, EmbeddingManifest, EmbeddingRecord


def _manifest(**overrides):
    defaults = dict(
        video_id="demo",
        video_name="Demo.mp4",
        backend="feature-hashing",
        provider="local",
        model="bge-m3",
        dimensions=256,
        batch_size=32,
        chunk_inputs=[
            EmbeddingChunkSignature(
                id="demo_chunk_0001",
                source_type="transcript",
                start_seconds=0.0,
                end_seconds=60.0,
                topic_hash="topic",
                summary_hash="summary",
                transcript_hash="transcript",
                ocr_hash="ocr",
                code_hash="code",
                metadata_hash="metadata",
            )
        ],
        records=[
            EmbeddingRecord(
                id="demo_chunk_0001_combined",
                chunk_id="demo_chunk_0001",
                embedding_type="combined",
                text="Introduzione",
                text_hash="hash",
                vector=[0.0, 1.0],
                dimensions=2,
            )
        ],
    )
    defaults.update(overrides)
    return EmbeddingManifest(**defaults)


def test_roundtrip(tmp_path):
    manifest = _manifest()
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert EmbeddingManifest.load(path) == manifest


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidEmbeddingManifestError):
        EmbeddingManifest.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidEmbeddingManifestError):
        EmbeddingManifest.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "demo.json"
    raw = _manifest().model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidEmbeddingManifestError):
        EmbeddingManifest.load(path)


def test_empty_records_roundtrip(tmp_path):
    manifest = _manifest(records=[])
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert EmbeddingManifest.load(path) == manifest
