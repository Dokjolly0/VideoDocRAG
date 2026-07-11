import typer

from videodoc.cli.output import console, print_check_result, print_warning
from videodoc.core.services.doctor_service import DoctorService
from videodoc.core.services.setup_service import SetupService


def setup_command() -> None:
    """Machine-scoped: no project argument. Runs doctor's checks, then
    offers to fix whatever isn't 'ok' -- pip-kind fixes run automatically
    (venv-scoped, reversible), system-kind fixes ask for confirmation first
    (they touch the machine outside this project), manual-kind fixes are
    only ever printed, never attempted (see doctor_service.py's CheckResult
    docstring for why -- e.g. a child process can't durably change its
    parent shell's PATH)."""
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

    if unresolved_error_ids:
        raise typer.Exit(code=1)
