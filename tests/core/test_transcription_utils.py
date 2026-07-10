import math
import sys
import types

import pytest

from videodoc.core.utils.transcription import TranscriptionError, load_whisper_model, transcribe_audio


def _install_fake_faster_whisper(monkeypatch, model_cls):
    fake_module = types.SimpleNamespace(WhisperModel=model_cls)
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
    assert captured["kwargs"] == {"language": "it", "word_timestamps": True}


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
