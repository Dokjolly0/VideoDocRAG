import contextlib
import json
import sqlite3
from pathlib import Path

import pytest

import videodoc.core.services.transcription_service as transcription_service_module
from videodoc.core.config import ProjectConfig
from videodoc.core.errors import DatabaseError, NoVideosFoundError, TranscriptionEngineError
from videodoc.core.models.transcript import Transcript, TranscriptSegment
from videodoc.core.models.video_metadata import VideoMetadata
from videodoc.core.services.transcription_service import TranscriptionService
from videodoc.core.storage.database import VideoRow, ensure_schema, upsert_video
from videodoc.core.storage.filesystem import ensure_video_workdir
from videodoc.core.utils.gpu import GpuInfo
from videodoc.core.utils.progress import ProgressReporter
from videodoc.core.utils.transcription import TranscriptSegmentResult, TranscriptionError


class _RecordingReporter(ProgressReporter):
    def __init__(self):
        self.announced = []

    def announce(self, message):
        self.announced.append(message)


def _config():
    return ProjectConfig.default(name="Demo", slug="demo")


def _seed_video(project_dir, config, video_id="demo", filename="Demo.mp4", with_audio=True):
    """Reproduces the on-disk/DB state left behind by ingest (+ extract-audio
    when with_audio=True), without invoking those services -- keeps these
    tests focused on TranscriptionService's own behavior."""
    db_path = project_dir / config.paths.database
    ensure_schema(db_path)

    video_path = project_dir / "videos" / filename
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake video")

    upsert_video(
        db_path,
        VideoRow(
            id=video_id, filename=filename, title=None, duration_seconds=10.0,
            file_hash="hash123", path=video_path.resolve().as_posix(),
            created_at="2026-01-01T00:00:00+00:00",
        ),
    )

    video_dir = project_dir / config.paths.workdir / video_id
    ensure_video_workdir(video_dir)
    workdir_rel = Path(config.paths.workdir) / video_id

    audio_rel = workdir_rel / "audio"
    if with_audio:
        (video_dir / "audio" / f"{video_id}.wav").write_bytes(b"RIFF....")
        audio_rel = workdir_rel / "audio" / f"{video_id}.wav"

    VideoMetadata(
        video_id=video_id, video_name=filename, title=None, duration_seconds=10.0,
        language="it", hash="hash123", format="mov,mp4", width=1280, height=720, codec="h264",
        audio_path=audio_rel.as_posix(),
        transcript_path=(workdir_rel / "transcript").as_posix(),
        frames_path=(workdir_rel / "frames").as_posix(),
        ocr_path=(workdir_rel / "ocr").as_posix(),
        chunks_path=(workdir_rel / "chunks").as_posix(),
    ).save(video_dir / "metadata.json")
    return video_path, video_dir


def _fake_results():
    return [
        TranscriptSegmentResult(start_seconds=0.0, end_seconds=2.5, text="Ciao a tutti", confidence=0.9),
        TranscriptSegmentResult(start_seconds=2.5, end_seconds=5.0, text="benvenuti", confidence=0.8),
    ]


def _rtx4070(free_vram_mb=7301):
    return GpuInfo(
        name="NVIDIA GeForce RTX 4070 Laptop GPU",
        total_vram_mb=8188,
        free_vram_mb=free_vram_mb,
        compute_capability=(8, 9),
        driver_version="555.99",
        source="nvml",
    )


def _stub_load_model(monkeypatch, fn=None):
    def default(model_name, **kwargs):
        return object()

    monkeypatch.setattr(transcription_service_module, "load_whisper_model", fn or default)


def _stub_transcribe(monkeypatch, fn=None):
    def default(model, audio_path, *, language, word_timestamps, progress_callback=None, **kwargs):
        return _fake_results()

    monkeypatch.setattr(transcription_service_module, "transcribe_audio", fn or default)


def test_no_project_db_raises_and_creates_nothing(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()

    with pytest.raises(NoVideosFoundError):
        TranscriptionService(project_dir, _config()).run()

    assert not (project_dir / "project.db").exists()


def test_empty_project_db_raises(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    ensure_schema(project_dir / "project.db")

    with pytest.raises(NoVideosFoundError):
        TranscriptionService(project_dir, _config()).run()


def test_project_db_as_directory_raises_database_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    (project_dir / "project.db").mkdir()

    with pytest.raises(DatabaseError):
        TranscriptionService(project_dir, _config()).run()


def test_zero_videos_have_audio_raises_no_videos_found(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    _seed_video(project_dir, _config(), with_audio=False)

    with pytest.raises(NoVideosFoundError):
        TranscriptionService(project_dir, _config()).run()


def test_some_videos_missing_audio_is_per_item_not_fatal(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, video_id="noaudio", filename="NoAudio.mp4", with_audio=False)
    _seed_video(project_dir, config, video_id="hasaudio", filename="HasAudio.mp4", with_audio=True)
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ("hasaudio",)
    assert any("noaudio" in e for e in result.errors)


def test_unsupported_engine_raises_transcription_engine_error(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    config = config.model_copy(update={"transcription": config.transcription.model_copy(update={"engine": "whisper.cpp"})})

    with pytest.raises(TranscriptionEngineError):
        TranscriptionService(project_dir, config).run()


def test_model_load_failure_raises_transcription_engine_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)

    def failing_load(model_name, **kwargs):
        raise TranscriptionError("no network")

    _stub_load_model(monkeypatch, failing_load)

    with pytest.raises(TranscriptionEngineError):
        TranscriptionService(project_dir, config).run()


def test_model_not_loaded_when_everything_already_transcribed(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)

    transcript = Transcript(
        video_id="demo", engine="faster-whisper", model="tiny", language="it",
        segments=[TranscriptSegment(id="demo_seg_0000", start_seconds=0.0, end_seconds=1.0, text="hi", confidence=0.9)],
    )
    transcript.save(video_dir / "transcript" / "demo.json")

    call_count = {"n": 0}
    _stub_load_model(monkeypatch, lambda model_name: call_count.__setitem__("n", call_count["n"] + 1))

    result = TranscriptionService(project_dir, config).run()

    assert call_count["n"] == 0
    assert result.skipped == ("demo",)


def test_announces_before_loading_model_when_needed(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    reporter = _RecordingReporter()
    TranscriptionService(project_dir, config).run(progress=reporter)

    assert any(config.transcription.model in message for message in reporter.announced)


def test_does_not_announce_when_everything_already_transcribed(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    transcript = Transcript(
        video_id="demo", engine="faster-whisper", model="tiny", language="it",
        segments=[TranscriptSegment(id="demo_seg_0000", start_seconds=0.0, end_seconds=1.0, text="hi", confidence=0.9)],
    )
    transcript.save(video_dir / "transcript" / "demo.json")
    _stub_load_model(monkeypatch, lambda model_name: (_ for _ in ()).throw(AssertionError("model should not load")))

    reporter = _RecordingReporter()
    result = TranscriptionService(project_dir, config).run(progress=reporter)

    assert result.skipped == ("demo",)
    assert reporter.announced == []



def test_cuda_auto_uses_batched_pipeline_and_runtime_options(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    config = config.model_copy(update={
        "transcription": config.transcription.model_copy(update={"device": "cuda", "mode": "auto"})
    })
    _seed_video(project_dir, config)

    loaded_model = object()
    batched_pipeline = object()
    captured = {}

    def load_model(model_name, **kwargs):
        captured["model_name"] = model_name
        captured["load_kwargs"] = kwargs
        return loaded_model

    def build_pipeline(model):
        captured["pipeline_model"] = model
        return batched_pipeline

    def fake_transcribe(engine, audio_path, **kwargs):
        captured["engine"] = engine
        captured["transcribe_kwargs"] = kwargs
        return _fake_results()

    monkeypatch.setattr(transcription_service_module, "load_whisper_model", load_model)
    monkeypatch.setattr(transcription_service_module, "build_batched_pipeline", build_pipeline)
    monkeypatch.setattr(transcription_service_module, "transcribe_audio", fake_transcribe)
    monkeypatch.setattr(transcription_service_module, "probe_gpu", lambda: _rtx4070())

    reporter = _RecordingReporter()
    result = TranscriptionService(project_dir, config).run(progress=reporter)

    assert result.transcribed == ("demo",)
    assert captured["model_name"] == "large-v3"
    assert captured["load_kwargs"]["device"] == "cuda"
    assert captured["load_kwargs"]["compute_type"] == "int8_float16"
    assert captured["load_kwargs"]["num_workers"] == 1
    assert captured["pipeline_model"] is loaded_model
    assert captured["engine"] is batched_pipeline
    assert captured["transcribe_kwargs"]["mode"] == "batched"
    assert captured["transcribe_kwargs"]["batch_size"] == 19
    assert captured["transcribe_kwargs"]["beam_size"] == 1
    assert captured["transcribe_kwargs"]["word_timestamps"] is False
    assert captured["transcribe_kwargs"]["vad_filter"] is True
    assert captured["transcribe_kwargs"]["chunk_length_seconds"] == 30
    assert "7301 MiB dedicated free" in reporter.announced[0]


def test_cuda_model_load_oom_downgrades_auto_compute_type(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    config = config.model_copy(update={
        "transcription": config.transcription.model_copy(update={"device": "cuda", "mode": "auto"})
    })
    _seed_video(project_dir, config)

    load_compute_types = []

    def load_model(model_name, **kwargs):
        load_compute_types.append(kwargs["compute_type"])
        if len(load_compute_types) == 1:
            raise TranscriptionError("CUDA out of memory while loading")
        return "loaded-model"

    monkeypatch.setattr(transcription_service_module, "probe_gpu", lambda: _rtx4070(free_vram_mb=12000))
    monkeypatch.setattr(transcription_service_module, "load_whisper_model", load_model)
    monkeypatch.setattr(transcription_service_module, "build_batched_pipeline", lambda model: "batched-pipeline")
    monkeypatch.setattr(transcription_service_module, "transcribe_audio", lambda model, audio_path, **kwargs: _fake_results())

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ("demo",)
    assert load_compute_types == ["float16", "int8_float16"]


def test_cuda_preflight_oom_halves_auto_batch(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    config = config.model_copy(update={
        "transcription": config.transcription.model_copy(update={"device": "cuda", "mode": "auto"})
    })
    _seed_video(project_dir, config)
    batches = []

    def transcribe(model, audio_path, **kwargs):
        batches.append(kwargs["batch_size"])
        if len(batches) == 1:
            raise TranscriptionError("CUDA out of memory during transcription")
        return _fake_results()

    _stub_load_model(monkeypatch)
    monkeypatch.setattr(transcription_service_module, "probe_gpu", lambda: _rtx4070())
    monkeypatch.setattr(transcription_service_module, "build_batched_pipeline", lambda model: model)
    monkeypatch.setattr(transcription_service_module, "transcribe_audio", transcribe)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ("demo",)
    assert batches == [19, 9]


def test_cuda_remaining_item_oom_retries_once_with_half_batch(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    config = config.model_copy(update={
        "transcription": config.transcription.model_copy(update={"device": "cuda", "mode": "auto"})
    })
    _seed_video(project_dir, config, video_id="alpha", filename="Alpha.mp4")
    _seed_video(project_dir, config, video_id="bravo", filename="Bravo.mp4")
    calls = []
    bravo_attempts = {"n": 0}

    def transcribe(model, audio_path, **kwargs):
        calls.append((audio_path.name, kwargs["batch_size"]))
        if audio_path.name == "bravo.wav":
            bravo_attempts["n"] += 1
            if bravo_attempts["n"] == 1:
                raise TranscriptionError("CUDA out of memory during transcription")
        return _fake_results()

    _stub_load_model(monkeypatch)
    monkeypatch.setattr(transcription_service_module, "probe_gpu", lambda: _rtx4070())
    monkeypatch.setattr(transcription_service_module, "build_batched_pipeline", lambda model: model)
    monkeypatch.setattr(transcription_service_module, "transcribe_audio", transcribe)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ("alpha", "bravo")
    assert ("bravo.wav", 19) in calls
    assert ("bravo.wav", 9) in calls


def test_cuda_explicit_runtime_oom_reports_actionable_hint(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    config = config.model_copy(update={
        "transcription": config.transcription.model_copy(update={
            "device": "cuda",
            "compute_type": "float16",
            "mode": "batched",
            "batch_size": 4,
        })
    })
    _seed_video(project_dir, config)

    _stub_load_model(monkeypatch)
    monkeypatch.setattr(transcription_service_module, "probe_gpu", lambda: _rtx4070())
    monkeypatch.setattr(transcription_service_module, "build_batched_pipeline", lambda model: model)
    monkeypatch.setattr(
        transcription_service_module,
        "transcribe_audio",
        lambda model, audio_path, **kwargs: (_ for _ in ()).throw(TranscriptionError("CUDA out of memory")),
    )

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ()
    assert "set transcription.batch_size" in result.errors[0]

def test_single_video_transcribed_updates_metadata_and_db(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ("demo",)
    transcript_path = video_dir / "transcript" / "demo.json"
    assert transcript_path.is_file()

    transcript = Transcript.load(transcript_path)
    assert len(transcript.segments) == 2
    assert transcript.segments[0].id == "demo_seg_0000"
    assert transcript.segments[1].id == "demo_seg_0001"

    metadata = json.loads((video_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["transcript_path"] == "workdir/demo/transcript/demo.json"

    with contextlib.closing(sqlite3.connect(project_dir / "project.db")) as conn, conn:
        rows = conn.execute("SELECT id FROM transcript_segments WHERE video_id = 'demo' ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["demo_seg_0000", "demo_seg_0001"]


def test_transcribes_against_pre_existing_db_missing_transcript_segments_table(tmp_path, monkeypatch):
    """Regression test: a project.db created before this feature shipped
    (or by an older ingest run) only has the videos table -- transcribe
    must provision transcript_segments itself (ensure_schema is idempotent)
    rather than assuming an earlier ensure_schema() call already did it,
    or every DB write fails with 'no such table: transcript_segments' and
    never recovers, even on rerun."""
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)

    # Simulate a pre-Step-5 project.db: _seed_video's own ensure_schema()
    # call already created transcript_segments too (it's idempotent and
    # now provisions both tables), so drop it back out to reproduce the
    # actual pre-existing state this regression covers.
    db_path = project_dir / "project.db"
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("DROP TABLE transcript_segments")
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    assert {t[0] for t in tables} == {"videos"}  # confirms the simulated pre-existing state

    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ("demo",)
    with contextlib.closing(sqlite3.connect(db_path)) as conn, conn:
        rows = conn.execute("SELECT id FROM transcript_segments WHERE video_id = 'demo'").fetchall()
    assert len(rows) == 2


def test_skip_when_transcript_exists_call_count_zero(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config)
    _stub_load_model(monkeypatch)

    call_count = {"n": 0}

    def counting_transcribe(model, audio_path, *, language, word_timestamps, progress_callback=None, **kwargs):
        call_count["n"] += 1
        return _fake_results()

    _stub_transcribe(monkeypatch, counting_transcribe)
    TranscriptionService(project_dir, config).run()
    assert call_count["n"] == 1

    result = TranscriptionService(project_dir, config).run()
    assert result.skipped == ("demo",)
    assert call_count["n"] == 1


def test_skip_self_heals_after_prior_db_failure(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)

    transcript = Transcript(
        video_id="demo", engine="faster-whisper", model="tiny", language="it",
        segments=[TranscriptSegment(id="demo_seg_0000", start_seconds=0.0, end_seconds=1.0, text="hi", confidence=0.9)],
    )
    transcript.save(video_dir / "transcript" / "demo.json")
    # No DB rows written -- simulates a prior run whose DB write failed
    # after the JSON was already saved.

    call_count = {"n": 0}
    _stub_load_model(monkeypatch, lambda model_name: call_count.__setitem__("n", call_count["n"] + 1))

    result = TranscriptionService(project_dir, config).run()

    assert call_count["n"] == 0
    assert result.skipped == ("demo",)

    with contextlib.closing(sqlite3.connect(project_dir / "project.db")) as conn, conn:
        rows = conn.execute("SELECT id FROM transcript_segments WHERE video_id = 'demo'").fetchall()
    assert [r[0] for r in rows] == ["demo_seg_0000"]


def test_skip_with_corrupt_transcript_json_reports_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    (video_dir / "transcript" / "demo.json").write_text("{not valid json", encoding="utf-8")

    call_count = {"n": 0}
    _stub_load_model(monkeypatch, lambda model_name: call_count.__setitem__("n", call_count["n"] + 1))

    result = TranscriptionService(project_dir, config).run()

    assert call_count["n"] == 0
    assert result.skipped == ()
    assert result.transcribed == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]


def test_skip_with_db_failure_reports_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)

    transcript = Transcript(
        video_id="demo", engine="faster-whisper", model="tiny", language="it",
        segments=[TranscriptSegment(id="demo_seg_0000", start_seconds=0.0, end_seconds=1.0, text="hi", confidence=0.9)],
    )
    transcript.save(video_dir / "transcript" / "demo.json")
    _stub_load_model(monkeypatch, lambda model_name: (_ for _ in ()).throw(AssertionError("model should not load")))

    def failing_replace_segments(db_path, video_id, segments):
        raise DatabaseError("simulated db failure")

    monkeypatch.setattr(transcription_service_module, "replace_transcript_segments", failing_replace_segments)

    result = TranscriptionService(project_dir, config).run()

    assert result.skipped == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]


def test_skip_with_metadata_save_failure_reports_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)

    transcript = Transcript(
        video_id="demo", engine="faster-whisper", model="tiny", language="it",
        segments=[TranscriptSegment(id="demo_seg_0000", start_seconds=0.0, end_seconds=1.0, text="hi", confidence=0.9)],
    )
    transcript.save(video_dir / "transcript" / "demo.json")

    def failing_save(self, path):
        raise OSError("simulated save failure")

    monkeypatch.setattr(VideoMetadata, "save", failing_save)

    result = TranscriptionService(project_dir, config).run()

    assert result.skipped == ()
    assert len(result.errors) == 1
    assert "demo" in result.errors[0]


def test_one_bad_video_does_not_block_others(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _seed_video(project_dir, config, video_id="bad", filename="Bad.mp4")
    _seed_video(project_dir, config, video_id="good", filename="Good.mp4")
    _stub_load_model(monkeypatch)

    def selective_transcribe(model, audio_path, *, language, word_timestamps, progress_callback=None, **kwargs):
        if audio_path.name == "bad.wav":
            raise TranscriptionError("corrupt audio")
        return _fake_results()

    _stub_transcribe(monkeypatch, selective_transcribe)
    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ("good",)
    assert any("bad" in e for e in result.errors)


def test_partial_write_failure_leaves_no_stray_json(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    real_replace = Path.replace

    def failing_replace(self, target):
        if self.name.endswith(".json.tmp"):
            raise OSError("simulated replace failure")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", failing_replace)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ()
    transcript_dir = video_dir / "transcript"
    assert not (transcript_dir / "demo.json").exists()
    assert not (transcript_dir / "demo.json.tmp").exists()


def test_missing_metadata_json_reported_as_error_json_still_written(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    (video_dir / "metadata.json").unlink()
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ()
    assert any("metadata.json" in e for e in result.errors)
    assert (video_dir / "transcript" / "demo.json").is_file()


def test_corrupt_metadata_json_reported_as_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    (video_dir / "metadata.json").write_text("{not valid json", encoding="utf-8")
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ()
    assert (video_dir / "transcript" / "demo.json").is_file()


def test_db_write_failure_after_successful_json_write_not_counted_transcribed(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    def failing_replace_segments(db_path, video_id, segments):
        raise DatabaseError("simulated db failure")

    monkeypatch.setattr(transcription_service_module, "replace_transcript_segments", failing_replace_segments)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ()
    assert len(result.errors) == 1
    assert (video_dir / "transcript" / "demo.json").is_file()


def test_metadata_save_failure_reported_as_error(tmp_path, monkeypatch):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    config = _config()
    _, video_dir = _seed_video(project_dir, config)
    _stub_load_model(monkeypatch)
    _stub_transcribe(monkeypatch)

    def failing_save(self, path):
        raise OSError("simulated save failure")

    monkeypatch.setattr(VideoMetadata, "save", failing_save)

    result = TranscriptionService(project_dir, config).run()

    assert result.transcribed == ()
    assert len(result.errors) == 1
    assert (video_dir / "transcript" / "demo.json").is_file()
