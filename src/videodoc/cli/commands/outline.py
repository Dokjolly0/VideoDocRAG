import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.core.errors import (
    DatabaseError,
    InvalidConfigError,
    NoVideosFoundError,
    OutlineSourceUnavailableError,
    ProjectNotFoundError,
)
from videodoc.core.services.outline_service import OutlineService
from videodoc.core.services.project_service import ProjectService


def outline_command(
    project: str = typer.Argument(..., help="Project name or path"),
    force: bool = typer.Option(False, "--force", help="Regenerate docs/outline.md even if it already exists."),
) -> None:
    try:
        service = ProjectService.load(project)
        result = OutlineService(service.project_dir, service.config).run(force=force)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        OutlineSourceUnavailableError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Generated", "yes" if result.generated else "no"),
        ("Skipped", "yes" if result.skipped else "no"),
        ("Sections", str(result.sections)),
        ("Outline", str(result.outline_path)),
    ])

    for warning in result.warnings:
        print_warning(warning)
