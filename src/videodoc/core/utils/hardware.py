from __future__ import annotations

import os
from typing import Literal

from videodoc.core.utils.cuda import cuda_is_usable

DEFAULT_GPU_WORKERS = 2
DEFAULT_BATCHED_GPU_WORKERS = 1
DEFAULT_GPU_BATCH_SIZE = 8


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


def resolve_compute_type(configured: str, device: Literal["cpu", "cuda"], override: str | None = None) -> str:
    if override is not None:
        return override
    if configured != "auto":
        return configured
    return "int8_float16" if device == "cuda" else "int8"


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
        default = DEFAULT_BATCHED_GPU_WORKERS if mode == "batched" else DEFAULT_GPU_WORKERS
        return resolve_gpu_workers(configured, override, default=default)
    return resolve_cpu_workers(configured, override)


def resolve_transcription_batch_size(
    configured: int | Literal["auto"],
    override: int | None,
    *,
    device: Literal["cpu", "cuda"],
    mode: Literal["standard", "batched"],
) -> int | None:
    if mode != "batched":
        return None
    default = DEFAULT_GPU_BATCH_SIZE if device == "cuda" else 1
    return _resolve_positive_auto(configured, override, default=default)


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
