from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


class OCRRunError(Exception):
    """Raised when the OCR engine fails on a single frame image (corrupt/
    unreadable file, engine internal error).

    Deliberately NOT a VideoDocError: this is a per-item failure the caller
    (OCRService) always folds into a per-video error, never lets propagate to
    the CLI layer -- same role as SceneDetectionError. Whether 'rapidocr' is
    even importable at all is a separate, structural concern checked once up
    front by the caller via rapidocr_available()."""


def rapidocr_available() -> bool:
    """Cheap one-time check for whether 'rapidocr' AND 'onnxruntime' can both
    be imported at all -- checked once per run by the caller, not once per
    video/frame, mirroring the lazy availability checks used by the other media phases. 'onnxruntime' is checked
    explicitly and separately: 'rapidocr' itself does not declare it as a
    hard dependency (verified against the installed package's own metadata),
    so a machine with 'rapidocr' installed but 'onnxruntime' missing would
    otherwise pass this check and only fail once RapidOCR() is actually
    instantiated inside load_engine() -- a structural, run-wide problem
    (every video would fail identically), not a legitimate per-video
    failure, and must not be silently folded into per-video warnings the way
    a genuinely broken/corrupt install is. Uses find_spec instead of a real
    import so it never pays the cost of actually loading either package or
    the OCR models just to answer "is it there"."""
    return (
        importlib.util.find_spec("rapidocr") is not None
        and importlib.util.find_spec("onnxruntime") is not None
    )


def load_engine() -> Any:
    """Instantiate one RapidOCR engine (loads its default detection/
    classification/recognition ONNX models). Meant to be called once per
    video, not once per frame -- model loading has real overhead, and the
    whole point of per-video-thread engine ownership (see OCRService) is to
    amortize that cost across every frame of one video.

    Assumes rapidocr_available() has already been checked by the caller --
    but that check only confirms the package can be *located*
    (importlib.util.find_spec), not that it actually imports/instantiates
    cleanly (a corrupted cached model file is a real-world failure mode).
    Any failure here is therefore a per-video error for the caller to fold
    in, not a run-aborting one -- only "the package isn't installed at all"
    is checked up front and treated as run-aborting.

    Wraps any failure from the rapidocr/onnxruntime stack in OCRRunError: at
    this boundary with a third-party library whose exception surface is not
    fully enumerable, broad exception handling is deliberate, matching
    the same reasoning used at other external-tool/library boundaries."""
    try:
        from rapidocr import RapidOCR  # imported lazily: this module must be importable even when rapidocr isn't installed
        return RapidOCR()
    except Exception as exc:  # noqa: BLE001 -- third-party boundary, see docstring
        raise OCRRunError(f"Could not load the RapidOCR engine: {exc}") from exc


def run_ocr(engine: Any, image_path: Path) -> tuple[str, float]:
    """Run one already-loaded RapidOCR engine on one image, returning
    (joined_text, mean_confidence).

    RapidOCR's own result object (RapidOCROutput) exposes `.txts` (a tuple of
    one recognized string per detected text box) and `.scores` (matching
    per-box confidences, 0..1) when at least one box is detected, but BOTH
    become None -- not empty tuples -- when zero text is detected (verified
    against the actually-installed rapidocr 3.9.1: a blank/textless image
    logs "The text detection result is empty" and returns
    txts=None/scores=None). That None case is treated here as "ran cleanly,
    found nothing" -> ("", 1.0), not as a failure: confidence 1.0 signals
    "fully confident there is no text here", as opposed to the low
    real-valued confidences OCRService.min_confidence filters out for actual
    (mis-)recognized text.

    Wraps any failure from the rapidocr/onnxruntime stack in OCRRunError,
    same reasoning as load_engine()."""
    try:
        result = engine(str(image_path))
    except Exception as exc:  # noqa: BLE001 -- third-party boundary, see docstring
        raise OCRRunError(f"RapidOCR failed on {image_path}: {exc}") from exc

    if not result.txts:
        return "", 1.0

    text = "\n".join(result.txts)
    confidence = sum(result.scores) / len(result.scores)
    return text, confidence
