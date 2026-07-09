from pathlib import Path
from typing import Optional

import typer

from videodoc.cli.output import console, print_error
from videodoc.core.errors import InvalidConfigError, InvalidProjectNameError, RegistryConflictError
from videodoc.core.services.project_service import ProjectService


def init_command(
    name: str = typer.Argument(..., help="Project name"),
    path: Optional[Path] = typer.Option(None, "--path", help="Explicit filesystem path for the project"),
) -> None:
    try:
        result = ProjectService.init(name, path=path)
    except (RegistryConflictError, InvalidConfigError, InvalidProjectNameError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    if result.created:
        console.print(f"Project '{result.name}' initialized at {result.project_dir}")
    else:
        console.print(
            f"Project '{result.name}' already initialized at {result.project_dir} "
            f"(config.yaml kept unchanged)"
        )
    console.print(f"Registered as '{result.name}' in the local project registry.")
