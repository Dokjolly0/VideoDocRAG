from __future__ import annotations

import os
import platform
import shutil
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from videodoc.core.services.project_service import HOME_ENV_VAR, default_projects_home
from videodoc.core.services.registry_service import DATA_DIR_ENV_VAR, ProjectRegistry
from videodoc.core.utils.cuda import CudaProbeError, get_cuda_device_count, probe_cublas_loadable

_MIN_PYTHON = (3, 11)

# One shared fix for both binaries: they come from the same FFmpeg install,
# so treating them as two separate checks would make `setup` prompt twice
# (or run the same system installer twice) for one underlying action.
_FFMPEG_FIX_COMMANDS: dict[str, tuple[str, ...]] = {
    "Windows": ("winget", "install", "Gyan.FFmpeg", "--accept-source-agreements", "--accept-package-agreements"),
    "Linux": ("sudo", "apt", "install", "-y", "ffmpeg"),
    "Darwin": ("brew", "install", "ffmpeg"),
}

# CUDA 12.x-specific shared library names -- matches the exact library named
# in the real "cublas64_12.dll is not found or cannot be loaded" error this
# check exists to catch. Not applicable on macOS (no NVIDIA CUDA support on
# modern hardware) or on an OS this dict doesn't recognize.
_CUBLAS_LIBRARY_NAMES: dict[str, str] = {
    "Windows": "cublas64_12.dll",
    "Linux": "libcublas.so.12",
}

_CUBLAS_PIP_FIX: tuple[str, ...] = (sys.executable, "-m", "pip", "install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12")


@dataclass(frozen=True)
class CheckResult:
    id: str
    name: str
    status: Literal["ok", "warning", "error"]
    message: str
    fix_kind: Literal["pip", "system", "manual"] | None = None
    fix_command: tuple[str, ...] | None = None  # argv, never a shell string
    fix_description: str | None = None  # human instructions; the whole fix when fix_kind == "manual"


@dataclass(frozen=True)
class DoctorResult:
    checks: tuple[CheckResult, ...]

    @property
    def has_errors(self) -> bool:
        return any(c.status == "error" for c in self.checks)


class DoctorService:
    def __init__(
        self,
        *,
        version_info: tuple[int, ...] | None = None,
        platform_name: str | None = None,
        registry: ProjectRegistry | None = None,
        projects_home: Path | None = None,
    ) -> None:
        # Every dependency is injectable (mirrors the path_class injection
        # precedent in core/utils/paths.py) so tests can deterministically
        # exercise every branch without touching this actual machine.
        self._version_info = tuple(version_info) if version_info is not None else tuple(sys.version_info)
        self._platform_name = platform_name if platform_name is not None else platform.system()
        self._registry = registry if registry is not None else ProjectRegistry()
        self._projects_home = projects_home if projects_home is not None else default_projects_home()

    def run(self) -> DoctorResult:
        checks = []
        for check_fn in (
            self._check_python_version,
            self._check_ffmpeg,
            self._check_faster_whisper,
            self._check_cuda,
            self._check_registry,
            self._check_projects_home,
        ):
            # doctor is a diagnostic tool: one check's unexpected internal
            # failure must never abort the rest of the report or crash the
            # whole command -- it's surfaced as that check's own error.
            try:
                checks.append(check_fn())
            except Exception as exc:  # noqa: BLE001 -- deliberately broad, see above
                checks.append(
                    CheckResult(
                        id=check_fn.__name__.removeprefix("_check_"),
                        name=check_fn.__name__.removeprefix("_check_").replace("_", " "),
                        status="error",
                        message=f"check failed unexpectedly: {exc}",
                    )
                )
        return DoctorResult(tuple(checks))

    def _check_python_version(self) -> CheckResult:
        current = self._version_info[:2]
        version_str = ".".join(str(p) for p in self._version_info[:3])
        if current >= _MIN_PYTHON:
            return CheckResult("python_version", "Python version", "ok", f"{version_str} (>= {'.'.join(map(str, _MIN_PYTHON))} required)")
        return CheckResult(
            "python_version", "Python version", "error",
            f"{version_str} is older than the required {'.'.join(map(str, _MIN_PYTHON))}.",
            fix_kind="manual",
            fix_description=f"Install Python {'.'.join(map(str, _MIN_PYTHON))} or newer and recreate the virtual environment (see RUN.md §2-§3).",
        )

    def _check_ffmpeg(self) -> CheckResult:
        missing = [tool for tool in ("ffprobe", "ffmpeg") if shutil.which(tool) is None]
        if not missing:
            return CheckResult("ffmpeg", "FFmpeg (ffprobe + ffmpeg)", "ok", "both found on PATH")
        fix_command = _FFMPEG_FIX_COMMANDS.get(self._platform_name)
        return CheckResult(
            "ffmpeg", "FFmpeg (ffprobe + ffmpeg)", "error",
            f"missing on PATH: {', '.join(missing)} -- required by 'videodoc ingest'/'videodoc extract-audio'.",
            fix_kind="system" if fix_command else "manual",
            fix_command=fix_command,
            fix_description=None if fix_command else "Install FFmpeg for your OS -- see https://ffmpeg.org/download.html and RUN.md §1.",
        )

    def _check_faster_whisper(self) -> CheckResult:
        # A bare import only -- never load_whisper_model(), which would
        # instantiate a real model and could trigger a multi-GB download.
        try:
            import faster_whisper  # noqa: F401
        except ImportError as exc:
            return CheckResult(
                "faster_whisper", "faster-whisper", "error",
                f"not importable: {exc}",
                fix_kind="manual",
                fix_description="faster-whisper is a required dependency -- reinstall the project: pip install -e \".[dev]\".",
            )
        return CheckResult("faster_whisper", "faster-whisper", "ok", "importable")

    def _check_cuda(self) -> CheckResult:
        try:
            device_count = get_cuda_device_count()
        except CudaProbeError:
            device_count = 0
        if device_count <= 0:
            return CheckResult("cuda", "GPU / CUDA", "ok", "no CUDA device detected -- CPU will be used")
        if self._platform_name == "Darwin":
            return CheckResult("cuda", "GPU / CUDA", "ok", "CUDA device reported, but macOS has no NVIDIA CUDA support -- CPU will be used")

        library_name = _CUBLAS_LIBRARY_NAMES.get(self._platform_name)
        if library_name is None:
            return CheckResult("cuda", "GPU / CUDA", "ok", f"{device_count} CUDA device(s) detected (cuBLAS not checked on this OS)")

        try:
            probe_cublas_loadable(library_name)
        except CudaProbeError as exc:
            # Warning, not error: transcribe still completes for the other
            # videos via its own per-item TranscriptionError handling
            # (verified in Step 5) -- only that one video's transcription
            # fails, exit code stays 0. See RUN.md §8 for the real-world
            # incident this check exists to catch before it surprises a user.
            fix_description = None
            if self._platform_name == "Windows":
                # Resolved against *this* interpreter's actual site-packages,
                # not a generic "<venv>" placeholder -- the pip packages land
                # in site-packages/nvidia/{cublas,cudnn}/bin regardless of
                # whether they're installed yet, so this path is valid even
                # before 'setup' has run the pip fix below.
                site_packages = Path(sysconfig.get_paths()["purelib"])
                cublas_bin = site_packages / "nvidia" / "cublas" / "bin"
                cudnn_bin = site_packages / "nvidia" / "cudnn" / "bin"
                fix_description = (
                    "On Windows the pip packages alone are not enough -- also run this in your "
                    "PowerShell session before 'videodoc transcribe' (see RUN.md §8): "
                    f'$env:PATH = "{cublas_bin};{cudnn_bin};$env:PATH"'
                )
            return CheckResult(
                "cuda", "GPU / CUDA", "warning",
                f"{device_count} CUDA device(s) detected but {library_name} could not be loaded: {exc}",
                fix_kind="pip", fix_command=_CUBLAS_PIP_FIX, fix_description=fix_description,
            )
        return CheckResult("cuda", "GPU / CUDA", "ok", f"{device_count} CUDA device(s) detected, {library_name} loadable")

    def _check_registry(self) -> CheckResult:
        entries = self._registry.list_all()
        override = os.environ.get(DATA_DIR_ENV_VAR)
        location = f"{self._registry.registry_path} ({'VIDEODOC_DATA_DIR override' if override else 'default location'})"
        if self._registry.last_load_was_corrupted:
            return CheckResult(
                "registry", "Project registry", "warning",
                f"was corrupted and has been automatically quarantined and reset to empty -- {location}. "
                f"Registered projects were not deleted from disk, re-add them with 'videodoc link <path>'.",
            )
        return CheckResult("registry", "Project registry", "ok", f"{len(entries)} project(s) registered -- {location}")

    def _check_projects_home(self) -> CheckResult:
        override = os.environ.get(HOME_ENV_VAR)
        source = "VIDEODOC_HOME override" if override else "default location"
        ancestor = self._projects_home
        while not ancestor.exists() and ancestor.parent != ancestor:
            ancestor = ancestor.parent
        if not os.access(ancestor, os.W_OK):
            return CheckResult(
                "projects_home", "Default projects folder", "error",
                f"{self._projects_home} is not writable ({source}, checked at {ancestor}).",
                fix_kind="manual",
                fix_description=f"Grant write permission to {ancestor}, or set VIDEODOC_HOME to a writable location.",
            )
        return CheckResult("projects_home", "Default projects folder", "ok", f"{self._projects_home} is writable ({source})")
