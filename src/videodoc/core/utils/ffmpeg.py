from __future__ import annotations

import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    """Raised when ffmpeg fails to extract audio from a single video file.

    Deliberately NOT a VideoDocError: this is a per-item failure that the
    caller (AudioExtractionService) always catches and folds into a
    per-video error list, never lets propagate to the CLI layer -- the same
    role VideoProbeError plays for a single unprobeable video. Availability
    of the ffmpeg binary itself is a separate, structural concern checked
    once up front by the caller via shutil.which."""


def extract_audio(video_path: Path, output_path: Path) -> None:
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
    auto-detection relies on the final path component's suffix."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", "-f", "wav",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        raise AudioExtractionError(f"ffmpeg failed to extract audio from {video_path}: {exc}") from exc
