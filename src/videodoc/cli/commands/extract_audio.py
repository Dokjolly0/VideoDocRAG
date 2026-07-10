import typer

from videodoc.cli.output import console, print_error, print_warning
from videodoc.core.errors import (
    DatabaseError,
    ExternalToolNotFoundError,
    InvalidConfigError,
    NoVideosFoundError,
    ProjectNotFoundError,
)
from videodoc.core.services.audio_extraction_service import AudioExtractionService
from videodoc.core.services.project_service import ProjectService


def extract_audio_command(project: str = typer.Argument(..., help="Project name or path")) -> None:
    try:
        service = ProjectService.load(project)
        result = AudioExtractionService(service.project_dir, service.config).run()
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
    console.print(f"Audio extracted: {len(result.extracted)}, skipped (already extracted): {len(result.skipped)}")

    for error in result.errors:
        print_warning(error)
