import typer

from videodoc.cli.output import console, print_error
from videodoc.core.errors import ProjectNotFoundError
from videodoc.core.services.registry_service import ProjectRegistry


def unlink_command(name: str = typer.Argument(...)) -> None:
    try:
        entry = ProjectRegistry().unlink(name)
    except ProjectNotFoundError as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)
    console.print(f"Unlinked '{name}' from the registry (files at {entry.path} were not deleted).")
