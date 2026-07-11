import sys
import types
from dataclasses import dataclass

import pytest

import videodoc.core.utils.ocr_engine as ocr_engine_module
from videodoc.core.utils.ocr_engine import OCRRunError, load_engine, rapidocr_available, run_ocr


def test_rapidocr_available_true_when_installed():
    assert rapidocr_available() is True


def test_rapidocr_available_false_when_not_importable(monkeypatch):
    monkeypatch.setattr(ocr_engine_module.importlib.util, "find_spec", lambda name: None)
    assert rapidocr_available() is False


def test_rapidocr_available_false_when_onnxruntime_missing(monkeypatch):
    """Regression test: 'rapidocr' does not declare 'onnxruntime' as a hard
    dependency of its own -- a machine with 'rapidocr' installed but
    'onnxruntime' missing must be treated the same as 'rapidocr' itself
    missing (a structural, run-wide problem), not silently left to surface
    only as a per-video failure inside load_engine()."""
    monkeypatch.setattr(
        ocr_engine_module.importlib.util, "find_spec",
        lambda name: object() if name == "rapidocr" else None,
    )
    assert rapidocr_available() is False


@dataclass(frozen=True)
class _FakeResult:
    txts: tuple[str, ...] | None
    scores: tuple[float, ...] | None

    def __call__(self, _path):
        return self


def test_run_ocr_joins_text_and_averages_confidence(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fake")
    engine = _FakeResult(txts=("npm create vite@latest my-app", "cd my-app"), scores=(0.9, 0.8))

    text, confidence = run_ocr(engine, image)

    assert text == "npm create vite@latest my-app\ncd my-app"
    assert confidence == pytest.approx(0.85)


def test_run_ocr_no_detections_returns_empty_text_full_confidence(tmp_path):
    """Regression test: RapidOCR's own result object returns txts=None/
    scores=None (not empty tuples) when zero text is detected -- verified
    against the actually-installed rapidocr 3.9.1 on a blank image. This
    must be treated as 'ran cleanly, found nothing', not as a failure."""
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fake")
    engine = _FakeResult(txts=None, scores=None)

    text, confidence = run_ocr(engine, image)

    assert text == ""
    assert confidence == 1.0


def test_run_ocr_wraps_engine_failure(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"fake")

    def broken_engine(_path):
        raise RuntimeError("corrupt image")

    with pytest.raises(OCRRunError):
        run_ocr(broken_engine, image)


def test_load_engine_wraps_broken_install_import_error(monkeypatch):
    """Regression test: rapidocr_available() only confirms the package can
    be *located* (importlib.util.find_spec), not that it actually imports/
    instantiates cleanly -- a broken install or corrupt cached model file is
    a real failure mode. load_engine must fold that into OCRRunError, the
    same as any other failure, rather than letting it escape uncaught and
    abort the whole OCRService run instead of just this one video."""
    broken_module = types.ModuleType("rapidocr")
    monkeypatch.setitem(sys.modules, "rapidocr", broken_module)

    with pytest.raises(OCRRunError):
        load_engine()
