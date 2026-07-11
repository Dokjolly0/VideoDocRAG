from typing import Optional

import typer

from videodoc.cli.output import console, print_check_result, print_error, print_warning
from videodoc.core.errors import InvalidConfigError, ProjectNotFoundError
from videodoc.core.services.doctor_service import DoctorService
from videodoc.core.services.project_service import ProjectService
from videodoc.core.services.setup_service import SetupService
from videodoc.core.utils.transcription import TranscriptionError, load_whisper_model


def setup_command(
    project: Optional[str] = typer.Argument(
        None, help="Project name or path -- if given, also pre-downloads its configured transcription model"
    ),
) -> None:
    """Runs doctor's checks, then offers to fix whatever isn't 'ok' --
    pip-kind fixes run automatically (venv-scoped, reversible), system-kind
    fixes ask for confirmation first (they touch the machine outside this
    project), manual-kind fixes are only ever printed, never attempted (see
    doctor_service.py's CheckResult docstring for why -- e.g. a child
    process can't durably change its parent shell's PATH).

    The machine-scoped checks above never take a project argument (doctor
    doesn't either -- see its _check_faster_whisper, which deliberately
    avoids loading a real model). PROJECT is optional and only controls one
    extra, project-scoped step at the end: pre-downloading that project's
    configured Whisper model, so 'videodoc transcribe' never has to do a
    silent, multi-GB first-time download in the middle of its own per-video
    progress bars (faster-whisper suppresses that download's own progress
    output -- see transcription_service.py)."""
    before = DoctorService().run()
    setup_service = SetupService()

    pip_fixed_ids: list[str] = []
    unresolved_error_ids: set[str] = set()

    for check in before.checks:
        line = f"{check.name}: {check.message}"
        print_check_result(check.status, line)
        if check.status == "ok":
            continue
        if check.status == "error":
            unresolved_error_ids.add(check.id)

        if check.fix_kind is None:
            continue

        if check.fix_kind == "manual":
            if check.fix_description:
                console.print(f"  Manual fix required: {check.fix_description}")
            continue

        action_text = " ".join(check.fix_command) if check.fix_command else ""
        console.print(f"  Applying fix for '{check.name}': {action_text}")

        if check.fix_kind == "system":
            console.print("  This runs a system package manager and may prompt for confirmation "
                           "or a password directly in this terminal.")
            if not typer.confirm("  Apply this fix now?"):
                console.print("  Skipped.")
                continue

        result = setup_service.apply(check)
        if result.status == "applied":
            console.print(f"  Applied: {result.detail}" if result.detail else "  Applied.")
            if check.fix_kind == "pip":
                # Not discarded from unresolved_error_ids yet: only the
                # re-verification pass below (which actually re-runs this
                # check in-process) may resolve it -- a successful `pip
                # install` doesn't by itself prove the underlying problem
                # is now fixed.
                pip_fixed_ids.append(check.id)
            else:
                # A "system" fix has no reliable in-process way to verify
                # (see the PATH caveat below) -- decision: a successful
                # subprocess exit counts as resolved (v1, see plan).
                unresolved_error_ids.discard(check.id)
        else:
            print_warning(f"  Fix failed: {result.detail}")

        if check.fix_description:
            console.print(f"  {check.fix_description}")

    # Only pip-kind fixes are re-verified in this same process: a fresh
    # import/ctypes.CDLL call sees a newly pip-installed package immediately,
    # but a newly installed system binary is not picked up by this already-
    # running process's PATH -- re-checking that would misleadingly report
    # "still broken" even after a genuinely successful install (see RUN.md §8
    # for the identical PATH caveat already documented for the manual fix).
    if pip_fixed_ids:
        console.print("Re-checking automatically-fixed items...")
        after = DoctorService().run()
        after_by_id = {c.id: c for c in after.checks}
        for check_id in pip_fixed_ids:
            updated = after_by_id.get(check_id)
            if updated is not None:
                print_check_result(updated.status, f"{updated.name}: {updated.message}")
                if updated.status != "error":
                    unresolved_error_ids.discard(check_id)

    if project is not None:
        try:
            service = ProjectService.load(project)
        except (ProjectNotFoundError, InvalidConfigError) as exc:
            print_error(str(exc))
            raise typer.Exit(code=1)

        engine = service.config.transcription.engine
        model_name = service.config.transcription.model
        if engine != "faster-whisper":
            print_warning(f"transcription engine '{engine}' has no model prefetch support yet -- skipped.")
        else:
            console.print(
                f"Pre-downloading transcription model '{model_name}' for '{service.config.project.slug}' "
                f"-- first use may download several GB from Hugging Face and show no progress while doing so."
            )
            try:
                load_whisper_model(model_name)
            except TranscriptionError as exc:
                print_error(f"could not load/download model '{model_name}': {exc}")
                raise typer.Exit(code=1)
            console.print(f"Model '{model_name}' is ready (downloaded and cached, or already present).")

    if unresolved_error_ids:
        raise typer.Exit(code=1)
