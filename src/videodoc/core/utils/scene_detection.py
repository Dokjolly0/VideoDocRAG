from __future__ import annotations

import importlib.util
from pathlib import Path

# PySceneDetect's own default ContentDetector threshold (0..255 scale on
# frame-to-frame content difference) -- not the same scale as ffmpeg's own
# 0..1 "scene" filter score, since this project uses PySceneDetect's
# detector directly rather than ffmpeg's scene filter.
SCENE_DETECTOR_THRESHOLD = 27.0


class SceneDetectionError(Exception):
    """Raised when PySceneDetect fails on a single video (corrupt file,
    unsupported codec for the video backend, etc.).

    Deliberately NOT a VideoDocError: this is a per-item failure the caller
    (FrameExtractionService) always folds into a per-video error, never lets
    propagate to the CLI layer -- same role as AudioExtractionError.
    Whether the 'scenedetect' package is even importable at all is a
    separate, structural concern checked once up front by the caller via
    scenedetect_available()."""


def scenedetect_available() -> bool:
    """Cheap one-time check for whether 'scenedetect' (and, transitively,
    its video backend) can be imported at all -- checked once per run by the
    caller, not once per video, mirroring shutil.which("ffmpeg") in
    AudioExtractionService. Uses find_spec instead of a real import so it
    never pays the cost of actually loading OpenCV just to answer "is it
    there"."""
    return importlib.util.find_spec("scenedetect") is not None


def detect_scene_timestamps(video_path: Path, *, threshold: float = SCENE_DETECTOR_THRESHOLD) -> list[float]:
    """Return the start timestamp (seconds) of every detected scene except
    the first -- the first scene always starts at t=0, which is redundant
    with the interval grid's own first frame and carries no "something
    changed here" signal.

    Assumes scenedetect_available() has already been checked by the caller.
    Wraps any failure from the scenedetect/OpenCV stack (corrupt file,
    unsupported codec, decode error) in SceneDetectionError: at this
    boundary with a third-party library whose exception surface is not
    fully enumerable, broad exception handling is deliberate, matching how
    extract_audio wraps subprocess/OSError at the ffmpeg boundary."""
    from scenedetect import ContentDetector, detect  # imported lazily: this module must be importable even when scenedetect isn't installed

    try:
        scenes = detect(str(video_path), ContentDetector(threshold=threshold))
    except Exception as exc:  # noqa: BLE001 -- third-party boundary, see docstring
        raise SceneDetectionError(f"scenedetect failed on {video_path}: {exc}") from exc

    return [start.seconds for start, _end in scenes[1:]]
