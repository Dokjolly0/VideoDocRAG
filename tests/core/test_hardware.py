import pytest

import videodoc.core.utils.hardware as hardware
from videodoc.core.utils.gpu import GpuInfo


def _gpu(free, total=8188, cc=(8, 9), name="GPU"):
    return GpuInfo(
        name=name,
        total_vram_mb=total,
        free_vram_mb=free,
        compute_capability=cc,
        driver_version="551.86",
        source="nvml",
    )


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


@pytest.mark.parametrize("gpu,expected_compute,expected_batch", [
    (_gpu(7301, total=8188, cc=(8, 9), name="4070 Laptop"), "int8_float16", 19),
    (_gpu(22000, total=24576, cc=(8, 9), name="4090"), "float16", 24),
    (_gpu(6000, total=8192, cc=(6, 1), name="GTX 1060"), "int8", 16),
    (_gpu(3500, total=4096, cc=(8, 9), name="tiny"), "int8_float16", 4),
    (_gpu(7301, total=8188, cc=None, name="old smi"), "int8_float16", 19),
    (None, "int8_float16", 8),
])
def test_plan_cuda_auto(gpu, expected_compute, expected_batch):
    plan = hardware.plan_cuda_auto(gpu)
    assert plan.compute_type == expected_compute
    assert plan.batch_size == expected_batch
    assert "dedicated VRAM" in plan.rationale or gpu is None


def test_compute_type_auto_depends_on_device_gpu_and_override():
    gpu = _gpu(22000, total=24576, cc=(8, 9))
    assert hardware.resolve_compute_type("auto", "cuda", gpu=gpu) == "float16"
    assert hardware.resolve_compute_type("auto", "cuda") == "int8_float16"
    assert hardware.resolve_compute_type("auto", "cpu", gpu=gpu) == "int8"
    assert hardware.resolve_compute_type("float16", "cuda", gpu=_gpu(3500)) == "float16"
    assert hardware.resolve_compute_type("auto", "cuda", "float16", gpu=_gpu(3500)) == "float16"


@pytest.mark.parametrize("configured,override,device,expected", [
    ("auto", None, "cuda", "batched"),
    ("auto", None, "cpu", "standard"),
    ("standard", None, "cuda", "standard"),
    ("batched", None, "cpu", "batched"),
    ("standard", "batched", "cuda", "batched"),
])
def test_resolve_transcription_mode(configured, override, device, expected):
    assert hardware.resolve_transcription_mode(configured, override, device=device) == expected


def test_transcription_workers_cpu_vs_gpu_defaults(monkeypatch):
    monkeypatch.setattr(hardware.os, "cpu_count", lambda: 16)
    assert hardware.resolve_transcription_workers("auto", None, device="cpu") == 16
    assert hardware.resolve_transcription_workers("auto", None, device="cuda", mode="standard") == hardware.DEFAULT_GPU_WORKERS
    assert hardware.resolve_transcription_workers("auto", None, device="cuda", mode="batched") == hardware.DEFAULT_BATCHED_GPU_WORKERS
    assert hardware.resolve_transcription_workers("auto", 5, device="cuda", mode="batched") == 5


def test_transcription_batch_size_defaults_gpu_and_overrides():
    gpu = _gpu(7301)
    assert hardware.resolve_transcription_batch_size("auto", None, device="cuda", mode="batched", gpu=gpu) == 19
    assert hardware.resolve_transcription_batch_size("auto", None, device="cuda", mode="batched") == hardware.DEFAULT_GPU_BATCH_SIZE
    assert hardware.resolve_transcription_batch_size("auto", None, device="cpu", mode="batched", gpu=gpu) == 1
    assert hardware.resolve_transcription_batch_size(4, None, device="cuda", mode="batched", gpu=gpu) == 4
    assert hardware.resolve_transcription_batch_size("auto", 2, device="cuda", mode="batched", gpu=gpu) == 2
    assert hardware.resolve_transcription_batch_size("auto", 2, device="cuda", mode="standard", gpu=gpu) is None


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
