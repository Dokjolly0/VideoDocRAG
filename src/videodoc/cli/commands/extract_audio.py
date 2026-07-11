import typer

from videodoc.cli.output import console, print_error, print_warning, render_summary_table
from videodoc.cli.progress import RichProgressReporter
from videodoc.core.errors import (
    DatabaseError,
    ExternalToolNotFoundError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
)
from videodoc.core.services.audio_extraction_service import AudioExtractionService
from videodoc.core.services.project_service import ProjectService


def extract_audio_command(
    project: str = typer.Argument(..., help="Project name or path"),
    workers: int | None = typer.Option(None, "--workers", min=1, help="Number of audio extractions to run concurrently."),
) -> None:
    try:
        service = ProjectService.load(project)
        with RichProgressReporter(console) as reporter:
            result = AudioExtractionService(service.project_dir, service.config, workers_override=workers).run(progress=reporter)
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        ExternalToolNotFoundError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    render_summary_table([
        ("Extracted", str(len(result.extracted))),
        ("Skipped", str(len(result.skipped))),
    ])

    for error in result.errors:
        print_warning(error)
