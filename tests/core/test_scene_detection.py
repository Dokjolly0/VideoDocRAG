import sys
import types

import pytest
import scenedetect as scenedetect_module
from scenedetect import FrameTimecode

import videodoc.core.utils.scene_detection as scene_detection_module
from videodoc.core.utils.scene_detection import SceneDetectionError, detect_scene_timestamps, scenedetect_available


def test_scenedetect_available_true_when_installed():
    assert scenedetect_available() is True


def test_scenedetect_available_false_when_not_importable(monkeypatch):
    monkeypatch.setattr(scene_detection_module.importlib.util, "find_spec", lambda name: None)
    assert scenedetect_available() is False


def test_detect_scene_timestamps_returns_seconds_excluding_first_scene(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")

    def fake_detect(path, detector):
        return [
            (FrameTimecode(0.0, fps=25.0), FrameTimecode(10.0, fps=25.0)),
            (FrameTimecode(10.0, fps=25.0), FrameTimecode(22.5, fps=25.0)),
        ]

    monkeypatch.setattr(scenedetect_module, "detect", fake_detect)
    assert detect_scene_timestamps(video) == [10.0]


def test_detect_scene_timestamps_no_cuts_returns_empty(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")

    def fake_detect(path, detector):
        return [(FrameTimecode(0.0, fps=25.0), FrameTimecode(30.0, fps=25.0))]

    monkeypatch.setattr(scenedetect_module, "detect", fake_detect)
    assert detect_scene_timestamps(video) == []


def test_detect_scene_timestamps_wraps_failure(tmp_path, monkeypatch):
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")

    def fake_detect(path, detector):
        raise RuntimeError("cannot open video")

    monkeypatch.setattr(scenedetect_module, "detect", fake_detect)
    with pytest.raises(SceneDetectionError):
        detect_scene_timestamps(video)


def test_detect_scene_timestamps_wraps_broken_install_import_error(tmp_path, monkeypatch):
    """Regression test: scenedetect_available() only confirms the package
    can be *located* (importlib.util.find_spec), not that it actually
    imports cleanly -- a broken/incompatible install (e.g. a corrupt or
    version-mismatched OpenCV wheel) is a real failure mode for exactly
    this dependency. detect_scene_timestamps must fold an ImportError at
    call time into SceneDetectionError, the same as any other failure,
    rather than letting it escape uncaught and crash the whole
    FrameExtractionService run instead of just this one video."""
    video = tmp_path / "a.mp4"
    video.write_bytes(b"fake")
    # A present-but-broken 'scenedetect' module: sys.modules already has an
    # entry for it (so it won't be re-executed), but it's missing
    # ContentDetector/detect entirely, so `from scenedetect import ...`
    # raises ImportError -- simulating a real broken install without
    # actually needing one.
    broken_module = types.ModuleType("scenedetect")
    monkeypatch.setitem(sys.modules, "scenedetect", broken_module)

    with pytest.raises(SceneDetectionError):
        detect_scene_timestamps(video)
