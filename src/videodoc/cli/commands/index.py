import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import (
    DatabaseError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
    VectorIndexNotSupportedError,
)
from videodoc.core.services.index_service import IndexService
from videodoc.core.services.project_service import ProjectService


def index_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = IndexService(service.project_dir, service.config).run(progress=reporter)
    except (ProjectNotFoundError, InvalidConfigError, NoVideosFoundError, VectorIndexNotSupportedError, DatabaseError) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Indexed", "yes" if result.indexed else "no"),
        ("Skipped", "yes" if result.skipped else "no"),
        ("Videos", str(result.videos)),
        ("Records", str(result.records)),
    ])

    for error in result.errors:
        print_warning(error)
