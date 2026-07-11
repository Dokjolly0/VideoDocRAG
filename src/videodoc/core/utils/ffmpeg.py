from __future__ import annotations

import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Callable, Sequence

from videodoc.core.utils.frame_selection import FRAME_MATCH_WINDOW_SECONDS
from videodoc.core.utils.gpu import probe_gpu


class AudioExtractionError(Exception):
    """Raised when ffmpeg fails to extract audio from a single video file.

    Deliberately NOT a VideoDocError: this is a per-item failure that the
    caller (AudioExtractionService) always catches and folds into a
    per-video error list, never lets propagate to the CLI layer. Availability
    of the ffmpeg binary itself is a separate, structural concern checked
    once up front by the caller via shutil.which.
    """


_FFMPEG_ARGS = ("-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-f", "wav")


def extract_audio(
    video_path: Path,
    output_path: Path,
    *,
    total_duration_seconds: float | None = None,
    progress_callback: Callable[[float], None] | None = None,
    threads: int | None = None,
) -> None:
    """Extract mono 16kHz PCM WAV audio from video_path into output_path."""
    thread_args = _thread_args(threads)
    if progress_callback is not None and total_duration_seconds:
        _extract_audio_with_progress(video_path, output_path, total_duration_seconds, progress_callback, thread_args)
        return

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), *thread_args, *_FFMPEG_ARGS, str(output_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        raise AudioExtractionError(f"ffmpeg failed to extract audio from {video_path}: {exc}") from exc


def _extract_audio_with_progress(
    video_path: Path,
    output_path: Path,
    total_duration_seconds: float,
    progress_callback: Callable[[float], None],
    thread_args: tuple[str, ...],
) -> None:
    """Stream ffmpeg progress lines and forward a 0..1 completion fraction."""
    try:
        process = subprocess.Popen(
            [
                "ffmpeg", "-y", "-i", str(video_path), *thread_args, *_FFMPEG_ARGS,
                "-progress", "pipe:1", "-nostats", str(output_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise AudioExtractionError(f"ffmpeg failed to extract audio from {video_path}: {exc}") from exc

    assert process.stdout is not None
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key != "out_time_ms":
            continue
        try:
            out_time_ms = int(value)
        except ValueError:
            continue
        progress_callback(min(1.0, out_time_ms / 1_000_000 / total_duration_seconds))

    stderr_output = process.stderr.read() if process.stderr is not None else ""
    returncode = process.wait()
    if returncode != 0:
        raise AudioExtractionError(
            f"ffmpeg failed to extract audio from {video_path}: exit code {returncode}: {stderr_output.strip()}"
        )


def _thread_args(threads: int | None) -> tuple[str, ...]:
    if threads is None:
        return ()
    if threads <= 0:
        raise ValueError("threads must be a positive integer")
    return ("-threads", str(threads))


class FrameExtractionError(Exception):
    """Raised when ffmpeg fails to extract frames from a single video file."""


def extract_frames(
    video_path: Path,
    output_dir: Path,
    timestamps: Sequence[float],
    *,
    threads: int | None = None,
    hwaccel: str = "none",
) -> list[tuple[float, Path]]:
    """Extract one frame per timestamp in a single ffmpeg invocation.

    ``hwaccel='cuda'`` only changes the decoder path by adding
    ``-hwaccel cuda`` before ``-i``. The selection filter, showinfo parsing,
    JPEG quality, and frame matching contract stay identical.
    """
    if not timestamps:
        return []
    if hwaccel not in {"none", "cuda"}:
        raise ValueError("hwaccel must be 'none' or 'cuda'")

    thread_args = _thread_args(threads)
    pattern = output_dir / "frame_%05d.jpg"
    select_expr = "+".join(
        f"between(t\\,{max(0.0, t - FRAME_MATCH_WINDOW_SECONDS)}\\,{t + FRAME_MATCH_WINDOW_SECONDS})"
        for t in sorted(timestamps)
    )
    filter_script = output_dir / "select.filter"
    filter_script.write_text(f"select='{select_expr}',showinfo", encoding="utf-8")

    command = ["ffmpeg", "-y"]
    if hwaccel == "cuda":
        command.extend(["-hwaccel", "cuda"])
    command.extend(
        [
            "-i", str(video_path), *thread_args,
            "-filter_script:v", str(filter_script), "-vsync", "vfr", "-qscale:v", "2",
            str(pattern),
        ]
    )

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        stderr = result.stderr
    except subprocess.CalledProcessError as exc:
        raise FrameExtractionError(f"ffmpeg failed to extract frames from {video_path}: {exc.stderr.strip()}") from exc
    except OSError as exc:
        raise FrameExtractionError(f"ffmpeg failed to extract frames from {video_path}: {exc}") from exc
    finally:
        filter_script.unlink(missing_ok=True)

    pts_values = _parse_showinfo_pts(stderr)
    output_files = sorted(output_dir.glob("frame_*.jpg"))
    if len(pts_values) != len(output_files):
        raise FrameExtractionError(
            f"ffmpeg produced {len(output_files)} frame(s) but showinfo reported {len(pts_values)} "
            f"timestamp(s) for {video_path} -- cannot reliably match frames to timestamps."
        )
    return list(zip(pts_values, output_files))


@lru_cache(maxsize=1)
def ffmpeg_cuda_available() -> bool:
    """Return True only when ffmpeg and the host expose CUDA decoding."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-hwaccels"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False

    if re.search(r"(?m)^\s*cuda\s*$", result.stdout) is None:
        return False

    try:
        return probe_gpu() is not None
    except Exception:
        return False


def _parse_showinfo_pts(stderr: str) -> list[float]:
    return [float(m.group(1)) for m in re.finditer(r"pts_time:(\d+(?:\.\d+)?)", stderr)]