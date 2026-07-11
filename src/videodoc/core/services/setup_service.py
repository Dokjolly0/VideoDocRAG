from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Literal

from videodoc.core.services.doctor_service import CheckResult
from videodoc.core.utils.setup_actions import SetupActionError, run_fix_command


@dataclass(frozen=True)
class SetupActionResult:
    check_id: str
    action: str  # human-readable command, e.g. "pip install ..."
    status: Literal["applied", "skipped", "failed", "manual"]
    detail: str


class SetupService:
    """No constructor state -- the second machine-scoped service, same
    shape as DoctorService's "no project_dir/config" but even simpler
    since apply() takes everything it needs as an argument.

    Deliberately has NO confirmation/prompting logic: the caller (CLI layer,
    cli/commands/setup.py) has already decided a given fix should run --
    unconditionally for a "pip"-kind fix, after an explicit typer.confirm()
    for a "system"-kind fix. Keeping that decision entirely in the CLI layer
    matches README §12.4 ("CLI: read args, load config, call core, show
    results") and keeps core usable from a future GUI, which would need a
    modal dialog instead of a terminal prompt -- core must never assume how
    confirmation is obtained."""

    def apply(self, check: CheckResult) -> SetupActionResult:
        if check.fix_kind is None:
            return SetupActionResult(check.id, "", "skipped", "no fix available for this check")
        if check.fix_kind == "manual":
            return SetupActionResult(check.id, "", "manual", check.fix_description or check.message)

        command = check.fix_command
        action = " ".join(command) if command else ""
        if not command:
            return SetupActionResult(check.id, action, "failed", "no fix command defined for this check")

        tool = command[0]
        if shutil.which(tool) is None:
            return SetupActionResult(
                check.id, action, "failed",
                f"'{tool}' was not found on PATH -- install it manually, see RUN.md §1.",
            )

        # capture=False only for the Linux/apt system fix, so an interactive
        # sudo password prompt is visible in the user's own terminal instead
        # of hanging invisibly against a captured pipe -- see run_fix_command.
        capture = not (check.fix_kind == "system" and tool == "sudo")
        try:
            output = run_fix_command(command, capture=capture)
        except SetupActionError as exc:
            return SetupActionResult(check.id, action, "failed", str(exc))
        return SetupActionResult(check.id, action, "applied", output.strip() or "done")
