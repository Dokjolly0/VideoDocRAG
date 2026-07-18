import json

import pytest

from videodoc.core.errors import InvalidCodeManifestError
from videodoc.core.models.code_manifest import (
    CodeInputFrameSignature,
    CodeManifest,
    CodeManifestEntry,
    CodeSourceFrame,
    CodeValidation,
)


def _manifest(**overrides):
    defaults = dict(
        video_id="demo",
        input_frames=[
            CodeInputFrameSignature(
                frame_id="demo_frame_0001",
                timestamp_seconds=8.0,
                perceptual_hash="abc",
                ocr_text_hash="hash",
                ocr_confidence=0.91,
            )
        ],
        entries=[
            CodeManifestEntry(
                id="demo_code_0001",
                content_type="terminal_command",
                language="bash",
                code="npm run dev",
                normalized_hash="hash",
                timestamp_seconds=8.0,
                source="ocr",
                confidence=0.91,
                verified=True,
                validation=CodeValidation(status="not_applicable"),
                source_frames=[CodeSourceFrame(frame_id="demo_frame_0001", timestamp_seconds=8.0, ocr_confidence=0.91)],
            )
        ],
        extract_from_ocr=True,
        strict_mode=True,
        mark_uncertain_code=True,
    )
    defaults.update(overrides)
    return CodeManifest(**defaults)


def test_roundtrip(tmp_path):
    manifest = _manifest()
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert CodeManifest.load(path) == manifest


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidCodeManifestError):
        CodeManifest.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidCodeManifestError):
        CodeManifest.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "demo.json"
    raw = _manifest().model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidCodeManifestError):
        CodeManifest.load(path)


def test_empty_entries_roundtrips(tmp_path):
    manifest = _manifest(entries=[])
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert CodeManifest.load(path) == manifest
