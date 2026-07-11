from __future__ import annotations

import re
import subprocess
import threading
from pathlib import Path
from typing import Callable

SCENE_DETECTOR_THRESHOLD = 0.10
_PTS_RE = re.compile(r"pts_time:(\d+(?:\.\d+)?)")


class SceneDetectionError(Exception):
    """Raised when ffmpeg scene detection fails on a single video.

    Deliberately NOT a VideoDocError: this is a per-item failure the caller
    (FrameExtractionService) folds into a per-video error, never lets
    propagate to the CLI layer -- same role as AudioExtractionError.
    """


def detect_scene_timestamps(
    video_path: Path,
    *,
    threshold: float = SCENE_DETECTOR_THRESHOLD,
    hwaccel: str = "none",
    threads: int | None = None,
    total_duration_seconds: float | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> list[float]:
    """Return scene-change timestamps detected by ffmpeg's scene filter.

    The scene score is on ffmpeg's native 0..1 scale. ffmpeg's
    ``gt(scene,threshold)`` does not emit the first frame merely because it
    starts at t=0, so unlike the previous scene wrapper there is no
    first-scene timestamp to drop.
    """
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if hwaccel not in {"none", "cuda"}:
        raise ValueError("hwaccel must be 'none' or 'cuda'")

    command = _scene_detection_command(video_path, threshold=threshold, hwaccel=hwaccel, threads=threads)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except OSError as exc:
        raise SceneDetectionError(f"ffmpeg failed to detect scenes in {video_path}: {exc}") from exc

    assert process.stdout is not None
    stderr_parts: list[str] = []
    stderr_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stderr, stderr_parts),
        daemon=True,
    )
    stderr_thread.start()

    timestamps: list[float] = []
    for line in process.stdout:
        match = _PTS_RE.search(line)
        if match is None:
            continue
        try:
            pts = float(match.group(1))
        except ValueError:
            continue
        timestamps.append(pts)
        if progress_callback is not None and total_duration_seconds:
            progress_callback(min(1.0, max(0.0, pts / total_duration_seconds)))

    returncode = process.wait()
    stderr_thread.join(timeout=1)
    stderr_output = "".join(stderr_parts).strip()
    if returncode != 0:
        raise SceneDetectionError(
            f"ffmpeg scene detection failed on {video_path}: exit code {returncode}: {_tail(stderr_output)}"
        )
    return timestamps


def _scene_detection_command(video_path: Path, *, threshold: float, hwaccel: str, threads: int | None) -> list[str]:
    threshold_text = f"{threshold:g}"
    command = ["ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error"]
    if hwaccel == "cuda":
        command.extend(["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"])
        scale_filter = "scale_cuda=320:-2,hwdownload,format=nv12"
    else:
        if threads is not None:
            if threads <= 0:
                raise ValueError("threads must be a positive integer")
            command.extend(["-threads", str(threads)])
        scale_filter = "scale=320:-2:flags=fast_bilinear"

    command.extend(
        [
            "-i", str(video_path),
            "-an", "-sn", "-dn",
            "-vf", f"{scale_filter},select=gt(scene\\,{threshold_text}),metadata=print:file=-",
            "-f", "null", "-",
        ]
    )
    return command


def _drain_stream(stream, sink: list[str]) -> None:
    if stream is None:
        return
    for line in stream:
        sink.append(line)


def _tail(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return "..." + text[-limit:]