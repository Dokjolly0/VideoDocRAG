from pathlib import Path

from videodoc.core.utils.frame_selection import (
    INTERVAL_PRIORITY,
    KEYWORD_PRIORITY,
    SCENE_PRIORITY,
    FrameCandidate,
    extract_keyword_timestamps,
    match_frames_to_candidates,
    select_frame_timestamps,
)


def test_interval_grid_covers_full_duration_excluding_endpoint():
    result = select_frame_timestamps(20.0, interval_seconds=8)
    assert [c.timestamp_seconds for c in result] == [0, 8, 16]
    assert all(c.priority == INTERVAL_PRIORITY for c in result)


def test_zero_or_negative_duration_produces_no_candidates():
    assert select_frame_timestamps(0.0, interval_seconds=8) == []
    assert select_frame_timestamps(-5.0, interval_seconds=8) == []


def test_scene_timestamp_merges_with_nearby_interval_tick():
    """A scene change 0.3s from an interval tick must collapse into one
    kept candidate (the higher-priority scene one), not two near-identical
    frames."""
    result = select_frame_timestamps(20.0, interval_seconds=8, scene_timestamps=[8.3])
    timestamps = [c.timestamp_seconds for c in result]
    assert 8.3 in timestamps
    assert 8 not in timestamps  # the interval tick was replaced, not kept alongside
    assert [c.priority for c in result if c.timestamp_seconds == 8.3] == [SCENE_PRIORITY]


def test_keyword_timestamp_never_loses_to_nearby_interval_tick():
    result = select_frame_timestamps(20.0, interval_seconds=8, keyword_timestamps=[8.1])
    kept = {c.timestamp_seconds: c.priority for c in result}
    assert kept[8.1] == KEYWORD_PRIORITY


def test_keyword_outranks_scene_within_gap():
    result = select_frame_timestamps(20.0, interval_seconds=8, scene_timestamps=[8.0], keyword_timestamps=[8.5])
    assert len(result) == 3  # 0, one of {8.0 or 8.5}, 16
    surviving = [c for c in result if 7 < c.timestamp_seconds < 9]
    assert len(surviving) == 1
    assert surviving[0].priority == KEYWORD_PRIORITY


def test_far_apart_candidates_are_all_kept():
    result = select_frame_timestamps(100.0, interval_seconds=8, scene_timestamps=[50.0], keyword_timestamps=[75.0])
    timestamps = [c.timestamp_seconds for c in result]
    assert 50.0 in timestamps
    assert 75.0 in timestamps


def test_max_frames_cap_keeps_higher_priority_first():
    # 5 interval ticks over a tiny max_frames budget of 2, plus one keyword hit --
    # the keyword candidate must survive the cap even though it's not first chronologically.
    result = select_frame_timestamps(
        40.0, interval_seconds=8, keyword_timestamps=[35.0], max_frames=2,
    )
    assert len(result) == 2
    assert any(c.priority == KEYWORD_PRIORITY for c in result)
    # still returned in chronological order
    assert result == sorted(result, key=lambda c: c.timestamp_seconds)


def test_extract_keyword_timestamps_matches_case_insensitive_substring():
    segments = [
        (0.0, 4.0, "Ciao a tutti, oggi vediamo un esempio."),
        (4.0, 10.0, "Ora apriamo il terminale e lanciamo il CODICE."),
        (10.0, 14.0, "Nient'altro di rilevante qui."),
    ]
    timestamps = extract_keyword_timestamps(segments)
    assert timestamps == [7.0]  # midpoint of the matching segment


def test_extract_keyword_timestamps_no_match_returns_empty():
    segments = [(0.0, 4.0, "Ciao a tutti, oggi vediamo un esempio.")]
    assert extract_keyword_timestamps(segments) == []


def test_match_frames_to_candidates_picks_nearest_within_window():
    candidates = [FrameCandidate(8.0, INTERVAL_PRIORITY)]
    extracted = [(7.95, Path("a.jpg")), (8.08, Path("b.jpg")), (20.0, Path("c.jpg"))]
    matched = match_frames_to_candidates(candidates, extracted, window_seconds=0.1)
    assert len(matched) == 1
    candidate, pts, path = matched[0]
    assert pts == 7.95  # closer to 8.0 than 8.08
    assert path == Path("a.jpg")


def test_match_frames_to_candidates_drops_unmatched_candidate():
    candidates = [FrameCandidate(8.0, INTERVAL_PRIORITY), FrameCandidate(50.0, INTERVAL_PRIORITY)]
    extracted = [(8.02, Path("a.jpg"))]  # nothing near 50.0
    matched = match_frames_to_candidates(candidates, extracted, window_seconds=0.1)
    assert len(matched) == 1
    assert matched[0][0].timestamp_seconds == 8.0


def test_match_frames_to_candidates_empty_extracted_returns_empty():
    candidates = [FrameCandidate(8.0, INTERVAL_PRIORITY)]
    assert match_frames_to_candidates(candidates, []) == []
