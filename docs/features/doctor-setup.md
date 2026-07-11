# Machine health check and guided fixes (`videodoc doctor`, `videodoc setup`)

## Summary
`videodoc doctor` and `videodoc setup` are the first two **machine-scoped** commands — no project argument, no `ProjectService.load()` call, unlike every command from `init` through `transcribe`. `doctor` reports the health of the local environment and its dependencies; `setup` reuses the exact same checks and offers to fix whatever isn't `ok`. Both exist because of a real, empirically-reproduced problem: during Step 5 manual testing, `faster-whisper`'s `WhisperModel` detected an NVIDIA GPU but couldn't load the `cublas64_12.dll` CUDA runtime library, on two different Windows machines, with the failure only surfacing mid-transcription rather than at startup.

## What was implemented
- `core/services/doctor_service.py::CheckResult` — a frozen dataclass (`id`, `name`, `status: "ok"|"warning"|"error"`, `message`, `fix_kind: "pip"|"system"|"manual"|None`, `fix_command: tuple[str, ...] | None`, `fix_description`). `setup` is defined entirely in terms of this schema — it never re-derives what's broken, only dispatches on `fix_kind`.
- `DoctorService.run() -> DoctorResult` runs six checks, each individually wrapped so one check's unexpected exception can never crash the whole diagnostic (doctor must never itself fail opaquely):
  - **Python version** (`>= 3.11`, matching `pyproject.toml`'s `requires-python`).
  - **FFmpeg** — `ffprobe` and `ffmpeg` are checked and fixed **together, as one check**, not two: both binaries come from the same FFmpeg install, so two separate checks would make `setup` prompt (or run a system installer) twice for the identical action.
  - **faster-whisper** — a bare `import faster_whisper`, never `load_whisper_model()` (which instantiates a real model and could trigger a multi-GB download — doctor must stay cheap and side-effect-free).
  - **GPU / CUDA**, the two-tier check this feature exists for: `ctranslate2.get_cuda_device_count()` (cheap, driver/cudart-level — confirmed empirically to return a nonzero count even on a machine where cuBLAS itself is broken, so this alone is not a sufficient check) then, only if a device is present and the OS is not macOS (no NVIDIA CUDA support there), a direct `ctypes.CDLL("cublas64_12.dll" / "libcublas.so.12", winmode=0)` probe — the same load faster-whisper/ctranslate2 perform lazily on first real transcription, reproduced here without downloading or running any model. A failure here is a **warning, never an error**: `transcribe` still completes for other videos via its own per-item `TranscriptionError` handling (verified in Step 5), only that video's transcription fails, exit code stays 0.
  - **Project registry** health — reuses `ProjectRegistry.list_all()` and the new `last_load_was_corrupted` property (see below), reporting project count and whether `VIDEODOC_DATA_DIR` is overriding the default location.
  - **Default projects folder** writability — reuses `default_projects_home()`, walks up to the nearest existing ancestor to check, reports whether `VIDEODOC_HOME` is overriding the default.
- `core/services/registry_service.py::ProjectRegistry.last_load_was_corrupted` (new property) and `.registry_path` (new property) — small, justified additions: doctor needed a way to report "the registry was just corrupted and auto-recovered" without reimplementing `registry.json` parsing, and a way to report which path was actually used without reaching into a private attribute.
- `core/utils/cuda.py` — `get_cuda_device_count()` and `probe_cublas_loadable()`, mirroring the `ffprobe.py`/`ffmpeg.py` layering exactly: a single plain `CudaProbeError` (deliberately **not** a `VideoDocError`), imported by name into `doctor_service.py` so tests can monkeypatch at that importing module's namespace.
  - **`probe_cublas_loadable()` passes `winmode=0` to `ctypes.CDLL()`, found necessary empirically, not by inspection.** Python 3.8+ hardened `ctypes.CDLL`'s default Windows DLL search behavior (an anti-hijacking security change) to no longer consult `PATH` at all, only `System32` and directories explicitly registered via `os.add_dll_directory()`. Without `winmode=0`, this probe reported a false "not loadable" even with the exact PATH configuration that lets the real `faster-whisper` code path succeed (it transitively imports the `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` packages, which self-register their bundled DLL directory via `os.add_dll_directory()` as an import side effect — this probe deliberately does not rely on that happening first, since `doctor` must never import `faster_whisper` itself). `winmode=0` restores the legacy PATH-inclusive search; the parameter is accepted (and ignored) on non-Windows platforms.
- `core/utils/setup_actions.py::run_fix_command()` — the only new subprocess-execution primitive, with a `capture` parameter no prior util needed: `capture=False` inherits the parent process's stdio instead of piping it, used **only** for the Linux/`apt` fix, so an interactive `sudo` password prompt is visible and answerable in the user's own terminal instead of hanging invisibly against a captured pipe.
- `core/services/setup_service.py::SetupService.apply(check) -> SetupActionResult` — pure, no confirmation logic at all. Checks the fix command's own binary is on `PATH` first (`shutil.which`), reporting a distinct `"failed"` outcome ("tool not found") rather than letting an opaque `subprocess` `FileNotFoundError` surface. `pip install` fixes always use `[sys.executable, "-m", "pip", "install", ...]`, never a bare `"pip"`, so the fix always lands in the running venv regardless of what a generic `pip` on `PATH` might resolve to.
- **The confirmation prompt lives entirely in `cli/commands/setup.py`, never in core** — `typer.confirm(...)` is called only for `fix_kind == "system"` fixes, right in the CLI command function. This matches README §12.4 ("CLI: read args, load config, call core, show results") and keeps `core/` usable from a future GUI, which would need a modal dialog instead of a terminal prompt.
- **System-level fixes are never re-verified in the same process; only pip-kind fixes are.** Even after a successful `winget`/`apt`/`brew` install, the already-running Python process's own `PATH` doesn't refresh — an immediate re-check would misleadingly report "still broken." A successful system-fix subprocess exit is trusted and counted as resolved for `setup`'s exit code (a deliberately simple v1 choice, see Design decisions). pip-kind fixes, by contrast, genuinely are re-verified: a fresh `import`/`ctypes.CDLL()` call in the same process sees a newly `pip install`ed package immediately.

## Main files
- `src/videodoc/core/services/doctor_service.py` — `DoctorService`, `DoctorResult`, `CheckResult`.
- `src/videodoc/core/services/setup_service.py` — `SetupService`, `SetupActionResult`.
- `src/videodoc/core/utils/cuda.py` — `get_cuda_device_count`, `probe_cublas_loadable`, `CudaProbeError`.
- `src/videodoc/core/utils/setup_actions.py` — `run_fix_command`, `SetupActionError`.
- `src/videodoc/core/services/registry_service.py` — `last_load_was_corrupted`, `registry_path` (additions).
- `src/videodoc/cli/commands/doctor.py`, `src/videodoc/cli/commands/setup.py` — the two commands.
- `src/videodoc/cli/output.py` — `print_check_error` (addition).

## Design decisions
- **No new `VideoDocError` subclass.** Neither command ever raises past its own boundary — `doctor` always returns a full report, `setup` always reports what it did/skipped/failed. Matches the existing per-item (plain exception, not domain exception) failure pattern already used by `extract-audio`/`transcribe`, generalized here to two commands that never have a single fatal "this whole run failed" condition at all.
- **`setup`'s exit code (v1, deliberately simple)**: `1` only if a check that was originally `"error"` ends up unresolved — no `fix_kind` at all, the confirmation was declined, or the fix attempt itself failed. A **successfully applied system fix always counts as resolved**, even though it can't be re-verified in-process (see above) — a fuller "verified vs. applied-but-unverifiable" distinction was deliberately deferred; revisit only if real usage shows the simple version is misleading.
- **`setup` never accepts a `--yes`/skip-confirmation flag.** The per-action confirmation for system-level fixes was a deliberate user decision, not something to be able to bypass in this first version.
- **Only `winget`/`apt`/`brew` are supported system installers** — matches `RUN.md`'s own FFmpeg install instructions, which already only cover these three.

## CLI

Clean machine:
```bash
videodoc doctor
# Python version: 3.13.14 (>= 3.11 required)
# FFmpeg (ffprobe + ffmpeg): both found on PATH
# faster-whisper: importable
# GPU / CUDA: 1 CUDA device(s) detected, cublas64_12.dll loadable
# Project registry: 3 project(s) registered -- ...
# Default projects folder: ... is writable (default location)
# 6 OK, 0 warning(s), 0 error(s).
```

A real machine with the cuBLAS problem this feature exists to catch:
```bash
videodoc doctor
# ...
# Warning: GPU / CUDA: 1 CUDA device(s) detected but cublas64_12.dll could not be loaded: ...
#   Fix: On Windows the pip packages alone are not enough -- also add <venv>\...\nvidia\cublas\bin and ...\nvidia\cudnn\bin to PATH for the session (see RUN.md).
# 5 OK, 1 warning(s), 0 error(s).

videodoc setup
# ...
# Warning: GPU / CUDA: 1 CUDA device(s) detected but cublas64_12.dll could not be loaded: ...
#   Applying fix for 'GPU / CUDA': <venv>\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
#   Applied: Requirement already satisfied: nvidia-cublas-cu12 ...
#   On Windows the pip packages alone are not enough -- also add ... to PATH for the session (see RUN.md).
# Re-checking automatically-fixed items...
# GPU / CUDA: 1 CUDA device(s) detected but cublas64_12.dll could not be loaded: ...
```
(The pip fix alone genuinely isn't enough on Windows — confirmed by the re-check above still reporting the warning; the PATH step remains manual by design, see RUN.md's troubleshooting entry.)

## Tests
- Unit: `tests/core/test_cuda.py` (device count success/missing-package/call-failure, cuBLAS probe success/`OSError`, and a dedicated regression test asserting `winmode=0` is passed), `tests/core/test_setup_actions.py` (success, `capture=False` threaded through, `CalledProcessError`/`OSError`), `tests/core/test_registry_service.py` (new: `last_load_was_corrupted` false/true/resets-on-next-clean-load, `registry_path`).
- Service: `tests/core/test_doctor_service.py` (one test per check per status, injected `version_info`/`platform_name`/`registry`/`projects_home`, macOS CUDA short-circuit without probing, one check crashing doesn't abort the run, `has_errors` mapping), `tests/core/test_setup_service.py` (pip fix, tool-missing-from-PATH failure without ever calling the subprocess, `apt`'s `capture=False` vs. `winget`'s `capture=True`, defensive no-fix-command guard).
- CLI: `tests/cli/test_cli_doctor_command.py` (exit 0 clean, exit 1 with an error, warning alone keeps exit 0), `tests/cli/test_cli_setup_command.py` (clean state applies nothing, pip fix applies without any prompt, system fix prompts and respects yes/no, a fix failure is reported without aborting the rest, a manual-only fix only prints instructions, a check with no fix available at all is reported and left unresolved).
- Manual: `videodoc doctor`/`videodoc setup` run for real on this machine, both with and without the cuBLAS PATH workaround in effect — confirmed the two-tier CUDA check correctly distinguishes both states, confirmed `setup`'s pip auto-fix runs without any prompt and its output is shown, and confirmed the real `winmode=0` bug (found only through this manual run, not by inspection) before it shipped.
