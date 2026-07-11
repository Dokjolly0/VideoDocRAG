import json

import pytest

from videodoc.core.errors import InvalidOCRManifestError
from videodoc.core.models.ocr_manifest import OCRManifest, OCRManifestEntry


def _manifest(**overrides) -> OCRManifest:
    defaults = dict(
        video_id="demo",
        entries=[
            OCRManifestEntry(frame_id="demo_frame_0001", ocr_text="npm create vite@latest my-app", confidence=0.92),
            OCRManifestEntry(frame_id="demo_frame_0002", ocr_text="", confidence=0.4),
        ],
        engine="rapidocr", languages=["it", "en"], min_confidence=0.65,
    )
    defaults.update(overrides)
    return OCRManifest(**defaults)


def test_roundtrip(tmp_path):
    manifest = _manifest()
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert OCRManifest.load(path) == manifest


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(InvalidOCRManifestError):
        OCRManifest.load(tmp_path / "does-not-exist.json")


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "demo.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(InvalidOCRManifestError):
        OCRManifest.load(path)


def test_load_unknown_key_raises(tmp_path):
    path = tmp_path / "demo.json"
    raw = _manifest().model_dump(mode="json")
    raw["unexpected_field"] = "boom"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(InvalidOCRManifestError):
        OCRManifest.load(path)


def test_empty_entries_list_roundtrips(tmp_path):
    manifest = OCRManifest(video_id="demo", entries=[])
    path = tmp_path / "demo.json"
    manifest.save(path)
    assert OCRManifest.load(path) == manifest


def test_manifest_without_settings_fields_loads_with_none_defaults(tmp_path):
    """Regression test: an ocr.json written before the settings fields
    existed must still load (as 'settings unknown', not a corrupt
    manifest) -- OCRService treats None the same as 'always re-OCR', the
    safe behavior for any pre-existing manifest."""
    path = tmp_path / "demo.json"
    raw = {
        "video_id": "demo",
        "entries": [{"frame_id": "demo_frame_0001", "ocr_text": "hello", "confidence": 0.9}],
    }
    path.write_text(json.dumps(raw), encoding="utf-8")

    manifest = OCRManifest.load(path)
    assert manifest.engine is None
    assert manifest.languages is None
    assert manifest.min_confidence is None


def test_manifest_settings_fields_roundtrip(tmp_path):
    manifest = _manifest(engine="rapidocr", languages=["it"], min_confidence=0.5)
    path = tmp_path / "demo.json"
    manifest.save(path)
    loaded = OCRManifest.load(path)
    assert loaded.engine == "rapidocr"
    assert loaded.languages == ["it"]
    assert loaded.min_confidence == 0.5


def test_low_confidence_entry_keeps_empty_text_not_omitted(tmp_path):
    """min_confidence is a filter on ocr_text, not a validity flag: a
    below-threshold entry is still recorded (ocr_text='', real confidence
    kept), distinguishing 'OCR ran and found low-confidence noise' from
    'OCR never ran on this frame' (which stays out of entries entirely)."""
    manifest = _manifest(entries=[OCRManifestEntry(frame_id="demo_frame_0002", ocr_text="", confidence=0.4)])
    path = tmp_path / "demo.json"
    manifest.save(path)
    loaded = OCRManifest.load(path)
    assert loaded.entries[0].ocr_text == ""
    assert loaded.entries[0].confidence == 0.4
