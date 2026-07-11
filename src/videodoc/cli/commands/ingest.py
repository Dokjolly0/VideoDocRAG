import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import (
    DatabaseError,
    ExternalToolNotFoundError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
    VideoIdCollisionError,
)
from videodoc.core.services.ingest_service import VideoIngestionService
from videodoc.core.services.project_service import ProjectService


def ingest_command(
    project: str = typer.Argument(..., help="Project name or path"),
    workers: int | None = typer.Option(None, "--workers", min=1, help="Number of videos to process concurrently."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = VideoIngestionService(service.project_dir, service.config, workers_override=workers).run(progress=reporter)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        ExternalToolNotFoundError,
        VideoIdCollisionError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Ingested", str(len(result.ingested))),
        ("Reingested", str(len(result.reingested))),
        ("Skipped", str(len(result.skipped))),
    ])
    console.print(f"Database updated: {result.database_path.name}")

    for warning in result.warnings:
        print_warning(warning)
    for error in result.errors:
        print_warning(error)
