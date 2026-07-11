from __future__ import annotations

import ctypes
import platform


CUBLAS_LIBRARY_NAMES: dict[str, str] = {
    "Windows": "cublas64_12.dll",
    "Linux": "libcublas.so.12",
}


class CudaProbeError(Exception):
    """Raised when a CUDA-related probe fails: ctranslate2 isn't importable,
    querying the CUDA device count fails, or a specific CUDA runtime shared
    library can't be loaded.

    Deliberately NOT a VideoDocError -- same per-item-failure rationale as
    AudioExtractionError/VideoProbeError/TranscriptionError: the caller
    (DoctorService) always catches this and folds it into a CheckResult,
    never lets it propagate -- a CUDA problem is never fatal to doctor
    itself, only ever informative."""


def get_cuda_device_count() -> int:
    """Lazily imports ctranslate2 (a transitive dependency of faster-whisper,
    already installed) and returns the number of CUDA devices it can see via
    the driver/cudart. This is a cheap, no-model-download call -- but it does
    NOT confirm the cuBLAS runtime library itself is loadable (a different
    library, only touched during actual inference); see probe_cublas_loadable
    for that. Raises CudaProbeError if ctranslate2 isn't importable or the
    call itself fails -- the caller treats that the same as '0 devices',
    i.e. no GPU acceleration available, not a structural problem."""
    try:
        import ctranslate2
    except ImportError as exc:
        raise CudaProbeError(f"ctranslate2 is not importable: {exc}") from exc
    try:
        return ctranslate2.get_cuda_device_count()
    except Exception as exc:
        raise CudaProbeError(f"Could not query CUDA device count: {exc}") from exc


def probe_cublas_loadable(library_name: str) -> None:
    """Attempts to load the given cuBLAS shared library by name (e.g.
    "cublas64_12.dll" on Windows, "libcublas.so.12" on Linux) via ctypes --
    the same load that faster-whisper/ctranslate2 perform lazily on first
    real transcription, reproduced here directly so this can be checked
    without downloading or running any model. Raises CudaProbeError
    (wrapping OSError) if the library can't be loaded.

    winmode=0 restores legacy (pre-Python 3.8) DLL search behavior on
    Windows, which includes PATH -- found necessary empirically: Python
    3.8+ hardened ctypes.CDLL's default search (a deliberate security
    change against DLL hijacking) to NOT consult PATH at all, only
    System32 and directories explicitly added via os.add_dll_directory().
    Without winmode=0, this probe would report a false "not loadable" even
    when the exact same PATH configuration lets the real faster-whisper
    code path succeed (it transitively imports the nvidia-cublas-cu12/
    nvidia-cudnn-cu12 packages, which self-register their bundled DLL
    directory via os.add_dll_directory() as an import side effect -- this
    probe intentionally does not rely on that happening first, since
    doctor must never import faster_whisper itself). winmode is accepted
    (and ignored) on non-Windows platforms, so this is safe cross-platform."""
    try:
        ctypes.CDLL(library_name, winmode=0)
    except OSError as exc:
        raise CudaProbeError(f"Could not load {library_name}: {exc}") from exc


def cuda_is_usable(platform_name: str | None = None) -> bool:
    """True when CTranslate2 sees a CUDA device and cuBLAS can be loaded.

    This is deliberately boolean and conservative for runtime auto-selection:
    diagnostic detail belongs in DoctorService, while `device: auto` only
    needs to know whether choosing CUDA is likely to succeed.
    """
    try:
        device_count = get_cuda_device_count()
    except CudaProbeError:
        return False
    if device_count <= 0:
        return False

    library_name = CUBLAS_LIBRARY_NAMES.get(platform_name or platform.system())
    if library_name is None:
        return False

    try:
        probe_cublas_loadable(library_name)
    except CudaProbeError:
        return False
    return True
