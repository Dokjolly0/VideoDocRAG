from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class TranscriptionError(Exception):
    """Raised when the faster-whisper engine cannot be loaded, or fails to
    transcribe a single audio file.

    Deliberately NOT a VideoDocError -- same per-item-failure rationale as
    AudioExtractionError/VideoProbeError: this module never raises a domain
    exception itself. The caller (TranscriptionService) decides whether a
    given failure is structural (model loading, translated into the domain
    TranscriptionEngineError) or per-item (a single file's transcription,
    folded into a per-video error list)."""


@dataclass(frozen=True)
class TranscriptSegmentResult:
    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None


def load_whisper_model(model_name: str) -> Any:
    """Lazily imports faster_whisper and instantiates WhisperModel(model_name).

    faster-whisper is a required dependency of this project (not an optional
    extra) -- the import is still deferred to inside this function purely to
    avoid paying its import cost (it pulls in ctranslate2/tokenizers) for
    every command that never transcribes anything, not because it might be
    missing. The try/except below is defensive (a broken/mismatched
    environment), not the expected path. Model instantiation itself can also
    fail (e.g. a first-time multi-GB download from Hugging Face failing due
    to no network) -- both failure modes are folded into TranscriptionError,
    which the caller translates into the structural, fatal
    TranscriptionEngineError (this loads once for an entire batch, never
    per-video, so a failure here can never be a per-item problem)."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(f"faster-whisper is not importable: {exc}") from exc
    try:
        return WhisperModel(model_name)
    except Exception as exc:
        raise TranscriptionError(f"Could not load Whisper model '{model_name}': {exc}") from exc


def transcribe_audio(
    model: Any,
    audio_path: Path,
    *,
    language: str,
    word_timestamps: bool,
    progress_callback: Callable[[float], None] | None = None,
) -> list[TranscriptSegmentResult]:
    """Transcribes a single audio file with an already-loaded model.

    model.transcribe() returns (segments, info): a lazy generator plus
    summary info. info.duration is the only field used -- language is
    forced by config, not auto-detected, so nothing else in info is needed
    here; it's what turns each segment's end timestamp into a 0..1 fraction
    for progress_callback. The generator is fully consumed inside the try
    block, since faster-whisper can raise mid-iteration, not only on the
    initial call.

    confidence is approximated as exp(avg_logprob) (avg_logprob is a
    log-probability, typically <= 0, so this lands in (0, 1]) -- faster-
    whisper does not expose a direct 0-1 "confidence" field itself."""
    try:
        segments_gen, info = model.transcribe(str(audio_path), language=language, word_timestamps=word_timestamps)
        results = []
        for segment in segments_gen:
            if progress_callback is not None and info.duration:
                progress_callback(min(1.0, float(segment.end) / info.duration))
            text = segment.text.strip()
            if not text:
                # A silence/music/non-speech interval can yield a segment
                # with empty or whitespace-only text -- dropped here so it
                # never pollutes the JSON file, project.db, or whatever
                # later consumes the transcript (retrieval, doc generation).
                continue
            avg_logprob = getattr(segment, "avg_logprob", None)
            confidence = math.exp(avg_logprob) if avg_logprob is not None else None
            results.append(
                TranscriptSegmentResult(
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=text,
                    confidence=confidence,
                )
            )
        return results
    except Exception as exc:
        raise TranscriptionError(f"Could not transcribe {audio_path}: {exc}") from exc
