from pathlib import Path
from typing import Optional

import typer

from videodoc.cli.output import console, print_error
from videodoc.core.errors import InvalidConfigError, RegistryConflictError
from videodoc.core.services.project_service import ProjectService


def link_command(
    path: Path = typer.Argument(..., help="Path to an existing project folder (must contain config.yaml)"),
    name: Optional[str] = typer.Option(
        None, "--name", help="Registry name (defaults to the project's slug in config.yaml)"
    ),
) -> None:
    try:
        result = ProjectService.link(path, name=name)
    except (InvalidConfigError, RegistryConflictError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)
    console.print(f"Linked '{result.name}' -> {result.project_dir}")
