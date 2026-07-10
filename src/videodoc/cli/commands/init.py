from pathlib import Path
from typing import Optional

import typer

from videodoc.cli.output import console, print_error, print_warning
from videodoc.core.errors import InvalidConfigError, InvalidProjectNameError, RegistryConflictError
from videodoc.core.services.project_service import ProjectService


def init_command(
    name: str = typer.Argument(..., help="Project name"),
    path: Optional[Path] = typer.Option(None, "--path", help="Explicit filesystem path for the project"),
    videos: Optional[str] = typer.Option(
        None, "--videos", help="External path for paths.videos (first creation only)"
    ),
    attachments: Optional[str] = typer.Option(
        None, "--attachments", help="External path for paths.attachments (first creation only)"
    ),
    codebase: Optional[str] = typer.Option(
        None, "--codebase", help="External path for paths.codebase (first creation only)"
    ),
) -> None:
    try:
        result = ProjectService.init(name, path=path, videos=videos, attachments=attachments, codebase=codebase)
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
        if result.ignored_source_overrides:
            flags = ", ".join(f"--{k}" for k in result.ignored_source_overrides)
            print_warning(f"{flags} ignored: config.yaml already exists and 'init' never overwrites it.")
    console.print(f"Registered as '{result.name}' in the local project registry.")
