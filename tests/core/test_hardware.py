import pytest

import videodoc.core.utils.hardware as hardware


def test_resolve_cpu_count_falls_back_to_one(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: None)
    assert hardware.resolve_cpu_count() == 1


def test_cpu_workers_precedence_override_config_auto(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: 8)
    assert hardware.resolve_cpu_workers("auto", None) == 8
    assert hardware.resolve_cpu_workers(4, None) == 4
    assert hardware.resolve_cpu_workers(4, 2) == 2


@pytest.mark.parametrize("configured,override,usable,expected", [
    ("auto", None, True, "cuda"),
    ("auto", None, False, "cpu"),
    ("cpu", None, True, "cpu"),
    ("cuda", None, False, "cuda"),
    ("cpu", "auto", True, "cuda"),
    ("cuda", "cpu", True, "cpu"),
])
def test_resolve_device(monkeypatch, configured, override, usable, expected):
    monkeypatch.setattr(hardware, "cuda_is_usable", lambda: usable)
    assert hardware.resolve_device(configured, override) == expected


def test_compute_type_auto_depends_on_device():
    assert hardware.resolve_compute_type("auto", "cuda") == "float16"
    assert hardware.resolve_compute_type("auto", "cpu") == "int8"
    assert hardware.resolve_compute_type("int8_float16", "cuda") == "int8_float16"


def test_transcription_workers_cpu_vs_gpu_defaults(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: 16)
    assert hardware.resolve_transcription_workers("auto", None, device="cpu") == 16
    assert hardware.resolve_transcription_workers("auto", None, device="cuda") == hardware.DEFAULT_GPU_WORKERS
    assert hardware.resolve_transcription_workers("auto", 5, device="cuda") == 5


def test_cpu_threads_auto_avoids_oversubscription(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: 16)
    assert hardware.resolve_cpu_threads("auto", None, device="cpu", workers=4) == 4
    assert hardware.resolve_cpu_threads("auto", None, device="cuda", workers=2) == 1
    assert hardware.resolve_cpu_threads(3, None, device="cpu", workers=4) == 3
    assert hardware.resolve_cpu_threads("auto", 6, device="cpu", workers=4) == 6


def test_ffmpeg_threads_and_executor_worker_cap(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: 16)
    assert hardware.resolve_ffmpeg_threads(4) == 4
    assert hardware.resolve_ffmpeg_threads(64) == 1
    assert hardware.resolve_executor_workers(32, 2) == 2
    assert hardware.resolve_executor_workers(32, 0) == 0
