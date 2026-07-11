from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from videodoc.core.utils.frame_selection import FRAME_MATCH_WINDOW_SECONDS


class AudioExtractionError(Exception):
    """Raised when ffmpeg fails to extract audio from a single video file.

    Deliberately NOT a VideoDocError: this is a per-item failure that the
    caller (AudioExtractionService) always catches and folds into a
    per-video error list, never lets propagate to the CLI layer -- the same
    role VideoProbeError plays for a single unprobeable video. Availability
    of the ffmpeg binary itself is a separate, structural concern checked
    once up front by the caller via shutil.which."""


_FFMPEG_ARGS = ("-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-f", "wav")


def extract_audio(
    video_path: Path,
    output_path: Path,
    *,
    total_duration_seconds: float | None = None,
    progress_callback: Callable[[float], None] | None = None,
    threads: int | None = None,
) -> None:
    """Extract mono 16kHz PCM WAV audio from video_path into output_path
    (README §16's exact invocation) -- the standard input format expected
    by speech-to-text models.

    Assumes the ffmpeg binary itself is present on PATH -- callers must
    check that once, up front (see core/services/audio_extraction_service.py),
    not per file. -y overwrites output_path without an interactive prompt:
    by the time this runs, the caller has already decided overwriting is
    intended (it always targets a disposable *.tmp path, never the final
    artifact directly -- see AudioExtractionService for why). -f wav is
    explicit rather than inferred from output_path's extension, since the
    caller's temporary path ends in .tmp, not .wav, and ffmpeg's format
    auto-detection relies on the final path component's suffix.

    progress_callback is only honored when total_duration_seconds is also
    given (it's what turns ffmpeg's raw out_time_ms into a 0..1 fraction);
    without both, this falls back to the plain blocking invocation, since
    there's nothing meaningful to report."""
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
    """-progress pipe:1 -nostats makes ffmpeg emit machine-readable
    'key=value' progress lines on stdout (out_time_ms=... among them)
    instead of its normal human-readable stderr stats -- read line by line
    so the caller gets a live fraction instead of only finding out once the
    whole (potentially minutes-long) conversion has finished."""
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
    """Raised when ffmpeg fails to extract frames from a single video file.

    Deliberately NOT a VideoDocError, same role as AudioExtractionError: a
    per-item failure the caller (FrameExtractionService) always catches and
    folds into a per-video error list."""


def extract_frames(
    video_path: Path,
    output_dir: Path,
    timestamps: Sequence[float],
    *,
    threads: int | None = None,
) -> list[tuple[float, Path]]:
    """Extract one frame per timestamp in a single ffmpeg invocation (not one
    process per timestamp -- too much spawn overhead for the hundreds of
    timestamps a long technical video can produce).

    Builds a select='between(t,t0-w,t0+w)+between(t,t1-w,t1+w)+...' filter
    (window w = FRAME_MATCH_WINDOW_SECONDS, shared with
    frame_selection.match_frames_to_candidates so the two can never drift
    apart) combined with showinfo, so the actual
    pts_time of each written frame -- not just the requested target -- is
    parsed back out of stderr; this is the authoritative timestamp, robust
    to VFR sources where the nearest actual frame may not land exactly on
    the requested time. -vsync vfr keeps only the selected frames (no
    duplicate padding). The filter expression is written to a script file
    and passed via -filter_script:v rather than inline on the command line:
    with up to MAX_FRAMES_PER_VIDEO timestamps the inline expression could
    otherwise approach OS command-line length limits.

    output_dir is expected to already exist (the caller creates a per-video
    staging directory). Returns (pts_time, path) pairs in chronological
    output order -- output_dir must not already contain frame_*.jpg files
    from an unrelated previous run, or the count-matching integrity check
    below will spuriously fail."""
    if not timestamps:
        return []

    thread_args = _thread_args(threads)
    pattern = output_dir / "frame_%05d.jpg"
    select_expr = "+".join(
        f"between(t\\,{max(0.0, t - FRAME_MATCH_WINDOW_SECONDS)}\\,{t + FRAME_MATCH_WINDOW_SECONDS})"
        for t in sorted(timestamps)
    )
    filter_script = output_dir / "select.filter"
    filter_script.write_text(f"select='{select_expr}',showinfo", encoding="utf-8")

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path), *thread_args,
                "-filter_script:v", str(filter_script), "-vsync", "vfr", "-qscale:v", "2",
                str(pattern),
            ],
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


def _parse_showinfo_pts(stderr: str) -> list[float]:
    return [float(m.group(1)) for m in re.finditer(r"pts_time:(\d+(?:\.\d+)?)", stderr)]
