from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

_MIB = 1024 * 1024
_OOM_MARKERS = (
    "out of memory",
    "cuda_error_out_of_memory",
    "cublas_status_alloc_failed",
    "cudnn_status_alloc_failed",
)


@dataclass(frozen=True)
class GpuInfo:
    name: str
    total_vram_mb: int
    free_vram_mb: int
    compute_capability: tuple[int, int] | None
    driver_version: str | None
    source: Literal["nvml", "nvidia-smi"]


@lru_cache(maxsize=1)
def probe_gpu() -> GpuInfo | None:
    """Return details for the CUDA device used by CTranslate2, if known.

    The reported memory is dedicated framebuffer VRAM only. Windows "shared
    GPU memory" is system RAM and is deliberately ignored for planning: using
    it for batch sizing would trade a predictable CUDA OOM for much slower PCIe
    paging or virtual-memory behavior.
    """
    index = _target_device_index()
    return _probe_via_nvml(index) or _probe_via_nvidia_smi(index)


def is_cuda_oom(exc: BaseException) -> bool:
    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        haystack = f"{type(current).__name__}: {current}".lower()
        if any(marker in haystack for marker in _OOM_MARKERS):
            return True
        stack.append(getattr(current, "__cause__", None))
        stack.append(getattr(current, "__context__", None))
    return False


def _target_device_index() -> int:
    visible = os.environ.get("CUDA_VISIBLE_DEVICES")
    if not visible:
        return 0
    first = visible.split(",", 1)[0].strip()
    try:
        index = int(first)
    except ValueError:
        return 0
    return index if index >= 0 else 0


def _probe_via_nvml(index: int) -> GpuInfo | None:
    try:
        import pynvml
    except Exception:
        return None

    initialized = False
    try:
        pynvml.nvmlInit()
        initialized = True
        handle = pynvml.nvmlDeviceGetHandleByIndex(index)
        memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
        return GpuInfo(
            name=_decode(pynvml.nvmlDeviceGetName(handle)),
            total_vram_mb=int(memory.total) // _MIB,
            free_vram_mb=int(memory.free) // _MIB,
            compute_capability=_nvml_compute_capability(pynvml, handle),
            driver_version=_decode(pynvml.nvmlSystemGetDriverVersion()) if hasattr(pynvml, "nvmlSystemGetDriverVersion") else None,
            source="nvml",
        )
    except Exception:
        return None
    finally:
        if initialized:
            try:
                pynvml.nvmlShutdown()
            except Exception:
                pass


def _nvml_compute_capability(pynvml, handle) -> tuple[int, int] | None:
    fn = getattr(pynvml, "nvmlDeviceGetCudaComputeCapability", None)
    if fn is None:
        return None
    try:
        major, minor = fn(handle)
    except Exception:
        return None
    return int(major), int(minor)


def _probe_via_nvidia_smi(index: int) -> GpuInfo | None:
    fields = ("name", "memory.total", "memory.free", "compute_cap", "driver_version")
    try:
        return _parse_nvidia_smi(_run_nvidia_smi(index, fields), has_compute_capability=True)
    except Exception:
        try:
            fields = ("name", "memory.total", "memory.free", "driver_version")
            return _parse_nvidia_smi(_run_nvidia_smi(index, fields), has_compute_capability=False)
        except Exception:
            return None


def _run_nvidia_smi(index: int, fields: tuple[str, ...]) -> str:
    result = subprocess.run(
        [
            "nvidia-smi",
            f"--query-gpu={','.join(fields)}",
            "--format=csv,noheader,nounits",
            "-i",
            str(index),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
    )
    return result.stdout.strip()


def _parse_nvidia_smi(stdout: str, *, has_compute_capability: bool) -> GpuInfo | None:
    line = next((part.strip() for part in stdout.splitlines() if part.strip()), "")
    if not line:
        return None
    parts = [part.strip() for part in line.split(",")]
    expected = 5 if has_compute_capability else 4
    if len(parts) != expected:
        return None

    if has_compute_capability:
        name, total, free, compute_cap, driver = parts
        capability = _parse_compute_capability(compute_cap)
    else:
        name, total, free, driver = parts
        capability = None
    return GpuInfo(
        name=name,
        total_vram_mb=_parse_mb(total),
        free_vram_mb=_parse_mb(free),
        compute_capability=capability,
        driver_version=driver or None,
        source="nvidia-smi",
    )


def _parse_mb(value: str) -> int:
    return int(float(value.strip()))


def _parse_compute_capability(value: str) -> tuple[int, int] | None:
    try:
        major, minor = value.strip().split(".", 1)
        return int(major), int(minor)
    except Exception:
        return None


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
