from pathlib import Path
from typing import Optional

import typer

from videodoc.cli.output import console, print_error
from videodoc.core.errors import InvalidConfigError, InvalidProjectNameError, RegistryConflictError
from videodoc.core.services.project_service import ProjectService


def link_command(
    path: Path = typer.Argument(..., help="Path to an existing project folder (must contain config.yaml)"),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=(
            "Explicit local alias for this project (normalized to a slug). "
            "Defaults to the project's own canonical slug in config.yaml; "
            "override only to resolve a local naming collision or to use a "
            "shorter local nickname -- it does not change config.yaml."
        ),
    ),
) -> None:
    try:
        result = ProjectService.link(path, name=name)
    except (InvalidConfigError, RegistryConflictError, InvalidProjectNameError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    if result.name != result.canonical_slug:
        console.print(
            f"Linked as alias '{result.name}' -> {result.project_dir} "
            f"(the project's own slug is '{result.canonical_slug}')"
        )
    else:
        console.print(f"Linked '{result.name}' -> {result.project_dir}")
