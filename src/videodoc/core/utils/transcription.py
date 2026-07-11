from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal


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


def load_whisper_model(
    model_name: str,
    *,
    device: str | None = None,
    compute_type: str | None = None,
    cpu_threads: int | None = None,
    num_workers: int | None = None,
) -> Any:
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
    kwargs = {}
    if device is not None:
        kwargs["device"] = device
    if compute_type is not None:
        kwargs["compute_type"] = compute_type
    if cpu_threads is not None:
        kwargs["cpu_threads"] = cpu_threads
    if num_workers is not None:
        kwargs["num_workers"] = num_workers

    try:
        return WhisperModel(model_name, **kwargs)
    except Exception as exc:
        raise TranscriptionError(f"Could not load Whisper model '{model_name}': {exc}") from exc


def build_batched_pipeline(model: Any) -> Any:
    """Wrap a loaded WhisperModel in faster-whisper's batched pipeline."""
    try:
        from faster_whisper import BatchedInferencePipeline
    except ImportError as exc:
        raise TranscriptionError(f"faster-whisper batched pipeline is not importable: {exc}") from exc
    except AttributeError as exc:
        raise TranscriptionError("faster-whisper does not expose BatchedInferencePipeline") from exc

    try:
        return BatchedInferencePipeline(model)
    except Exception as exc:
        raise TranscriptionError(f"Could not initialize batched transcription pipeline: {exc}") from exc


def transcribe_audio(
    model: Any,
    audio_path: Path,
    *,
    language: str,
    word_timestamps: bool,
    mode: Literal["standard", "batched"] = "standard",
    batch_size: int | None = None,
    beam_size: int = 5,
    best_of: int = 5,
    vad_filter: bool = False,
    chunk_length_seconds: int | None = None,
    condition_on_previous_text: bool = True,
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
        kwargs: dict[str, Any] = {
            "language": language,
            "word_timestamps": word_timestamps,
            "beam_size": beam_size,
            "best_of": best_of,
            "vad_filter": vad_filter,
            "condition_on_previous_text": condition_on_previous_text,
        }
        if chunk_length_seconds is not None:
            kwargs["chunk_length"] = chunk_length_seconds
        if mode == "batched":
            if batch_size is not None:
                kwargs["batch_size"] = batch_size
            # Batched mode can still return chunk-level timestamps while
            # sampling text-only tokens, which is much faster than decoding
            # timestamp tokens or aligning word timestamps for every chunk.
            kwargs["without_timestamps"] = not word_timestamps

        segments_gen, info = model.transcribe(str(audio_path), **kwargs)
        duration = getattr(info, "duration", None)
        results = []
        for segment in segments_gen:
            if progress_callback is not None and duration:
                progress_callback(min(1.0, float(segment.end) / duration))
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
