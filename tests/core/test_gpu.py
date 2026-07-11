import subprocess
import sys
import types

import pytest

import videodoc.core.utils.gpu as gpu_module
from videodoc.core.utils.gpu import GpuInfo, is_cuda_oom, probe_gpu


@pytest.fixture(autouse=True)
def _clear_probe_cache():
    probe_gpu.cache_clear()
    yield
    probe_gpu.cache_clear()


class _Memory:
    total = 8_188 * 1024 * 1024
    free = 7_301 * 1024 * 1024


def _fake_nvml(*, name=b"NVIDIA GeForce RTX 4070 Laptop GPU", driver=b"551.86", capability=(8, 9)):
    calls = {"shutdown": 0}

    def get_capability(handle):
        return capability

    fake = types.SimpleNamespace(
        nvmlInit=lambda: None,
        nvmlShutdown=lambda: calls.__setitem__("shutdown", calls["shutdown"] + 1),
        nvmlDeviceGetHandleByIndex=lambda index: f"handle-{index}",
        nvmlDeviceGetName=lambda handle: name,
        nvmlDeviceGetMemoryInfo=lambda handle: _Memory(),
        nvmlSystemGetDriverVersion=lambda: driver,
        nvmlDeviceGetCudaComputeCapability=get_capability,
    )
    return fake, calls


def test_probe_gpu_via_nvml_decodes_and_converts(monkeypatch):
    fake, calls = _fake_nvml()
    monkeypatch.setitem(sys.modules, "pynvml", fake)

    info = probe_gpu()

    assert info == GpuInfo(
        name="NVIDIA GeForce RTX 4070 Laptop GPU",
        total_vram_mb=8188,
        free_vram_mb=7301,
        compute_capability=(8, 9),
        driver_version="551.86",
        source="nvml",
    )
    assert calls["shutdown"] == 1


def test_probe_gpu_accepts_nvml_strings_and_missing_capability(monkeypatch):
    fake, _ = _fake_nvml(name="GPU", driver="driver", capability=(8, 9))
    del fake.nvmlDeviceGetCudaComputeCapability
    monkeypatch.setitem(sys.modules, "pynvml", fake)

    info = probe_gpu()

    assert info.name == "GPU"
    assert info.driver_version == "driver"
    assert info.compute_capability is None


def test_probe_gpu_falls_back_to_nvidia_smi(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)

    def fake_run(args, **kwargs):
        assert "--query-gpu=name,memory.total,memory.free,compute_cap,driver_version" in args
        return subprocess.CompletedProcess(args, 0, stdout="NVIDIA GeForce RTX 4070 Laptop GPU, 8188, 7301, 8.9, 551.86\n")

    monkeypatch.setattr(gpu_module.subprocess, "run", fake_run)

    info = probe_gpu()

    assert info == GpuInfo(
        name="NVIDIA GeForce RTX 4070 Laptop GPU",
        total_vram_mb=8188,
        free_vram_mb=7301,
        compute_capability=(8, 9),
        driver_version="551.86",
        source="nvidia-smi",
    )


def test_probe_gpu_retries_nvidia_smi_without_compute_capability(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)
    calls = {"n": 0}

    def fake_run(args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise subprocess.CalledProcessError(1, args, stderr="Unknown Error")
        assert "--query-gpu=name,memory.total,memory.free,driver_version" in args
        return subprocess.CompletedProcess(args, 0, stdout="GPU, 24576, 22000, 560.00\n")

    monkeypatch.setattr(gpu_module.subprocess, "run", fake_run)

    info = probe_gpu()

    assert info.name == "GPU"
    assert info.total_vram_mb == 24576
    assert info.free_vram_mb == 22000
    assert info.compute_capability is None
    assert calls["n"] == 2


@pytest.mark.parametrize("stdout", ["", "broken", "GPU, nope, 1, 8.9, 551.86"])
def test_probe_gpu_returns_none_on_parse_or_tool_failure(monkeypatch, stdout):
    monkeypatch.setitem(sys.modules, "pynvml", None)
    monkeypatch.setattr(gpu_module.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=stdout))

    assert probe_gpu() is None


@pytest.mark.parametrize("visible,expected", [
    (None, 0),
    ("1,2", 1),
    ("GPU-abcd", 0),
    ("-1", 0),
])
def test_target_device_index(monkeypatch, visible, expected):
    if visible is None:
        monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    else:
        monkeypatch.setenv("CUDA_VISIBLE_DEVICES", visible)
    assert gpu_module._target_device_index() == expected


def test_probe_gpu_cache(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynvml", None)
    calls = {"n": 0}

    def fake_run(args, **kwargs):
        calls["n"] += 1
        return subprocess.CompletedProcess(args, 0, stdout="GPU, 8188, 7301, 8.9, 551.86\n")

    monkeypatch.setattr(gpu_module.subprocess, "run", fake_run)

    assert probe_gpu() == probe_gpu()
    assert calls["n"] == 1


def test_is_cuda_oom_checks_exception_chain():
    root = RuntimeError("CUDA_ERROR_OUT_OF_MEMORY")
    wrapped = RuntimeError("top")
    wrapped.__cause__ = root

    assert is_cuda_oom(wrapped) is True
    assert is_cuda_oom(RuntimeError("ordinary decoder failure")) is False
