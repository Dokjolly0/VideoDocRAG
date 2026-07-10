import typer

from videodoc.cli.output import console, print_error, print_warning
from videodoc.core.errors import (
    DatabaseError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
    TranscriptionEngineError,
)
from videodoc.core.services.project_service import ProjectService
from videodoc.core.services.transcription_service import TranscriptionService


def transcribe_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        result = TranscriptionService(service.project_dir, service.config).run()
    except (
        ProjectNotFoundError,
        InvalidConfigError,
        NoVideosFoundError,
        TranscriptionEngineError,
        DatabaseError,
    ) as exc:
        print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(f"Project: {service.config.project.slug}")
    console.print(f"Transcribed: {len(result.transcribed)}, skipped (already transcribed): {len(result.skipped)}")

    for error in result.errors:
        print_warning(error)
