import typer

from videodoc.cli.output import print_error
from videodoc.core.services.registry_service import ProjectRegistry


def path_command(name: str = typer.Argument(...)) -> None:
    resolved = ProjectRegistry().resolve(name)
    if resolved is None:
        print_error(f"Project '{name}' is not registered. Run 'videodoc list' to see registered projects.")
        raise typer.Exit(code=1)
    # Plain stdout (no rich formatting/wrapping) so the output stays script-friendly,
    # e.g. `cd (videodoc path myproj)`, and long paths are never line-wrapped.
    typer.echo(str(resolved))
