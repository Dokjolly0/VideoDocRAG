from rich.text import Text
import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.core.errors import (
    DatabaseError,
    DocumentationOutlineUnavailableError,
    InvalidConfigError,
    InvalidVectorIndexError,
    NoVideosFoundError,
    ProjectNotFoundError,
    VectorIndexUnavailableError,
)
from videodoc.core.services.documentation_service import DocumentationService
from videodoc.core.services.project_service import ProjectService


def regenerate_command(
    project: str = typer.Argument(..., help="Project name or path"),
    section: str = typer.Option(..., "--section", help="Section title, slug, or outline number to regenerate."),
    top_k: int | None = typer.Option(None, "--top-k", min=1, help="Maximum number of source chunks for the section."),
) -> None:
    try:
        service = ProjectService.load(project)
        result = DocumentationService(service.project_dir, service.config).run(force=True, top_k=top_k, section=section)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        DocumentationOutlineUnavailableError,
        VectorIndexUnavailableError,
        InvalidVectorIndexError,
        NoVideosFoundError,
        DatabaseError,
        ValueError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Regenerated", str(len(result.generated))),
        ("Skipped", str(len(result.skipped))),
    ])
    for generated in result.generated:
        console.print(Text(f"Regenerated: {generated.output_path}"))
    for warning in result.warnings:
        print_warning(warning)
