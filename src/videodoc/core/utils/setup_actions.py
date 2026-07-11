from __future__ import annotations

import subprocess


class SetupActionError(Exception):
    """Raised when a single setup fix command fails to run or exits non-zero.

    Deliberately NOT a VideoDocError -- same per-item-failure rationale as
    AudioExtractionError/TranscriptionError/CudaProbeError: one fix failing
    is never fatal to the rest of a `videodoc setup` run, the caller
    (SetupService) always catches this and folds it into a SetupActionResult."""


def run_fix_command(command: tuple[str, ...], *, capture: bool = True) -> str:
    """Runs a fix command (already-decided argv, never a shell string) and
    returns its combined stdout+stderr on success.

    capture=True (default) pipes stdout/stderr so the CLI can show a clean
    summary -- appropriate for non-interactive commands (pip, winget with
    --accept-*-agreements, brew). capture=False instead inherits this
    process's own stdio, so an interactive prompt on the underlying command
    (e.g. `sudo` asking for a password during `apt install`) is visible and
    answerable in the user's own terminal instead of silently hanging
    against a pipe with no visible prompt -- used only for the Linux/apt fix.

    Raises SetupActionError wrapping subprocess.CalledProcessError/OSError
    (e.g. the command itself not found -- though callers are expected to
    check that with shutil.which first, see SetupService.apply)."""
    try:
        result = subprocess.run(list(command), check=True, capture_output=capture, text=True)
    except (subprocess.CalledProcessError, OSError) as exc:
        raise SetupActionError(f"Command {' '.join(command)!r} failed: {exc}") from exc
    if not capture:
        return ""
    return (result.stdout or "") + (result.stderr or "")
