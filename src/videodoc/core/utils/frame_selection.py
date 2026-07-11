from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# README §18.3 -- words that, when they appear in a transcript segment,
# suggest something worth screenshotting (code, a command, an error...) is
# on screen during that segment. Hardcoded module constant, same precedent
# as core/storage/filesystem.py::DEFAULT_EXCLUDES: this is data the README
# itself specifies, not something a project needs to tune per-run.
KEYWORDS: tuple[str, ...] = (
    "codice", "comando", "terminale", "funzione", "classe", "file",
    "configurazione", "errore", "copiamo", "incolliamo", "eseguiamo",
)

# A scene-change or keyword timestamp within this many seconds of an
# already-kept candidate is considered "the same moment" and merged away
# rather than producing a near-duplicate frame.
MIN_FRAME_GAP_SECONDS = 2.0

# +/- window used both by core/utils/ffmpeg.py::extract_frames (to build its
# select filter) and by match_frames_to_candidates below (to associate an
# extracted frame's real pts back to the candidate that requested it) --
# defined once here so the two can never silently drift apart. Comfortably
# wider than a single frame period at any realistic frame rate (>=1 fps),
# so the requested moment is never missed, yet narrow enough that
# MIN_FRAME_GAP_SECONDS candidates never share a window.
FRAME_MATCH_WINDOW_SECONDS = 0.1

# Defensive cap: a pathological config (e.g. interval_seconds=1 on a very
# long video) should not be allowed to request tens of thousands of frames.
MAX_FRAMES_PER_VIDEO = 2000

INTERVAL_PRIORITY = 0
SCENE_PRIORITY = 1
KEYWORD_PRIORITY = 2


@dataclass(frozen=True)
class FrameCandidate:
    timestamp_seconds: float
    priority: int  # higher wins when two candidates fall within min_gap_seconds of each other


def select_frame_timestamps(
    duration_seconds: float,
    *,
    interval_seconds: int,
    scene_timestamps: Sequence[float] = (),
    keyword_timestamps: Sequence[float] = (),
    min_gap_seconds: float = MIN_FRAME_GAP_SECONDS,
    max_frames: int = MAX_FRAMES_PER_VIDEO,
) -> list[FrameCandidate]:
    """Merge the fixed-interval baseline with optional scene-change and
    keyword-boosted timestamps into one sorted, deduplicated candidate list.

    The interval grid is always included -- it is the guaranteed pacing
    baseline (README §18.1). Scene/keyword timestamps are additive boosts
    the caller passes in only when their respective config flags are on and
    (for keywords) a transcript is actually available.
    """
    candidates = [
        FrameCandidate(t, INTERVAL_PRIORITY)
        for t in _interval_grid(duration_seconds, interval_seconds)
    ]
    candidates += [FrameCandidate(t, SCENE_PRIORITY) for t in scene_timestamps]
    candidates += [FrameCandidate(t, KEYWORD_PRIORITY) for t in keyword_timestamps]
    candidates.sort(key=lambda c: c.timestamp_seconds)

    merged = _merge_by_min_gap(candidates, min_gap_seconds)
    return _apply_max_frames(merged, max_frames)


def _interval_grid(duration_seconds: float, interval_seconds: int) -> list[float]:
    if duration_seconds <= 0 or interval_seconds <= 0:
        return []
    count = int(duration_seconds // interval_seconds) + 1
    return [i * interval_seconds for i in range(count) if i * interval_seconds < duration_seconds]


def _merge_by_min_gap(candidates: list[FrameCandidate], min_gap_seconds: float) -> list[FrameCandidate]:
    """Sweep chronologically; a candidate within min_gap_seconds of the last
    *kept* candidate is dropped, unless it has strictly higher priority, in
    which case it replaces the kept one. Ties (equal priority, within the
    gap) keep the earlier timestamp, since candidates arrive sorted and the
    earlier one was already kept."""
    kept: list[FrameCandidate] = []
    for candidate in candidates:
        if kept and candidate.timestamp_seconds - kept[-1].timestamp_seconds < min_gap_seconds:
            if candidate.priority > kept[-1].priority:
                kept[-1] = candidate
            continue
        kept.append(candidate)
    return kept


def _apply_max_frames(candidates: list[FrameCandidate], max_frames: int) -> list[FrameCandidate]:
    if len(candidates) <= max_frames:
        return candidates
    # Keep the highest-priority candidates first, then fill remaining slots
    # in chronological order -- a defensive cap not expected to trigger for
    # normal technical-video lengths.
    by_priority = sorted(candidates, key=lambda c: (-c.priority, c.timestamp_seconds))
    kept = by_priority[:max_frames]
    return sorted(kept, key=lambda c: c.timestamp_seconds)


def match_frames_to_candidates(
    candidates: Sequence[FrameCandidate],
    extracted: Sequence[tuple[float, Path]],
    *,
    window_seconds: float = FRAME_MATCH_WINDOW_SECONDS,
) -> list[tuple[FrameCandidate, float, Path]]:
    """Associate each candidate with the extracted (pts, path) frame closest
    to its requested timestamp, among those within window_seconds.

    ffmpeg's select filter (core/utils/ffmpeg.py::extract_frames) can return
    more than one real frame per requested window (e.g. a high-fps source
    where several frames fall within +/-window_seconds), since between(...)
    matches every frame in range, not just the nearest -- this function is
    what reduces that back down to one frame per candidate. A candidate with
    no frame in range (e.g. a timestamp past the last decodable frame) is
    simply dropped, not an error: the caller ends up with one frame fewer
    than requested, not a failed video.

    Both candidates and extracted are assumed sorted by timestamp (the
    caller already sorts both). Since MIN_FRAME_GAP_SECONDS (candidate
    spacing) is always >> 2*window_seconds (window width), windows around
    distinct candidates never overlap, so a two-pointer sweep is safe: no
    extracted frame can legitimately belong to more than one candidate."""
    extracted_sorted = sorted(extracted, key=lambda pair: pair[0])
    matched: list[tuple[FrameCandidate, float, Path]] = []
    n = len(extracted_sorted)
    idx = 0
    for candidate in candidates:
        while idx < n and extracted_sorted[idx][0] < candidate.timestamp_seconds - window_seconds:
            idx += 1
        best: tuple[float, Path] | None = None
        best_distance: float | None = None
        j = idx
        while j < n and extracted_sorted[j][0] <= candidate.timestamp_seconds + window_seconds:
            distance = abs(extracted_sorted[j][0] - candidate.timestamp_seconds)
            if best_distance is None or distance < best_distance:
                best, best_distance = extracted_sorted[j], distance
            j += 1
        if best is not None:
            matched.append((candidate, best[0], best[1]))
    return matched


def extract_keyword_timestamps(segments: Sequence[tuple[float, float, str]]) -> list[float]:
    """Given (start_seconds, end_seconds, text) transcript segments, return
    the midpoint timestamp of every segment whose text contains at least one
    of KEYWORDS (case-insensitive substring match). Plain substring matching
    is deliberate: these are common Italian words, not code identifiers that
    need word-boundary precision, and README §18.3 itself only asks for
    "quando nella trascrizione compaiono parole come...", not exact tokens."""
    timestamps = []
    for start, end, text in segments:
        lowered = text.lower()
        if any(keyword in lowered for keyword in KEYWORDS):
            timestamps.append((start + end) / 2)
    return timestamps
