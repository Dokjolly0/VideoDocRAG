from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class VideoProbeError(Exception):
    """Raised when ffprobe fails to produce usable metadata for a single video file.

    Deliberately NOT a VideoDocError: this is a per-item failure that the
    caller (VideoIngestionService) always catches and folds into a
    per-video error list, never lets propagate to the CLI layer -- the same
    role slugify()'s plain ValueError plays for a single unslugifiable
    name. Availability of the ffprobe binary itself is a separate,
    structural concern checked once up front by the caller via shutil.which
    and reported as the domain exception ExternalToolNotFoundError."""


@dataclass(frozen=True)
class VideoProbeResult:
    duration_seconds: float
    format_name: str
    width: int
    height: int
    codec_name: str


def probe_video(path: Path) -> VideoProbeResult:
    """Run ffprobe on a single video file and parse duration/format/resolution/codec.

    Assumes the ffprobe binary itself is present on PATH -- callers must
    check that once, up front (see core/services/ingest_service.py), not
    per file: a missing binary is a structural/environment problem, not a
    per-video one."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        raise VideoProbeError(f"ffprobe failed for {path}: {exc}") from exc

    try:
        data = json.loads(proc.stdout)
        video_stream = next(s for s in data["streams"] if s.get("codec_type") == "video")
        return VideoProbeResult(
            duration_seconds=float(data["format"]["duration"]),
            format_name=str(data["format"]["format_name"]),
            width=int(video_stream["width"]),
            height=int(video_stream["height"]),
            codec_name=str(video_stream["codec_name"]),
        )
    except StopIteration:
        raise VideoProbeError(f"no video stream found in ffprobe output for {path}") from None
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise VideoProbeError(f"could not parse ffprobe output for {path}: {exc}") from exc
