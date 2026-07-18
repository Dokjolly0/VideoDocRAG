import json

import pytest

from videodoc.core.errors import InvalidChunkManifestError
from videodoc.core.models.chunk_manifest import (
    ChunkCodeBlock,
    ChunkCodeSignature,
    ChunkFrameSignature,
    ChunkManifest,
    ChunkManifestEntry,
    ChunkTranscriptSignature,
)


def _manifest(**overrides):
    defaults = dict(
        video_id="demo",
        video_name="Demo.mp4",
        chunks=[
            ChunkManifestEntry(
                id="demo_chunk_0001",
                source_type="transcript_ocr_code",
                start_seconds=0.0,
                end_seconds=120.0,
                topic="Introduzione",
                summary="Si introduce il progetto.",
                transcript="Si introduce il progetto.",
                ocr_text="npm run dev",
                code_blocks=[
                    ChunkCodeBlock(
                        id="demo_code_0001",
                        language="bash",
                        code="npm run dev",
                        timestamp_seconds=30.0,
                        confidence=0.9,
                        verified=True,
                    )
                ],
                video_name="Demo.mp4",
            )
        ],
        transcript_inputs=[
            ChunkTranscriptSignature(
                id="demo_seg_0001",
                start_seconds=0.0,
                end_seconds=10.0,
                text_hash="hash",
                confidence=0.9,
            )
        ],
        frame_inputs=[
            ChunkFrameSignature(
                id="demo_frame_0001",
                timestamp_seconds=8.0,
                perceptual_hash="abc",
                ocr_text_hash="hash",
                ocr_confidence=0.9,
                contains_code=True,
            )
        ],
        code_inputs=[
            ChunkCodeSignature(
                id="demo_code_0001",
                timestamp_seconds=30.0,
                language="bash",
                code_hash="hash",
                confidence=0.9,
                verified=True,
            )
        ],
        min_duration_seconds=90,
        max_duration_seconds=480,
        include_nearby_frames=True,
    )
    defaults.update(overrides)
    return ChunkManifest(**defaults)


def test_roundtrip(tmp_path):
    manifest = _manifest()
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert ChunkManifest.load(path) == manifest


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidChunkManifestError):
        ChunkManifest.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidChunkManifestError):
        ChunkManifest.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "demo.json"
    raw = _manifest().model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidChunkManifestError):
        ChunkManifest.load(path)


def test_empty_chunks_roundtrips(tmp_path):
    manifest = _manifest(chunks=[])
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert ChunkManifest.load(path) == manifest
