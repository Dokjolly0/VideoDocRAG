import typer

from videodoc.cli.output import console, print_error, render_summary_table
from videodoc.core.errors import (
    DatabaseError,
    DocumentationReviewUnavailableError,
    InvalidConfigError,
    InvalidDocumentationSectionManifestError,
    InvalidVectorIndexError,
    ProjectNotFoundError,
)
from videodoc.core.services.project_service import ProjectService
from videodoc.core.services.review_service import DocumentationReviewService


def review_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        result = DocumentationReviewService(service.project_dir, service.config).run()
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        DocumentationReviewUnavailableError,
        InvalidDocumentationSectionManifestError,
        InvalidVectorIndexError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Sections", str(result.sections)),
        ("Issues", str(result.issues)),
        ("Errors", str(result.errors)),
        ("Warnings", str(result.warnings)),
        ("Report", str(result.report_path)),
    ])
