import typer

from videodoc.cli.output import console, print_error, render_summary_table
from videodoc.core.errors import (
    DatabaseError,
    DocumentationExportFormatError,
    DocumentationExportUnavailableError,
    InvalidConfigError,
    ProjectNotFoundError,
)
from videodoc.core.services.export_service import DocumentationExportService, SUPPORTED_EXPORT_FORMATS
from videodoc.core.services.project_service import ProjectService


def export_command(
    project: str = typer.Argument(..., help="Project name or path"),
    export_format: str = typer.Option(
        "markdown",
        "--format",
        help=f"Export format: {', '.join(SUPPORTED_EXPORT_FORMATS)}.",
    ),
) -> None:
    try:
        service = ProjectService.load(project)
        result = DocumentationExportService(service.project_dir, service.config).run(export_format)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        DocumentationExportUnavailableError,
        DocumentationExportFormatError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Format", result.format),
        ("Files", str(len(result.files))),
        ("Output", str(result.output_path)),
    ])
