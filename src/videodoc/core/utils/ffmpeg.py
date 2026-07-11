from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable


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
    if progress_callback is not None and total_duration_seconds:
        _extract_audio_with_progress(video_path, output_path, total_duration_seconds, progress_callback)
        return

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), *_FFMPEG_ARGS, str(output_path)],
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
) -> None:
    """-progress pipe:1 -nostats makes ffmpeg emit machine-readable
    'key=value' progress lines on stdout (out_time_ms=... among them)
    instead of its normal human-readable stderr stats -- read line by line
    so the caller gets a live fraction instead of only finding out once the
    whole (potentially minutes-long) conversion has finished."""
    try:
        process = subprocess.Popen(
            [
                "ffmpeg", "-y", "-i", str(video_path), *_FFMPEG_ARGS,
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
