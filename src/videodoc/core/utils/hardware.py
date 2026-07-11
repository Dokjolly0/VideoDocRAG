from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from videodoc.core.utils.cuda import cuda_is_usable
from videodoc.core.utils.gpu import GpuInfo

DEFAULT_GPU_WORKERS = 2
DEFAULT_BATCHED_GPU_WORKERS = 1
DEFAULT_GPU_BATCH_SIZE = 8
MIN_CUDA_BATCH_SIZE = 4
MAX_CUDA_BATCH_SIZE = 24
SAFETY_MARGIN_MB = 1024
FLOAT16_BASE_MB = 4800
INT8_FLOAT16_BASE_MB = 3300
INT8_BASE_MB = 2800
FLOAT16_PER_ITEM_MB = 200
INT8_FLOAT16_PER_ITEM_MB = 150
INT8_PER_ITEM_MB = 130
FLOAT16_MIN_FREE_MB = 9216


@dataclass(frozen=True)
class CudaAutoPlan:
    compute_type: str
    batch_size: int
    rationale: str


def resolve_cpu_count() -> int:
    return os.cpu_count() or 1


def resolve_device(
    configured: Literal["auto", "cpu", "cuda"],
    override: Literal["auto", "cpu", "cuda"] | None,
) -> Literal["cpu", "cuda"]:
    selected = override if override is not None else configured
    if selected == "auto":
        return "cuda" if cuda_is_usable() else "cpu"
    return selected


def plan_cuda_auto(gpu: GpuInfo | None) -> CudaAutoPlan:
    """Plan CUDA transcription knobs from dedicated VRAM only.

    `GpuInfo.free_vram_mb` comes from NVML/nvidia-smi framebuffer memory.
    Shared GPU memory reported by Windows is intentionally excluded: it is
    system RAM over PCIe and should not be used for CTranslate2 batch sizing.
    """
    if gpu is None:
        return CudaAutoPlan(
            "int8_float16",
            DEFAULT_GPU_BATCH_SIZE,
            "GPU details unavailable; using conservative CUDA defaults",
        )

    capability = gpu.compute_capability
    if capability is not None and capability < (7, 0):
        compute_type = "int8"
        reason = f"{gpu.free_vram_mb} MiB dedicated VRAM free; compute capability {capability[0]}.{capability[1]} is below tensor-core generation"
    elif gpu.free_vram_mb >= FLOAT16_MIN_FREE_MB:
        compute_type = "float16"
        reason = f"{gpu.free_vram_mb} MiB dedicated VRAM free is enough for float16"
    else:
        compute_type = "int8_float16"
        cc_note = "unknown compute capability assumed tensor-core capable" if capability is None else f"compute capability {capability[0]}.{capability[1]}"
        reason = f"{gpu.free_vram_mb} MiB dedicated VRAM free with {cc_note}; using balanced quantization"

    batch_size = estimate_cuda_batch_size(gpu, compute_type)
    return CudaAutoPlan(compute_type, batch_size, f"{reason}; batch_size={batch_size}")


def estimate_cuda_batch_size(gpu: GpuInfo | None, compute_type: str) -> int:
    if gpu is None:
        return DEFAULT_GPU_BATCH_SIZE
    base_mb, per_item_mb = _cuda_memory_estimate(compute_type)
    usable_mb = max(0, gpu.free_vram_mb - SAFETY_MARGIN_MB - base_mb)
    return _clamp(usable_mb // per_item_mb, MIN_CUDA_BATCH_SIZE, MAX_CUDA_BATCH_SIZE)


def resolve_compute_type(
    configured: str,
    device: Literal["cpu", "cuda"],
    override: str | None = None,
    *,
    gpu: GpuInfo | None = None,
) -> str:
    if override is not None:
        return override
    if configured != "auto":
        return configured
    if device == "cuda":
        return plan_cuda_auto(gpu).compute_type
    return "int8"


def resolve_transcription_mode(
    configured: Literal["auto", "standard", "batched"],
    override: Literal["auto", "standard", "batched"] | None,
    *,
    device: Literal["cpu", "cuda"],
) -> Literal["standard", "batched"]:
    selected = override if override is not None else configured
    if selected == "auto":
        return "batched" if device == "cuda" else "standard"
    return selected


def resolve_cpu_workers(configured: int | Literal["auto"], override: int | None) -> int:
    return _resolve_positive_auto(configured, override, default=resolve_cpu_count())


def resolve_gpu_workers(
    configured: int | Literal["auto"],
    override: int | None,
    *,
    default: int = DEFAULT_GPU_WORKERS,
) -> int:
    return _resolve_positive_auto(configured, override, default=default)


def resolve_transcription_workers(
    configured: int | Literal["auto"],
    override: int | None,
    *,
    device: Literal["cpu", "cuda"],
    mode: Literal["standard", "batched"] = "standard",
) -> int:
    if device == "cuda":
        # Batched inference should normally fill a single GPU by increasing
        # batch_size, not by running multiple large videos through one model.
        default = DEFAULT_BATCHED_GPU_WORKERS if mode == "batched" else DEFAULT_GPU_WORKERS
        return resolve_gpu_workers(configured, override, default=default)
    return resolve_cpu_workers(configured, override)


def resolve_transcription_batch_size(
    configured: int | Literal["auto"],
    override: int | None,
    *,
    device: Literal["cpu", "cuda"],
    mode: Literal["standard", "batched"],
    gpu: GpuInfo | None = None,
) -> int | None:
    if mode != "batched":
        return None
    if override is not None:
        return _positive(override, "batch_size override")
    if configured != "auto":
        return _positive(configured, "batch_size")
    if device == "cuda":
        return plan_cuda_auto(gpu).batch_size
    return 1


def resolve_cpu_threads(
    configured: int | Literal["auto"],
    override: int | None,
    *,
    device: Literal["cpu", "cuda"],
    workers: int,
) -> int:
    if override is not None:
        return _positive(override, "cpu_threads override")
    if configured != "auto":
        return _positive(configured, "cpu_threads")
    if device == "cuda":
        return 1
    return max(1, resolve_cpu_count() // max(1, workers))


def resolve_ffmpeg_threads(workers: int) -> int:
    return max(1, resolve_cpu_count() // max(1, workers))


def resolve_executor_workers(workers: int, item_count: int) -> int:
    if item_count <= 0:
        return 0
    return min(_positive(workers, "workers"), item_count)


def _cuda_memory_estimate(compute_type: str) -> tuple[int, int]:
    if compute_type == "float16":
        return FLOAT16_BASE_MB, FLOAT16_PER_ITEM_MB
    if compute_type == "int8":
        return INT8_BASE_MB, INT8_PER_ITEM_MB
    return INT8_FLOAT16_BASE_MB, INT8_FLOAT16_PER_ITEM_MB


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(value)))


def _resolve_positive_auto(configured: int | Literal["auto"], override: int | None, *, default: int) -> int:
    if override is not None:
        return _positive(override, "workers override")
    if configured != "auto":
        return _positive(configured, "workers")
    return _positive(default, "workers default")


def _positive(value: int, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value
