import math
import sys
import types

import pytest

from videodoc.core.utils.transcription import TranscriptionError, build_batched_pipeline, load_whisper_model, transcribe_audio


def _install_fake_faster_whisper(monkeypatch, model_cls, pipeline_cls=None):
    fake_module = types.SimpleNamespace(WhisperModel=model_cls)
    if pipeline_cls is not None:
        fake_module.BatchedInferencePipeline = pipeline_cls
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)


def test_load_whisper_model_success(monkeypatch):
    calls = []

    class FakeModel:
        def __init__(self, name):
            calls.append(name)

    _install_fake_faster_whisper(monkeypatch, FakeModel)

    model = load_whisper_model("tiny")
    assert isinstance(model, FakeModel)
    assert calls == ["tiny"]


def test_load_whisper_model_missing_package_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(TranscriptionError):
        load_whisper_model("tiny")


def test_load_whisper_model_instantiation_failure_raises(monkeypatch):
    class FailingModel:
        def __init__(self, name):
            raise RuntimeError("no network, could not download model")

    _install_fake_faster_whisper(monkeypatch, FailingModel)

    with pytest.raises(TranscriptionError):
        load_whisper_model("large-v3")


class _FakeSegment:
    def __init__(self, start, end, text, avg_logprob):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob


class _FakeModel:
    def __init__(self, segments, captured):
        self._segments = segments
        self._captured = captured

    def transcribe(self, audio_path, **kwargs):
        self._captured["audio_path"] = audio_path
        self._captured["kwargs"] = kwargs
        return iter(self._segments), object()


def test_transcribe_audio_happy_path(tmp_path):
    captured = {}
    segments = [
        _FakeSegment(0.0, 2.5, "  Ciao a tutti  ", -0.1),
        _FakeSegment(2.5, 5.0, "benvenuti nel corso", -0.05),
    ]
    model = _FakeModel(segments, captured)

    results = transcribe_audio(model, tmp_path / "a.wav", language="it", word_timestamps=True)

    assert len(results) == 2
    assert results[0].start_seconds == 0.0
    assert results[0].end_seconds == 2.5
    assert results[0].text == "Ciao a tutti"  # stripped
    assert results[0].confidence == pytest.approx(math.exp(-0.1))
    assert captured["audio_path"] == str(tmp_path / "a.wav")
    assert captured["kwargs"] == {
        "language": "it",
        "word_timestamps": True,
        "beam_size": 5,
        "best_of": 5,
        "vad_filter": False,
        "condition_on_previous_text": True,
    }


def test_transcribe_audio_drops_empty_and_whitespace_only_segments(tmp_path):
    """Regression test: a silence/music/non-speech interval can yield a
    segment with empty or whitespace-only text -- these must be dropped,
    not stored as empty-text rows in the JSON/DB."""
    segments = [
        _FakeSegment(0.0, 1.0, "   ", -0.1),
        _FakeSegment(1.0, 2.0, "", -0.1),
        _FakeSegment(2.0, 3.0, "  Ciao  ", -0.1),
    ]
    model = _FakeModel(segments, {})

    results = transcribe_audio(model, tmp_path / "a.wav", language="it", word_timestamps=False)
    assert len(results) == 1
    assert results[0].text == "Ciao"


def test_transcribe_audio_confidence_none_when_avg_logprob_missing(tmp_path):
    segments = [_FakeSegment(0.0, 1.0, "hello", None)]
    model = _FakeModel(segments, {})

    results = transcribe_audio(model, tmp_path / "a.wav", language="it", word_timestamps=False)
    assert results[0].confidence is None


def test_transcribe_audio_raises_on_failure_during_iteration(tmp_path):
    class RaisingModel:
        def transcribe(self, audio_path, **kwargs):
            def gen():
                yield _FakeSegment(0.0, 1.0, "ok", -0.1)
                raise RuntimeError("decoder crashed")

            return gen(), object()

    with pytest.raises(TranscriptionError):
        transcribe_audio(RaisingModel(), tmp_path / "a.wav", language="it", word_timestamps=False)


def test_transcribe_audio_raises_when_transcribe_call_itself_fails(tmp_path):
    class RaisingModel:
        def transcribe(self, audio_path, **kwargs):
            raise RuntimeError("corrupt audio file")

    with pytest.raises(TranscriptionError):
        transcribe_audio(RaisingModel(), tmp_path / "a.wav", language="it", word_timestamps=False)


class _FakeModelWithDuration:
    def __init__(self, segments, duration):
        self._segments = segments
        self._duration = duration

    def transcribe(self, audio_path, **kwargs):
        return iter(self._segments), types.SimpleNamespace(duration=self._duration)


def test_transcribe_audio_reports_progress_as_fraction_of_duration(tmp_path):
    segments = [
        _FakeSegment(0.0, 2.5, "Ciao", -0.1),
        _FakeSegment(2.5, 5.0, "benvenuti", -0.1),
    ]
    model = _FakeModelWithDuration(segments, duration=5.0)

    fractions = []
    transcribe_audio(
        model, tmp_path / "a.wav", language="it", word_timestamps=False,
        progress_callback=fractions.append,
    )

    assert fractions == [0.5, 1.0]


def test_transcribe_audio_progress_callback_not_required(tmp_path):
    """info without a usable duration (0/None) must never be divided by --
    progress_callback is simply never invoked, transcription still succeeds."""
    segments = [_FakeSegment(0.0, 1.0, "hi", -0.1)]
    model = _FakeModelWithDuration(segments, duration=0.0)

    fractions = []
    results = transcribe_audio(
        model, tmp_path / "a.wav", language="it", word_timestamps=False,
        progress_callback=fractions.append,
    )

    assert fractions == []
    assert len(results) == 1

def test_build_batched_pipeline_wraps_loaded_model(monkeypatch):
    wrapped = {}

    class FakeModel:
        pass

    class FakePipeline:
        def __init__(self, model):
            wrapped["model"] = model

    _install_fake_faster_whisper(monkeypatch, FakeModel, FakePipeline)
    model = FakeModel()

    pipeline = build_batched_pipeline(model)

    assert isinstance(pipeline, FakePipeline)
    assert wrapped["model"] is model


def test_transcribe_audio_batched_passes_batch_options(tmp_path):
    captured = {}
    segments = [_FakeSegment(0.0, 30.0, "Ciao", -0.1)]
    model = _FakeModelWithDuration(segments, duration=30.0)

    def transcribe(audio_path, **kwargs):
        captured["audio_path"] = audio_path
        captured["kwargs"] = kwargs
        return iter(segments), types.SimpleNamespace(duration=30.0)

    model.transcribe = transcribe

    results = transcribe_audio(
        model,
        tmp_path / "a.wav",
        language="it",
        word_timestamps=False,
        mode="batched",
        batch_size=8,
        beam_size=1,
        best_of=1,
        vad_filter=True,
        chunk_length_seconds=30,
        condition_on_previous_text=False,
    )

    assert len(results) == 1
    assert captured["kwargs"] == {
        "language": "it",
        "word_timestamps": False,
        "beam_size": 1,
        "best_of": 1,
        "vad_filter": True,
        "condition_on_previous_text": False,
        "chunk_length": 30,
        "batch_size": 8,
        "without_timestamps": True,
    }


def test_load_whisper_model_passes_runtime_kwargs(monkeypatch):
    captured = {}

    class FakeModel:
        def __init__(self, name, **kwargs):
            captured["name"] = name
            captured["kwargs"] = kwargs

    _install_fake_faster_whisper(monkeypatch, FakeModel)

    model = load_whisper_model("tiny", device="cpu", compute_type="int8", cpu_threads=2, num_workers=3)

    assert isinstance(model, FakeModel)
    assert captured == {
        "name": "tiny",
        "kwargs": {"device": "cpu", "compute_type": "int8", "cpu_threads": 2, "num_workers": 3},
    }
