import typer

from videodoc.cli.output import console, render_projects_table
from videodoc.core.services.registry_service import ProjectRegistry


def list_command() -> None:
    entries = ProjectRegistry().list_all()
    if not entries:
        console.print("No registered projects. Use 'videodoc init <name>' or 'videodoc link <path>'.")
        raise typer.Exit(code=0)
    render_projects_table(entries)
