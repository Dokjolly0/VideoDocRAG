import typer

from videodoc.cli.output import console, print_check_error, print_warning
from videodoc.core.services.doctor_service import DoctorService


def doctor_command() -> None:
    """Machine-scoped: no project argument, no ProjectService.load()."""
    result = DoctorService().run()

    ok = warning = error = 0
    for check in result.checks:
        line = f"{check.name}: {check.message}"
        if check.status == "ok":
            console.print(line)
            ok += 1
        elif check.status == "warning":
            print_warning(line)
            warning += 1
        else:
            print_check_error(line)
            error += 1
        if check.status != "ok" and check.fix_description:
            console.print(f"  Fix: {check.fix_description}")

    console.print(f"{ok} OK, {warning} warning(s), {error} error(s).")
    if result.has_errors:
        raise typer.Exit(code=1)
